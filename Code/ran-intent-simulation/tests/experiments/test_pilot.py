"""Tests for the minimal six-case pilot orchestration and validation."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from experiments.pilot import load_pilot_config, run_pilot


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_minimal_pilot_writes_six_traceable_validated_cases(
    tmp_path: Path,
) -> None:
    config = load_pilot_config(
        REPOSITORY_ROOT / "experiments" / "configs" / "pilot_minimal.yaml"
    ).model_copy(update={"output_root": str(tmp_path)})
    pilot_root = run_pilot(
        config,
        repository_root=REPOSITORY_ROOT,
        batch_id="pilot-test",
    )

    manifest = json.loads(
        (pilot_root / "batch_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["caseCount"] == 6
    assert manifest["successfulCaseCount"] == 6
    assert all(
        value is True
        for key, value in manifest["validations"].items()
        if key
        in {
            "caseFileCompleteness",
            "summaryMatchesSourceJson",
            "relativePathsResolve",
            "feedbackOnlySwitchDiff",
            "feedbackInitialCandidatesEqual",
            "weightOnlyScoringWeightsDiffer",
            "weightCandidatesEqual",
            "weightPerformanceEqual",
            "loadOnlyInputDiffers",
            "infeasibleScoreRuleValid",
            "feedbackParentChildChainValid",
            "allResultsFinite",
        }
    )
    assert manifest["reproducibility"]["mismatchCount"] == 0

    summary = pd.read_csv(pilot_root / "pilot_summary.csv")
    assert len(summary) == 6
    disabled = summary.loc[
        summary["caseId"] == "feedback_enabled_false"
    ].iloc[0]
    enabled = summary.loc[
        summary["caseId"] == "feedback_enabled_true"
    ].iloc[0]
    assert disabled["generationRounds"] == 1
    assert disabled["feedbackIterations"] == 0
    assert disabled["terminationReason"] == "feedback_disabled"
    assert enabled["generationRounds"] > 1
    assert enabled["feedbackIterations"] > 0
