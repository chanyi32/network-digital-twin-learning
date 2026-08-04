"""Deterministic grid generator for first-version candidate RAN policies."""

from __future__ import annotations

from collections import Counter
from itertools import product
from typing import Iterable

from ran_intent_simulation.config import SimulationConfig
from ran_intent_simulation.exceptions import PolicyGenerationError
from ran_intent_simulation.io.validators import resolve_config_reference
from ran_intent_simulation.models.policy import (
    ActionLibrary,
    ActionType,
    CandidatePolicy,
    Constraint,
    PolicyAction,
    PolicyGenerationResult,
    PolicyScope,
)
from ran_intent_simulation.models.translation import TranslatedRANIntent
from ran_intent_simulation.policy.constraints import StaticPolicyConstraintChecker
from ran_intent_simulation.policy.templates import (
    PolicyTemplate,
    build_policy_templates,
)


class CandidatePolicyGenerator:
    """Generate stable policy grids without random sampling or SLA evaluation."""

    _ACTION_TARGETS = {
        ActionType.UL_RESOURCE_RESERVE.value: "video",
        ActionType.SCHEDULING_WEIGHT_ADJUST.value: "video",
        ActionType.VOICE_RESOURCE_PROTECT.value: "voice",
    }

    def __init__(
        self,
        simulation_config: SimulationConfig,
        action_library: ActionLibrary,
    ) -> None:
        self._config = simulation_config
        self._action_library = action_library
        self._definitions = {
            definition.type: definition for definition in action_library.actions
        }
        self._constraints = StaticPolicyConstraintChecker(
            simulation_config, action_library
        )

    def generate(
        self,
        translated_intent: TranslatedRANIntent,
        *,
        generation_round: int = 0,
        parent_policy_id: str | None = None,
    ) -> PolicyGenerationResult:
        """Generate, statically filter, deduplicate, and deterministically limit."""

        if translated_intent.translationStatus != "ready":
            raise PolicyGenerationError(
                "candidate generation requires translationStatus=ready"
            )
        if translated_intent.scope is None:
            raise PolicyGenerationError(
                "candidate generation requires a resolved single-cell scope"
            )
        if generation_round < 0:
            raise PolicyGenerationError("generation_round must not be negative")

        policy_scope = PolicyScope(
            startTime=translated_intent.scope.effectiveTime.effectiveStartTime,
            endTime=translated_intent.scope.effectiveTime.effectiveEndTime,
            cellIds=translated_intent.scope.cellIds,
            targetUserGroups=[
                rule.group for rule in translated_intent.scope.targetUserRules
            ],
        )
        templates = build_policy_templates(translated_intent)
        generated_count = 0
        filtered_reasons: Counter[str] = Counter()
        accepted: list[tuple[PolicyTemplate, list[PolicyAction]]] = []
        seen: set[tuple[tuple[str, str, tuple[tuple[str, object], ...]], ...]] = set()

        for template in templates:
            for actions in self._expand_template(template, policy_scope):
                generated_count += 1
                static_result = self._constraints.check(actions, policy_scope)
                if not static_result.accepted:
                    filtered_reasons[static_result.reason or "static_constraint"] += 1
                    continue
                key = self._canonical_action_key(actions)
                if key in seen:
                    filtered_reasons["duplicate_policy"] += 1
                    continue
                seen.add(key)
                accepted.append((template, actions))

        maximum = self._config.generation.maximum_candidates_per_round
        retained_combinations = accepted[:maximum]
        truncated_count = len(accepted) - len(retained_combinations)
        if truncated_count:
            filtered_reasons["maximum_candidates_per_round"] += truncated_count

        constraints = [
            Constraint(
                metric=item.metric,
                operator=item.operator,
                thresholdRef=item.thresholdRef,
            )
            for item in translated_intent.slaConstraints
        ]
        objectives = [
            objective.name for objective in translated_intent.ranObjectives
        ]
        policies = [
            self._build_candidate_policy(
                index=index,
                template=template,
                actions=actions,
                translated_intent=translated_intent,
                scope=policy_scope,
                objectives=objectives,
                constraints=constraints,
                generation_round=generation_round,
                parent_policy_id=parent_policy_id,
            )
            for index, (template, actions) in enumerate(
                retained_combinations, start=1
            )
        ]
        filtered_count = sum(filtered_reasons.values())
        return PolicyGenerationResult(
            policies=policies,
            generatedCount=generated_count,
            filteredCount=filtered_count,
            filteredReasonCounts=dict(sorted(filtered_reasons.items())),
            retainedCount=len(policies),
            generationRound=generation_round,
        )

    def _expand_template(
        self,
        template: PolicyTemplate,
        scope: PolicyScope,
    ) -> Iterable[list[PolicyAction]]:
        if not template.actionTypes:
            yield []
            return
        value_sets: list[list[float]] = []
        parameter_names: list[str] = []
        for action_type in template.actionTypes:
            definition = self._definitions.get(action_type.value)
            if definition is None:
                raise PolicyGenerationError(
                    f"action library does not define {action_type.value}"
                )
            parameter_name, parameter_definition = next(
                iter(definition.parameters.items())
            )
            values = resolve_config_reference(
                self._config, parameter_definition.valueSetRef
            )
            if not isinstance(values, list) or not values:
                raise PolicyGenerationError(
                    f"empty parameter space: {parameter_definition.valueSetRef}"
                )
            parameter_names.append(parameter_name)
            value_sets.append(values)

        for values in product(*value_sets):
            yield [
                PolicyAction(
                    type=action_type,
                    target=self._target_for(action_type, scope),
                    parameters={parameter_name: value},
                )
                for action_type, parameter_name, value in zip(
                    template.actionTypes,
                    parameter_names,
                    values,
                    strict=True,
                )
            ]

    def _target_for(
        self,
        action_type: ActionType,
        scope: PolicyScope,
    ) -> str:
        if action_type == ActionType.RAN_ENERGY_SAVING.value:
            return scope.cellIds[0]
        return self._ACTION_TARGETS[action_type.value]

    @staticmethod
    def _canonical_action_key(
        actions: list[PolicyAction],
    ) -> tuple[tuple[str, str, tuple[tuple[str, object], ...]], ...]:
        return tuple(
            sorted(
                (
                    action.type,
                    action.target,
                    tuple(sorted(action.parameters.items())),
                )
                for action in actions
            )
        )

    def _build_candidate_policy(
        self,
        *,
        index: int,
        template: PolicyTemplate,
        actions: list[PolicyAction],
        translated_intent: TranslatedRANIntent,
        scope: PolicyScope,
        objectives: list[str],
        constraints: list[Constraint],
        generation_round: int,
        parent_policy_id: str | None,
    ) -> CandidatePolicy:
        parameters = {
            name: value
            for action in actions
            for name, value in action.parameters.items()
        }
        return CandidatePolicy(
            policyId=f"RAN-POLICY-R{generation_round:02d}-{index:04d}",
            intentId=translated_intent.intentId,
            scope=scope,
            actions=actions,
            parameters=parameters,
            objectives=objectives,
            hardConstraints=constraints,
            triggerConditions=["effective_time_reached"],
            rollbackConditions=[
                "voice_sla_violation",
                "prb_limit_violation",
                "effective_time_ended",
            ],
            generationRound=generation_round,
            status="pending_evaluation",
            parentPolicyId=parent_policy_id,
            generationReason=template.templateId,
            configVersion=self._config.schema_version,
        )
