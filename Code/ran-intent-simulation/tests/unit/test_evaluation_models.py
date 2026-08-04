"""Unit tests for performance, score, and feedback contracts."""

from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from ran_intent_simulation.models.evaluation import (
    PolicyFeedback,
    PolicyPerformanceResult,
    PolicyScore,
)


def performance_payload() -> dict[str, object]:
    return {
        "policyId": "RAN-POLICY-R00-0001",
        "generationRound": 0,
        "cellId": "CELL-101",
        "videoUsers": [
            {
                "userId": "VIDEO-001",
                "videoUplinkThroughputMbps": 21.0,
                "videoUplinkDelayMs": 25.0,
                "videoUplinkBler": 0.03,
                "outputDiagnostics": {},
            }
        ],
        "videoUserSatisfactionRatio": 1.0,
        "videoThroughputMeanMbps": 21.0,
        "videoThroughputP05Mbps": 21.0,
        "videoDelayMeanMs": 25.0,
        "videoDelayP95Ms": 25.0,
        "videoUplinkBlerMean": 0.03,
        "voiceQualityScore": 0.96,
        "voiceQualityDegradation": 0.01,
        "prbUtilization": 0.88,
        "ranEnergy": 0.95,
        "normalUserPerformanceDegradation": 0.05,
        "riskScore": 0.10,
        "riskComponents": {"bler": 0.03, "fairness": 0.05},
        "quantileMethod": "linear",
        "performanceModelVersion": "simplified-ran-v1",
        "coefficientVersion": "simplified-ran-coefficients-v1",
        "randomSeed": 20260730,
        "stochasticEnabled": False,
        "outputDiagnostics": {},
        "clippingSummary": {},
        "modelWarnings": [],
    }


def score_payload() -> dict[str, object]:
    return {
        "policyId": "RAN-POLICY-R00-0001",
        "constraintCheck": {
            "policyId": "RAN-POLICY-R00-0001",
            "checks": [
                {
                    "metric": "prbUtilization",
                    "operator": "<=",
                    "thresholdRef": "resources.maximum_prb_utilization",
                    "actualValue": 0.88,
                    "thresholdValue": 0.90,
                    "passed": True,
                }
            ],
            "feasible": True,
        },
        "feasible": True,
        "performance": performance_payload(),
        "normalizedMetrics": {"videoDelayP95Ms": 0.8},
        "serviceScore": 0.9,
        "energyScore": 0.7,
        "resourceScore": 0.6,
        "riskScore": 0.9,
        "totalScore": 0.83,
        "rank": 1,
        "scoreConfigVersion": "1.1",
    }


def test_performance_result_rejects_negative_delay() -> None:
    payload = performance_payload()
    payload["videoDelayP95Ms"] = -1
    with pytest.raises(ValidationError):
        PolicyPerformanceResult.model_validate(payload)


def test_infeasible_score_must_be_zero_and_unranked() -> None:
    payload = deepcopy(score_payload())
    payload["constraintCheck"]["checks"][0]["passed"] = False  # type: ignore[index]
    payload["constraintCheck"]["feasible"] = False  # type: ignore[index]
    payload["feasible"] = False
    with pytest.raises(ValidationError, match="totalScore=0"):
        PolicyScore.model_validate(payload)


def test_policy_score_json_round_trip() -> None:
    original = PolicyScore.model_validate(score_payload())
    restored = PolicyScore.model_validate_json(original.model_dump_json())
    assert restored == original


def test_policy_feedback_json_round_trip() -> None:
    original = PolicyFeedback(
        policyId="RAN-POLICY-R00-0001",
        generationRound=0,
        violations=["video_user_satisfaction_below_threshold"],
        weakMetrics=[
            {
                "metric": "videoUserSatisfactionRatio",
                "thresholdRef": "sla.video.required_user_satisfaction_ratio",
                "gap": 0.05,
            }
        ],
        suggestedParameterUpdates=[
            {
                "parameter": "reservedPrbRatio",
                "direction": "increase",
                "method": "next_configured_value",
                "searchSpaceRef": "action_space.reserved_prb_ratio",
            }
        ],
        suggestedActionChanges={"add": ["UL_RESOURCE_RESERVE"], "remove": []},
        searchSpaceUpdates=[],
        feedbackReason="video_throughput_insufficient",
    )
    restored = PolicyFeedback.model_validate_json(original.model_dump_json())
    assert restored == original
