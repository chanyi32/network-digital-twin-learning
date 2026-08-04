"""Validation and end-to-end tests for the experiment framework."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import yaml
from pydantic import ValidationError

from experiments.config import ExperimentConfig, load_experiment_config
from experiments.runner import ExperimentRunner, _set_dotted_value


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIRECTORY = REPOSITORY_ROOT / "experiments" / "configs"


@pytest.mark.parametrize(
    "experiment_name",
    [
        "baseline_e2e",
        "load_sweep",
        "feedback_compare",
        "weight_sensitivity",
    ],
)
def test_default_experiment_yaml_is_valid(
    experiment_name: str,
) -> None:
    config = load_experiment_config(
        CONFIG_DIRECTORY / f"{experiment_name}.yaml"
    )
    assert config.experiment_name == experiment_name
    assert config.schema_version == "1.1"
    assert config.fixed_random_seed == 20260730
    assert config.cases


def test_duplicate_case_ids_and_unknown_fields_are_rejected() -> None:
    payload = {
        "schema_version": "1.0",
        "experiment_name": "baseline_e2e",
        "description": "invalid duplicate test",
        "fixed_random_seed": 7,
        "cases": [
            {"case_id": "same", "description": "first"},
            {"case_id": "same", "description": "second"},
        ],
    }
    with pytest.raises(ValidationError, match="case_id"):
        ExperimentConfig.model_validate(payload)

    payload["cases"] = [
        {
            "case_id": "one",
            "description": "unknown field",
            "unsupported": True,
        }
    ]
    with pytest.raises(ValidationError, match="unsupported"):
        ExperimentConfig.model_validate(payload)


def test_dotted_override_must_replace_an_existing_field() -> None:
    payload = {"scoring": {"weights": {"service": 0.6}}}
    _set_dotted_value(payload, "scoring.weights.service", 0.7)
    assert payload["scoring"]["weights"]["service"] == 0.7

    with pytest.raises(ValueError, match="does not exist"):
        _set_dotted_value(payload, "scoring.weights.energy", 0.1)


def test_batch_runner_archives_inputs_versions_and_summaries(
    tmp_path: Path,
) -> None:
    config = ExperimentConfig.model_validate(
        {
            "schema_version": "1.1",
            "experiment_name": "baseline_e2e",
            "description": "fast experiment integration test",
            "fixed_random_seed": 314159,
            "output_root": str(tmp_path),
            "cases": [
                {
                    "case_id": "case_a",
                    "description": "small deterministic case",
                    "scenario_id": "SCENARIO-HIGH-LOAD",
                    "simulation_overrides": {
                        "generation.maximum_candidates_per_round": 4,
                        "optimization.maximum_feedback_iterations": 1,
                    },
                },
                {
                    "case_id": "case_b",
                    "description": "second load case",
                    "scenario_id": "SCENARIO-HIGH-LOAD",
                    "simulation_overrides": {
                        "generation.maximum_candidates_per_round": 4,
                        "optimization.maximum_feedback_iterations": 1,
                    },
                    "ran_state_overrides": {
                        "cellLoad": 0.70,
                        "prbUtilization": 0.68,
                        "availablePrbRatio": 0.32,
                    },
                },
            ],
        }
    )
    result = ExperimentRunner(
        config,
        repository_root=REPOSITORY_ROOT,
        batch_id="test-batch",
    ).run()

    assert result.case_count == 2
    assert result.successful_case_count == 2
    batch_manifest = json.loads(
        (result.batch_directory / "batch_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert batch_manifest["fixedRandomSeed"] == 314159
    assert batch_manifest["successfulCaseCount"] == 2
    assert batch_manifest["schemaVersion"] == "1.1"
    assert batch_manifest["experimentId"].startswith("EXP-")

    for case_id in ("case_a", "case_b"):
        case_directory = result.batch_directory / "cases" / case_id
        manifest = json.loads(
            (case_directory / "case_manifest.json").read_text(
                encoding="utf-8"
            )
        )
        assert manifest["fixedRandomSeed"] == 314159
        assert manifest["modelVersion"] == "simplified-ran-v1"
        assert manifest["schemaVersion"] == "1.1"
        assert manifest["experimentId"] == batch_manifest["experimentId"]
        assert manifest["caseId"] == case_id
        assert manifest["runId"] == "run"
        assert manifest["experimentType"] == "baseline_e2e"
        assert manifest["codeVersion"] == "0.1.1"
        assert manifest["baseModelVersion"] == "simplified-ran-v1"
        assert manifest["randomSeed"] == 314159
        assert manifest["executionStatus"] == "succeeded"
        assert len(manifest["configurationHash"]) == 64
        assert len(manifest["inputHash"]) == 64
        assert len(manifest["simulationConfigSha256"]) == 64
        assert len(manifest["inputFileHashes"]) == 8
        assert (case_directory / "strategy_results.json").is_file()
        performance_frame = pd.read_csv(
            case_directory / "performance_metrics.csv"
        )
        scoring_frame = pd.read_csv(
            case_directory / "scoring_results.csv"
        )
        assert not performance_frame.empty
        assert not scoring_frame.empty
        required_columns = {
            "experimentId",
            "caseId",
            "runId",
            "experimentType",
            "executionStatus",
            "feedbackEnabled",
            "feedbackIterations",
            "generationRounds",
            "terminationReason",
            "codeVersion",
            "baseModelVersion",
            "configurationHash",
            "inputHash",
            "randomSeed",
            "runManifestPath",
            "resultDirectory",
            "errorType",
            "errorMessage",
        }
        assert required_columns <= set(performance_frame.columns)
        assert required_columns <= set(scoring_frame.columns)
        for frame in (performance_frame, scoring_frame):
            assert set(frame["experimentId"]) == {
                manifest["experimentId"]
            }
            assert set(frame["caseId"]) == {case_id}
            assert set(frame["runId"]) == {"run"}
        run_manifest = result.batch_directory / manifest["runManifestPath"]
        result_directory = (
            result.batch_directory / manifest["resultDirectory"]
        )
        assert run_manifest.is_file()
        assert result_directory.is_dir()
        for relative_path in manifest["inputFileHashes"]:
            assert (result.batch_directory / relative_path).is_file()
        resolved_config = yaml.safe_load(
            (
                case_directory
                / "inputs"
                / "simulation_config.yaml"
            ).read_text(encoding="utf-8")
        )
        assert resolved_config["reproducibility"]["random_seed"] == 314159


def test_failed_and_skipped_cases_are_recorded_and_batch_continues(
    tmp_path: Path,
) -> None:
    config = ExperimentConfig.model_validate(
        {
            "schema_version": "1.1",
            "experiment_name": "load_sweep",
            "description": "failure recording test",
            "fixed_random_seed": 1,
            "output_root": str(tmp_path),
            "cases": [
                {
                    "case_id": "invalid_column",
                    "description": "invalid state override",
                    "ran_state_overrides": {"notAColumn": 1},
                },
                {
                    "case_id": "continues",
                    "description": "valid case after failure",
                    "simulation_overrides": {
                        "generation.maximum_candidates_per_round": 4,
                        "optimization.maximum_feedback_iterations": 1,
                    },
                },
                {
                    "case_id": "planned_skip",
                    "description": "explicitly skipped case",
                    "skip": True,
                    "skip_reason": "acceptance skip test",
                }
            ],
        }
    )
    result = ExperimentRunner(
        config,
        repository_root=REPOSITORY_ROOT,
        batch_id="partial-batch",
    ).run()

    assert result.successful_case_count == 1
    manifest = json.loads(
        (result.batch_directory / "batch_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["cases"][0]["status"] == "failed"
    assert "notAColumn" in manifest["cases"][0]["errorMessage"]
    assert manifest["failedCaseCount"] == 1
    assert manifest["skippedCaseCount"] == 1
    assert manifest["successfulCaseCount"] == 1

    failed_directory = (
        result.batch_directory / "cases" / "invalid_column"
    )
    failed_manifest = json.loads(
        (failed_directory / "case_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert failed_manifest["executionStatus"] == "failed"
    assert failed_manifest["errorType"] == "ValueError"
    assert failed_manifest["inputFileHashes"]
    for csv_name in ("performance_metrics.csv", "scoring_results.csv"):
        frame = pd.read_csv(failed_directory / csv_name)
        assert len(frame) == 1
        assert frame.loc[0, "executionStatus"] == "failed"
        assert frame.loc[0, "errorType"] == "ValueError"
        assert "notAColumn" in frame.loc[0, "errorMessage"]

    skipped_manifest = json.loads(
        (
            result.batch_directory
            / "cases"
            / "planned_skip"
            / "case_manifest.json"
        ).read_text(encoding="utf-8")
    )
    assert skipped_manifest["executionStatus"] == "skipped"
    assert skipped_manifest["skipReason"] == "acceptance skip test"


def test_configuration_and_input_hashes_change_only_with_inputs(
    tmp_path: Path,
) -> None:
    config = ExperimentConfig.model_validate(
        {
            "schema_version": "1.1",
            "experiment_name": "load_sweep",
            "description": "hash behavior test",
            "fixed_random_seed": 9,
            "output_root": str(tmp_path),
            "cases": [
                {
                    "case_id": "base",
                    "description": "base skipped case",
                    "skip": True,
                    "skip_reason": "hash-only test",
                },
                {
                    "case_id": "config_change",
                    "description": "changed configuration",
                    "skip": True,
                    "skip_reason": "hash-only test",
                    "simulation_overrides": {
                        "generation.maximum_candidates_per_round": 4
                    },
                },
                {
                    "case_id": "input_change",
                    "description": "changed RAN input",
                    "skip": True,
                    "skip_reason": "hash-only test",
                    "ran_state_overrides": {"cellLoad": 0.70},
                },
            ],
        }
    )
    result = ExperimentRunner(
        config,
        repository_root=REPOSITORY_ROOT,
        batch_id="hash-batch",
    ).run()
    records = {
        case_id: json.loads(
            (
                result.batch_directory
                / "cases"
                / case_id
                / "case_manifest.json"
            ).read_text(encoding="utf-8")
        )
        for case_id in ("base", "config_change", "input_change")
    }

    assert (
        records["base"]["configurationHash"]
        != records["config_change"]["configurationHash"]
    )
    assert (
        records["base"]["inputHash"]
        != records["config_change"]["inputHash"]
    )
    assert (
        records["base"]["configurationHash"]
        == records["input_change"]["configurationHash"]
    )
    assert (
        records["base"]["inputHash"]
        != records["input_change"]["inputHash"]
    )


def test_same_config_and_seed_reproduce_business_artifacts(
    tmp_path: Path,
) -> None:
    config = ExperimentConfig.model_validate(
        {
            "schema_version": "1.1",
            "experiment_name": "baseline_e2e",
            "description": "reproducibility test",
            "fixed_random_seed": 271828,
            "output_root": str(tmp_path),
            "cases": [
                {
                    "case_id": "repro",
                    "description": "small reproducible case",
                    "simulation_overrides": {
                        "generation.maximum_candidates_per_round": 4,
                        "optimization.maximum_feedback_iterations": 1,
                    },
                }
            ],
        }
    )
    first = ExperimentRunner(
        config,
        repository_root=REPOSITORY_ROOT,
        batch_id="repro-first",
    ).run()
    second = ExperimentRunner(
        config,
        repository_root=REPOSITORY_ROOT,
        batch_id="repro-second",
    ).run()

    excluded = {
        "batch_manifest.json",
        "case_manifest.json",
        "run_manifest.json",
    }
    first_files = [
        path
        for path in first.batch_directory.rglob("*")
        if path.is_file() and path.name not in excluded
    ]
    for first_path in first_files:
        relative_path = first_path.relative_to(first.batch_directory)
        second_path = second.batch_directory / relative_path
        assert second_path.is_file()
        assert first_path.read_bytes() == second_path.read_bytes()

    first_record = json.loads(
        (
            first.batch_directory
            / "cases"
            / "repro"
            / "case_manifest.json"
        ).read_text(encoding="utf-8")
    )
    second_record = json.loads(
        (
            second.batch_directory
            / "cases"
            / "repro"
            / "case_manifest.json"
        ).read_text(encoding="utf-8")
    )
    for field in (
        "experimentId",
        "configurationHash",
        "inputHash",
        "inputFileHashes",
        "randomSeed",
        "baseModelVersion",
    ):
        assert first_record[field] == second_record[field]


def test_input_preparation_failure_still_writes_complete_case_record(
    tmp_path: Path,
) -> None:
    config = ExperimentConfig.model_validate(
        {
            "schema_version": "1.1",
            "experiment_name": "baseline_e2e",
            "description": "preparation failure test",
            "fixed_random_seed": 11,
            "output_root": str(tmp_path),
            "inputs": {
                "ran_state_samples": "data/missing-ran-state.csv"
            },
            "cases": [
                {
                    "case_id": "missing_input",
                    "description": "missing source input",
                }
            ],
        }
    )
    result = ExperimentRunner(
        config,
        repository_root=REPOSITORY_ROOT,
        batch_id="preparation-failure",
    ).run()
    manifest = json.loads(
        (
            result.batch_directory
            / "cases"
            / "missing_input"
            / "case_manifest.json"
        ).read_text(encoding="utf-8")
    )

    assert manifest["executionStatus"] == "failed"
    assert manifest["errorType"] == "FileNotFoundError"
    assert manifest["configurationHash"]
    assert manifest["inputHash"]
    assert manifest["inputFileHashes"]
    assert manifest["startTime"]
    assert manifest["endTime"]
