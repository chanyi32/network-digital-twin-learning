from __future__ import annotations

import math

import pandas as pd
import pytest

from analysis.formal_analysis import (
    FORMAL_ROOT,
    build_feedback_analysis,
    build_load_analysis,
    build_weight_analysis,
    case_directories,
    pareto_ids,
    spearman_rank,
)


def test_spearman_rank_identity_and_reversal() -> None:
    assert spearman_rank(["a", "b", "c"], ["a", "b", "c"]) == 1.0
    assert math.isclose(
        spearman_rank(["a", "b", "c"], ["c", "b", "a"]),
        -1.0,
    )


def test_pareto_ids_removes_dominated_policy() -> None:
    scores = [
        {
            "policyId": "a",
            "serviceScore": 1.0,
            "energyScore": 1.0,
            "resourceScore": 1.0,
            "riskScore": 1.0,
        },
        {
            "policyId": "b",
            "serviceScore": 0.5,
            "energyScore": 0.5,
            "resourceScore": 0.5,
            "riskScore": 0.5,
        },
    ]
    assert pareto_ids(scores) == {"a"}


def test_formal_load_and_feedback_statistics_match_acceptance() -> None:
    root = FORMAL_ROOT.resolve()
    summary = pd.read_csv(root / "all_experiments_summary.csv")
    cases = case_directories(root)
    load = build_load_analysis(summary, cases)
    feedback = build_feedback_analysis(summary, cases)
    assert load.feasibleRatio.tolist() == pytest.approx(
        [0.95, 0.87, 0.14]
    )
    assert load.bestPolicyId.nunique() == 1
    assert load.feasibleRatioAbruptDrop.tolist() == [
        False,
        False,
        True,
    ]
    assert (feedback.bestTotalScoreDelta == 0).all()
    assert (feedback.bestPolicyChanged == False).all()  # noqa: E712
    assert (feedback.evaluatedPolicyCountDelta == 9).all()


def test_weight_analysis_has_five_profiles_per_seed() -> None:
    root = FORMAL_ROOT.resolve()
    summary = pd.read_csv(root / "all_experiments_summary.csv")
    weights = build_weight_analysis(summary, case_directories(root))
    assert len(weights) == 15
    assert weights.groupby("randomSeed").size().eq(5).all()
    assert weights.bestPolicyId.nunique() == 1
    assert weights.bestPolicyIsPareto.all()
    assert not weights.bestPolicyParetoDominatesAll.any()
