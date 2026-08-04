"""Tests for the configured simplified RAN performance evaluator."""

from __future__ import annotations

import itertools
import math
from datetime import timedelta

import pytest

from ran_intent_simulation.config import (
    PerformanceModelFile,
    SimulationConfig,
    load_performance_model_config,
    load_simulation_config,
)
from ran_intent_simulation.exceptions import MonotonicityViolationError
from ran_intent_simulation.io import load_action_library
from ran_intent_simulation.models.evaluation import (
    PerformanceEvaluationBatch,
    PerformanceEvaluationInput,
)
from ran_intent_simulation.models.policy import (
    ActionLibrary,
    CandidatePolicy,
    PolicyAction,
)
from ran_intent_simulation.models.ran_state import RANState
from ran_intent_simulation.performance import (
    SimplifiedRANPerformanceEvaluator,
)


@pytest.fixture(scope="module")
def simulation_config() -> SimulationConfig:
    return load_simulation_config("config/simulation_config.yaml")


@pytest.fixture(scope="module")
def model_file() -> PerformanceModelFile:
    return load_performance_model_config("config/performance_model_v1.yaml")


@pytest.fixture(scope="module")
def action_library(
    simulation_config: SimulationConfig,
) -> ActionLibrary:
    return load_action_library(
        "config/action_library.json", simulation_config
    )


@pytest.fixture(scope="module")
def evaluator(
    simulation_config: SimulationConfig,
    action_library: ActionLibrary,
) -> SimplifiedRANPerformanceEvaluator:
    return SimplifiedRANPerformanceEvaluator.from_project_config(
        simulation_config, action_library
    )


@pytest.fixture(scope="module")
def validation_states(
    simulation_config: SimulationConfig,
    model_file: PerformanceModelFile,
) -> list[RANState]:
    return [
        scenario.to_ran_state(
            simulation_config.statistics.quantile_method
        )
        for scenario in (
            model_file.performance_model.monotonicity_validation_scenarios
        )
    ]


def make_policy(
    state: RANState,
    *,
    policy_id: str,
    r: float | None = None,
    w: float | None = None,
    v: float | None = None,
    e: float | None = None,
) -> CandidatePolicy:
    actions: list[PolicyAction] = []
    parameters: dict[str, float] = {}
    if r is not None:
        actions.append(
            PolicyAction(
                type="UL_RESOURCE_RESERVE",
                target="video",
                parameters={"reservedPrbRatio": r},
            )
        )
        parameters["reservedPrbRatio"] = r
    if w is not None:
        actions.append(
            PolicyAction(
                type="SCHEDULING_WEIGHT_ADJUST",
                target="video",
                parameters={"videoSchedulingWeight": w},
            )
        )
        parameters["videoSchedulingWeight"] = w
    if v is not None:
        actions.append(
            PolicyAction(
                type="VOICE_RESOURCE_PROTECT",
                target="voice",
                parameters={"minimumVoicePrbRatio": v},
            )
        )
        parameters["minimumVoicePrbRatio"] = v
    if e is not None:
        actions.append(
            PolicyAction(
                type="RAN_ENERGY_SAVING",
                target=state.cellId,
                parameters={"energySavingIntensity": e},
            )
        )
        parameters["energySavingIntensity"] = e
    return CandidatePolicy(
        policyId=policy_id,
        intentId="INTENT-PERFORMANCE-TEST",
        scope={
            "startTime": state.timestamp,
            "endTime": state.timestamp + timedelta(hours=1),
            "cellIds": [state.cellId],
            "targetUserGroups": ["video", "voice"],
        },
        actions=actions,
        parameters=parameters,
        objectives=["video_uplink_assurance"],
        hardConstraints=[
            {
                "metric": "prbUtilization",
                "operator": "<=",
                "thresholdRef": "resources.maximum_prb_utilization",
            }
        ],
        triggerConditions=["effective_time_reached"],
        rollbackConditions=["effective_time_ended"],
        generationRound=0,
        status="pending_evaluation",
        parentPolicyId=None,
        generationReason="performance_model_test",
        configVersion="1.1",
    )


def evaluate(
    evaluator: SimplifiedRANPerformanceEvaluator,
    model_file: PerformanceModelFile,
    state: RANState,
    policy: CandidatePolicy,
):
    return evaluator.evaluate(
        PerformanceEvaluationInput(
            ranState=state,
            candidatePolicy=policy,
            modelConfigVersion=(
                model_file.performance_model.coefficient_version
            ),
        )
    )


def test_baseline_policy_has_no_additional_effect(
    evaluator: SimplifiedRANPerformanceEvaluator,
    model_file: PerformanceModelFile,
    validation_states: list[RANState],
) -> None:
    for index, state in enumerate(validation_states):
        result = evaluate(
            evaluator,
            model_file,
            state,
            make_policy(state, policy_id=f"BASELINE-{index}"),
        )

        assert result.prbUtilization == pytest.approx(
            state.prbUtilization
        )
        assert result.voiceQualityScore == pytest.approx(
            state.voiceQualityScore
        )
        assert result.ranEnergy == pytest.approx(state.baselineRanEnergy)
        assert result.normalUserPerformanceDegradation == pytest.approx(0)
        for user_before, user_after in zip(
            state.videoUsers, result.videoUsers, strict=True
        ):
            assert user_after.videoUplinkThroughputMbps == pytest.approx(
                user_before.baselineUplinkThroughputMbps
            )
            assert user_after.videoUplinkDelayMs == pytest.approx(
                user_before.baselineUplinkDelayMs
            )
            assert user_after.videoUplinkBler == pytest.approx(
                user_before.baselineUplinkBler
            )


def test_no_random_mode_is_reproducible_and_traceable(
    evaluator: SimplifiedRANPerformanceEvaluator,
    model_file: PerformanceModelFile,
    simulation_config: SimulationConfig,
    validation_states: list[RANState],
) -> None:
    state = validation_states[1]
    policy = make_policy(
        state,
        policy_id="DETERMINISTIC",
        r=0.20,
        w=1.50,
        v=0.10,
        e=0.05,
    )

    first = evaluate(evaluator, model_file, state, policy)
    second = evaluate(evaluator, model_file, state, policy)

    assert first.model_dump_json() == second.model_dump_json()
    assert first.randomSeed == simulation_config.reproducibility.random_seed
    assert first.stochasticEnabled is False
    assert model_file.performance_model.stochastic_enabled is False


def test_all_discrete_action_combinations_are_finite_and_bounded(
    evaluator: SimplifiedRANPerformanceEvaluator,
    model_file: PerformanceModelFile,
    simulation_config: SimulationConfig,
    validation_states: list[RANState],
) -> None:
    combination_count = 0
    for state_index, state in enumerate(validation_states):
        for combo_index, (r, w, v, e) in enumerate(
            itertools.product(
                simulation_config.action_space.reserved_prb_ratio,
                simulation_config.action_space.video_scheduling_weight,
                simulation_config.action_space.minimum_voice_prb_ratio,
                simulation_config.energy.saving_intensity_values,
            )
        ):
            result = evaluate(
                evaluator,
                model_file,
                state,
                make_policy(
                    state,
                    policy_id=f"GRID-{state_index}-{combo_index}",
                    r=r,
                    w=w,
                    v=v,
                    e=e,
                ),
            )
            combination_count += 1
            numeric_outputs = [
                result.videoUserSatisfactionRatio,
                result.videoThroughputMeanMbps,
                result.videoThroughputP05Mbps,
                result.videoDelayMeanMs,
                result.videoDelayP95Ms,
                result.videoUplinkBlerMean,
                result.voiceQualityScore,
                result.voiceQualityDegradation,
                result.prbUtilization,
                result.ranEnergy,
                result.normalUserPerformanceDegradation,
                result.riskScore,
                *result.riskComponents.values(),
            ]
            assert all(math.isfinite(value) for value in numeric_outputs)
            assert all(value >= 0 for value in numeric_outputs)
            assert 0 <= result.prbUtilization <= 1
            assert 0 <= result.videoUplinkBlerMean <= 1
            assert 0 <= result.voiceQualityScore <= 1
            assert 0 <= result.riskScore <= 1
            assert all(
                record.lowerBound
                <= record.clippedValue
                <= record.upperBound
                for record in result.outputDiagnostics.values()
            )
    assert combination_count == 576


def test_monotonicity_in_configured_domain_only(
    evaluator: SimplifiedRANPerformanceEvaluator,
    model_file: PerformanceModelFile,
    simulation_config: SimulationConfig,
    validation_states: list[RANState],
) -> None:
    violations: list[str] = []
    for state_index, state in enumerate(validation_states):
        r_results = [
            evaluate(
                evaluator,
                model_file,
                state,
                make_policy(
                    state,
                    policy_id=f"MONO-R-{state_index}-{r}",
                    r=r,
                    w=1.0,
                    v=0.05,
                    e=0.0,
                ),
            )
            for r in simulation_config.action_space.reserved_prb_ratio
        ]
        _check_non_decreasing(
            [item.videoThroughputMeanMbps for item in r_results],
            f"scenario {state_index}: throughput vs r",
            violations,
        )
        _check_non_increasing(
            [item.videoDelayMeanMs for item in r_results],
            f"scenario {state_index}: delay vs r",
            violations,
        )
        _check_non_increasing(
            [item.videoUplinkBlerMean for item in r_results],
            f"scenario {state_index}: BLER vs r",
            violations,
        )

        w_results = [
            evaluate(
                evaluator,
                model_file,
                state,
                make_policy(
                    state,
                    policy_id=f"MONO-W-{state_index}-{w}",
                    r=0.0,
                    w=w,
                    v=0.05,
                    e=0.0,
                ),
            )
            for w in simulation_config.action_space.video_scheduling_weight
        ]
        _check_non_decreasing(
            [item.videoThroughputMeanMbps for item in w_results],
            f"scenario {state_index}: throughput vs w",
            violations,
        )
        _check_non_increasing(
            [item.videoDelayMeanMs for item in w_results],
            f"scenario {state_index}: delay vs w",
            violations,
        )
        _check_non_increasing(
            [item.videoUplinkBlerMean for item in w_results],
            f"scenario {state_index}: BLER vs w",
            violations,
        )

        v_results = [
            evaluate(
                evaluator,
                model_file,
                state,
                make_policy(
                    state,
                    policy_id=f"MONO-V-{state_index}-{v}",
                    r=0.0,
                    w=1.0,
                    v=v,
                    e=0.0,
                ),
            )
            for v in simulation_config.action_space.minimum_voice_prb_ratio
        ]
        _check_non_decreasing(
            [item.voiceQualityScore for item in v_results],
            f"scenario {state_index}: voice quality vs v",
            violations,
        )

        e_results = [
            evaluate(
                evaluator,
                model_file,
                state,
                make_policy(
                    state,
                    policy_id=f"MONO-E-{state_index}-{e}",
                    r=0.0,
                    w=1.0,
                    v=0.05,
                    e=e,
                ),
            )
            for e in simulation_config.energy.saving_intensity_values
        ]
        _check_non_increasing(
            [item.videoThroughputMeanMbps for item in e_results],
            f"scenario {state_index}: throughput vs e",
            violations,
        )
        _check_non_decreasing(
            [item.videoDelayMeanMs for item in e_results],
            f"scenario {state_index}: delay vs e",
            violations,
        )
        _check_non_increasing(
            [item.voiceQualityScore for item in e_results],
            f"scenario {state_index}: voice quality vs e",
            violations,
        )
        _check_non_increasing(
            [item.ranEnergy for item in e_results],
            f"scenario {state_index}: energy vs e",
            violations,
        )

    evaluator.enforce_monotonicity_validation(violations)
    assert violations == []


def test_fail_on_monotonicity_violation_is_enforced(
    evaluator: SimplifiedRANPerformanceEvaluator,
) -> None:
    with pytest.raises(MonotonicityViolationError):
        evaluator.enforce_monotonicity_validation(
            ["synthetic configured-domain violation"]
        )


def test_risk_components_and_voice_max_rule(
    evaluator: SimplifiedRANPerformanceEvaluator,
    model_file: PerformanceModelFile,
    validation_states: list[RANState],
) -> None:
    state = validation_states[-1]
    result = evaluate(
        evaluator,
        model_file,
        state,
        make_policy(
            state,
            policy_id="RISK-CHECK",
            r=0.30,
            w=2.00,
            v=0.05,
            e=0.10,
        ),
    )
    components = result.riskComponents
    assert set(components) == {
        "overload",
        "voiceAbsoluteMargin",
        "voiceBaselineDegradation",
        "energyIntensity",
        "actionComplexity",
        "fairness",
        "blerDegradation",
    }
    weights = model_file.performance_model.coefficients.risk_weights
    expected = (
        weights.omega_u * components["overload"]
        + weights.omega_q
        * max(
            components["voiceAbsoluteMargin"],
            components["voiceBaselineDegradation"],
        )
        + weights.omega_e * components["energyIntensity"]
        + weights.omega_a * components["actionComplexity"]
        + weights.omega_f * components["fairness"]
        + weights.omega_b * components["blerDegradation"]
    )
    assert result.riskScore == pytest.approx(expected)


def test_clipping_records_summary_and_batch_warning(
    evaluator: SimplifiedRANPerformanceEvaluator,
    model_file: PerformanceModelFile,
    validation_states: list[RANState],
    caplog: pytest.LogCaptureFixture,
) -> None:
    state = validation_states[0]
    policy = make_policy(
        state,
        policy_id="CLIPPING",
        r=0.30,
        w=2.00,
        v=0.05,
        e=0.00,
    )
    result = evaluate(evaluator, model_file, state, policy)
    user_bler_record = result.videoUsers[0].outputDiagnostics[
        "videoUplinkBler"
    ]
    assert user_bler_record.rawValue < 0
    assert user_bler_record.clippedValue == 0
    assert user_bler_record.wasClipped is True
    assert user_bler_record.lowerBound == 0
    assert user_bler_record.upperBound == 1
    assert result.clippingSummary["videoUplinkBler"].clippedCount == 2
    assert (
        result.clippingSummary[
            "videoUplinkBler"
        ].maximumClippingMagnitude
        > 0
    )

    with caplog.at_level("INFO"):
        batch = evaluator.evaluate_batch(state, [policy] * 10)
    assert batch.clippingSummary["videoUplinkBler"].evaluationCount == 20
    assert batch.clippingSummary["videoUplinkBler"].clippedCount == 20
    assert any(
        "videoUplinkBler" in warning for warning in batch.modelWarnings
    )
    assert any(
        record.levelname == "WARNING"
        and "metric=videoUplinkBler" in record.message
        for record in caplog.records
    )
    assert any(
        record.levelname == "INFO"
        and "metric=risk." in record.message
        for record in caplog.records
    )
    assert not any(
        record.levelname == "WARNING"
        and "metric=risk." in record.message
        for record in caplog.records
    )
    restored = PerformanceEvaluationBatch.model_validate_json(
        batch.model_dump_json()
    )
    assert restored == batch


def test_high_cost_energy_overhead_comes_from_action_library(
    simulation_config: SimulationConfig,
    model_file: PerformanceModelFile,
    action_library: ActionLibrary,
    validation_states: list[RANState],
) -> None:
    state = validation_states[0]
    policy = make_policy(
        state,
        policy_id="HIGH-COST",
        r=0.00,
    )
    configured_evaluator = SimplifiedRANPerformanceEvaluator(
        simulation_config,
        model_file.performance_model,
        action_library,
    )
    configured_result = evaluate(
        configured_evaluator, model_file, state, policy
    )

    modified_library = action_library.model_copy(deep=True)
    reserve_definition = next(
        item
        for item in modified_library.actions
        if item.type == "UL_RESOURCE_RESERVE"
    )
    reserve_definition.isHighCostAction = False
    modified_evaluator = SimplifiedRANPerformanceEvaluator(
        simulation_config,
        model_file.performance_model,
        modified_library,
    )
    modified_result = evaluate(
        modified_evaluator, model_file, state, policy
    )

    assert configured_result.ranEnergy > modified_result.ranEnergy
    assert modified_result.ranEnergy == pytest.approx(
        state.baselineRanEnergy
    )


def _check_non_decreasing(
    values: list[float],
    description: str,
    violations: list[str],
) -> None:
    if any(
        later + 1e-12 < earlier
        for earlier, later in zip(values, values[1:])
    ):
        violations.append(description)


def _check_non_increasing(
    values: list[float],
    description: str,
    violations: list[str],
) -> None:
    if any(
        later > earlier + 1e-12
        for earlier, later in zip(values, values[1:])
    ):
        violations.append(description)
