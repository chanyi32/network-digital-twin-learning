"""Unit tests for candidate policies and the action library."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from ran_intent_simulation.models.policy import (
    ActionLibrary,
    CandidatePolicy,
    PolicyAction,
)


def candidate_policy_payload() -> dict[str, object]:
    return {
        "policyId": "RAN-POLICY-R00-0001",
        "intentId": "INTENT-001",
        "scope": {
            "startTime": "2026-07-29T19:15:00+08:00",
            "endTime": "2026-07-29T22:45:00+08:00",
            "cellIds": ["CELL-101"],
            "targetUserGroups": ["video", "voice"],
        },
        "actions": [
            {
                "type": "UL_RESOURCE_RESERVE",
                "target": "video",
                "parameters": {"reservedPrbRatio": 0.20},
            },
            {
                "type": "VOICE_RESOURCE_PROTECT",
                "target": "voice",
                "parameters": {"minimumVoicePrbRatio": 0.15},
            },
        ],
        "parameters": {
            "reservedPrbRatio": 0.20,
            "minimumVoicePrbRatio": 0.15,
        },
        "objectives": ["video_uplink_assurance", "voice_service_protection"],
        "hardConstraints": [
            {
                "metric": "prbUtilization",
                "operator": "<=",
                "thresholdRef": "resources.maximum_prb_utilization",
            }
        ],
        "triggerConditions": ["effective_time_reached"],
        "rollbackConditions": ["prb_limit_violation"],
        "generationRound": 0,
        "status": "pending_evaluation",
        "parentPolicyId": None,
        "generationReason": "initial_template_grid",
        "configVersion": "1.1",
    }


def test_policy_action_rejects_invalid_ratio() -> None:
    with pytest.raises(ValidationError, match=r"\[0, 1\]"):
        PolicyAction(
            type="UL_RESOURCE_RESERVE",
            target="video",
            parameters={"reservedPrbRatio": 1.1},
        )


def test_candidate_policy_rejects_multiple_cells() -> None:
    payload = candidate_policy_payload()
    payload["scope"]["cellIds"] = ["CELL-101", "CELL-102"]  # type: ignore[index]
    with pytest.raises(ValidationError):
        CandidatePolicy.model_validate(payload)


def test_candidate_policy_parameters_must_match_actions() -> None:
    payload = deepcopy(candidate_policy_payload())
    payload["parameters"]["reservedPrbRatio"] = 0.30  # type: ignore[index]
    with pytest.raises(ValidationError, match="flattened"):
        CandidatePolicy.model_validate(payload)


def test_candidate_policy_json_round_trip() -> None:
    original = CandidatePolicy.model_validate(candidate_policy_payload())
    restored = CandidatePolicy.model_validate_json(original.model_dump_json())
    assert restored == original


def test_action_library_json_round_trip() -> None:
    original = ActionLibrary.model_validate_json(
        Path("config/action_library.json").read_text(encoding="utf-8")
    )
    restored = ActionLibrary.model_validate_json(original.model_dump_json())
    assert restored == original
