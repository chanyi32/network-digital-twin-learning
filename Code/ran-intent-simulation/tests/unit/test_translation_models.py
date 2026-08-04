"""Unit tests for translated RAN intent contracts."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from ran_intent_simulation.models.translation import (
    EffectiveTime,
    EventRecord,
    ObjectiveRelationship,
    RANObjective,
    RANScope,
    SLAConstraint,
    TargetUserRule,
    TranslatedRANIntent,
    VenueCellMapping,
)


def make_effective_time() -> EffectiveTime:
    return EffectiveTime(
        eventStartTime=datetime(2026, 7, 29, 19, 30, tzinfo=timezone.utc),
        eventEndTime=datetime(2026, 7, 29, 22, 30, tzinfo=timezone.utc),
        effectiveStartTime=datetime(2026, 7, 29, 19, 15, tzinfo=timezone.utc),
        effectiveEndTime=datetime(2026, 7, 29, 22, 45, tzinfo=timezone.utc),
        preWindowRef="time.pre_effective_minutes",
        postWindowRef="time.post_effective_minutes",
        source="event_database",
    )


def make_translated_intent() -> TranslatedRANIntent:
    return TranslatedRANIntent(
        schemaVersion="1.0",
        intentId="INTENT-001",
        scope=RANScope(
            effectiveTime=make_effective_time(),
            venueId="STADIUM-001",
            gnbIds=["GNB-001"],
            cellIds=["CELL-101"],
            carrierIds=["NR-CARRIER-01"],
            targetUserRules=[
                TargetUserRule(
                    group="video",
                    serviceType="uplink_video",
                    source="static_user_identification_rule",
                )
            ],
            source="venue_cell_mapping",
        ),
        ranObjectives=[
            RANObjective(
                name="video_uplink_assurance",
                priority="primary",
                source="business_intent_mapping",
            )
        ],
        slaConstraints=[
            SLAConstraint(
                metric="videoDelayP95Ms",
                operator="<=",
                thresholdRef="sla.video.delay_p95_threshold_ms",
                source="simulation_sla_template",
            )
        ],
        objectiveRelationship=ObjectiveRelationship(
            hardConstraints=["video_delay_p95"],
            primaryObjective="video_uplink_assurance",
            secondaryObjectives=["risk_reduction"],
            source="business_intent_and_static_constraints",
        ),
        unresolvedItems=[],
        translationStatus="ready",
    )


def test_effective_time_rejects_reversed_event() -> None:
    with pytest.raises(ValidationError, match="endTime"):
        EventRecord(
            eventId="EVENT-001",
            eventType="concert",
            venueId="STADIUM-001",
            startTime="2026-07-29T22:30:00+08:00",
            endTime="2026-07-29T19:30:00+08:00",
        )


def test_translation_scope_rejects_multiple_cells() -> None:
    with pytest.raises(ValidationError):
        VenueCellMapping(
            venueId="STADIUM-001",
            geoFence="POLYGON(...)",
            gnbIds=["GNB-001"],
            cellIds=["CELL-101", "CELL-102"],
            carrierIds=["NR-CARRIER-01"],
        )


def test_ready_translation_rejects_blocking_item() -> None:
    payload = make_translated_intent().model_dump()
    payload["unresolvedItems"] = [{"code": "ran_scope", "severity": "blocking"}]
    with pytest.raises(ValidationError, match="blocking"):
        TranslatedRANIntent.model_validate(payload)


def test_translated_intent_json_round_trip() -> None:
    original = make_translated_intent()
    restored = TranslatedRANIntent.model_validate_json(original.model_dump_json())
    assert restored == original
    assert restored.scope.cellIds == ["CELL-101"]
