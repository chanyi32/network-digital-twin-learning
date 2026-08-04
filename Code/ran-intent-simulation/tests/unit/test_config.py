"""Tests for YAML configuration loading and validation."""

from pathlib import Path

import pytest

from ran_intent_simulation.config import (
    load_performance_model_config,
    load_simulation_config,
)
from ran_intent_simulation.exceptions import (
    ConfigurationFileNotFoundError,
    ConfigurationValidationError,
)


def test_load_project_configuration() -> None:
    """The checked-in default configuration is valid."""

    config = load_simulation_config(Path("config/simulation_config.yaml"))

    assert config.schema_version == "1.1"
    assert config.parameter_nature == "simulation_assumption"
    assert config.optimization.allow_relax_hard_constraints is False
    assert config.optimization.feedback_enabled is True


def test_feedback_enabled_defaults_to_true_when_omitted(
    tmp_path: Path,
) -> None:
    source = Path("config/simulation_config.yaml").read_text(
        encoding="utf-8"
    )
    path = tmp_path / "legacy-config.yaml"
    path.write_text(
        source.replace("  feedback_enabled: true\n", ""),
        encoding="utf-8",
    )

    config = load_simulation_config(path)

    assert config.optimization.feedback_enabled is True


def test_missing_configuration_raises_project_exception(tmp_path: Path) -> None:
    """A missing YAML file raises a specific configuration error."""

    with pytest.raises(ConfigurationFileNotFoundError):
        load_simulation_config(tmp_path / "missing.yaml")


def test_invalid_weight_sum_is_rejected(tmp_path: Path) -> None:
    """Scoring weights must remain normalized."""

    source = Path("config/simulation_config.yaml").read_text(encoding="utf-8")
    invalid = source.replace("service: 0.60", "service: 0.50")
    path = tmp_path / "invalid.yaml"
    path.write_text(invalid, encoding="utf-8")

    with pytest.raises(ConfigurationValidationError):
        load_simulation_config(path)


def test_performance_coefficients_are_required(tmp_path: Path) -> None:
    """No code-level default may silently supply performance coefficients."""

    source = Path("config/performance_model_v1.yaml").read_text(encoding="utf-8")
    invalid = source.replace("      alpha_r: 1.50\n", "")
    path = tmp_path / "missing-coefficients.yaml"
    path.write_text(invalid, encoding="utf-8")

    with pytest.raises(ConfigurationValidationError):
        load_performance_model_config(path)


def test_load_performance_model_configuration() -> None:
    model_file = load_performance_model_config(
        "config/performance_model_v1.yaml"
    )

    assert model_file.parameter_nature == "simulation_assumption"
    assert (
        model_file.performance_model.model_version == "simplified-ran-v1"
    )
    assert len(
        model_file.performance_model.monotonicity_validation_scenarios
    ) == 3
