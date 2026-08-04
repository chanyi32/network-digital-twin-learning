"""Batch runner layered on the versioned frozen-core pipeline."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from experiments.config import ExperimentCase, ExperimentConfig
from experiments.records import ExperimentCaseRecord
from ran_intent_simulation import __version__
from ran_intent_simulation.pipeline import PipelinePaths, SimulationPipeline


_SAFE_BATCH_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_RUN_ID = "run"


@dataclass(frozen=True, slots=True)
class ExperimentBatchResult:
    """Compact result returned after a complete batch."""

    experiment_name: str
    batch_id: str
    batch_directory: Path
    case_count: int
    successful_case_count: int


@dataclass(frozen=True, slots=True)
class _PreparedCase:
    case_directory: Path
    paths: PipelinePaths
    configuration_hash: str
    input_hash: str
    input_file_hashes: dict[str, str]
    base_model_version: str
    coefficient_version: str | None
    simulation_config_sha256: str
    ran_state_sha256: str
    feedback_enabled: bool
    preparation_error: Exception | None


class ExperimentRunner:
    """Prepare case inputs, run the core pipeline, and archive summaries."""

    def __init__(
        self,
        config: ExperimentConfig,
        *,
        repository_root: str | Path | None = None,
        batch_id: str | None = None,
        output_root: str | Path | None = None,
    ) -> None:
        self.config = config
        self.repository_root = (
            Path(repository_root).resolve()
            if repository_root is not None
            else Path(__file__).resolve().parents[1]
        )
        self.batch_id = batch_id or datetime.now(timezone.utc).strftime(
            "%Y%m%dT%H%M%S-%fZ"
        )
        if not _SAFE_BATCH_ID.fullmatch(self.batch_id):
            raise ValueError("batch_id contains unsupported characters")
        configured_root = output_root or config.output_root
        root = Path(configured_root)
        if not root.is_absolute():
            root = self.repository_root / root
        self.batch_directory = (
            root / config.experiment_name / self.batch_id
        )
        self.experiment_id = _stable_experiment_id(config)

    def run(
        self,
        *,
        source_config_path: str | Path | None = None,
    ) -> ExperimentBatchResult:
        """Execute every configured case and persist a batch manifest."""

        if self.batch_directory.exists() and any(
            self.batch_directory.iterdir()
        ):
            raise FileExistsError(
                f"experiment batch directory is not empty: "
                f"{self.batch_directory}"
            )
        self.batch_directory.mkdir(parents=True, exist_ok=True)
        started_at = datetime.now(timezone.utc)
        self._write_yaml(
            self.batch_directory / "experiment_config.yaml",
            self.config.model_dump(mode="json"),
        )

        records = [self._run_case(case) for case in self.config.cases]
        completed_at = datetime.now(timezone.utc)
        source_path = (
            Path(source_config_path).resolve()
            if source_config_path is not None
            else None
        )
        manifest = {
            "schemaVersion": "1.1",
            "experimentId": self.experiment_id,
            "experimentName": self.config.experiment_name,
            "batchId": self.batch_id,
            "description": self.config.description,
            "startedAt": started_at.isoformat(),
            "completedAt": completed_at.isoformat(),
            "durationSeconds": (
                completed_at - started_at
            ).total_seconds(),
            "fixedRandomSeed": self.config.fixed_random_seed,
            "sourceExperimentConfig": (
                self._relative_path(source_path)
                if source_path is not None
                else None
            ),
            "sourceExperimentConfigSha256": (
                _sha256(source_path) if source_path is not None else None
            ),
            "caseCount": len(records),
            "successfulCaseCount": sum(
                record.executionStatus == "succeeded"
                for record in records
            ),
            "failedCaseCount": sum(
                record.executionStatus == "failed"
                for record in records
            ),
            "skippedCaseCount": sum(
                record.executionStatus == "skipped"
                for record in records
            ),
            "cases": [
                record.model_dump(mode="json")
                for record in records
            ],
        }
        self._write_json(
            self.batch_directory / "batch_manifest.json",
            manifest,
        )
        return ExperimentBatchResult(
            experiment_name=self.config.experiment_name,
            batch_id=self.batch_id,
            batch_directory=self.batch_directory,
            case_count=len(records),
            successful_case_count=manifest["successfulCaseCount"],
        )

    def _run_case(self, case: ExperimentCase) -> ExperimentCaseRecord:
        start_time = datetime.now(timezone.utc)
        try:
            prepared = self._prepare_case(case)
        except Exception as exc:
            prepared = self._fallback_prepared_case(case, exc)
        pipeline_status: str | None = None
        final_artifact: Path | None = None
        error: Exception | None = prepared.preparation_error
        execution_status = "skipped" if case.skip else "failed"

        if case.skip:
            error = None
        elif error is None:
            try:
                pipeline = SimulationPipeline(
                    paths=prepared.paths,
                    results_root=prepared.case_directory / "pipeline",
                    run_id=_RUN_ID,
                    intent_id=case.intent_id,
                    scenario_id=case.scenario_id,
                )
                pipeline_result = pipeline.run()
                pipeline_status = pipeline_result.status
                final_artifact = pipeline_result.finalArtifact
                execution_status = "succeeded"
            except Exception as exc:
                error = exc

        end_time = datetime.now(timezone.utc)
        run_directory = (
            prepared.case_directory / "pipeline" / _RUN_ID
        )
        run_manifest = run_directory / "run_manifest.json"
        coefficient_version = prepared.coefficient_version
        feedback_iterations = 0
        generation_rounds = 0
        termination_reason: str | None = (
            "skipped" if execution_status == "skipped" else None
        )
        if run_manifest.is_file():
            core_manifest = _read_json(run_manifest)
            versions = core_manifest.get("versions", {})
            coefficient_version = versions.get(
                "performanceCoefficientVersion",
                coefficient_version,
            )
            feedback_iterations = int(
                core_manifest.get("feedbackIterations", 0)
            )
            generation_rounds = int(
                core_manifest.get(
                    "generationRounds",
                    core_manifest.get("roundsCompleted", 0),
                )
            )
            termination_reason = core_manifest.get("terminationReason")

        record = self._build_record(
            case=case,
            prepared=prepared,
            start_time=start_time,
            end_time=end_time,
            execution_status=execution_status,
            pipeline_status=pipeline_status,
            run_manifest=run_manifest if run_manifest.is_file() else None,
            final_artifact=final_artifact,
            coefficient_version=coefficient_version,
            feedback_iterations=feedback_iterations,
            generation_rounds=generation_rounds,
            termination_reason=termination_reason,
            error=error,
        )
        if record.executionStatus == "succeeded":
            self._write_case_summaries(
                prepared.case_directory,
                run_directory,
                record,
            )
        else:
            self._write_non_success_summaries(
                prepared.case_directory,
                record,
            )
        self._write_json(
            prepared.case_directory / "case_manifest.json",
            record.model_dump(mode="json"),
        )
        return record

    def _fallback_prepared_case(
        self,
        case: ExperimentCase,
        error: Exception,
    ) -> _PreparedCase:
        """Create auditable metadata even when input preparation itself fails."""

        case_directory = self.batch_directory / "cases" / case.case_id
        inputs_directory = case_directory / "inputs"
        inputs_directory.mkdir(parents=True, exist_ok=True)
        attempted_path = inputs_directory / "attempted_case.json"
        attempted_payload = {
            "experiment": self.config.model_dump(mode="json"),
            "case": case.model_dump(mode="json"),
        }
        self._write_json(attempted_path, attempted_payload)
        attempted_hash = _sha256(attempted_path)
        relative_path = self._relative_path(attempted_path)
        input_file_hashes = {relative_path: attempted_hash}
        return _PreparedCase(
            case_directory=case_directory,
            paths=PipelinePaths(),
            configuration_hash=_canonical_json_hash(attempted_payload),
            input_hash=_aggregate_input_hash(input_file_hashes),
            input_file_hashes=input_file_hashes,
            base_model_version="unavailable",
            coefficient_version=None,
            simulation_config_sha256=attempted_hash,
            ran_state_sha256=attempted_hash,
            feedback_enabled=bool(
                case.simulation_overrides.get(
                    "optimization.feedback_enabled",
                    True,
                )
            ),
            preparation_error=error,
        )

    def _prepare_case(self, case: ExperimentCase) -> _PreparedCase:
        case_directory = self.batch_directory / "cases" / case.case_id
        inputs_directory = case_directory / "inputs"
        inputs_directory.mkdir(parents=True, exist_ok=True)

        simulation_payload = self._load_yaml_input(
            self.config.inputs.simulation_config
        )
        configured_model_path = Path(
            simulation_payload["performance_model"]["config_file"]
        )
        if not configured_model_path.is_absolute():
            configured_model_path = (
                self.repository_root / configured_model_path
            ).resolve()
        _set_dotted_value(
            simulation_payload,
            "performance_model.config_file",
            str(configured_model_path),
        )
        _set_dotted_value(
            simulation_payload,
            "reproducibility.random_seed",
            self.config.fixed_random_seed,
        )

        preparation_error: Exception | None = None
        for dotted_path, value in sorted(
            case.simulation_overrides.items()
        ):
            try:
                _set_dotted_value(
                    simulation_payload,
                    dotted_path,
                    value,
                )
            except Exception as exc:
                preparation_error = preparation_error or exc

        simulation_path = inputs_directory / "simulation_config.yaml"
        self._write_yaml(simulation_path, simulation_payload)

        ran_source = self._resolve_input(
            self.config.inputs.ran_state_samples
        )
        ran_frame = pd.read_csv(ran_source)
        for column, value in sorted(case.ran_state_overrides.items()):
            if column not in ran_frame.columns:
                preparation_error = preparation_error or ValueError(
                    f"unknown RAN state override column: {column}"
                )
                continue
            ran_frame.loc[:, column] = value
        ran_state_path = inputs_directory / "ran_state_samples.csv"
        ran_frame.to_csv(ran_state_path, index=False)

        action_library_path = self._copy_input(
            self.config.inputs.action_library,
            inputs_directory / "action_library.json",
        )
        sla_templates_path = self._copy_input(
            self.config.inputs.sla_templates,
            inputs_directory / "sla_templates.json",
        )
        intent_samples_path = self._copy_input(
            self.config.inputs.intent_samples,
            inputs_directory / "intent_samples.json",
        )
        event_database_path = self._copy_input(
            self.config.inputs.event_database,
            inputs_directory / "event_database.json",
        )
        venue_mapping_path = self._copy_input(
            self.config.inputs.venue_cell_mapping,
            inputs_directory / "venue_cell_mapping.json",
        )
        archived_model_path = inputs_directory / "performance_model_v1.yaml"
        shutil.copy2(configured_model_path, archived_model_path)

        paths = PipelinePaths(
            simulation_config=simulation_path,
            action_library=action_library_path,
            sla_templates=sla_templates_path,
            intent_samples=intent_samples_path,
            event_database=event_database_path,
            venue_cell_mapping=venue_mapping_path,
            ran_state_samples=ran_state_path,
        )
        archived_inputs = [
            simulation_path,
            archived_model_path,
            action_library_path,
            sla_templates_path,
            intent_samples_path,
            event_database_path,
            venue_mapping_path,
            ran_state_path,
        ]
        input_file_hashes = {
            self._relative_path(path): _sha256(path)
            for path in archived_inputs
        }
        model_payload = self._load_yaml_path(configured_model_path)
        return _PreparedCase(
            case_directory=case_directory,
            paths=paths,
            configuration_hash=_canonical_configuration_hash(
                simulation_payload,
                self.batch_directory,
                self.repository_root,
            ),
            input_hash=_aggregate_input_hash(input_file_hashes),
            input_file_hashes=dict(sorted(input_file_hashes.items())),
            base_model_version=str(
                simulation_payload["performance_model"]["version"]
            ),
            coefficient_version=str(
                model_payload["performance_model"]["coefficient_version"]
            ),
            simulation_config_sha256=_sha256(simulation_path),
            ran_state_sha256=_sha256(ran_state_path),
            feedback_enabled=bool(
                simulation_payload["optimization"].get(
                    "feedback_enabled",
                    True,
                )
            ),
            preparation_error=preparation_error,
        )

    def _build_record(
        self,
        *,
        case: ExperimentCase,
        prepared: _PreparedCase,
        start_time: datetime,
        end_time: datetime,
        execution_status: str,
        pipeline_status: str | None,
        run_manifest: Path | None,
        final_artifact: Path | None,
        coefficient_version: str | None,
        feedback_iterations: int,
        generation_rounds: int,
        termination_reason: str | None,
        error: Exception | None,
    ) -> ExperimentCaseRecord:
        run_directory = (
            prepared.case_directory / "pipeline" / _RUN_ID
        )
        legacy_status = {
            "succeeded": "completed",
            "failed": "failed",
            "skipped": "skipped",
        }[execution_status]
        error_type: str | None = None
        error_message: str | None = None
        if execution_status == "failed":
            if error is None:
                error = RuntimeError("case failed without an exception")
            error_type = type(error).__name__
            error_message = str(error)
        return ExperimentCaseRecord(
            schemaVersion="1.1",
            experimentId=self.experiment_id,
            caseId=case.case_id,
            runId=_RUN_ID,
            experimentType=self.config.experiment_name,
            codeVersion=__version__,
            baseModelVersion=prepared.base_model_version,
            configurationHash=prepared.configuration_hash,
            inputHash=prepared.input_hash,
            inputFileHashes=prepared.input_file_hashes,
            randomSeed=self.config.fixed_random_seed,
            startTime=start_time,
            endTime=end_time,
            durationSeconds=(end_time - start_time).total_seconds(),
            executionStatus=execution_status,
            feedbackEnabled=prepared.feedback_enabled,
            feedbackIterations=feedback_iterations,
            generationRounds=generation_rounds,
            terminationReason=termination_reason,
            runManifestPath=(
                self._relative_path(run_manifest)
                if run_manifest is not None
                else None
            ),
            resultDirectory=self._relative_path(run_directory),
            errorType=error_type,
            errorMessage=error_message,
            skipReason=case.skip_reason,
            description=case.description,
            status=legacy_status,
            pipelineStatus=pipeline_status,
            startedAt=start_time,
            completedAt=end_time,
            fixedRandomSeed=self.config.fixed_random_seed,
            scenarioId=case.scenario_id,
            intentId=case.intent_id,
            simulationOverrides=case.simulation_overrides,
            ranStateOverrides=case.ran_state_overrides,
            modelVersion=prepared.base_model_version,
            coefficientVersion=coefficient_version,
            simulationConfigSha256=prepared.simulation_config_sha256,
            ranStateInputSha256=prepared.ran_state_sha256,
            pipelineRunDirectory=self._relative_path(run_directory),
            finalArtifact=(
                self._relative_path(final_artifact)
                if final_artifact is not None
                else None
            ),
        )

    def _write_case_summaries(
        self,
        case_directory: Path,
        run_directory: Path,
        record: ExperimentCaseRecord,
    ) -> None:
        round_directories = sorted(run_directory.glob("round_*"))
        strategy_rounds = [
            {
                "round": round_directory.name,
                "rankedPolicies": _read_json(
                    round_directory / "ranked_policies.json"
                ),
            }
            for round_directory in round_directories
        ]
        recommendation_path = run_directory / "final_recommendation.json"
        no_feasible_path = run_directory / "no_feasible_policy.json"
        final_result_path = (
            recommendation_path
            if recommendation_path.exists()
            else no_feasible_path
        )
        self._write_json(
            case_directory / "strategy_results.json",
            {
                "provenance": record.csv_provenance(),
                "rounds": strategy_rounds,
                "finalResult": _read_json(final_result_path),
            },
        )
        self._concatenate_csv(
            round_directories,
            "performance_results.csv",
            case_directory / "performance_metrics.csv",
            record,
        )
        self._concatenate_csv(
            round_directories,
            "policy_scores.csv",
            case_directory / "scoring_results.csv",
            record,
        )

    @staticmethod
    def _write_non_success_summaries(
        case_directory: Path,
        record: ExperimentCaseRecord,
    ) -> None:
        row = record.csv_provenance()
        row["roundDirectory"] = None
        row["policyId"] = None
        pd.DataFrame([row]).to_csv(
            case_directory / "performance_metrics.csv",
            index=False,
        )
        pd.DataFrame([row]).to_csv(
            case_directory / "scoring_results.csv",
            index=False,
        )

    @staticmethod
    def _concatenate_csv(
        round_directories: list[Path],
        source_name: str,
        output_path: Path,
        record: ExperimentCaseRecord,
    ) -> None:
        frames: list[pd.DataFrame] = []
        provenance = record.csv_provenance()
        for round_directory in round_directories:
            frame = pd.read_csv(round_directory / source_name)
            frame.insert(0, "roundDirectory", round_directory.name)
            for index, (column, value) in enumerate(
                provenance.items(),
                start=1,
            ):
                frame.insert(index, column, value)
            frames.append(frame)
        if not frames:
            raise ValueError(f"no round data found for {source_name}")
        pd.concat(frames, ignore_index=True).to_csv(
            output_path,
            index=False,
        )

    def _resolve_input(self, configured_path: str) -> Path:
        path = Path(configured_path)
        if not path.is_absolute():
            path = self.repository_root / path
        resolved = path.resolve()
        if not resolved.is_file():
            raise FileNotFoundError(f"experiment input not found: {resolved}")
        return resolved

    def _load_yaml_input(self, configured_path: str) -> dict[str, Any]:
        return self._load_yaml_path(self._resolve_input(configured_path))

    def _copy_input(
        self,
        configured_path: str,
        destination: Path,
    ) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self._resolve_input(configured_path), destination)
        return destination

    @staticmethod
    def _load_yaml_path(path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8") as stream:
            payload = yaml.safe_load(stream)
        if not isinstance(payload, dict):
            raise ValueError(f"YAML root must be an object: {path}")
        return payload

    def _relative_path(self, path: Path) -> str:
        return Path(
            os.path.relpath(path.resolve(), self.batch_directory.resolve())
        ).as_posix()

    @staticmethod
    def _write_json(path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _write_yaml(path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            yaml.safe_dump(
                payload,
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )


def _set_dotted_value(
    payload: dict[str, Any],
    dotted_path: str,
    value: Any,
) -> None:
    """Replace an existing leaf without permitting misspelled new fields."""

    parts = dotted_path.split(".")
    if not parts or any(not part for part in parts):
        raise ValueError(f"invalid override path: {dotted_path}")
    target: dict[str, Any] = payload
    for part in parts[:-1]:
        nested = target.get(part)
        if not isinstance(nested, dict):
            raise ValueError(
                f"override path does not resolve to an object: {dotted_path}"
            )
        target = nested
    leaf = parts[-1]
    if leaf not in target:
        raise ValueError(f"override path does not exist: {dotted_path}")
    target[leaf] = value


def _stable_experiment_id(config: ExperimentConfig) -> str:
    payload = config.model_dump(mode="json")
    payload.pop("output_root", None)
    digest = _canonical_json_hash(payload)
    return f"EXP-{digest[:16].upper()}"


def _canonical_configuration_hash(
    payload: dict[str, Any],
    batch_directory: Path,
    repository_root: Path,
) -> str:
    """Hash canonical JSON after normalizing absolute paths."""

    def normalize(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: normalize(value[key])
                for key in sorted(value)
            }
        if isinstance(value, list):
            return [normalize(item) for item in value]
        if isinstance(value, str):
            path = Path(value)
            if path.is_absolute():
                resolved = path.resolve()
                try:
                    repository_relative = resolved.relative_to(
                        repository_root.resolve()
                    )
                    return (
                        Path("repository")
                        .joinpath(repository_relative)
                        .as_posix()
                    )
                except ValueError:
                    try:
                        relative = os.path.relpath(
                            resolved,
                            batch_directory.resolve(),
                        )
                        return Path(relative).as_posix()
                    except ValueError:
                        return f"external/{resolved.name}"
        return value

    return _canonical_json_hash(normalize(payload))


def _aggregate_input_hash(input_file_hashes: dict[str, str]) -> str:
    digest = hashlib.sha256()
    for path, file_hash in sorted(input_file_hashes.items()):
        digest.update(path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_hash.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _canonical_json_hash(payload: Any) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
