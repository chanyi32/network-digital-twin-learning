"""Unified, validated provenance records for experiment cases."""

from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


ExecutionStatus = Literal["succeeded", "failed", "skipped"]


class ExperimentCaseRecord(BaseModel):
    """Schema v1.1 record shared by successful, failed, and skipped cases."""

    model_config = ConfigDict(extra="forbid")

    schemaVersion: Literal["1.1"]
    experimentId: str = Field(min_length=1)
    caseId: str = Field(min_length=1)
    runId: str = Field(min_length=1)
    experimentType: str = Field(min_length=1)
    codeVersion: str = Field(min_length=1)
    baseModelVersion: str = Field(min_length=1)
    configurationHash: str = Field(pattern=r"^[0-9a-f]{64}$")
    inputHash: str = Field(pattern=r"^[0-9a-f]{64}$")
    inputFileHashes: dict[str, str]
    randomSeed: int
    startTime: datetime
    endTime: datetime
    durationSeconds: float = Field(ge=0)
    executionStatus: ExecutionStatus
    feedbackEnabled: bool
    feedbackIterations: int = Field(ge=0)
    generationRounds: int = Field(ge=0)
    terminationReason: str | None
    runManifestPath: str | None
    resultDirectory: str
    errorType: str | None
    errorMessage: str | None
    skipReason: str | None

    # Backward-compatible fields from schema v1.0.
    description: str
    status: str
    pipelineStatus: str | None
    startedAt: datetime
    completedAt: datetime
    fixedRandomSeed: int
    scenarioId: str | None
    intentId: str | None
    simulationOverrides: dict[str, object]
    ranStateOverrides: dict[str, object]
    modelVersion: str
    coefficientVersion: str | None
    simulationConfigSha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    ranStateInputSha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    pipelineRunDirectory: str
    finalArtifact: str | None

    @field_validator(
        "runManifestPath",
        "resultDirectory",
        "pipelineRunDirectory",
        "finalArtifact",
    )
    @classmethod
    def validate_relative_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        path = PurePosixPath(value)
        if path.is_absolute() or Path(value).is_absolute():
            raise ValueError("manifest paths must be relative to the batch root")
        return value

    @field_validator("inputFileHashes")
    @classmethod
    def validate_input_file_hashes(
        cls,
        value: dict[str, str],
    ) -> dict[str, str]:
        if not value:
            raise ValueError("inputFileHashes must not be empty")
        for path, digest in value.items():
            if PurePosixPath(path).is_absolute() or Path(path).is_absolute():
                raise ValueError(
                    "inputFileHashes paths must be relative to the batch root"
                )
            if len(digest) != 64 or any(
                character not in "0123456789abcdef"
                for character in digest
            ):
                raise ValueError("inputFileHashes values must be SHA-256")
        return value

    @model_validator(mode="after")
    def validate_record_consistency(self) -> "ExperimentCaseRecord":
        if self.endTime < self.startTime:
            raise ValueError("endTime must not precede startTime")
        if not math.isclose(
            self.durationSeconds,
            (self.endTime - self.startTime).total_seconds(),
            rel_tol=0.0,
            abs_tol=0.1,
        ):
            raise ValueError("durationSeconds must match startTime/endTime")
        if self.startedAt != self.startTime or self.completedAt != self.endTime:
            raise ValueError("legacy timestamps must match v1.1 timestamps")
        if self.fixedRandomSeed != self.randomSeed:
            raise ValueError("legacy seed must match randomSeed")
        if self.modelVersion != self.baseModelVersion:
            raise ValueError("legacy modelVersion must match baseModelVersion")
        if self.executionStatus == "failed":
            if not self.errorType or not self.errorMessage:
                raise ValueError("failed cases require errorType and errorMessage")
        elif self.errorType is not None or self.errorMessage is not None:
            raise ValueError(
                "non-failed cases must not contain errorType/errorMessage"
            )
        if self.executionStatus == "skipped" and not self.skipReason:
            raise ValueError("skipped cases require skipReason")
        if self.executionStatus != "skipped" and self.skipReason is not None:
            raise ValueError("skipReason is only valid for skipped cases")
        if self.executionStatus == "succeeded" and self.runManifestPath is None:
            raise ValueError("succeeded cases require runManifestPath")
        return self

    def csv_provenance(self) -> dict[str, object]:
        """Fields embedded into every aggregate CSV row."""

        return {
            "experimentId": self.experimentId,
            "caseId": self.caseId,
            "runId": self.runId,
            "experimentType": self.experimentType,
            "executionStatus": self.executionStatus,
            "feedbackEnabled": self.feedbackEnabled,
            "feedbackIterations": self.feedbackIterations,
            "generationRounds": self.generationRounds,
            "terminationReason": self.terminationReason,
            "codeVersion": self.codeVersion,
            "baseModelVersion": self.baseModelVersion,
            "configurationHash": self.configurationHash,
            "inputHash": self.inputHash,
            "randomSeed": self.randomSeed,
            "runManifestPath": self.runManifestPath,
            "resultDirectory": self.resultDirectory,
            "errorType": self.errorType,
            "errorMessage": self.errorMessage,
            "skipReason": self.skipReason,
        }
