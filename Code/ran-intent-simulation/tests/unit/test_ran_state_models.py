"""Unit tests for the single-cell RAN state contract."""

from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from ran_intent_simulation.models.ran_state import RANState


def ran_state_payload() -> dict[str, object]:
    return {
        "timestamp": "2026-07-29T19:30:00+08:00",
        "cellId": "CELL-101",
        "cellLoad": 0.82,
        "prbUtilization": 0.80,
        "availablePrbRatio": 0.20,
        "videoUserCount": 1,
        "voiceUserCount": 1,
        "normalUserCount": 1,
        "videoUsers": [
            {
                "userId": "VIDEO-001",
                "baselineUplinkThroughputMbps": 16.5,
                "baselineUplinkDelayMs": 38.0,
                "baselineUplinkBler": 0.05,
                "meanSinrDb": 8.0,
            }
        ],
        "videoThroughputMeanMbps": 16.5,
        "videoThroughputP05Mbps": 16.5,
        "videoDelayMeanMs": 38.0,
        "videoDelayP95Ms": 38.0,
        "videoUplinkBlerMean": 0.05,
        "voiceQualityScore": 0.97,
        "baselineRanEnergy": 1.0,
        "meanSinrDb": 8.0,
        "normalUserPerformanceIndex": 1.0,
        "quantileMethod": "linear",
    }


def test_ran_state_rejects_negative_user_count() -> None:
    payload = ran_state_payload()
    payload["voiceUserCount"] = -1
    with pytest.raises(ValidationError):
        RANState.model_validate(payload)


def test_ran_state_rejects_video_count_mismatch() -> None:
    payload = ran_state_payload()
    payload["videoUserCount"] = 2
    with pytest.raises(ValidationError, match="videoUsers length"):
        RANState.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("prbUtilization", 1.1),
        ("videoThroughputMeanMbps", -0.1),
        ("videoDelayP95Ms", -0.1),
        ("baselineRanEnergy", -0.1),
    ],
)
def test_ran_state_rejects_invalid_numeric_fields(
    field: str, invalid_value: float
) -> None:
    payload = deepcopy(ran_state_payload())
    payload[field] = invalid_value
    with pytest.raises(ValidationError):
        RANState.model_validate(payload)


def test_ran_state_json_round_trip() -> None:
    original = RANState.model_validate(ran_state_payload())
    restored = RANState.model_validate_json(original.model_dump_json())
    assert restored == original
