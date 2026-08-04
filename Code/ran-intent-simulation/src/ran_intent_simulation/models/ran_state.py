"""Validated single-cell RAN state models."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator, model_validator

from ran_intent_simulation.models.common import (
    NonEmptyString,
    NonNegativeFloat,
    NonNegativeInt,
    PositiveFloat,
    Proportion,
    StrictDomainModel,
    ensure_timezone_aware,
)


class VideoUserState(StrictDomainModel):
    """Per-user video baseline needed for user-level SLA statistics."""

    userId: NonEmptyString
    baselineUplinkThroughputMbps: NonNegativeFloat
    baselineUplinkDelayMs: NonNegativeFloat
    baselineUplinkBler: Proportion
    meanSinrDb: float


class RANState(StrictDomainModel):
    """One fixed state snapshot for exactly one RAN cell."""

    timestamp: datetime
    cellId: NonEmptyString
    cellLoad: Proportion
    prbUtilization: Proportion
    availablePrbRatio: Proportion
    videoUserCount: NonNegativeInt
    voiceUserCount: NonNegativeInt
    normalUserCount: NonNegativeInt
    videoUsers: list[VideoUserState] = Field(min_length=1)
    videoThroughputMeanMbps: NonNegativeFloat
    videoThroughputP05Mbps: NonNegativeFloat
    videoDelayMeanMs: NonNegativeFloat
    videoDelayP95Ms: NonNegativeFloat
    videoUplinkBlerMean: Proportion
    voiceQualityScore: Proportion
    baselineRanEnergy: PositiveFloat
    meanSinrDb: float
    normalUserPerformanceIndex: Proportion
    quantileMethod: NonEmptyString

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, value: datetime) -> datetime:
        return ensure_timezone_aware(value)

    @model_validator(mode="after")
    def validate_video_users(self) -> "RANState":
        if len(self.videoUsers) != self.videoUserCount:
            raise ValueError("videoUsers length must equal videoUserCount")
        user_ids = [user.userId for user in self.videoUsers]
        if len(user_ids) != len(set(user_ids)):
            raise ValueError("videoUsers must have unique userId values")
        return self
