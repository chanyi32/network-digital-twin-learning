"""Tests for hard constraints, fixed normalization, scoring, and ranking."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from ran_intent_simulation.config import (
    ScoringNormalizationBound,
    SimulationConfig,
    load_simulation_config,
)
from ran_intent_simulation.exceptions import (
    NormalizationError,
    ScoringError,
)
from ran_intent_simulation.models.evaluation import PolicyPerformanceResult
from ran_intent_simulation.models.policy import CandidatePolicy, PolicyAction
from ran_intent_simulation.scoring import (
    HardConstraintChecker,
    PolicyScorer,
    normalize_cost,
    normalize_gain,
)


@pytest.fixture(scope="module")
def simulation_config() -> SimulationConfig:
    return load_simulation_config("config/simulation_config.yaml")


def make_policy(
    policy_id: str,
    *,
    actions: list[PolicyAction] | None = None,
) -> CandidatePolicy:
    policy_actions = actions or []
    parameters = {
        key: value
        for action in policy_actions
        for key, value in action.parameters.items()
    }
    start = datetime(2026, 7, 30, 19, 15, tzinfo=timezone(timedelta(hours=8)))
    return CandidatePolicy(
        policyId=policy_id,
        intentId="INTENT-SCORING-TEST",
        scope={
            "startTime": start,
            "endTime": start + timedelta(hours=3),
            "cellIds": ["CELL-101"],
            "targetUserGroups": ["video", "voice"],
        },
        actions=policy_actions,
        parameters=parameters,
        objectives=["video_uplink_assurance"],
        hardConstraints=[
            {
                "metric": "videoUserSatisfactionRatio",
                "operator": ">=",
                "thresholdRef": "sla.video.required_user_satisfaction_ratio",
            },
            {
                "metric": "videoDelayP95Ms",
                "operator": "<=",
                "thresholdRef": "sla.video.delay_p95_threshold_ms",
            },
            {
                "metric": "voiceQualityScore",
                "operator": ">=",
                "thresholdRef": "sla.voice.minimum_quality_score",
            },
            {
                "metric": "voiceQualityDegradation",
                "operator": "<=",
                "thresholdRef": "sla.voice.maximum_degradation_from_baseline",
            },
            {
                "metric": "prbUtilization",
                "operator": "<=",
                "thresholdRef": "resources.maximum_prb_utilization",
            },
        ],
        triggerConditions=["effective_time_reached"],
        rollbackConditions=["effective_time_ended"],
        generationRound=0,
        status="pending_evaluation",
        parentPolicyId=None,
        generationReason="scoring_test",
        configVersion="1.1",
    )


def make_performance(
    policy_id: str,
    **updates: float,
) -> PolicyPerformanceResult:
    payload: dict[str, object] = {
        "policyId": policy_id,
        "generationRound": 0,
        "cellId": "CELL-101",
        "videoUsers": [
            {
                "userId": "VIDEO-001",
                "videoUplinkThroughputMbps": 24.0,
                "videoUplinkDelayMs": 20.0,
                "videoUplinkBler": 0.03,
                "outputDiagnostics": {},
            }
        ],
        "videoUserSatisfactionRatio": 1.0,
        "videoThroughputMeanMbps": 24.0,
        "videoThroughputP05Mbps": 24.0,
        "videoDelayMeanMs": 20.0,
        "videoDelayP95Ms": 20.0,
        "videoUplinkBlerMean": 0.03,
        "voiceQualityScore": 0.97,
        "voiceQualityDegradation": 0.0,
        "prbUtilization": 0.60,
        "ranEnergy": 0.95,
        "normalUserPerformanceDegradation": 0.03,
        "riskScore": 0.10,
        "riskComponents": {"overload": 0.0},
        "quantileMethod": "linear",
        "performanceModelVersion": "simplified-ran-v1",
        "coefficientVersion": "simplified-ran-coefficients-v1",
        "randomSeed": 20260730,
        "stochasticEnabled": False,
        "outputDiagnostics": {},
        "clippingSummary": {},
        "modelWarnings": [],
    }
    payload.update(updates)
    return PolicyPerformanceResult.model_validate(payload)


def test_hard_constraint_boundaries_are_inclusive(
    simulation_config: SimulationConfig,
) -> None:
    policy = make_policy("POLICY-BOUNDARY")
    performance = make_performance(
        policy.policyId,
        videoUserSatisfactionRatio=0.95,
        videoDelayP95Ms=30.0,
        voiceQualityScore=0.95,
        voiceQualityDegradation=0.02,
        prbUtilization=0.90,
    )

    result = HardConstraintChecker(simulation_config).check(policy, performance)

    assert result.feasible
    assert len(result.checks) == 5
    assert all(check.passed and check.violation is None for check in result.checks)


def test_infeasible_policy_keeps_every_violation_and_cannot_be_compensated(
    simulation_config: SimulationConfig,
) -> None:
    policy = make_policy("POLICY-INFEASIBLE")
    performance = make_performance(
        policy.policyId,
        videoUserSatisfactionRatio=0.94,
        videoDelayP95Ms=31.0,
        voiceQualityScore=0.94,
        voiceQualityDegradation=0.03,
        prbUtilization=0.91,
        ranEnergy=0.01,
    )

    [score] = PolicyScorer(simulation_config).score_and_rank(
        [policy],
        [performance],
    )

    violations = [
        check.violation
        for check in score.constraintCheck.checks
        if not check.passed
    ]
    assert len(violations) == 5
    assert all(violations)
    assert not score.feasible
    assert score.totalScore == 0
    assert score.rank is None
    assert score.energyScore > 0


def test_fixed_normalization_boundaries_clipping_and_directions() -> None:
    bounds = ScoringNormalizationBound(minimum=10.0, maximum=20.0)

    assert normalize_gain(10.0, bounds) == 0.0
    assert normalize_gain(20.0, bounds) == 1.0
    assert normalize_gain(25.0, bounds) == 1.0
    assert normalize_gain(5.0, bounds) == 0.0
    assert normalize_cost(10.0, bounds) == 1.0
    assert normalize_cost(20.0, bounds) == 0.0


def test_normalization_rejects_invalid_runtime_inputs() -> None:
    invalid_bounds = ScoringNormalizationBound.model_construct(
        minimum=1.0,
        maximum=1.0,
    )
    valid_bounds = ScoringNormalizationBound(minimum=0.0, maximum=1.0)

    with pytest.raises(NormalizationError, match="greater than"):
        normalize_gain(1.0, invalid_bounds)
    with pytest.raises(NormalizationError, match="finite"):
        normalize_gain(float("nan"), valid_bounds)


def test_scores_use_configured_weights_and_fixed_bounds(
    simulation_config: SimulationConfig,
) -> None:
    policy = make_policy("POLICY-SCORED")
    performance = make_performance(policy.policyId)

    [score] = PolicyScorer(simulation_config).score_and_rank(
        [policy],
        [performance],
    )
    weights = simulation_config.scoring.weights
    expected = (
        weights.service * score.serviceScore
        + weights.energy * score.energyScore
        + weights.resource * score.resourceScore
        + weights.risk * score.riskScore
    )

    assert score.feasible
    assert score.rank == 1
    assert score.totalScore == pytest.approx(expected)
    assert set(score.normalizedMetrics) == {
        "videoUserSatisfactionRatio",
        "videoThroughputP05Mbps",
        "videoDelayP95Ms",
        "videoUplinkBlerMean",
        "voiceQualityScore",
        "energySavingRatio",
        "prbUtilization",
        "actionComplexity",
        "policyRisk",
    }
    assert all(0 <= value <= 1 for value in score.normalizedMetrics.values())
    assert score.scoreConfigVersion == simulation_config.scoring.version


def test_identical_scores_are_ranked_deterministically_by_policy_id(
    simulation_config: SimulationConfig,
) -> None:
    policies = [make_policy("POLICY-B"), make_policy("POLICY-A")]
    performances = [
        make_performance("POLICY-B"),
        make_performance("POLICY-A"),
    ]
    scorer = PolicyScorer(simulation_config)

    first = scorer.score_and_rank(policies, performances)
    second = scorer.score_and_rank(
        list(reversed(policies)),
        list(reversed(performances)),
    )

    assert [(item.policyId, item.rank) for item in first] == [
        ("POLICY-A", 1),
        ("POLICY-B", 2),
    ]
    assert [(item.policyId, item.rank) for item in second] == [
        ("POLICY-A", 1),
        ("POLICY-B", 2),
    ]


def test_scoring_does_not_modify_policy_or_performance(
    simulation_config: SimulationConfig,
) -> None:
    action = PolicyAction(
        type="UL_RESOURCE_RESERVE",
        target="video",
        parameters={"reservedPrbRatio": 0.1},
    )
    policy = make_policy("POLICY-IMMUTABLE", actions=[action])
    performance = make_performance(policy.policyId)
    policy_before = policy.model_dump_json()
    performance_before = performance.model_dump_json()

    PolicyScorer(simulation_config).score_and_rank([policy], [performance])

    assert policy.model_dump_json() == policy_before
    assert performance.model_dump_json() == performance_before


def test_invalid_weight_sum_is_rejected(
    simulation_config: SimulationConfig,
) -> None:
    payload = deepcopy(simulation_config.model_dump())
    payload["scoring"]["weights"]["service"] = 0.50

    with pytest.raises(ValidationError, match="weights must sum to 1.0"):
        SimulationConfig.model_validate(payload)


def test_invalid_normalization_range_is_rejected(
    simulation_config: SimulationConfig,
) -> None:
    payload = deepcopy(simulation_config.model_dump())
    bounds = payload["scoring"]["normalization_bounds"]["policy_risk"]
    bounds["maximum"] = bounds["minimum"]

    with pytest.raises(ValidationError, match="maximum must exceed minimum"):
        SimulationConfig.model_validate(payload)


def test_policy_and_performance_sets_must_match(
    simulation_config: SimulationConfig,
) -> None:
    with pytest.raises(ScoringError, match="ID sets differ"):
        PolicyScorer(simulation_config).score_and_rank(
            [make_policy("POLICY-ONLY")],
            [make_performance("RESULT-ONLY")],
        )
