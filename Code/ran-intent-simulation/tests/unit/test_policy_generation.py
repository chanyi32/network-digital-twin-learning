"""Tests for deterministic candidate RAN-policy generation."""

from __future__ import annotations

from copy import deepcopy

import pytest

import ran_intent_simulation.policy.generator as generator_module
from ran_intent_simulation.config import SimulationConfig, load_simulation_config
from ran_intent_simulation.exceptions import PolicyGenerationError
from ran_intent_simulation.intent import RuleBasedIntentExtractor
from ran_intent_simulation.io import (
    load_action_library,
    load_intent_samples,
)
from ran_intent_simulation.models.policy import (
    ActionLibrary,
    ActionType,
    PolicyGenerationResult,
)
from ran_intent_simulation.models.translation import (
    ConfigurationRefs,
    IntentTranslationInput,
    TranslatedRANIntent,
)
from ran_intent_simulation.policy import (
    CandidatePolicyGenerator,
    PolicyTemplate,
    build_policy_templates,
)
from ran_intent_simulation.translation import StaticIntentTranslator


@pytest.fixture
def simulation_config() -> SimulationConfig:
    return load_simulation_config("config/simulation_config.yaml")


@pytest.fixture
def action_library(
    simulation_config: SimulationConfig,
) -> ActionLibrary:
    return load_action_library(
        "config/action_library.json", simulation_config
    )


@pytest.fixture
def translated_intent(
    simulation_config: SimulationConfig,
) -> TranslatedRANIntent:
    refs = ConfigurationRefs(
        eventDatabase="data/event_database.json",
        venueCellMapping="data/venue_cell_mapping.json",
        slaTemplates="config/sla_templates.json",
        resourceConstraints="config/simulation_config.yaml",
    )
    extracted = RuleBasedIntentExtractor(
        simulation_config.intent_extraction
    ).extract(load_intent_samples("data/intent_samples.json")[0])
    return StaticIntentTranslator.from_configuration_refs(refs).translate(
        IntentTranslationInput(
            structuredIntent=extracted,
            configurationRefs=refs,
        )
    )


def generate(
    config: SimulationConfig,
    library: ActionLibrary,
    translated: TranslatedRANIntent,
    *,
    generation_round: int = 0,
) -> PolicyGenerationResult:
    return CandidatePolicyGenerator(config, library).generate(
        translated,
        generation_round=generation_round,
    )


def test_templates_cover_baseline_assurance_and_energy(
    translated_intent: TranslatedRANIntent,
) -> None:
    templates = build_policy_templates(translated_intent)
    by_id = {template.templateId: template.actionTypes for template in templates}

    assert by_id["baseline"] == ()
    assert by_id["scheduling_assurance"] == (
        ActionType.SCHEDULING_WEIGHT_ADJUST,
        ActionType.VOICE_RESOURCE_PROTECT,
    )
    assert by_id["resource_assurance"] == (
        ActionType.UL_RESOURCE_RESERVE,
        ActionType.VOICE_RESOURCE_PROTECT,
    )
    assert by_id["joint_assurance"] == (
        ActionType.UL_RESOURCE_RESERVE,
        ActionType.SCHEDULING_WEIGHT_ADJUST,
        ActionType.VOICE_RESOURCE_PROTECT,
    )
    assert (
        ActionType.RAN_ENERGY_SAVING
        in by_id["joint_assurance_with_energy"]
    )


def test_cartesian_generation_reports_counts_and_reasons(
    simulation_config: SimulationConfig,
    action_library: ActionLibrary,
    translated_intent: TranslatedRANIntent,
) -> None:
    result = generate(
        simulation_config, action_library, translated_intent
    )

    assert result.generatedCount == 385
    assert result.retainedCount == 100
    assert result.filteredCount == 285
    assert result.filteredReasonCounts == {
        "high_energy_saving_with_high_prb_reserve": 20,
        "maximum_candidates_per_round": 265,
    }
    assert result.generatedCount == result.filteredCount + result.retainedCount


def test_baseline_policy_has_no_adjustment_actions(
    simulation_config: SimulationConfig,
    action_library: ActionLibrary,
    translated_intent: TranslatedRANIntent,
) -> None:
    baseline = generate(
        simulation_config, action_library, translated_intent
    ).policies[0]

    assert baseline.generationReason == "baseline"
    assert baseline.actions == []
    assert baseline.parameters == {}
    assert baseline.policyId == "RAN-POLICY-R00-0001"
    assert baseline.status == "pending_evaluation"


def test_parameters_come_from_configured_spaces(
    simulation_config: SimulationConfig,
    action_library: ActionLibrary,
    translated_intent: TranslatedRANIntent,
) -> None:
    result = generate(
        simulation_config, action_library, translated_intent
    )
    allowed = {
        "reservedPrbRatio": simulation_config.action_space.reserved_prb_ratio,
        "videoSchedulingWeight": (
            simulation_config.action_space.video_scheduling_weight
        ),
        "minimumVoicePrbRatio": (
            simulation_config.action_space.minimum_voice_prb_ratio
        ),
        "energySavingIntensity": (
            simulation_config.energy.saving_intensity_values
        ),
    }

    for policy in result.policies:
        for parameter, value in policy.parameters.items():
            assert value in allowed[parameter]


def test_generation_is_reproducible_and_deduplicated(
    simulation_config: SimulationConfig,
    action_library: ActionLibrary,
    translated_intent: TranslatedRANIntent,
) -> None:
    first = generate(
        simulation_config,
        action_library,
        translated_intent,
        generation_round=2,
    )
    second = generate(
        simulation_config,
        action_library,
        translated_intent,
        generation_round=2,
    )

    assert first.model_dump_json() == second.model_dump_json()
    assert first.policies[0].policyId == "RAN-POLICY-R02-0001"
    policy_keys = [
        tuple(
            sorted(
                (
                    action.type,
                    action.target,
                    tuple(sorted(action.parameters.items())),
                )
                for action in policy.actions
            )
        )
        for policy in first.policies
    ]
    assert len(policy_keys) == len(set(policy_keys))
    assert len({policy.policyId for policy in first.policies}) == len(
        first.policies
    )
    restored = PolicyGenerationResult.model_validate_json(
        first.model_dump_json()
    )
    assert restored == first


def test_duplicate_templates_are_reported_and_removed(
    monkeypatch: pytest.MonkeyPatch,
    simulation_config: SimulationConfig,
    action_library: ActionLibrary,
    translated_intent: TranslatedRANIntent,
) -> None:
    duplicate_baselines = (
        PolicyTemplate(templateId="baseline-a", priority=0, actionTypes=()),
        PolicyTemplate(templateId="baseline-b", priority=1, actionTypes=()),
    )
    monkeypatch.setattr(
        generator_module,
        "build_policy_templates",
        lambda _: duplicate_baselines,
    )

    result = generate(
        simulation_config, action_library, translated_intent
    )

    assert result.generatedCount == 2
    assert result.retainedCount == 1
    assert result.filteredReasonCounts == {"duplicate_policy": 1}


def test_maximum_candidate_limit_uses_stable_prefix(
    simulation_config: SimulationConfig,
    action_library: ActionLibrary,
    translated_intent: TranslatedRANIntent,
) -> None:
    full = generate(
        simulation_config, action_library, translated_intent
    )
    limited_config = simulation_config.model_copy(deep=True)
    limited_config.generation.maximum_candidates_per_round = 5
    limited = generate(limited_config, action_library, translated_intent)

    assert limited.retainedCount == 5
    assert [policy.parameters for policy in limited.policies] == [
        policy.parameters for policy in full.policies[:5]
    ]
    assert (
        limited.filteredReasonCounts["maximum_candidates_per_round"]
        > full.filteredReasonCounts["maximum_candidates_per_round"]
    )


def test_reserved_and_voice_prb_resource_constraint_is_filtered(
    simulation_config: SimulationConfig,
    action_library: ActionLibrary,
    translated_intent: TranslatedRANIntent,
) -> None:
    constrained_config = simulation_config.model_copy(deep=True)
    constrained_config.action_space.reserved_prb_ratio = [0.80]
    constrained_config.action_space.video_scheduling_weight = [1.00]
    constrained_config.action_space.minimum_voice_prb_ratio = [0.20]
    constrained_config.energy.saving_intensity_values = [0.00]
    constrained_config.generation.maximum_candidates_per_round = 100

    result = generate(
        constrained_config, action_library, translated_intent
    )

    assert (
        result.filteredReasonCounts[
            "reserved_and_voice_prb_exceeds_resource_limit"
        ]
        == 4
    )
    assert all(
        policy.parameters.get("reservedPrbRatio", 0)
        + policy.parameters.get("minimumVoicePrbRatio", 0)
        <= constrained_config.resources.maximum_prb_utilization
        for policy in result.policies
    )


def test_generation_does_not_filter_on_performance_sla(
    simulation_config: SimulationConfig,
    action_library: ActionLibrary,
    translated_intent: TranslatedRANIntent,
) -> None:
    result = generate(
        simulation_config, action_library, translated_intent
    )

    assert result.policies[0].generationReason == "baseline"
    assert all(
        not reason.startswith("sla")
        and "throughput" not in reason
        and "delay" not in reason
        for reason in result.filteredReasonCounts
    )


def test_blocked_translation_cannot_generate(
    simulation_config: SimulationConfig,
    action_library: ActionLibrary,
    translated_intent: TranslatedRANIntent,
) -> None:
    blocked_payload = deepcopy(translated_intent.model_dump())
    blocked_payload["scope"] = None
    blocked_payload["unresolvedItems"] = [
        {"code": "ran_scope", "severity": "blocking"}
    ]
    blocked_payload["translationStatus"] = "blocked"
    blocked = TranslatedRANIntent.model_validate(blocked_payload)

    with pytest.raises(PolicyGenerationError, match="translationStatus=ready"):
        generate(simulation_config, action_library, blocked)
