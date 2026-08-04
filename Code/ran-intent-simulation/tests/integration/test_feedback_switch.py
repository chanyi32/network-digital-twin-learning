"""Integration tests for the v0.1.1 feedback execution switch."""

from __future__ import annotations

import json
from pathlib import Path

import yaml
import pytest

from ran_intent_simulation.pipeline import PipelinePaths, SimulationPipeline


def _write_config(
    path: Path,
    *,
    feedback_enabled: bool | None,
    maximum_feedback_iterations: int,
) -> Path:
    payload = yaml.safe_load(
        Path("config/simulation_config.yaml").read_text(encoding="utf-8")
    )
    if feedback_enabled is None:
        payload["optimization"].pop("feedback_enabled", None)
    else:
        payload["optimization"]["feedback_enabled"] = feedback_enabled
    payload["optimization"][
        "maximum_feedback_iterations"
    ] = maximum_feedback_iterations
    payload["generation"]["maximum_candidates_per_round"] = 4
    path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return path


def _run(
    tmp_path: Path,
    *,
    name: str,
    feedback_enabled: bool | None,
    maximum_feedback_iterations: int,
) -> Path:
    config_path = _write_config(
        tmp_path / f"{name}.yaml",
        feedback_enabled=feedback_enabled,
        maximum_feedback_iterations=maximum_feedback_iterations,
    )
    return SimulationPipeline(
        paths=PipelinePaths(simulation_config=config_path),
        results_root=tmp_path,
        run_id=name,
    ).run().runDirectory


def _read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _final_artifact(run_directory: Path) -> Path:
    recommendation = run_directory / "final_recommendation.json"
    return (
        recommendation
        if recommendation.is_file()
        else run_directory / "no_feasible_policy.json"
    )


def test_feedback_disabled_stops_after_scored_round_zero(
    tmp_path: Path,
) -> None:
    run_directory = _run(
        tmp_path,
        name="feedback-disabled",
        feedback_enabled=False,
        maximum_feedback_iterations=10,
    )

    assert (run_directory / "round_000").is_dir()
    assert not (run_directory / "round_001").exists()
    assert not (run_directory / "round_000" / "feedback.json").exists()
    for required in (
        "candidate_policies.json",
        "performance_results.json",
        "constraint_checks.csv",
        "policy_scores.csv",
        "ranked_policies.json",
        "round_summary.json",
    ):
        assert (run_directory / "round_000" / required).is_file()

    manifest = _read_json(run_directory / "run_manifest.json")
    assert manifest["feedbackEnabled"] is False  # type: ignore[index]
    assert manifest["feedbackIterations"] == 0  # type: ignore[index]
    assert manifest["generationRounds"] == 1  # type: ignore[index]
    assert manifest["roundsCompleted"] == 1  # type: ignore[index]
    assert manifest["terminationReason"] == "feedback_disabled"  # type: ignore[index]
    final = _read_json(_final_artifact(run_directory))
    assert final["terminationReason"] == "feedback_disabled"  # type: ignore[index]


def test_feedback_disabled_never_calls_optimizer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_optimize(*args: object, **kwargs: object) -> object:
        raise AssertionError("feedback optimizer must not be called")

    monkeypatch.setattr(
        "ran_intent_simulation.pipeline.FeedbackOptimizer.optimize",
        forbidden_optimize,
    )

    run_directory = _run(
        tmp_path,
        name="optimizer-call-guard",
        feedback_enabled=False,
        maximum_feedback_iterations=10,
    )

    assert (run_directory / "round_000").is_dir()
    assert not (run_directory / "round_000" / "feedback.json").exists()


def test_maximum_iterations_do_not_affect_feedback_disabled_outputs(
    tmp_path: Path,
) -> None:
    first = _run(
        tmp_path,
        name="disabled-max-one",
        feedback_enabled=False,
        maximum_feedback_iterations=1,
    )
    second = _run(
        tmp_path,
        name="disabled-max-ten",
        feedback_enabled=False,
        maximum_feedback_iterations=10,
    )

    comparable = [
        "round_000/candidate_policies.json",
        "round_000/performance_results.json",
        "round_000/constraint_checks.csv",
        "round_000/policy_scores.csv",
        "round_000/ranked_policies.json",
        "round_000/round_summary.json",
    ]
    for relative in comparable:
        assert (first / relative).read_bytes() == (
            second / relative
        ).read_bytes()
    assert _final_artifact(first).read_bytes() == _final_artifact(
        second
    ).read_bytes()


def test_enabled_and_disabled_share_identical_initial_candidates(
    tmp_path: Path,
) -> None:
    disabled = _run(
        tmp_path,
        name="switch-disabled",
        feedback_enabled=False,
        maximum_feedback_iterations=1,
    )
    enabled = _run(
        tmp_path,
        name="switch-enabled",
        feedback_enabled=True,
        maximum_feedback_iterations=1,
    )

    assert (
        disabled / "round_000" / "candidate_policies.json"
    ).read_bytes() == (
        enabled / "round_000" / "candidate_policies.json"
    ).read_bytes()
    assert (
        disabled / "round_000" / "performance_results.json"
    ).read_bytes() == (
        enabled / "round_000" / "performance_results.json"
    ).read_bytes()
    enabled_manifest = _read_json(enabled / "run_manifest.json")
    assert enabled_manifest["feedbackEnabled"] is True  # type: ignore[index]
    assert enabled_manifest["feedbackIterations"] == 1  # type: ignore[index]
    assert enabled_manifest["generationRounds"] == 2  # type: ignore[index]
    assert (enabled / "round_000" / "feedback.json").is_file()
    assert (enabled / "round_001").is_dir()


def test_omitted_switch_matches_explicit_true_business_outputs(
    tmp_path: Path,
) -> None:
    omitted = _run(
        tmp_path,
        name="switch-omitted",
        feedback_enabled=None,
        maximum_feedback_iterations=1,
    )
    explicit = _run(
        tmp_path,
        name="switch-explicit",
        feedback_enabled=True,
        maximum_feedback_iterations=1,
    )

    for round_name in ("round_000", "round_001"):
        omitted_files = sorted(
            path.relative_to(omitted / round_name)
            for path in (omitted / round_name).iterdir()
        )
        explicit_files = sorted(
            path.relative_to(explicit / round_name)
            for path in (explicit / round_name).iterdir()
        )
        assert omitted_files == explicit_files
        for relative in omitted_files:
            assert (
                omitted / round_name / relative
            ).read_bytes() == (
                explicit / round_name / relative
            ).read_bytes()
    assert (
        omitted / "no_feasible_policy.json"
    ).read_bytes() == (
        explicit / "no_feasible_policy.json"
    ).read_bytes()
