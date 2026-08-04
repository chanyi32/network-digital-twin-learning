"""Validated YAML schema for experiment batches."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


ExperimentName = Literal[
    "baseline_e2e",
    "load_sweep",
    "feedback_compare",
    "weight_sensitivity",
]
Scalar = str | int | float | bool | None


class StrictExperimentModel(BaseModel):
    """Forbid silent experiment-config typos."""

    model_config = ConfigDict(extra="forbid")


class ExperimentInputs(StrictExperimentModel):
    """Repository-relative inputs consumed by the frozen pipeline."""

    simulation_config: str = "config/simulation_config.yaml"
    action_library: str = "config/action_library.json"
    sla_templates: str = "config/sla_templates.json"
    intent_samples: str = "data/intent_samples.json"
    event_database: str = "data/event_database.json"
    venue_cell_mapping: str = "data/venue_cell_mapping.json"
    ran_state_samples: str = "data/ran_state_samples.csv"


class ExperimentCase(StrictExperimentModel):
    """One deterministic case in an experiment batch."""

    case_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    description: str = Field(min_length=1)
    intent_id: str | None = None
    scenario_id: str | None = "SCENARIO-HIGH-LOAD"
    simulation_overrides: dict[str, Scalar] = Field(default_factory=dict)
    ran_state_overrides: dict[str, Scalar] = Field(default_factory=dict)
    skip: bool = False
    skip_reason: str | None = None

    @model_validator(mode="after")
    def validate_skip_reason(self) -> "ExperimentCase":
        if self.skip and not self.skip_reason:
            raise ValueError("skipped cases require skip_reason")
        if not self.skip and self.skip_reason is not None:
            raise ValueError("skip_reason requires skip=true")
        return self


class ExperimentConfig(StrictExperimentModel):
    """Top-level experiment definition loaded from YAML."""

    schema_version: Literal["1.0", "1.1"]
    experiment_name: ExperimentName
    description: str = Field(min_length=1)
    fixed_random_seed: int
    output_root: str = "results/experiments"
    inputs: ExperimentInputs = Field(default_factory=ExperimentInputs)
    cases: list[ExperimentCase] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_cases(self) -> "ExperimentConfig":
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("case_id values must be unique within one batch")
        return self


def load_experiment_config(path: str | Path) -> ExperimentConfig:
    """Load and validate one YAML experiment definition."""

    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as stream:
        payload = yaml.safe_load(stream)
    if not isinstance(payload, dict):
        raise ValueError("experiment YAML root must be an object")
    return ExperimentConfig.model_validate(payload)
