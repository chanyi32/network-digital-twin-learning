"""Tests for static-data-backed RAN intent translation."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from ran_intent_simulation.config import load_simulation_config
from ran_intent_simulation.exceptions import DataValidationError
from ran_intent_simulation.intent import RuleBasedIntentExtractor
from ran_intent_simulation.models.intent import IntentExtractionInput
from ran_intent_simulation.models.translation import (
    ConfigurationRefs,
    IntentTranslationInput,
    TranslatedRANIntent,
)
from ran_intent_simulation.translation import (
    StaticIntentTranslator,
    StaticTranslationRepositories,
)


def configuration_refs(
    *,
    venue_mapping: str = "data/venue_cell_mapping.json",
) -> ConfigurationRefs:
    return ConfigurationRefs(
        eventDatabase="data/event_database.json",
        venueCellMapping=venue_mapping,
        slaTemplates="config/sla_templates.json",
        resourceConstraints="config/simulation_config.yaml",
    )


def structured_intent(text: str):
    config = load_simulation_config("config/simulation_config.yaml")
    extractor = RuleBasedIntentExtractor(config.intent_extraction)
    return extractor.extract(
        IntentExtractionInput(
            intentId="INTENT-CONCERT-UL-001",
            originalText=text,
            requestTime="2026-07-29T09:00:00+08:00",
        )
    )


def translate(text: str) -> TranslatedRANIntent:
    refs = configuration_refs()
    translator = StaticIntentTranslator.from_configuration_refs(refs)
    return translator.translate(
        IntentTranslationInput(
            structuredIntent=structured_intent(text),
            configurationRefs=refs,
        )
    )


def test_complete_intent_resolves_time_window_and_single_cell() -> None:
    result = translate(
        "????????????????????????"
        "?????????????????"
    )

    assert result.translationStatus == "ready"
    assert result.unresolvedItems == []
    assert result.scope is not None
    assert result.scope.effectiveTime.eventStartTime == datetime.fromisoformat(
        "2026-07-29T19:30:00+08:00"
    )
    assert result.scope.effectiveTime.eventEndTime == datetime.fromisoformat(
        "2026-07-29T22:30:00+08:00"
    )
    assert result.scope.effectiveTime.effectiveStartTime == datetime.fromisoformat(
        "2026-07-29T19:15:00+08:00"
    )
    assert result.scope.effectiveTime.effectiveEndTime == datetime.fromisoformat(
        "2026-07-29T22:45:00+08:00"
    )
    assert result.scope.cellIds == ["CELL-101"]
    assert result.scope.gnbIds == ["GNB-001"]
    assert result.scope.carrierIds == ["NR-CARRIER-01"]


def test_translation_generates_users_objectives_and_sla_constraints() -> None:
    result = translate(
        "????????????????????????"
        "?????????????????"
    )

    assert result.scope is not None
    assert [
        (rule.group, rule.serviceType)
        for rule in result.scope.targetUserRules
    ] == [
        ("video", "uplink_video"),
        ("voice", "voice_service"),
    ]
    assert [(item.name, item.priority) for item in result.ranObjectives] == [
        ("video_uplink_assurance", "primary"),
        ("ran_energy_optimization", "secondary"),
        ("voice_service_protection", "mandatory"),
    ]
    assert {constraint.metric for constraint in result.slaConstraints} == {
        "videoUserSatisfactionRatio",
        "videoDelayP95Ms",
        "voiceQualityScore",
        "voiceQualityDegradation",
        "prbUtilization",
    }
    satisfaction = next(
        constraint
        for constraint in result.slaConstraints
        if constraint.metric == "videoUserSatisfactionRatio"
    )
    assert satisfaction.perUserCondition is not None
    assert (
        satisfaction.perUserCondition.thresholdRef
        == "sla.video.throughput_threshold_mbps"
    )
    assert result.objectiveRelationship.hardConstraints == [
        "video_user_satisfaction",
        "video_delay_p95",
        "voice_quality_absolute",
        "voice_quality_degradation",
        "prb_limit",
    ]


def test_all_completed_groups_record_source() -> None:
    result = translate(
        "????????????????????????"
        "?????????????????"
    )

    assert result.scope is not None
    assert result.scope.source == "venue_cell_mapping"
    assert result.scope.effectiveTime.source == "event_database"
    assert all(rule.source for rule in result.scope.targetUserRules)
    assert all(objective.source for objective in result.ranObjectives)
    assert all(constraint.source for constraint in result.slaConstraints)
    assert result.objectiveRelationship.source


def test_missing_time_remains_blocked() -> None:
    result = translate(
        "???????????????????????"
        "??????????"
    )

    assert result.translationStatus == "blocked"
    assert result.scope is None
    unresolved = {item.code: item.severity for item in result.unresolvedItems}
    assert unresolved["exact_time_period"] == "blocking"
    assert unresolved["ran_scope"] == "blocking"


def test_event_database_can_complete_venue_scope() -> None:
    result = translate(
        "????????????????????"
        "?????????????????"
    )

    assert result.translationStatus == "ready"
    assert result.scope is not None
    assert result.scope.venueId == "STADIUM-001"
    assert result.scope.cellIds == ["CELL-101"]


def test_multi_cell_mapping_is_rejected(tmp_path: Path) -> None:
    mapping_path = tmp_path / "multi-cell-mapping.json"
    mapping_path.write_text(
        json.dumps(
            [
                {
                    "venueId": "STADIUM-001",
                    "geoFence": "POLYGON(...)",
                    "gnbIds": ["GNB-001"],
                    "cellIds": ["CELL-101", "CELL-102"],
                    "carrierIds": ["NR-CARRIER-01"],
                }
            ]
        ),
        encoding="utf-8",
    )
    refs = configuration_refs(venue_mapping=str(mapping_path))
    config = load_simulation_config(refs.resourceConstraints)

    with pytest.raises(DataValidationError):
        StaticTranslationRepositories.from_configuration_refs(refs, config)


def test_translation_json_round_trip() -> None:
    original = translate(
        "????????????????????????"
        "?????????????????"
    )
    restored = TranslatedRANIntent.model_validate_json(
        original.model_dump_json()
    )
    assert restored == original
