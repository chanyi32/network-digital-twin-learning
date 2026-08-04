"""Pydantic contracts for performance results, scoring, and feedback."""

from __future__ import annotations

import math
from enum import Enum

from pydantic import Field, model_validator

from ran_intent_simulation.models.common import (
    NonEmptyString,
    NonNegativeFloat,
    NonNegativeInt,
    Proportion,
    StrictDomainModel,
)
from ran_intent_simulation.models.policy import ActionType, CandidatePolicy
from ran_intent_simulation.models.ran_state import RANState
from ran_intent_simulation.models.translation import ConstraintOperator


class VideoUserPerformance(StrictDomainModel):
    userId: NonEmptyString
    videoUplinkThroughputMbps: NonNegativeFloat
    videoUplinkDelayMs: NonNegativeFloat
    videoUplinkBler: Proportion
    outputDiagnostics: dict[str, "ClippedValue"]


class ClippedValue(StrictDomainModel):
    """Raw and bounded representation of one model output."""

    rawValue: float
    clippedValue: float
    wasClipped: bool
    lowerBound: float
    upperBound: float

    @model_validator(mode="after")
    def validate_clipping_record(self) -> "ClippedValue":
        if self.upperBound <= self.lowerBound:
            raise ValueError("upperBound must exceed lowerBound")
        if not self.lowerBound <= self.clippedValue <= self.upperBound:
            raise ValueError("clippedValue must lie within configured bounds")
        expected = not math.isclose(
            self.rawValue,
            self.clippedValue,
            rel_tol=0.0,
            abs_tol=1e-12,
        )
        if self.wasClipped != expected:
            raise ValueError("wasClipped does not match raw and clipped values")
        return self


class MetricClippingSummary(StrictDomainModel):
    evaluationCount: NonNegativeInt
    clippedCount: NonNegativeInt
    maximumClippingMagnitude: NonNegativeFloat

    @model_validator(mode="after")
    def validate_counts(self) -> "MetricClippingSummary":
        if self.clippedCount > self.evaluationCount:
            raise ValueError("clippedCount cannot exceed evaluationCount")
        return self


class PolicyPerformanceResult(StrictDomainModel):
    policyId: NonEmptyString
    generationRound: NonNegativeInt
    cellId: NonEmptyString
    videoUsers: list[VideoUserPerformance] = Field(min_length=1)
    videoUserSatisfactionRatio: Proportion
    videoThroughputMeanMbps: NonNegativeFloat
    videoThroughputP05Mbps: NonNegativeFloat
    videoDelayMeanMs: NonNegativeFloat
    videoDelayP95Ms: NonNegativeFloat
    videoUplinkBlerMean: Proportion
    voiceQualityScore: Proportion
    voiceQualityDegradation: Proportion
    prbUtilization: Proportion
    ranEnergy: NonNegativeFloat
    normalUserPerformanceDegradation: Proportion
    riskScore: Proportion
    riskComponents: dict[str, Proportion]
    quantileMethod: NonEmptyString
    performanceModelVersion: NonEmptyString
    coefficientVersion: NonEmptyString
    randomSeed: int
    stochasticEnabled: bool
    outputDiagnostics: dict[str, ClippedValue]
    clippingSummary: dict[str, MetricClippingSummary]
    modelWarnings: list[str]

    @model_validator(mode="after")
    def validate_unique_video_users(self) -> "PolicyPerformanceResult":
        user_ids = [user.userId for user in self.videoUsers]
        if len(user_ids) != len(set(user_ids)):
            raise ValueError("videoUsers must have unique userId values")
        return self


class ConstraintCheckResult(StrictDomainModel):
    metric: NonEmptyString
    operator: ConstraintOperator
    thresholdRef: NonEmptyString
    actualValue: float
    thresholdValue: float
    passed: bool
    violation: str | None = None


class ConstraintCheck(StrictDomainModel):
    policyId: NonEmptyString
    checks: list[ConstraintCheckResult] = Field(min_length=1)
    feasible: bool

    @model_validator(mode="after")
    def validate_feasibility(self) -> "ConstraintCheck":
        if self.feasible != all(item.passed for item in self.checks):
            raise ValueError("feasible must equal the conjunction of all checks")
        return self


class PolicyScore(StrictDomainModel):
    policyId: NonEmptyString
    constraintCheck: ConstraintCheck
    feasible: bool
    performance: PolicyPerformanceResult
    normalizedMetrics: dict[str, Proportion]
    serviceScore: Proportion
    energyScore: Proportion
    resourceScore: Proportion
    riskScore: Proportion
    totalScore: Proportion
    rank: int | None = Field(default=None, ge=1)
    scoreConfigVersion: NonEmptyString

    @model_validator(mode="after")
    def validate_score_state(self) -> "PolicyScore":
        if self.policyId != self.constraintCheck.policyId:
            raise ValueError("policyId must match constraintCheck.policyId")
        if self.policyId != self.performance.policyId:
            raise ValueError("policyId must match performance.policyId")
        if self.feasible != self.constraintCheck.feasible:
            raise ValueError("feasible must match constraintCheck.feasible")
        if not self.feasible and (self.totalScore != 0 or self.rank is not None):
            raise ValueError("infeasible policy must have totalScore=0 and rank=null")
        return self


class WeakMetric(StrictDomainModel):
    metric: NonEmptyString
    thresholdRef: NonEmptyString
    gap: float


class UpdateDirection(str, Enum):
    INCREASE = "increase"
    DECREASE = "decrease"


class SuggestedParameterUpdate(StrictDomainModel):
    parameter: NonEmptyString
    direction: UpdateDirection
    method: NonEmptyString
    searchSpaceRef: NonEmptyString


class SuggestedActionChanges(StrictDomainModel):
    add: list[ActionType]
    remove: list[ActionType]


class SearchSpaceUpdate(StrictDomainModel):
    parameter: NonEmptyString
    operation: NonEmptyString
    value: float | int | str | None = None
    reason: NonEmptyString


class PolicyFeedback(StrictDomainModel):
    policyId: NonEmptyString
    generationRound: NonNegativeInt
    violations: list[NonEmptyString]
    weakMetrics: list[WeakMetric]
    suggestedParameterUpdates: list[SuggestedParameterUpdate]
    suggestedActionChanges: SuggestedActionChanges
    searchSpaceUpdates: list[SearchSpaceUpdate]
    feedbackReason: NonEmptyString


class PerformanceEvaluationInput(StrictDomainModel):
    """Interface reserved for the simplified model or a future twin adapter."""

    ranState: RANState
    candidatePolicy: CandidatePolicy
    modelConfigVersion: NonEmptyString

    @model_validator(mode="after")
    def validate_cell_scope(self) -> "PerformanceEvaluationInput":
        if self.candidatePolicy.scope.cellIds != [self.ranState.cellId]:
            raise ValueError("candidate policy and RAN state must use the same cellId")
        return self


class PerformanceEvaluationBatch(StrictDomainModel):
    """One generation round of results and aggregate clipping diagnostics."""

    generationRound: NonNegativeInt
    results: list[PolicyPerformanceResult]
    clippingSummary: dict[str, MetricClippingSummary]
    modelWarnings: list[str]
    performanceModelVersion: NonEmptyString
    coefficientVersion: NonEmptyString
    randomSeed: int
    stochasticEnabled: bool
