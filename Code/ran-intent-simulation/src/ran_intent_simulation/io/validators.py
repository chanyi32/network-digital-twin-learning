"""Cross-record and cross-file validation helpers."""

from __future__ import annotations

from collections.abc import Collection, Sequence
from datetime import datetime
from typing import Any

import pandas as pd
from pydantic import BaseModel

from ran_intent_simulation.config import SimulationConfig
from ran_intent_simulation.exceptions import (
    DataValidationError,
    SingleCellValidationError,
)
from ran_intent_simulation.models.common import ensure_timezone_aware
from ran_intent_simulation.models.policy import ActionLibrary
from ran_intent_simulation.models.translation import SLATemplate


RAN_STATE_REQUIRED_COLUMNS = frozenset(
    {
        "scenarioId",
        "timestamp",
        "cellId",
        "userId",
        "userType",
        "cellLoad",
        "prbUtilization",
        "availablePrbRatio",
        "baselineUplinkThroughputMbps",
        "baselineUplinkDelayMs",
        "baselineUplinkBler",
        "baselineVoiceQuality",
        "baselineNormalUserPerformance",
        "baselineRanEnergy",
        "meanSinrDb",
    }
)


def validate_single_cell_ids(cell_ids: Collection[str]) -> str:
    """Require exactly one non-empty cell ID for one simulation run."""

    if not cell_ids or any(
        not isinstance(cell_id, str) or not cell_id for cell_id in cell_ids
    ):
        raise SingleCellValidationError(
            "a simulation run must contain exactly one non-empty cellId"
        )
    unique_ids = set(cell_ids)
    if len(unique_ids) != 1:
        raise SingleCellValidationError(
            "a simulation run must contain exactly one non-empty cellId"
        )
    return next(iter(unique_ids))


def validate_unique_field(records: Sequence[BaseModel], field_name: str) -> None:
    """Require a model field to be unique across a repository."""

    values = [getattr(record, field_name) for record in records]
    if len(values) != len(set(values)):
        raise DataValidationError(f"{field_name} values must be unique")


def resolve_config_reference(
    simulation_config: SimulationConfig,
    reference: str,
) -> Any:
    """Resolve a dotted reference against the validated configuration object."""

    current: Any = simulation_config.model_dump()
    for component in reference.split("."):
        if not isinstance(current, dict) or component not in current:
            raise DataValidationError(
                f"configuration reference cannot be resolved: {reference}"
            )
        current = current[component]
    return current


def validate_configuration_references(
    *,
    simulation_config: SimulationConfig,
    action_library: ActionLibrary | None = None,
    sla_template: SLATemplate | None = None,
) -> None:
    """Resolve action and SLA references without executing business logic."""

    if action_library is not None:
        for action in action_library.actions:
            for definition in action.parameters.values():
                values = resolve_config_reference(
                    simulation_config, definition.valueSetRef
                )
                if not isinstance(values, list) or not values:
                    raise DataValidationError(
                        f"action value set must be a non-empty list: "
                        f"{definition.valueSetRef}"
                    )
    if sla_template is not None:
        for constraint in sla_template.constraints:
            threshold = resolve_config_reference(
                simulation_config, constraint.thresholdRef
            )
            if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
                raise DataValidationError(
                    f"SLA threshold must be numeric: {constraint.thresholdRef}"
                )
            if constraint.perUserThresholdRef is not None:
                per_user_threshold = resolve_config_reference(
                    simulation_config, constraint.perUserThresholdRef
                )
                if isinstance(per_user_threshold, bool) or not isinstance(
                    per_user_threshold, (int, float)
                ):
                    raise DataValidationError(
                        "per-user SLA threshold must be numeric: "
                        f"{constraint.perUserThresholdRef}"
                    )


def validate_ran_state_frame(
    frame: pd.DataFrame,
    simulation_config: SimulationConfig,
) -> None:
    """Validate the documented CSV schema and its single-cell invariants."""

    missing_columns = RAN_STATE_REQUIRED_COLUMNS.difference(frame.columns)
    if missing_columns:
        raise DataValidationError(
            f"RAN state CSV is missing columns: {sorted(missing_columns)}"
        )
    if frame.empty:
        raise DataValidationError("RAN state CSV must not be empty")
    always_required = (
        "scenarioId",
        "timestamp",
        "cellId",
        "userId",
        "userType",
        "cellLoad",
        "prbUtilization",
        "availablePrbRatio",
        "baselineVoiceQuality",
        "baselineNormalUserPerformance",
        "baselineRanEnergy",
        "meanSinrDb",
    )
    if frame[list(always_required)].isnull().any().any():
        raise DataValidationError("RAN state CSV contains a missing required value")

    validate_single_cell_ids(frame["cellId"].dropna().astype(str).tolist())

    if frame.duplicated(subset=["scenarioId", "userId"]).any():
        raise DataValidationError(
            "scenarioId + userId must be unique in RAN state CSV"
        )
    invalid_user_types = set(frame["userType"].dropna()) - {"video", "voice", "normal"}
    if invalid_user_types:
        raise DataValidationError(
            f"unsupported userType values: {sorted(invalid_user_types)}"
        )
    if not (frame["userType"] == "video").any():
        raise DataValidationError("RAN state CSV must include at least one video user")

    for raw_timestamp in frame["timestamp"]:
        try:
            timestamp = datetime.fromisoformat(str(raw_timestamp))
            ensure_timezone_aware(timestamp)
        except (TypeError, ValueError) as exc:
            raise DataValidationError(
                f"timestamp must be timezone-aware: {raw_timestamp}"
            ) from exc

    ratio_columns = (
        "cellLoad",
        "prbUtilization",
        "availablePrbRatio",
        "baselineUplinkBler",
        "baselineVoiceQuality",
        "baselineNormalUserPerformance",
    )
    _validate_numeric_ranges(frame, ratio_columns, minimum=0.0, maximum=1.0)
    _validate_numeric_ranges(
        frame,
        (
            "baselineUplinkThroughputMbps",
            "baselineUplinkDelayMs",
            "baselineRanEnergy",
        ),
        minimum=0.0,
    )
    mean_sinr = pd.to_numeric(frame["meanSinrDb"], errors="coerce")
    if mean_sinr.isna().any():
        raise DataValidationError("meanSinrDb must contain numeric values")

    video_rows = frame["userType"] == "video"
    video_required = (
        "baselineUplinkThroughputMbps",
        "baselineUplinkDelayMs",
        "baselineUplinkBler",
    )
    if frame.loc[video_rows, list(video_required)].isnull().any().any():
        raise DataValidationError(
            "video rows require throughput, delay, and BLER baseline values"
        )
    if (frame["baselineRanEnergy"] <= 0).any():
        raise DataValidationError("baselineRanEnergy must be greater than zero")

    difference = (
        frame["availablePrbRatio"] - (1.0 - frame["prbUtilization"])
    ).abs()
    tolerance = simulation_config.validation.available_prb_ratio_tolerance
    if (difference > tolerance).any():
        raise DataValidationError(
            "availablePrbRatio differs from 1-prbUtilization beyond configured "
            "tolerance"
        )

    consistency_columns = (
        "timestamp",
        "cellLoad",
        "prbUtilization",
        "availablePrbRatio",
        "baselineVoiceQuality",
        "baselineNormalUserPerformance",
        "baselineRanEnergy",
        "meanSinrDb",
    )
    grouped = frame.groupby(["scenarioId", "cellId"], dropna=False)
    for column in consistency_columns:
        if (grouped[column].nunique(dropna=False) > 1).any():
            raise DataValidationError(
                f"{column} must be consistent within scenarioId + cellId"
            )


def _validate_numeric_ranges(
    frame: pd.DataFrame,
    columns: Collection[str],
    *,
    minimum: float,
    maximum: float | None = None,
) -> None:
    for column in columns:
        numeric = pd.to_numeric(frame[column], errors="coerce")
        present = frame[column].notna()
        if numeric[present].isna().any():
            raise DataValidationError(f"{column} must contain numeric values")
        if (numeric[present] < minimum).any():
            raise DataValidationError(f"{column} contains values below {minimum}")
        if maximum is not None and (numeric[present] > maximum).any():
            raise DataValidationError(f"{column} contains values above {maximum}")
