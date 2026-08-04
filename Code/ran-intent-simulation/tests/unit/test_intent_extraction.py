"""Tests for the deterministic first-version intent extractor."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ran_intent_simulation.config import load_simulation_config
from ran_intent_simulation.exceptions import UnsupportedIntentError
from ran_intent_simulation.intent.base import IntentExtractor
from ran_intent_simulation.intent.rule_based import RuleBasedIntentExtractor
from ran_intent_simulation.models.intent import (
    IntentExtractionInput,
    StructuredIntent,
)


@pytest.fixture
def extractor() -> RuleBasedIntentExtractor:
    config = load_simulation_config("config/simulation_config.yaml")
    return RuleBasedIntentExtractor(config.intent_extraction)


def make_input(text: str) -> IntentExtractionInput:
    return IntentExtractionInput(
        intentId="INTENT-CONCERT-UL-001",
        originalText=text,
        requestTime="2026-07-29T09:00:00+08:00",
    )


def unresolved_codes(result: StructuredIntent) -> set[str]:
    return {item.code for item in result.unresolvedItems}


def intent_type_names(result: StructuredIntent) -> list[str]:
    return [intent_type.type for intent_type in result.intentTypes]


def test_complete_concert_intent(extractor: RuleBasedIntentExtractor) -> None:
    request = make_input(
        "????????????????????????"
        "?????????????????"
    )

    result = extractor.extract(request)

    assert isinstance(extractor, IntentExtractor)
    assert intent_type_names(result) == [
        "service_assurance",
        "energy_optimization",
        "service_protection",
    ]
    semantics = result.extractedSemantics
    assert semantics.timeExpression is not None
    assert semantics.timeExpression.rawText == "???????"
    assert semantics.timeExpression.normalizedValue is None
    assert semantics.timeExpression.source == "explicit_text"
    assert semantics.timeExpression.confidence == 0.99
    assert semantics.locationExpression is not None
    assert semantics.locationExpression.normalizedValue == "stadium"
    assert semantics.targetService is not None
    assert semantics.targetService.normalizedValue == "uplink_video"
    assert semantics.assuranceTarget is not None
    assert semantics.assuranceTarget.normalizedValue == "uplink_experience"
    assert semantics.optimizationGoal is not None
    assert semantics.optimizationGoal.normalizedValue == "minimize_ran_energy"
    assert semantics.protectedService is not None
    assert semantics.protectedService.normalizedValue == "voice_service"
    assert semantics.modifier is not None
    assert semantics.modifier.normalizedValue == "best_effort"
    assert semantics.negation is not None
    assert semantics.negation.normalizedValue == "non_degradation"
    extracted_slots = [
        semantics.timeExpression,
        semantics.locationExpression,
        semantics.targetObject,
        semantics.targetService,
        semantics.assuranceTarget,
        semantics.optimizationGoal,
        semantics.protectedService,
        semantics.modifier,
        semantics.negation,
    ]
    assert all(
        slot is not None
        and slot.rawText
        and slot.source
        and 0 <= slot.confidence <= 1
        for slot in extracted_slots
    )
    assert result.logicalRelations is not None
    assert result.logicalRelations.combination == "conjunction"
    assert result.logicalRelations.energyOptimizationType == "soft_objective"
    assert result.logicalRelations.voiceProtectionType == "hard_constraint"
    assert {relation.relation for relation in result.semanticRelations} == {
        "assure",
        "minimize",
        "protect",
        "temporal_scope",
        "spatial_scope",
    }
    assert unresolved_codes(result) == {
        "exact_time_period",
        "ran_scope",
        "uplink_experience_slo",
        "voice_protection_threshold",
        "objective_weights",
    }

    restored = StructuredIntent.model_validate_json(result.model_dump_json())
    assert restored == result


def test_missing_time_is_reported(
    extractor: RuleBasedIntentExtractor,
) -> None:
    result = extractor.extract(
        make_input(
            "???????????????????????"
            "??????????"
        )
    )

    assert result.extractedSemantics.timeExpression is None
    assert "exact_time_period" in unresolved_codes(result)


def test_missing_location_is_reported(
    extractor: RuleBasedIntentExtractor,
) -> None:
    result = extractor.extract(
        make_input(
            "????????????????????"
            "?????????????????"
        )
    )

    assert result.extractedSemantics.locationExpression is None
    assert "ran_scope" in unresolved_codes(result)
    assert not any(
        relation.relation == "spatial_scope"
        for relation in result.semanticRelations
    )


def test_intent_without_energy_goal(
    extractor: RuleBasedIntentExtractor,
) -> None:
    result = extractor.extract(
        make_input(
            "????????????????????????"
            "??????????"
        )
    )

    assert intent_type_names(result) == [
        "service_assurance",
        "service_protection",
    ]
    assert result.extractedSemantics.optimizationGoal is None
    assert result.logicalRelations is not None
    assert result.logicalRelations.energyOptimizationType is None
    assert not any(
        relation.relation == "minimize" for relation in result.semanticRelations
    )


def test_intent_without_voice_protection(
    extractor: RuleBasedIntentExtractor,
) -> None:
    result = extractor.extract(
        make_input(
            "????????????????????????"
            "???????"
        )
    )

    assert intent_type_names(result) == [
        "service_assurance",
        "energy_optimization",
    ]
    assert result.extractedSemantics.protectedService is None
    assert result.logicalRelations is not None
    assert result.logicalRelations.voiceProtectionType is None
    assert "voice_protection_threshold" not in unresolved_codes(result)


@pytest.mark.parametrize("text", ["", "   "])
def test_empty_text_is_rejected(text: str) -> None:
    with pytest.raises(ValidationError):
        make_input(text)


def test_unsupported_intent_text_is_rejected(
    extractor: RuleBasedIntentExtractor,
) -> None:
    with pytest.raises(UnsupportedIntentError, match="no supported RAN intent"):
        extractor.extract(make_input("?????????"))
