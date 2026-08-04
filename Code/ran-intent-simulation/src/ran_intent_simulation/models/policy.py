"""Pydantic contracts for action libraries and candidate policies."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import Field, field_validator, model_validator

from ran_intent_simulation.models.common import (
    NonEmptyString,
    NonNegativeInt,
    StrictDomainModel,
    ensure_timezone_aware,
)
from ran_intent_simulation.models.translation import ConstraintOperator


ParameterValue = float | int | str


class ActionType(str, Enum):
    UL_RESOURCE_RESERVE = "UL_RESOURCE_RESERVE"
    SCHEDULING_WEIGHT_ADJUST = "SCHEDULING_WEIGHT_ADJUST"
    VOICE_RESOURCE_PROTECT = "VOICE_RESOURCE_PROTECT"
    RAN_ENERGY_SAVING = "RAN_ENERGY_SAVING"


class PolicyStatus(str, Enum):
    PENDING_EVALUATION = "pending_evaluation"
    EVALUATED = "evaluated"
    FEASIBLE = "feasible"
    INFEASIBLE = "infeasible"
    REJECTED = "rejected"


class PolicyScope(StrictDomainModel):
    startTime: datetime
    endTime: datetime
    cellIds: list[NonEmptyString] = Field(min_length=1, max_length=1)
    targetUserGroups: list[NonEmptyString] = Field(min_length=1)

    @field_validator("startTime", "endTime")
    @classmethod
    def validate_aware_time(cls, value: datetime) -> datetime:
        return ensure_timezone_aware(value)

    @model_validator(mode="after")
    def validate_scope(self) -> "PolicyScope":
        if self.endTime <= self.startTime:
            raise ValueError("endTime must be later than startTime")
        if len(self.targetUserGroups) != len(set(self.targetUserGroups)):
            raise ValueError("targetUserGroups must not contain duplicates")
        return self


class PolicyAction(StrictDomainModel):
    type: ActionType
    target: NonEmptyString
    parameters: dict[str, ParameterValue]

    @model_validator(mode="after")
    def validate_action_parameters(self) -> "PolicyAction":
        expected_parameter = {
            ActionType.UL_RESOURCE_RESERVE.value: "reservedPrbRatio",
            ActionType.SCHEDULING_WEIGHT_ADJUST.value: "videoSchedulingWeight",
            ActionType.VOICE_RESOURCE_PROTECT.value: "minimumVoicePrbRatio",
            ActionType.RAN_ENERGY_SAVING.value: "energySavingIntensity",
        }[self.type]
        if set(self.parameters) != {expected_parameter}:
            raise ValueError(
                f"{self.type} requires only parameter {expected_parameter}"
            )
        value = self.parameters[expected_parameter]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{expected_parameter} must be numeric")
        if expected_parameter == "videoSchedulingWeight":
            if value < 0:
                raise ValueError("videoSchedulingWeight must not be negative")
        elif not 0 <= value <= 1:
            raise ValueError(f"{expected_parameter} must be within [0, 1]")
        return self


class Constraint(StrictDomainModel):
    metric: NonEmptyString
    operator: ConstraintOperator
    thresholdRef: NonEmptyString


class CandidatePolicy(StrictDomainModel):
    policyId: NonEmptyString
    intentId: NonEmptyString
    scope: PolicyScope
    actions: list[PolicyAction]
    parameters: dict[str, ParameterValue]
    objectives: list[NonEmptyString] = Field(min_length=1)
    hardConstraints: list[Constraint] = Field(min_length=1)
    triggerConditions: list[NonEmptyString]
    rollbackConditions: list[NonEmptyString]
    generationRound: NonNegativeInt
    status: PolicyStatus
    parentPolicyId: str | None
    generationReason: NonEmptyString
    configVersion: NonEmptyString

    @model_validator(mode="after")
    def validate_actions_and_parameters(self) -> "CandidatePolicy":
        action_types = [action.type for action in self.actions]
        if len(action_types) != len(set(action_types)):
            raise ValueError("a policy cannot contain duplicate action types")
        flattened = {
            key: value
            for action in self.actions
            for key, value in action.parameters.items()
        }
        if self.parameters != flattened:
            raise ValueError("parameters must equal the flattened action parameters")
        return self


class ActionParameterDefinition(StrictDomainModel):
    valueSetRef: NonEmptyString


class ActionDefinition(StrictDomainModel):
    type: ActionType
    targetType: NonEmptyString
    isHighCostAction: bool
    parameters: dict[str, ActionParameterDefinition]
    conflicts: list[NonEmptyString] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_parameter_count(self) -> "ActionDefinition":
        if len(self.parameters) != 1:
            raise ValueError("first-version action definitions require one parameter")
        return self


class ActionLibrary(StrictDomainModel):
    version: NonEmptyString
    scope: Literal["single_cell_ran_only"]
    actions: list[ActionDefinition] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_actions(self) -> "ActionLibrary":
        action_types = [action.type for action in self.actions]
        if len(action_types) != len(set(action_types)):
            raise ValueError("action names must be unique")
        return self


class PolicyGenerationResult(StrictDomainModel):
    """Candidate collection plus deterministic generation diagnostics."""

    policies: list[CandidatePolicy]
    generatedCount: NonNegativeInt
    filteredCount: NonNegativeInt
    filteredReasonCounts: dict[str, NonNegativeInt]
    retainedCount: NonNegativeInt
    generationRound: NonNegativeInt

    @model_validator(mode="after")
    def validate_counts(self) -> "PolicyGenerationResult":
        if self.retainedCount != len(self.policies):
            raise ValueError("retainedCount must equal the policy list length")
        if self.generatedCount != self.filteredCount + self.retainedCount:
            raise ValueError(
                "generatedCount must equal filteredCount + retainedCount"
            )
        if self.filteredCount != sum(self.filteredReasonCounts.values()):
            raise ValueError(
                "filteredCount must equal the sum of filteredReasonCounts"
            )
        return self
