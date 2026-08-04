"""Fixed-bound metric normalization used by policy scoring."""

from __future__ import annotations

import math
from typing import Literal

from ran_intent_simulation.config import ScoringNormalizationBound
from ran_intent_simulation.exceptions import NormalizationError


NormalizationDirection = Literal["gain", "cost"]


def normalize_metric(
    value: float,
    bounds: ScoringNormalizationBound,
    *,
    direction: NormalizationDirection,
) -> float:
    """Normalize a finite value to ``[0, 1]`` using fixed configured bounds."""

    numeric_value = float(value)
    lower = float(bounds.minimum)
    upper = float(bounds.maximum)
    if not all(math.isfinite(item) for item in (numeric_value, lower, upper)):
        raise NormalizationError("normalization value and bounds must be finite")
    if upper <= lower:
        raise NormalizationError(
            "normalization maximum must be greater than minimum"
        )

    gain = (numeric_value - lower) / (upper - lower)
    clipped_gain = min(1.0, max(0.0, gain))
    if direction == "gain":
        return clipped_gain
    if direction == "cost":
        return 1.0 - clipped_gain
    raise NormalizationError(f"unsupported normalization direction: {direction}")


def normalize_gain(
    value: float,
    bounds: ScoringNormalizationBound,
) -> float:
    """Return higher-is-better normalized utility."""

    return normalize_metric(value, bounds, direction="gain")


def normalize_cost(
    value: float,
    bounds: ScoringNormalizationBound,
) -> float:
    """Return lower-is-better normalized utility."""

    return normalize_metric(value, bounds, direction="cost")
