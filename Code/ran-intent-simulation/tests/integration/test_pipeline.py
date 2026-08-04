"""End-to-end integration tests for a feasible simulation run."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ran_intent_simulation.cli import main
from ran_intent_simulation.exceptions import PipelineStageError
from ran_intent_simulation.pipeline import PipelinePaths, SimulationPipeline


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def test_pipeline_writes_reproducible_round_outputs(
    tmp_path: Path,
) -> None:
    result = SimulationPipeline(
        results_root=tmp_path,
        run_id="integration-feasible",
    ).run()
    run_directory = tmp_path / "integration-feasible"

    assert result.status == "completed"
    assert result.roundsCompleted >= 1
    assert result.finalArtifact == (
        run_directory / "final_recommendation.json"
    )
    assert result.finalArtifact.is_file()
    assert not (run_directory / "no_feasible_policy.json").exists()
    assert (run_directory / "extracted_intents.json").is_file()
    assert (run_directory / "translated_intents.json").is_file()

    manifest = read_json(run_directory / "run_manifest.json")
    assert manifest["status"] == "completed"  # type: ignore[index]
    assert manifest["outcome"] == "feasible_policy_recommended"  # type: ignore[index]
    assert manifest["randomSeed"] == 20260730  # type: ignore[index]
    assert manifest["versions"]["performanceModelImplementation"] == (  # type: ignore[index]
        "simplified-ran-v1"
    )
    assert manifest["versions"]["performanceCoefficientVersion"] == (  # type: ignore[index]
        "simplified-ran-coefficients-v1"
    )
    hashes = manifest["inputFileHashes"]  # type: ignore[index]
    assert len(hashes) == 8
    assert all(
        len(digest) == 64
        for digest in hashes.values()  # type: ignore[union-attr]
    )

    round_directories = sorted(run_directory.glob("round_*"))
    assert len(round_directories) == result.roundsCompleted
    expected_files = {
        "candidate_policies.json",
        "performance_results.json",
        "performance_results.csv",
        "constraint_checks.csv",
        "policy_scores.csv",
        "ranked_policies.json",
        "feedback.json",
        "round_summary.json",
    }
    for index, directory in enumerate(round_directories):
        assert directory.name == f"round_{index:03d}"
        assert expected_files <= {
            path.name for path in directory.iterdir()
        }

    recommendation = read_json(result.finalArtifact)
    assert recommendation["status"] == "recommended"  # type: ignore[index]
    assert recommendation["score"]["feasible"] is True  # type: ignore[index]
    assert recommendation["policy"]["policyId"] == (  # type: ignore[index]
        recommendation["score"]["policyId"]  # type: ignore[index]
    )
    assert any(  # type: ignore[index]
        "voiceQualityScore" in warning
        for warning in recommendation["modelWarning"]  # type: ignore[index]
    )


def test_pipeline_reports_the_failing_module_and_re_raises(
    tmp_path: Path,
) -> None:
    paths = PipelinePaths(
        intent_samples=tmp_path / "missing_intents.json",
    )
    pipeline = SimulationPipeline(
        paths=paths,
        results_root=tmp_path,
        run_id="integration-failure",
    )

    with pytest.raises(
        PipelineStageError,
        match="input_hashing failed",
    ) as error:
        pipeline.run()

    assert error.value.stage == "input_hashing"
    manifest = read_json(
        tmp_path / "integration-failure" / "run_manifest.json"
    )
    assert manifest["status"] == "failed"  # type: ignore[index]
    assert manifest["errorSummary"]["stage"] == "input_hashing"  # type: ignore[index]


def test_main_entry_point_runs_the_complete_pipeline(
    tmp_path: Path,
) -> None:
    exit_code = main(
        [
            "--results-root",
            str(tmp_path),
            "--run-id",
            "integration-cli",
            "--log-level",
            "ERROR",
        ]
    )

    assert exit_code == 0
    assert (
        tmp_path
        / "integration-cli"
        / "final_recommendation.json"
    ).is_file()
