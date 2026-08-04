"""Tests for deterministic feedback optimization."""

from __future__ import annotations

from collections.abc import Iterable

import pytest

from ran_intent_simulation.config import SimulationConfig, load_simulation_config
from ran_intent_simulation.feedback import FeedbackOptimizer
from ran_intent_simulation.io import load_action_library
from ran_intent_simulation.models.evaluation import PolicyScore
from ran_intent_simulation.models.policy import (
    ActionLibrary,
    ActionType,
    CandidatePolicy,
    PolicyAction,
)
from ran_intent_simulation.scoring import PolicyScorer
from tests.unit.test_scoring import make_performance, make_policy


@pytest.fixture(scope="module")
def simulation_config() -> SimulationConfig:
    return load_simulation_config("config/simulation_config.yaml")


@pytest.fixture(scope="module")
def action_library(
    simulation_config: SimulationConfig,
) -> ActionLibrary:
    return load_action_library(
        "config/action_library.json",
        simulation_config,
    )


def action(
    action_type: ActionType,
    value: float,
) -> PolicyAction:
    parameter = {
        ActionType.UL_RESOURCE_RESERVE: "reservedPrbRatio",
        ActionType.SCHEDULING_WEIGHT_ADJUST: "videoSchedulingWeight",
        ActionType.VOICE_RESOURCE_PROTECT: "minimumVoicePrbRatio",
        ActionType.RAN_ENERGY_SAVING: "energySavingIntensity",
    }[action_type]
    target = {
        ActionType.UL_RESOURCE_RESERVE: "video",
        ActionType.SCHEDULING_WEIGHT_ADJUST: "video",
        ActionType.VOICE_RESOURCE_PROTECT: "voice",
        ActionType.RAN_ENERGY_SAVING: "CELL-101",
    }[action_type]
    return PolicyAction(
        type=action_type,
        target=target,
        parameters={parameter: value},
    )


def with_objectives(
    policy: CandidatePolicy,
    objectives: list[str],
) -> CandidatePolicy:
    payload = policy.model_dump()
    payload["objectives"] = objectives
    return CandidatePolicy.model_validate(payload)


def score_for(
    config: SimulationConfig,
    policy: CandidatePolicy,
    **performance_updates: float,
) -> PolicyScore:
    performance = make_performance(policy.policyId, **performance_updates)
    return PolicyScorer(config).score_and_rank([policy], [performance])[0]


def parameter_values(
    policies: Iterable[CandidatePolicy],
    parameter: str,
) -> set[float]:
    return {
        float(policy.parameters[parameter])
        for policy in policies
        if parameter in policy.parameters
    }


def test_throughput_and_delay_feedback_moves_only_one_adjacent_level(
    simulation_config: SimulationConfig,
    action_library: ActionLibrary,
) -> None:
    parent = make_policy(
        "PARENT-VIDEO",
        actions=[
            action(ActionType.UL_RESOURCE_RESERVE, 0.10),
            action(ActionType.SCHEDULING_WEIGHT_ADJUST, 1.25),
            action(ActionType.VOICE_RESOURCE_PROTECT, 0.05),
        ],
    )
    score = score_for(
        simulation_config,
        parent,
        videoUserSatisfactionRatio=0.80,
        videoThroughputP05Mbps=15.0,
        videoDelayP95Ms=35.0,
    )

    result = FeedbackOptimizer.from_project_config(
        simulation_config,
        action_library,
    ).optimize(parent, score, feedback_iteration=0)

    assert result.status == "continue"
    assert "video_throughput_insufficient" in result.feedback.feedbackReason
    assert "video_delay_excessive" in result.feedback.feedbackReason
    assert parameter_values(
        result.candidatePolicies,
        "reservedPrbRatio",
    ) <= {0.10, 0.20}
    assert 0.20 in parameter_values(
        result.candidatePolicies,
        "reservedPrbRatio",
    )
    assert parameter_values(
        result.candidatePolicies,
        "videoSchedulingWeight",
    ) <= {1.25, 1.50}
    assert 1.50 in parameter_values(
        result.candidatePolicies,
        "videoSchedulingWeight",
    )


def test_voice_and_prb_feedback_supports_adjustment_and_action_removal(
    simulation_config: SimulationConfig,
    action_library: ActionLibrary,
) -> None:
    parent = make_policy(
        "PARENT-VOICE-PRB",
        actions=[
            action(ActionType.UL_RESOURCE_RESERVE, 0.20),
            action(ActionType.SCHEDULING_WEIGHT_ADJUST, 1.50),
            action(ActionType.VOICE_RESOURCE_PROTECT, 0.05),
            action(ActionType.RAN_ENERGY_SAVING, 0.10),
        ],
    )
    score = score_for(
        simulation_config,
        parent,
        voiceQualityScore=0.94,
        voiceQualityDegradation=0.03,
        prbUtilization=0.95,
    )

    result = FeedbackOptimizer.from_project_config(
        simulation_config,
        action_library,
    ).optimize(parent, score, feedback_iteration=2)

    assert "voice_protection_violation" in result.feedback.feedbackReason
    assert "prb_overload" in result.feedback.feedbackReason
    assert 0.10 in parameter_values(
        result.candidatePolicies,
        "minimumVoicePrbRatio",
    )
    assert 0.10 in parameter_values(
        result.candidatePolicies,
        "reservedPrbRatio",
    )
    assert 0.05 in parameter_values(
        result.candidatePolicies,
        "energySavingIntensity",
    )
    assert result.feedback.suggestedActionChanges.remove


def test_feedback_candidates_record_lineage_and_preserve_hard_constraints(
    simulation_config: SimulationConfig,
    action_library: ActionLibrary,
) -> None:
    parent = make_policy("PARENT-LINEAGE")
    score = score_for(
        simulation_config,
        parent,
        videoUserSatisfactionRatio=0.80,
        videoThroughputP05Mbps=15.0,
    )
    parent_before = parent.model_dump_json()
    score_before = score.model_dump_json()

    result = FeedbackOptimizer.from_project_config(
        simulation_config,
        action_library,
    ).optimize(parent, score, feedback_iteration=0)

    assert result.candidatePolicies
    for candidate in result.candidatePolicies:
        assert candidate.parentPolicyId == parent.policyId
        assert candidate.generationRound == parent.generationRound + 1
        assert candidate.generationReason.startswith("feedback:")
        assert candidate.hardConstraints == parent.hardConstraints
        assert candidate.policyId.startswith("RAN-POLICY-R01-FB-")
    assert parent.model_dump_json() == parent_before
    assert score.model_dump_json() == score_before


def test_energy_feedback_adds_next_energy_level_when_sla_is_feasible(
    simulation_config: SimulationConfig,
    action_library: ActionLibrary,
) -> None:
    parent = with_objectives(
        make_policy("PARENT-ENERGY"),
        ["video_uplink_assurance", "ran_energy_optimization"],
    )
    score = score_for(simulation_config, parent, ranEnergy=1.10)

    result = FeedbackOptimizer.from_project_config(
        simulation_config,
        action_library,
    ).optimize(parent, score, feedback_iteration=0)

    assert score.feasible
    assert "ran_energy_excessive" in result.feedback.feedbackReason
    assert 0.05 in parameter_values(
        result.candidatePolicies,
        "energySavingIntensity",
    )
    assert (
        ActionType.RAN_ENERGY_SAVING.value
        in result.feedback.suggestedActionChanges.add
    )


def test_fairness_and_bler_feedback_reduce_configured_adjacent_levels(
    simulation_config: SimulationConfig,
    action_library: ActionLibrary,
) -> None:
    parent = make_policy(
        "PARENT-SOFT-RISK",
        actions=[
            action(ActionType.UL_RESOURCE_RESERVE, 0.20),
            action(ActionType.SCHEDULING_WEIGHT_ADJUST, 1.50),
            action(ActionType.VOICE_RESOURCE_PROTECT, 0.05),
            action(ActionType.RAN_ENERGY_SAVING, 0.10),
        ],
    )
    score = score_for(
        simulation_config,
        parent,
        normalUserPerformanceDegradation=0.11,
    )
    score.performance.riskComponents["blerDegradation"] = 0.20

    result = FeedbackOptimizer.from_project_config(
        simulation_config,
        action_library,
    ).optimize(parent, score, feedback_iteration=0)

    assert "normal_user_fairness_degradation" in result.feedback.feedbackReason
    assert "video_bler_degradation" in result.feedback.feedbackReason
    assert 0.10 in parameter_values(
        result.candidatePolicies,
        "reservedPrbRatio",
    )
    assert 1.25 in parameter_values(
        result.candidatePolicies,
        "videoSchedulingWeight",
    )
    assert 0.05 in parameter_values(
        result.candidatePolicies,
        "energySavingIntensity",
    )


def test_infeasible_policy_can_disable_only_the_energy_soft_objective(
    simulation_config: SimulationConfig,
    action_library: ActionLibrary,
) -> None:
    parent = with_objectives(
        make_policy(
            "PARENT-DISABLE-ENERGY",
            actions=[action(ActionType.RAN_ENERGY_SAVING, 0.05)],
        ),
        ["video_uplink_assurance", "ran_energy_optimization"],
    )
    score = score_for(
        simulation_config,
        parent,
        videoUserSatisfactionRatio=0.80,
        videoThroughputP05Mbps=15.0,
    )

    result = FeedbackOptimizer.from_project_config(
        simulation_config,
        action_library,
    ).optimize(parent, score, feedback_iteration=0)
    disabled = [
        candidate
        for candidate in result.candidatePolicies
        if "ran_energy_optimization" not in candidate.objectives
    ]

    assert result.energyObjectiveDisabled
    assert disabled
    for candidate in disabled:
        assert "video_uplink_assurance" in candidate.objectives
        assert all(
            action_item.type != ActionType.RAN_ENERGY_SAVING.value
            for action_item in candidate.actions
        )
        assert candidate.hardConstraints == parent.hardConstraints


def test_optimizer_skips_already_generated_strategy_signatures(
    simulation_config: SimulationConfig,
    action_library: ActionLibrary,
) -> None:
    parent = make_policy("PARENT-DUPLICATE")
    score = score_for(
        simulation_config,
        parent,
        videoUserSatisfactionRatio=0.80,
        videoThroughputP05Mbps=15.0,
    )
    optimizer = FeedbackOptimizer.from_project_config(
        simulation_config,
        action_library,
    )

    first = optimizer.optimize(parent, score, feedback_iteration=0)
    second = optimizer.optimize(parent, score, feedback_iteration=1)

    assert first.candidatePolicies
    assert second.candidatePolicies == []
    assert second.duplicateCandidatesSkipped >= len(first.candidatePolicies)
    assert second.status == "no_feasible_policy"


def test_feasible_score_threshold_stops_without_new_candidates(
    simulation_config: SimulationConfig,
    action_library: ActionLibrary,
) -> None:
    parent = make_policy("PARENT-CONVERGED")
    score = score_for(
        simulation_config,
        parent,
        videoUserSatisfactionRatio=1.0,
        videoThroughputP05Mbps=40.0,
        videoDelayP95Ms=0.0,
        videoUplinkBlerMean=0.0,
        voiceQualityScore=1.0,
        prbUtilization=0.0,
        ranEnergy=0.05,
        riskScore=0.0,
    )

    result = FeedbackOptimizer.from_project_config(
        simulation_config,
        action_library,
    ).optimize(parent, score, feedback_iteration=0)

    assert score.totalScore >= simulation_config.optimization.score_threshold
    assert result.status == "converged"
    assert result.stopReason == "feasible_score_threshold_reached"
    assert result.candidatePolicies == []


def test_consecutive_small_improvements_trigger_stagnation(
    simulation_config: SimulationConfig,
    action_library: ActionLibrary,
) -> None:
    parent = make_policy("PARENT-STAGNATED")
    score = score_for(simulation_config, parent)
    history = [score.totalScore - 0.006, score.totalScore - 0.003]

    result = FeedbackOptimizer.from_project_config(
        simulation_config,
        action_library,
    ).optimize(
        parent,
        score,
        feedback_iteration=3,
        best_score_history=history,
    )

    assert result.status == "converged"
    assert result.stopReason == "best_score_improvement_stagnated"


def test_maximum_iterations_reports_no_feasible_policy(
    simulation_config: SimulationConfig,
    action_library: ActionLibrary,
) -> None:
    parent = make_policy("PARENT-MAXIMUM")
    score = score_for(
        simulation_config,
        parent,
        videoUserSatisfactionRatio=0.80,
    )

    result = FeedbackOptimizer.from_project_config(
        simulation_config,
        action_library,
    ).optimize(
        parent,
        score,
        feedback_iteration=(
            simulation_config.optimization.maximum_feedback_iterations
        ),
    )

    assert result.status == "no_feasible_policy"
    assert result.stopReason == (
        "maximum_iterations_reached_without_feasible_policy"
    )
    assert result.candidatePolicies == []
