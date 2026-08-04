"""Integration test for an intentionally infeasible simulation scenario."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from ran_intent_simulation.pipeline import PipelinePaths, SimulationPipeline


def test_pipeline_outputs_no_feasible_policy_without_relaxing_constraints(
    tmp_path: Path,
) -> None:
    source_config = yaml.safe_load(
        Path("config/simulation_config.yaml").read_text(encoding="utf-8")
    )
    source_config["sla"]["video"]["throughput_threshold_mbps"] = 10_000.0
    source_config["optimization"]["maximum_feedback_iterations"] = 2
    infeasible_config = tmp_path / "infeasible_simulation_config.yaml"
    infeasible_config.write_text(
        yaml.safe_dump(
            source_config,
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    result = SimulationPipeline(
        paths=PipelinePaths(simulation_config=infeasible_config),
        results_root=tmp_path,
        run_id="integration-no-feasible",
    ).run()

    assert result.status == "completed_no_feasible_policy"
    assert result.roundsCompleted >= 1
    assert result.finalArtifact.name == "no_feasible_policy.json"
    assert not (
        result.runDirectory / "final_recommendation.json"
    ).exists()

    failure = json.loads(
        result.finalArtifact.read_text(encoding="utf-8")
    )
    assert failure["status"] == "no_feasible_policy"
    assert failure["attemptedPolicyCount"] > 0
    assert failure["minimumViolationGaps"]
    assert failure["violationReasons"]
    assert failure["hardConstraintsRelaxed"] is False

    manifest = json.loads(
        (result.runDirectory / "run_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["outcome"] == "no_feasible_policy"
    assert manifest["status"] == "completed_no_feasible_policy"
