"""Unit tests for intent data contracts."""

from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from ran_intent_simulation.models.intent import (
    ExtractedSemantics,
    IntentExtractionInput,
    IntentType,
    LogicalRelations,
    SemanticRelation,
    SemanticSlot,
    StructuredIntent,
)


def make_structured_intent() -> StructuredIntent:
    return StructuredIntent(
        schemaVersion="1.0",
        intentId="INTENT-001",
        originalText="????????????",
        intentTypes=[{"type": "service_assurance", "confidence": 0.97}],
        extractedSemantics=ExtractedSemantics(
            targetService=SemanticSlot(
                rawText="??",
                normalizedValue="uplink_video",
                source="dictionary_normalization",
                confidence=0.95,
            )
        ),
        semanticRelations=[
            SemanticRelation(relation="assure", object="video_uplink_experience")
        ],
        logicalRelations=LogicalRelations(combination="conjunction"),
        unresolvedItems=[],
        extractionMethod="rule_based_v1",
    )


def test_intent_extraction_input_requires_timezone() -> None:
    with pytest.raises(ValidationError, match="timezone"):
        IntentExtractionInput(
            intentId="INTENT-001",
            originalText="??",
            requestTime=datetime(2026, 7, 29, 9, 0),
        )


def test_intent_confidence_is_a_proportion() -> None:
    with pytest.raises(ValidationError):
        IntentType(type="service_assurance", confidence=1.01)


def test_structured_intent_json_round_trip() -> None:
    original = make_structured_intent()
    restored = StructuredIntent.model_validate_json(original.model_dump_json())
    assert restored == original
    assert restored.model_dump()["intentId"] == "INTENT-001"
