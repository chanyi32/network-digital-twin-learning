"""Unit tests for typed loaders and cross-file validators."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from ran_intent_simulation.config import load_simulation_config
from ran_intent_simulation.exceptions import (
    DataValidationError,
    SingleCellValidationError,
)
from ran_intent_simulation.io.loaders import (
    load_action_library,
    load_event_database,
    load_intent_samples,
    load_ran_state_samples,
    load_sla_templates,
    load_venue_cell_mapping,
)
from ran_intent_simulation.io.validators import validate_single_cell_ids


def test_checked_in_inputs_load_and_cross_references_resolve() -> None:
    config = load_simulation_config("config/simulation_config.yaml")
    assert load_action_library("config/action_library.json", config).actions
    assert load_sla_templates("config/sla_templates.json", config).constraints
    assert load_intent_samples("data/intent_samples.json")
    assert load_event_database("data/event_database.json")
    assert load_venue_cell_mapping("data/venue_cell_mapping.json")
    assert not load_ran_state_samples("data/ran_state_samples.csv", config).empty


def test_single_cell_validator_rejects_multiple_cells() -> None:
    with pytest.raises(SingleCellValidationError):
        validate_single_cell_ids(["CELL-101", "CELL-102"])


def test_ran_state_loader_rejects_negative_energy(tmp_path: Path) -> None:
    config = load_simulation_config("config/simulation_config.yaml")
    frame = pd.read_csv("data/ran_state_samples.csv")
    frame["baselineRanEnergy"] = -1.0
    path = tmp_path / "invalid.csv"
    frame.to_csv(path, index=False)
    with pytest.raises(DataValidationError, match="baselineRanEnergy"):
        load_ran_state_samples(path, config)
