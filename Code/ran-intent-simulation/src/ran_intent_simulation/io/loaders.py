"""Typed loading entry points for checked-in configuration and sample data."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypeVar

import pandas as pd
import yaml
from pydantic import BaseModel, ValidationError

from ran_intent_simulation.config import (
    SimulationConfig,
    load_performance_model_config,
    load_simulation_config,
)
from ran_intent_simulation.exceptions import (
    DataFileNotFoundError,
    DataLoadingError,
    DataValidationError,
)
from ran_intent_simulation.io.validators import (
    validate_configuration_references,
    validate_ran_state_frame,
    validate_unique_field,
)
from ran_intent_simulation.models.intent import IntentSample
from ran_intent_simulation.models.policy import ActionLibrary
from ran_intent_simulation.models.translation import (
    EventRecord,
    SLATemplate,
    VenueCellMapping,
)

ModelT = TypeVar("ModelT", bound=BaseModel)


def load_json_file(path: str | Path) -> Any:
    """Decode a UTF-8 JSON file and wrap filesystem/parser errors."""

    input_path = _require_file(path)
    try:
        return json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DataLoadingError(f"Unable to read JSON data: {input_path}") from exc


def load_yaml_file(path: str | Path) -> Any:
    """Decode a UTF-8 YAML file without applying a domain schema."""

    input_path = _require_file(path)
    try:
        return yaml.safe_load(input_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise DataLoadingError(f"Unable to read YAML data: {input_path}") from exc


def load_action_library(
    path: str | Path,
    simulation_config: SimulationConfig | None = None,
) -> ActionLibrary:
    """Load an action library and optionally resolve every config reference."""

    library = _validate_model(load_json_file(path), ActionLibrary, path)
    if simulation_config is not None:
        validate_configuration_references(
            simulation_config=simulation_config,
            action_library=library,
        )
    return library


def load_sla_templates(
    path: str | Path,
    simulation_config: SimulationConfig | None = None,
) -> SLATemplate:
    """Load an SLA template and optionally resolve every threshold reference."""

    template = _validate_model(load_json_file(path), SLATemplate, path)
    if simulation_config is not None:
        validate_configuration_references(
            simulation_config=simulation_config,
            sla_template=template,
        )
    return template


def load_intent_samples(path: str | Path) -> list[IntentSample]:
    """Load intent fixtures and require unique ``intentId`` values."""

    samples = _validate_model_list(load_json_file(path), IntentSample, path)
    validate_unique_field(samples, "intentId")
    return samples


def load_event_database(path: str | Path) -> list[EventRecord]:
    """Load the static event repository."""

    records = _validate_model_list(load_json_file(path), EventRecord, path)
    validate_unique_field(records, "eventId")
    event_venue_pairs = [(record.eventType, record.venueId) for record in records]
    if len(event_venue_pairs) != len(set(event_venue_pairs)):
        raise DataValidationError(
            "eventType + venueId combinations must be unique"
        )
    return records


def load_venue_cell_mapping(path: str | Path) -> list[VenueCellMapping]:
    """Load static venue-to-RAN mappings."""

    mappings = _validate_model_list(load_json_file(path), VenueCellMapping, path)
    validate_unique_field(mappings, "venueId")
    return mappings


def load_ran_state_samples(
    path: str | Path,
    simulation_config: SimulationConfig,
) -> pd.DataFrame:
    """Load and validate user-level single-cell RAN state samples."""

    input_path = _require_file(path)
    try:
        frame = pd.read_csv(input_path)
    except (OSError, UnicodeError, pd.errors.ParserError) as exc:
        raise DataLoadingError(f"Unable to read CSV data: {input_path}") from exc
    validate_ran_state_frame(frame, simulation_config)
    return frame


def _require_file(path: str | Path) -> Path:
    input_path = Path(path)
    if not input_path.is_file():
        raise DataFileNotFoundError(f"Data file not found: {input_path}")
    return input_path


def _validate_model(
    raw_data: Any,
    model_type: type[ModelT],
    path: str | Path,
) -> ModelT:
    try:
        return model_type.model_validate(raw_data)
    except ValidationError as exc:
        raise DataValidationError(f"Invalid {model_type.__name__}: {path}") from exc


def _validate_model_list(
    raw_data: Any,
    model_type: type[ModelT],
    path: str | Path,
) -> list[ModelT]:
    if not isinstance(raw_data, list) or not raw_data:
        raise DataValidationError(f"{path} must contain a non-empty JSON array")
    try:
        return [model_type.model_validate(item) for item in raw_data]
    except ValidationError as exc:
        raise DataValidationError(
            f"Invalid {model_type.__name__} collection: {path}"
        ) from exc


__all__ = [
    "load_action_library",
    "load_event_database",
    "load_intent_samples",
    "load_json_file",
    "load_performance_model_config",
    "load_ran_state_samples",
    "load_simulation_config",
    "load_sla_templates",
    "load_venue_cell_mapping",
    "load_yaml_file",
]
