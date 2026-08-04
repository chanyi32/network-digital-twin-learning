"""Run and validate the six-case minimal experiment pilot."""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import pandas as pd
import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from experiments.config import ExperimentConfig
from experiments.runner import ExperimentRunner


SUMMARY_COLUMNS = [
    "experimentId",
    "caseId",
    "runId",
    "experimentType",
    "executionStatus",
    "codeVersion",
    "baseModelVersion",
    "configurationHash",
    "inputHash",
    "randomSeed",
    "runManifestPath",
    "resultDirectory",
    "generationRounds",
    "feedbackIterations",
    "terminationReason",
    "generatedPolicyCount",
    "evaluatedPolicyCount",
    "feasiblePolicyCount",
    "feasibleRatio",
    "bestPolicyId",
    "bestTotalScore",
    "serviceScore",
    "energyScore",
    "resourceScore",
    "riskScore",
    "videoUserSatisfactionRatio",
    "videoThroughputP05Mbps",
    "videoDelayP95Ms",
    "videoUplinkBlerMean",
    "voiceQualityScore",
    "voiceQualityDegradation",
    "prbUtilization",
    "ranEnergy",
    "normalUserDegradation",
    "clippingCount",
    "durationSeconds",
]


class _StrictPilotModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Weights(_StrictPilotModel):
    service: float = Field(ge=0, le=1)
    energy: float = Field(ge=0, le=1)
    resource: float = Field(ge=0, le=1)
    risk: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_sum(self) -> "_Weights":
        if not math.isclose(
            self.service + self.energy + self.resource + self.risk,
            1.0,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise ValueError("pilot scoring weights must sum to 1")
        return self


class PilotConfig(_StrictPilotModel):
    schema_version: str
    pilot_id: str
    description: str
    output_root: str
    random_seed: int
    maximum_candidates_per_round: int = Field(gt=0)
    feedback_maximum_iterations: int = Field(gt=0)
    load_sweep: dict[str, dict[str, float]]
    feedback_compare: dict[str, bool]
    weight_sensitivity: dict[str, _Weights]


def load_pilot_config(path: str | Path) -> PilotConfig:
    with Path(path).open("r", encoding="utf-8") as stream:
        payload = yaml.safe_load(stream)
    return PilotConfig.model_validate(payload)


def run_pilot(
    config: PilotConfig,
    *,
    repository_root: str | Path,
    batch_id: str,
    source_config_path: str | Path | None = None,
) -> Path:
    """Execute six lightweight cases and write validated pilot summaries."""

    repository = Path(repository_root).resolve()
    output_root = Path(config.output_root)
    if not output_root.is_absolute():
        output_root = repository / output_root
    pilot_root = output_root / batch_id
    if pilot_root.exists() and any(pilot_root.iterdir()):
        raise FileExistsError(f"pilot directory is not empty: {pilot_root}")
    pilot_root.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(timezone.utc)

    experiment_configs = _experiment_configs(config, pilot_root)
    subbatches: dict[str, Path] = {}
    case_contexts: list[tuple[Path, Path]] = []
    for experiment_type, experiment_config in experiment_configs.items():
        result = ExperimentRunner(
            experiment_config,
            repository_root=repository,
            batch_id="pilot",
        ).run(source_config_path=source_config_path)
        subbatches[experiment_type] = result.batch_directory
        for case in experiment_config.cases:
            case_contexts.append(
                (
                    result.batch_directory,
                    result.batch_directory / "cases" / case.case_id,
                )
            )

    summaries = [
        _write_case_outputs(pilot_root, subbatch, case_directory)
        for subbatch, case_directory in case_contexts
    ]
    summary_path = pilot_root / "pilot_summary.csv"
    pd.DataFrame(summaries, columns=SUMMARY_COLUMNS).to_csv(
        summary_path,
        index=False,
    )

    validations = _validate_pilot(
        pilot_root,
        subbatches,
        summaries,
        config,
    )
    reproducibility = _repeat_and_compare_case(
        pilot_root,
        repository,
        experiment_configs["load_sweep"],
    )
    completed_at = datetime.now(timezone.utc)
    estimate = _estimate_formal_scale(
        summaries,
        (completed_at - started_at).total_seconds(),
    )
    manifest = {
        "schemaVersion": "1.0",
        "pilotId": config.pilot_id,
        "batchId": batch_id,
        "description": config.description,
        "startTime": started_at.isoformat(),
        "endTime": completed_at.isoformat(),
        "durationSeconds": (
            completed_at - started_at
        ).total_seconds(),
        "caseCount": len(summaries),
        "successfulCaseCount": sum(
            summary["executionStatus"] == "succeeded"
            for summary in summaries
        ),
        "randomSeed": config.random_seed,
        "subbatchManifests": {
            name: _relative(
                pilot_root,
                path / "batch_manifest.json",
            )
            for name, path in subbatches.items()
        },
        "pilotSummaryPath": "pilot_summary.csv",
        "pilotReportPath": "pilot_experiment_report.md",
        "validations": validations,
        "reproducibility": reproducibility,
        "formalExperimentEstimate": estimate,
    }
    _write_json(pilot_root / "batch_manifest.json", manifest)
    _write_report(
        pilot_root / "pilot_experiment_report.md",
        config,
        summaries,
        validations,
        reproducibility,
        estimate,
    )
    return pilot_root


def _experiment_configs(
    pilot: PilotConfig,
    pilot_root: Path,
) -> dict[str, ExperimentConfig]:
    common = {
        "schema_version": "1.1",
        "fixed_random_seed": pilot.random_seed,
        "output_root": str(pilot_root / "experiments"),
    }
    common_simulation = {
        "generation.maximum_candidates_per_round": (
            pilot.maximum_candidates_per_round
        ),
        "optimization.maximum_feedback_iterations": (
            pilot.feedback_maximum_iterations
        ),
    }
    load_cases = []
    for case_id, state_overrides in pilot.load_sweep.items():
        load_cases.append(
            {
                "case_id": case_id,
                "description": f"pilot load case: {case_id}",
                "scenario_id": "SCENARIO-HIGH-LOAD",
                "simulation_overrides": {
                    **common_simulation,
                    "optimization.feedback_enabled": False,
                },
                "ran_state_overrides": state_overrides,
            }
        )
    feedback_cases = [
        {
            "case_id": case_id,
            "description": f"pilot feedback case: {case_id}",
            "scenario_id": "SCENARIO-HIGH-LOAD",
            "simulation_overrides": {
                **common_simulation,
                "optimization.feedback_enabled": enabled,
            },
        }
        for case_id, enabled in pilot.feedback_compare.items()
    ]
    weight_cases = [
        {
            "case_id": case_id,
            "description": f"pilot weight case: {case_id}",
            "scenario_id": "SCENARIO-HIGH-LOAD",
            "simulation_overrides": {
                **common_simulation,
                "optimization.feedback_enabled": False,
                "scoring.weights.service": weights.service,
                "scoring.weights.energy": weights.energy,
                "scoring.weights.resource": weights.resource,
                "scoring.weights.risk": weights.risk,
            },
        }
        for case_id, weights in pilot.weight_sensitivity.items()
    ]
    return {
        "load_sweep": ExperimentConfig.model_validate(
            {
                **common,
                "experiment_name": "load_sweep",
                "description": "minimal load sweep pilot",
                "cases": load_cases,
            }
        ),
        "feedback_compare": ExperimentConfig.model_validate(
            {
                **common,
                "experiment_name": "feedback_compare",
                "description": "minimal feedback switch pilot",
                "cases": feedback_cases,
            }
        ),
        "weight_sensitivity": ExperimentConfig.model_validate(
            {
                **common,
                "experiment_name": "weight_sensitivity",
                "description": "minimal weight sensitivity pilot",
                "cases": weight_cases,
            }
        ),
    }


def _write_case_outputs(
    pilot_root: Path,
    subbatch: Path,
    case_directory: Path,
) -> dict[str, Any]:
    manifest = _read_json(case_directory / "case_manifest.json")
    run_manifest_path = (
        subbatch / manifest["runManifestPath"]
        if manifest["runManifestPath"]
        else None
    )
    if run_manifest_path is None or not run_manifest_path.is_file():
        raise ValueError(f"pilot case has no core manifest: {case_directory}")
    run_manifest = _read_json(run_manifest_path)
    run_directory = run_manifest_path.parent
    simulation_config = yaml.safe_load(
        (
            case_directory
            / "inputs"
            / "simulation_config.yaml"
        ).read_text(encoding="utf-8")
    )
    effective = {
        "schemaVersion": "1.0",
        "experimentId": manifest["experimentId"],
        "caseId": manifest["caseId"],
        "runId": manifest["runId"],
        "experimentType": manifest["experimentType"],
        "randomSeed": manifest["randomSeed"],
        "simulationConfig": simulation_config,
        "ranStateOverrides": manifest["ranStateOverrides"],
    }
    _write_json(
        case_directory / "effective_experiment_config.json",
        effective,
    )

    round_directories = sorted(run_directory.glob("round_*"))
    policies: list[dict[str, Any]] = []
    performances: list[dict[str, Any]] = []
    scores: list[dict[str, Any]] = []
    clipping: dict[str, int] = {}
    for round_directory in round_directories:
        policies.extend(
            _read_json(round_directory / "candidate_policies.json")
        )
        round_performance = _read_json(
            round_directory / "performance_results.json"
        )
        performances.extend(round_performance)
        scores.extend(
            _read_json(round_directory / "ranked_policies.json")
        )
        for result in round_performance:
            for metric, item in result["clippingSummary"].items():
                clipping[metric] = (
                    clipping.get(metric, 0) + item["clippedCount"]
                )

    feasible_scores = [score for score in scores if score["feasible"]]
    best_score = (
        sorted(
            feasible_scores,
            key=lambda score: (
                -round(score["totalScore"], 12),
                score["performance"]["prbUtilization"],
                score["performance"]["riskScore"],
                score["performance"]["ranEnergy"],
                score["policyId"],
            ),
        )[0]
        if feasible_scores
        else None
    )
    performance = best_score["performance"] if best_score else {}
    summary = {
        "experimentId": manifest["experimentId"],
        "caseId": manifest["caseId"],
        "runId": manifest["runId"],
        "experimentType": manifest["experimentType"],
        "executionStatus": manifest["executionStatus"],
        "codeVersion": manifest["codeVersion"],
        "baseModelVersion": manifest["baseModelVersion"],
        "configurationHash": manifest["configurationHash"],
        "inputHash": manifest["inputHash"],
        "randomSeed": manifest["randomSeed"],
        "runManifestPath": _relative(pilot_root, run_manifest_path),
        "resultDirectory": _relative(pilot_root, run_directory),
        "generationRounds": run_manifest["generationRounds"],
        "feedbackIterations": run_manifest["feedbackIterations"],
        "terminationReason": run_manifest["terminationReason"],
        "generatedPolicyCount": len(policies),
        "evaluatedPolicyCount": len(performances),
        "feasiblePolicyCount": len(feasible_scores),
        "feasibleRatio": (
            len(feasible_scores) / len(scores) if scores else 0.0
        ),
        "bestPolicyId": best_score["policyId"] if best_score else None,
        "bestTotalScore": (
            best_score["totalScore"] if best_score else 0.0
        ),
        "serviceScore": (
            best_score["serviceScore"] if best_score else None
        ),
        "energyScore": (
            best_score["energyScore"] if best_score else None
        ),
        "resourceScore": (
            best_score["resourceScore"] if best_score else None
        ),
        "riskScore": best_score["riskScore"] if best_score else None,
        "videoUserSatisfactionRatio": performance.get(
            "videoUserSatisfactionRatio"
        ),
        "videoThroughputP05Mbps": performance.get(
            "videoThroughputP05Mbps"
        ),
        "videoDelayP95Ms": performance.get("videoDelayP95Ms"),
        "videoUplinkBlerMean": performance.get("videoUplinkBlerMean"),
        "voiceQualityScore": performance.get("voiceQualityScore"),
        "voiceQualityDegradation": performance.get(
            "voiceQualityDegradation"
        ),
        "prbUtilization": performance.get("prbUtilization"),
        "ranEnergy": performance.get("ranEnergy"),
        "normalUserDegradation": performance.get(
            "normalUserPerformanceDegradation"
        ),
        "clippingCount": sum(clipping.values()),
        "durationSeconds": manifest["durationSeconds"],
    }
    case_summary = {
        **summary,
        "clippingByMetric": dict(sorted(clipping.items())),
    }
    _write_json(
        case_directory / "case_summary.json",
        case_summary,
    )
    return case_summary


def _validate_pilot(
    pilot_root: Path,
    subbatches: dict[str, Path],
    summaries: list[dict[str, Any]],
    config: PilotConfig,
) -> dict[str, Any]:
    completeness_errors: list[str] = []
    trace_errors: list[str] = []
    constraint_errors: list[str] = []
    chain_errors: list[str] = []
    non_finite_errors: list[str] = []
    for subbatch in subbatches.values():
        for case_directory in sorted((subbatch / "cases").iterdir()):
            manifest = _read_json(case_directory / "case_manifest.json")
            for name in (
                "case_manifest.json",
                "effective_experiment_config.json",
                "case_summary.json",
            ):
                if not (case_directory / name).is_file():
                    completeness_errors.append(
                        f"{manifest['caseId']}:{name}"
                    )
            run_manifest = pilot_root / next(
                summary["runManifestPath"]
                for summary in summaries
                if summary["caseId"] == manifest["caseId"]
                and summary["experimentType"]
                == manifest["experimentType"]
            )
            if not run_manifest.is_file():
                trace_errors.append(manifest["caseId"])
                continue
            run_directory = run_manifest.parent
            prior_policy_ids: set[str] = set()
            for round_directory in sorted(run_directory.glob("round_*")):
                required = {
                    "candidate_policies.json",
                    "performance_results.json",
                    "constraint_checks.csv",
                    "policy_scores.csv",
                    "ranked_policies.json",
                    "round_summary.json",
                }
                if manifest["feedbackEnabled"]:
                    required.add("feedback.json")
                missing = [
                    name
                    for name in required
                    if not (round_directory / name).is_file()
                ]
                completeness_errors.extend(
                    f"{manifest['caseId']}:{round_directory.name}:{name}"
                    for name in missing
                )
                policies = _read_json(
                    round_directory / "candidate_policies.json"
                )
                scores = _read_json(
                    round_directory / "ranked_policies.json"
                )
                for score in scores:
                    if not score["feasible"] and (
                        score["totalScore"] != 0
                        or score["rank"] is not None
                    ):
                        constraint_errors.append(score["policyId"])
                for policy in policies:
                    if policy["generationRound"] > 0:
                        if policy["parentPolicyId"] not in prior_policy_ids:
                            chain_errors.append(policy["policyId"])
                        if not policy["generationReason"].startswith(
                            "feedback:"
                        ):
                            chain_errors.append(policy["policyId"])
                prior_policy_ids.update(
                    policy["policyId"] for policy in policies
                )
                for json_path in round_directory.glob("*.json"):
                    if not _all_finite(_read_json(json_path)):
                        non_finite_errors.append(str(json_path))
                for csv_path in round_directory.glob("*.csv"):
                    numeric = pd.read_csv(csv_path).select_dtypes(
                        include="number"
                    )
                    if not numeric.empty and not (
                        numeric.apply(
                            lambda column: column.dropna().map(
                                math.isfinite
                            ).all()
                        ).all()
                    ):
                        non_finite_errors.append(str(csv_path))

    feedback_diff = _configuration_diff(
        _effective_config(subbatches["feedback_compare"], "feedback_enabled_false"),
        _effective_config(subbatches["feedback_compare"], "feedback_enabled_true"),
    )
    weight_diff = _configuration_diff(
        _effective_config(subbatches["weight_sensitivity"], "default_weights"),
        _effective_config(
            subbatches["weight_sensitivity"],
            "service_priority_weights",
        ),
    )
    load_config_diff = _configuration_diff(
        _effective_config(subbatches["load_sweep"], "low_load"),
        _effective_config(subbatches["load_sweep"], "high_load"),
    )
    low_frame = pd.read_csv(
        subbatches["load_sweep"]
        / "cases"
        / "low_load"
        / "inputs"
        / "ran_state_samples.csv"
    )
    high_frame = pd.read_csv(
        subbatches["load_sweep"]
        / "cases"
        / "high_load"
        / "inputs"
        / "ran_state_samples.csv"
    )
    different_columns = [
        column
        for column in low_frame.columns
        if not low_frame[column].equals(high_frame[column])
    ]
    allowed_load_columns = set(config.load_sweep["low_load"])

    summary_frame = pd.read_csv(pilot_root / "pilot_summary.csv")
    summary_consistent = len(summary_frame) == len(summaries)
    for summary in summaries:
        row = summary_frame[
            (summary_frame["experimentType"] == summary["experimentType"])
            & (summary_frame["caseId"] == summary["caseId"])
        ].iloc[0]
        for field in SUMMARY_COLUMNS:
            expected = summary[field]
            actual = row[field]
            if expected is None and pd.isna(actual):
                continue
            if isinstance(expected, float):
                if not math.isclose(
                    float(actual),
                    expected,
                    rel_tol=0.0,
                    abs_tol=1e-12,
                ):
                    summary_consistent = False
            elif str(actual) != str(expected):
                summary_consistent = False

    initial_candidates_equal = (
        _round_bytes(
            subbatches["feedback_compare"],
            "feedback_enabled_false",
            "candidate_policies.json",
        )
        == _round_bytes(
            subbatches["feedback_compare"],
            "feedback_enabled_true",
            "candidate_policies.json",
        )
    )
    weight_candidates_equal = (
        _round_bytes(
            subbatches["weight_sensitivity"],
            "default_weights",
            "candidate_policies.json",
        )
        == _round_bytes(
            subbatches["weight_sensitivity"],
            "service_priority_weights",
            "candidate_policies.json",
        )
    )
    weight_performance_equal = (
        _round_bytes(
            subbatches["weight_sensitivity"],
            "default_weights",
            "performance_results.json",
        )
        == _round_bytes(
            subbatches["weight_sensitivity"],
            "service_priority_weights",
            "performance_results.json",
        )
    )
    return {
        "caseFileCompleteness": not completeness_errors,
        "caseFileCompletenessErrors": completeness_errors,
        "summaryMatchesSourceJson": summary_consistent,
        "relativePathsResolve": not trace_errors,
        "relativePathErrors": trace_errors,
        "feedbackConfigDiff": feedback_diff,
        "feedbackOnlySwitchDiff": feedback_diff
        == ["optimization.feedback_enabled"],
        "feedbackInitialCandidatesEqual": initial_candidates_equal,
        "weightConfigDiff": weight_diff,
        "weightOnlyScoringWeightsDiffer": bool(weight_diff)
        and all(
            path.startswith("scoring.weights.")
            for path in weight_diff
        ),
        "weightCandidatesEqual": weight_candidates_equal,
        "weightPerformanceEqual": weight_performance_equal,
        "loadSimulationConfigDiff": load_config_diff,
        "loadOnlyInputDiffers": not load_config_diff
        and set(different_columns) <= allowed_load_columns,
        "loadDifferentColumns": different_columns,
        "infeasibleScoreRuleValid": not constraint_errors,
        "infeasibleScoreRuleErrors": constraint_errors,
        "feedbackParentChildChainValid": not chain_errors,
        "feedbackParentChildChainErrors": chain_errors,
        "allResultsFinite": not non_finite_errors,
        "nonFiniteErrors": non_finite_errors,
    }


def _repeat_and_compare_case(
    pilot_root: Path,
    repository: Path,
    load_config: ExperimentConfig,
) -> dict[str, Any]:
    high_case = next(
        case
        for case in load_config.cases
        if case.case_id == "high_load"
    )
    repeat_config = load_config.model_copy(
        update={"cases": [high_case]},
        deep=True,
    )
    repeated = ExperimentRunner(
        repeat_config,
        repository_root=repository,
        batch_id="repeat",
        output_root=pilot_root / "reproducibility",
    ).run()
    original_root = (
        pilot_root
        / "experiments"
        / "load_sweep"
        / "pilot"
        / "cases"
        / "high_load"
        / "pipeline"
        / "run"
    )
    repeated_root = (
        repeated.batch_directory
        / "cases"
        / "high_load"
        / "pipeline"
        / "run"
    )
    relative_files = [
        path.relative_to(original_root)
        for path in original_root.rglob("*")
        if path.is_file()
        and path.name != "run_manifest.json"
        and (
            path.parent.name.startswith("round_")
            or path.name
            in {"final_recommendation.json", "no_feasible_policy.json"}
        )
    ]
    mismatches = [
        relative.as_posix()
        for relative in relative_files
        if not (repeated_root / relative).is_file()
        or (original_root / relative).read_bytes()
        != (repeated_root / relative).read_bytes()
    ]
    return {
        "caseId": "high_load",
        "comparedArtifactCount": len(relative_files),
        "mismatchCount": len(mismatches),
        "mismatches": mismatches,
        "reproducible": not mismatches,
    }


def _estimate_formal_scale(
    summaries: list[dict[str, Any]],
    pilot_duration: float,
) -> dict[str, Any]:
    evaluated = sum(item["evaluatedPolicyCount"] for item in summaries)
    seconds_per_evaluation = pilot_duration / max(evaluated, 1)
    recommended_case_count = 31
    assumed_evaluations_per_case = 120
    estimated_seconds = (
        seconds_per_evaluation
        * recommended_case_count
        * assumed_evaluations_per_case
    )
    return {
        "recommendedCaseCount": recommended_case_count,
        "design": {
            "baseline": 1,
            "loadSweep": "3 loads ? 3 seeds = 9",
            "feedbackCompare": "2 modes ? 3 seeds = 6",
            "weightSensitivity": "5 weight sets ? 3 seeds = 15",
        },
        "assumedEvaluationsPerCase": assumed_evaluations_per_case,
        "pilotEvaluatedPolicyCount": evaluated,
        "pilotDurationSeconds": pilot_duration,
        "estimatedDurationSeconds": estimated_seconds,
        "estimatedDurationMinutes": estimated_seconds / 60,
        "note": (
            "Linear estimate from pilot policy evaluations; filesystem and "
            "feedback convergence can make actual runtime differ."
        ),
    }


def _write_report(
    path: Path,
    config: PilotConfig,
    summaries: list[dict[str, Any]],
    validations: dict[str, Any],
    reproducibility: dict[str, Any],
    estimate: dict[str, Any],
) -> None:
    by_case = {summary["caseId"]: summary for summary in summaries}
    low = by_case["low_load"]
    high = by_case["high_load"]
    feedback_off = by_case["feedback_enabled_false"]
    feedback_on = by_case["feedback_enabled_true"]
    default_weights = by_case["default_weights"]
    service_weights = by_case["service_priority_weights"]
    rows = "\n".join(
        "| {experimentType} | {caseId} | {executionStatus} | "
        "{generationRounds} | {feedbackIterations} | "
        "{evaluatedPolicyCount} | {feasiblePolicyCount} | "
        "{bestTotalScore:.6f} | {clippingCount} |".format(**summary)
        for summary in summaries
    )
    validation_rows = "\n".join(
        f"| `{key}` | `{value}` |"
        for key, value in validations.items()
        if not isinstance(value, list)
    )
    clipping_rows = "\n".join(
        "| {caseId} | {clippingCount} | `{metrics}` |".format(
            caseId=summary["caseId"],
            clippingCount=summary["clippingCount"],
            metrics=", ".join(
                f"{metric}={count}"
                for metric, count in summary["clippingByMetric"].items()
                if count
            ),
        )
        for summary in summaries
    )
    path.write_text(
        f"""# ??????????

## 1. ????

- Pilot?`{config.pilot_id}`
- ?????`{config.random_seed}`
- ??????????`{config.maximum_candidates_per_round}`
- ????????????`{config.feedback_maximum_iterations}`
- ?????`simplified-ran-v1`
- ??????????????????

## 2. ??case??

| ?? | Case | ?? | ??? | ???? | ???? | ???? | ??? | ???? |
|---|---|---|---:|---:|---:|---:|---:|---:|
{rows}

## 3. ????

| ?? | ?? |
|---|---|
{validation_rows}

???????`{reproducibility['comparedArtifactCount']}`?????????
?????`{reproducibility['mismatchCount']}`?

## 4. ????

| Case | ???? | ??? |
|---|---:|---|
{clipping_rows}

## 5. ????

???????????????????????

- ????????P05??????
  `{low['videoThroughputP05Mbps']:.4f}`?
  `{high['videoThroughputP05Mbps']:.4f}` Mbps?
  P95?????`{low['videoDelayP95Ms']:.4f}`?
  `{high['videoDelayP95Ms']:.4f}` ms?PRB??????
  `{low['prbUtilization']:.4f}`?`{high['prbUtilization']:.4f}`?
  ???????????????????
- ??????`{feedback_off['generationRounds']}`??
  `{feedback_off['feedbackIterations']}`????????
  `{feedback_on['generationRounds']}`??
  `{feedback_on['feedbackIterations']}`?????????????
  ????????`{feedback_on['bestTotalScore']:.6f}`??????
  ??????????????????????
- ??????????????????????????????????
  `{default_weights['bestTotalScore']:.6f}`?
  `{service_weights['bestTotalScore']:.6f}`???????
  `{default_weights['bestPolicyId']}`?
- ??case????????????????????
  `voiceQualityScore`????????NaN?Infinity?????????????

???????????????????????????????????

## 6. ????????

- ??case??`{estimate['recommendedCaseCount']}`
- ???case???????`{estimate['assumedEvaluationsPerCase']}`
- ????????`{estimate['estimatedDurationMinutes']:.2f}`??

?????pilot????????????????????????I/O???
""",
        encoding="utf-8",
    )


def _effective_config(subbatch: Path, case_id: str) -> dict[str, Any]:
    return _read_json(
        subbatch
        / "cases"
        / case_id
        / "effective_experiment_config.json"
    )["simulationConfig"]


def _round_bytes(
    subbatch: Path,
    case_id: str,
    filename: str,
) -> bytes:
    return (
        subbatch
        / "cases"
        / case_id
        / "pipeline"
        / "run"
        / "round_000"
        / filename
    ).read_bytes()


def _configuration_diff(
    left: dict[str, Any],
    right: dict[str, Any],
) -> list[str]:
    differences: list[str] = []

    def visit(first: Any, second: Any, prefix: str) -> None:
        if isinstance(first, dict) and isinstance(second, dict):
            for key in sorted(set(first) | set(second)):
                path = f"{prefix}.{key}" if prefix else key
                if key not in first or key not in second:
                    differences.append(path)
                else:
                    visit(first[key], second[key], path)
            return
        if first != second:
            differences.append(prefix)

    visit(left, right, "")
    return differences


def _all_finite(value: Any) -> bool:
    if isinstance(value, dict):
        return all(_all_finite(item) for item in value.values())
    if isinstance(value, list):
        return all(_all_finite(item) for item in value)
    if isinstance(value, float):
        return math.isfinite(value)
    return True


def _relative(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
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


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the six-case minimal pilot."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parent
        / "configs"
        / "pilot_minimal.yaml",
    )
    parser.add_argument("--batch-id", required=True)
    arguments = parser.parse_args(argv)
    config = load_pilot_config(arguments.config)
    root = Path(__file__).resolve().parents[1]
    output = run_pilot(
        config,
        repository_root=root,
        batch_id=arguments.batch_id,
        source_config_path=arguments.config,
    )
    print(f"pilot={config.pilot_id} output={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
