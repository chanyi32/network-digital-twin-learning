"""Shared Pydantic primitives for RAN-only domain models."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class StrictDomainModel(BaseModel):
    """Reject unknown fields and validate subsequent assignments."""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        use_enum_values=True,
        allow_inf_nan=False,
    )


Proportion = Annotated[float, Field(ge=0.0, le=1.0)]
NonNegativeFloat = Annotated[float, Field(ge=0.0)]
PositiveFloat = Annotated[float, Field(gt=0.0)]
NonNegativeInt = Annotated[int, Field(ge=0)]
NonEmptyString = Annotated[str, Field(min_length=1)]


def ensure_timezone_aware(value: datetime) -> datetime:
    """Return a datetime only when it carries a usable UTC offset."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must include timezone information")
    return value
