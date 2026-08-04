"""Pydantic contracts for RAN intent translation and static repositories."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import Field, field_validator, model_validator

from ran_intent_simulation.models.common import (
    NonEmptyString,
    Proportion,
    StrictDomainModel,
    ensure_timezone_aware,
)
from ran_intent_simulation.models.intent import StructuredIntent, UnresolvedItem


class ConstraintOperator(str, Enum):
    """Supported comparison operators for SLA constraints."""

    GREATER_THAN_OR_EQUAL = ">="
    LESS_THAN_OR_EQUAL = "<="
    GREATER_THAN = ">"
    LESS_THAN = "<"
    EQUAL = "=="


class TranslationStatus(str, Enum):
    READY = "ready"
    BLOCKED = "blocked"


class ObjectivePriority(str, Enum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    MANDATORY = "mandatory"


class ConfigurationRefs(StrictDomainModel):
    """Static data sources used by the translation module."""

    eventDatabase: NonEmptyString
    venueCellMapping: NonEmptyString
    slaTemplates: NonEmptyString
    resourceConstraints: NonEmptyString


class IntentTranslationInput(StrictDomainModel):
    """Structured intent plus its external configuration references."""

    structuredIntent: StructuredIntent
    configurationRefs: ConfigurationRefs


class EffectiveTime(StrictDomainModel):
    """Event and effective policy window with explicit provenance."""

    eventStartTime: datetime
    eventEndTime: datetime
    effectiveStartTime: datetime
    effectiveEndTime: datetime
    preWindowRef: NonEmptyString
    postWindowRef: NonEmptyString
    source: NonEmptyString
    confidence: Proportion | None = None

    @field_validator(
        "eventStartTime",
        "eventEndTime",
        "effectiveStartTime",
        "effectiveEndTime",
    )
    @classmethod
    def validate_aware_time(cls, value: datetime) -> datetime:
        return ensure_timezone_aware(value)

    @model_validator(mode="after")
    def validate_time_order(self) -> "EffectiveTime":
        if self.eventEndTime <= self.eventStartTime:
            raise ValueError("eventEndTime must be later than eventStartTime")
        if self.effectiveEndTime <= self.effectiveStartTime:
            raise ValueError("effectiveEndTime must be later than effectiveStartTime")
        if self.effectiveStartTime > self.eventStartTime:
            raise ValueError("effectiveStartTime cannot be later than eventStartTime")
        if self.effectiveEndTime < self.eventEndTime:
            raise ValueError("effectiveEndTime cannot be earlier than eventEndTime")
        return self


class TargetUserRule(StrictDomainModel):
    group: NonEmptyString
    serviceType: NonEmptyString
    source: NonEmptyString


class RANScope(StrictDomainModel):
    """Single-cell RAN scope produced by translation."""

    effectiveTime: EffectiveTime
    venueId: NonEmptyString
    gnbIds: list[NonEmptyString] = Field(min_length=1)
    cellIds: list[NonEmptyString] = Field(min_length=1, max_length=1)
    carrierIds: list[NonEmptyString] = Field(min_length=1)
    targetUserRules: list[TargetUserRule] = Field(min_length=1)
    source: NonEmptyString

    @field_validator("gnbIds", "cellIds", "carrierIds")
    @classmethod
    def validate_unique_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("identifier arrays must not contain duplicates")
        return value


class RANObjective(StrictDomainModel):
    name: NonEmptyString
    priority: ObjectivePriority
    source: NonEmptyString


class PerUserCondition(StrictDomainModel):
    metric: NonEmptyString
    operator: ConstraintOperator
    thresholdRef: NonEmptyString


class SLAConstraint(StrictDomainModel):
    metric: NonEmptyString
    operator: ConstraintOperator
    thresholdRef: NonEmptyString
    perUserCondition: PerUserCondition | None = None
    source: NonEmptyString


class ObjectiveRelationship(StrictDomainModel):
    hardConstraints: list[NonEmptyString] = Field(min_length=1)
    primaryObjective: NonEmptyString
    secondaryObjectives: list[NonEmptyString]
    source: NonEmptyString


class TranslatedRANIntent(StrictDomainModel):
    """RAN-only requirements consumed by policy generation."""

    schemaVersion: NonEmptyString
    intentId: NonEmptyString
    scope: RANScope | None
    ranObjectives: list[RANObjective] = Field(min_length=1)
    slaConstraints: list[SLAConstraint] = Field(min_length=1)
    objectiveRelationship: ObjectiveRelationship
    unresolvedItems: list[UnresolvedItem]
    translationStatus: TranslationStatus

    @model_validator(mode="after")
    def validate_status_and_unresolved_items(self) -> "TranslatedRANIntent":
        has_blocking = any(item.severity == "blocking" for item in self.unresolvedItems)
        if self.translationStatus == "ready" and has_blocking:
            raise ValueError("ready translation cannot contain blocking unresolved items")
        if self.translationStatus == "ready" and self.scope is None:
            raise ValueError("ready translation requires a resolved single-cell scope")
        if self.translationStatus == "blocked" and not has_blocking:
            raise ValueError("blocked translation must contain a blocking unresolved item")
        return self


class EventRecord(StrictDomainModel):
    """Static event database record."""

    eventId: NonEmptyString
    eventType: NonEmptyString
    venueId: NonEmptyString
    startTime: datetime
    endTime: datetime

    @field_validator("startTime", "endTime")
    @classmethod
    def validate_aware_time(cls, value: datetime) -> datetime:
        return ensure_timezone_aware(value)

    @model_validator(mode="after")
    def validate_time_order(self) -> "EventRecord":
        if self.endTime <= self.startTime:
            raise ValueError("endTime must be later than startTime")
        return self


class VenueCellMapping(StrictDomainModel):
    """Static venue-to-single-cell RAN mapping."""

    venueId: NonEmptyString
    geoFence: NonEmptyString
    gnbIds: list[NonEmptyString] = Field(min_length=1)
    cellIds: list[NonEmptyString] = Field(min_length=1, max_length=1)
    carrierIds: list[NonEmptyString] = Field(min_length=1)

    @field_validator("gnbIds", "cellIds", "carrierIds")
    @classmethod
    def validate_unique_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("identifier arrays must not contain duplicates")
        return value


class SLATemplateConstraint(StrictDomainModel):
    metric: NonEmptyString
    operator: ConstraintOperator
    thresholdRef: NonEmptyString
    perUserMetric: str | None = None
    perUserThresholdRef: str | None = None

    @model_validator(mode="after")
    def validate_per_user_pair(self) -> "SLATemplateConstraint":
        if (self.perUserMetric is None) != (self.perUserThresholdRef is None):
            raise ValueError(
                "perUserMetric and perUserThresholdRef must be provided together"
            )
        return self


class SLATemplate(StrictDomainModel):
    templateVersion: NonEmptyString
    scenario: NonEmptyString
    constraints: list[SLATemplateConstraint] = Field(min_length=1)
    parameterNature: Literal["simulation_assumption"]
