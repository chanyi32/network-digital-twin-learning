"""Tests for configuration-injected RAN-state aggregation statistics."""

from __future__ import annotations

import inspect
from copy import deepcopy
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml
from pydantic import ValidationError

import ran_intent_simulation.pipeline as pipeline_module
from ran_intent_simulation.config import (
    SimulationConfig,
    StatisticsConfig,
    load_simulation_config,
)
from ran_intent_simulation.exceptions import ConfigurationValidationError
from ran_intent_simulation.pipeline import ran_state_from_frame


def ran_state_frame() -> pd.DataFrame:
    common = {
        "scenarioId": "STATISTICS-TEST",
        "timestamp": "2026-07-29T19:30:00+08:00",
        "cellId": "CELL-101",
        "cellLoad": 0.60,
        "prbUtilization": 0.50,
        "availablePrbRatio": 0.50,
        "baselineVoiceQuality": 0.97,
        "baselineNormalUserPerformance": 1.0,
        "baselineRanEnergy": 1.0,
        "meanSinrDb": 8.0,
    }
    rows: list[dict[str, object]] = []
    for index, (throughput, delay) in enumerate(
        [(10.0, 10.0), (20.0, 20.0), (30.0, 30.0), (40.0, 40.0)],
        start=1,
    ):
        rows.append(
            common
            | {
                "userId": f"VIDEO-{index:03d}",
                "userType": "video",
                "baselineUplinkThroughputMbps": throughput,
                "baselineUplinkDelayMs": delay,
                "baselineUplinkBler": 0.02,
            }
        )
    rows.extend(
        [
            common
            | {
                "userId": "VOICE-001",
                "userType": "voice",
                "baselineUplinkThroughputMbps": None,
                "baselineUplinkDelayMs": None,
                "baselineUplinkBler": None,
            },
            common
            | {
                "userId": "NORMAL-001",
                "userType": "normal",
                "baselineUplinkThroughputMbps": None,
                "baselineUplinkDelayMs": None,
                "baselineUplinkBler": None,
            },
        ]
    )
    return pd.DataFrame(rows)


def test_default_quantiles_preserve_baseline_aggregation() -> None:
    statistics = StatisticsConfig(
        throughput_low_quantile=0.05,
        delay_high_quantile=0.95,
        quantile_method="linear",
    )

    state = ran_state_from_frame(
        ran_state_frame(),
        statistics=statistics,
    )

    assert state.videoThroughputP05Mbps == pytest.approx(11.5)
    assert state.videoDelayP95Ms == pytest.approx(38.5)
    assert state.quantileMethod == "linear"


def test_non_default_quantiles_change_aggregation_as_configured() -> None:
    default_state = ran_state_from_frame(
        ran_state_frame(),
        statistics=StatisticsConfig(
            throughput_low_quantile=0.05,
            delay_high_quantile=0.95,
            quantile_method="linear",
        ),
    )
    changed_state = ran_state_from_frame(
        ran_state_frame(),
        statistics=StatisticsConfig(
            throughput_low_quantile=0.10,
            delay_high_quantile=0.90,
            quantile_method="linear",
        ),
    )

    assert changed_state.videoThroughputP05Mbps == pytest.approx(13.0)
    assert changed_state.videoDelayP95Ms == pytest.approx(37.0)
    assert changed_state.videoThroughputP05Mbps != (
        default_state.videoThroughputP05Mbps
    )
    assert changed_state.videoDelayP95Ms != default_state.videoDelayP95Ms


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("throughput_low_quantile", -0.01),
        ("throughput_low_quantile", 1.01),
        ("delay_high_quantile", -0.01),
        ("delay_high_quantile", 1.01),
    ],
)
def test_out_of_range_quantiles_are_rejected(
    field: str,
    value: float,
) -> None:
    payload = {
        "throughput_low_quantile": 0.05,
        "delay_high_quantile": 0.95,
        "quantile_method": "linear",
    }
    payload[field] = value

    with pytest.raises(ValidationError):
        StatisticsConfig.model_validate(payload)


@pytest.mark.parametrize(
    "missing_field",
    [
        "throughput_low_quantile",
        "delay_high_quantile",
        "quantile_method",
    ],
)
def test_missing_statistics_configuration_is_rejected(
    missing_field: str,
) -> None:
    config = load_simulation_config("config/simulation_config.yaml")
    payload = deepcopy(config.model_dump())
    del payload["statistics"][missing_field]

    with pytest.raises(ValidationError):
        SimulationConfig.model_validate(payload)


def test_unsupported_quantile_method_is_rejected() -> None:
    with pytest.raises(ValidationError):
        StatisticsConfig(
            throughput_low_quantile=0.05,
            delay_high_quantile=0.95,
            quantile_method="unsupported_method",
        )


def test_configuration_loader_rejects_missing_statistics_before_run(
    tmp_path: Path,
) -> None:
    payload = yaml.safe_load(
        Path("config/simulation_config.yaml").read_text(encoding="utf-8")
    )
    del payload["statistics"]["quantile_method"]
    invalid_path = tmp_path / "missing-statistics.yaml"
    invalid_path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationValidationError):
        load_simulation_config(invalid_path)


def test_quantile_method_and_positions_are_passed_to_numpy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[float, str]] = []
    numpy_quantile = np.quantile

    def recording_quantile(
        values: np.ndarray,
        quantile: float,
        *,
        method: str,
    ) -> np.floating:
        calls.append((quantile, method))
        return numpy_quantile(values, quantile, method=method)

    monkeypatch.setattr(
        pipeline_module.np,
        "quantile",
        recording_quantile,
    )
    statistics = StatisticsConfig(
        throughput_low_quantile=0.10,
        delay_high_quantile=0.90,
        quantile_method="nearest",
    )

    state = ran_state_from_frame(
        ran_state_frame(),
        statistics=statistics,
    )

    assert calls == [(0.10, "nearest"), (0.90, "nearest")]
    assert state.quantileMethod == "nearest"


def test_aggregation_requires_statistics_without_implicit_defaults() -> None:
    parameter = inspect.signature(ran_state_from_frame).parameters[
        "statistics"
    ]

    assert parameter.default is inspect.Parameter.empty
