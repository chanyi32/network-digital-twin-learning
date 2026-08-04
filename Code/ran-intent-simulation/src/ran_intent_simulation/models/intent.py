"""Pydantic contracts for intent-extraction inputs and outputs."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import Field, field_validator

from ran_intent_simulation.models.common import (
    NonEmptyString,
    Proportion,
    StrictDomainModel,
    ensure_timezone_aware,
)


class IntentTypeName(str, Enum):
    """Intent types supported by the first-version RAN scenario."""

    SERVICE_ASSURANCE = "service_assurance"
    ENERGY_OPTIMIZATION = "energy_optimization"
    SERVICE_PROTECTION = "service_protection"


class UnresolvedSeverity(str, Enum):
    """Whether an unresolved item blocks downstream processing."""

    BLOCKING = "blocking"
    NON_BLOCKING = "non_blocking"


class IntentExtractionInput(StrictDomainModel):
    """Natural-language request passed to the extraction module."""

    intentId: NonEmptyString
    originalText: NonEmptyString
    requestTime: datetime
    context: dict[str, Any] | None = None

    @field_validator("originalText")
    @classmethod
    def validate_original_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("originalText must not be blank")
        return value

    @field_validator("requestTime")
    @classmethod
    def validate_request_time(cls, value: datetime) -> datetime:
        return ensure_timezone_aware(value)


class IntentType(StrictDomainModel):
    """Detected intent type with field-level confidence."""

    type: IntentTypeName
    confidence: Proportion


class SemanticSlot(StrictDomainModel):
    """Extracted slot retaining provenance and confidence."""

    rawText: NonEmptyString
    normalizedValue: str | None
    source: NonEmptyString
    confidence: Proportion


class ExtractedSemantics(StrictDomainModel):
    """Documented semantic slots for the concert scenario."""

    timeExpression: SemanticSlot | None = None
    locationExpression: SemanticSlot | None = None
    targetService: SemanticSlot | None = None
    targetObject: SemanticSlot | None = None
    assuranceTarget: SemanticSlot | None = None
    optimizationGoal: SemanticSlot | None = None
    protectedService: SemanticSlot | None = None
    modifier: SemanticSlot | None = None
    negation: SemanticSlot | None = None


class SemanticRelation(StrictDomainModel):
    """Semantic relation between an action and its business object."""

    relation: NonEmptyString
    object: NonEmptyString
    modifier: str | None = None
    constraintType: str | None = None


class LogicalRelations(StrictDomainModel):
    """Logical relationship among extracted intent clauses."""

    combination: NonEmptyString
    energyOptimizationType: str | None = None
    voiceProtectionType: str | None = None


class UnresolvedItem(StrictDomainModel):
    """Information that could not yet be resolved."""

    code: NonEmptyString
    severity: UnresolvedSeverity


class StructuredIntent(StrictDomainModel):
    """Stable extraction result consumed by intent translation."""

    schemaVersion: NonEmptyString
    intentId: NonEmptyString
    originalText: NonEmptyString
    intentTypes: list[IntentType] = Field(min_length=1)
    extractedSemantics: ExtractedSemantics
    semanticRelations: list[SemanticRelation]
    logicalRelations: LogicalRelations | None = None
    unresolvedItems: list[UnresolvedItem]
    extractionMethod: Literal["rule_based_v1"]


class IntentSample(IntentExtractionInput):
    """Checked-in intent sample plus expected extraction labels."""

    expectedIntentTypes: list[IntentTypeName] = Field(min_length=1)
    expectedSlots: dict[str, Any] | None = None
