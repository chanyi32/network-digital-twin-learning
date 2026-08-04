"""Deterministic, configuration-bounded feedback optimization."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Literal

from pydantic import Field, model_validator

from ran_intent_simulation.config import (
    NeutralParameterConfig,
    SimulationConfig,
    load_performance_model_config,
)
from ran_intent_simulation.exceptions import FeedbackOptimizationError
from ran_intent_simulation.io.validators import resolve_config_reference
from ran_intent_simulation.models.common import (
    NonEmptyString,
    NonNegativeInt,
    StrictDomainModel,
)
from ran_intent_simulation.models.evaluation import (
    PolicyFeedback,
    PolicyScore,
    SearchSpaceUpdate,
    SuggestedActionChanges,
    SuggestedParameterUpdate,
    WeakMetric,
)
from ran_intent_simulation.models.policy import (
    ActionDefinition,
    ActionLibrary,
    ActionType,
    CandidatePolicy,
    PolicyAction,
)
from ran_intent_simulation.policy.constraints import StaticPolicyConstraintChecker


class OptimizationStatus(str, Enum):
    """Outcome of one feedback-optimization decision."""

    CONTINUE = "continue"
    CONVERGED = "converged"
    MAX_ITERATIONS = "max_iterations"
    SEARCH_SPACE_EXHAUSTED = "search_space_exhausted"
    NO_FEASIBLE_POLICY = "no_feasible_policy"


class FeedbackOptimizationResult(StrictDomainModel):
    """Traceable feedback result and unevaluated next-round candidates."""

    feedbackIteration: NonNegativeInt
    status: OptimizationStatus
    stopReason: str | None
    feedback: PolicyFeedback
    candidatePolicies: list[CandidatePolicy]
    duplicateCandidatesSkipped: NonNegativeInt
    energyObjectiveDisabled: bool

    @model_validator(mode="after")
    def validate_terminal_state(self) -> "FeedbackOptimizationResult":
        if self.status != OptimizationStatus.CONTINUE.value:
            if self.candidatePolicies:
                raise ValueError("terminal optimization result cannot have candidates")
            if self.stopReason is None:
                raise ValueError("terminal optimization result requires stopReason")
        return self


OperationKind = Literal["adjust", "remove", "disable_energy_objective"]


@dataclass(frozen=True, slots=True)
class _Operation:
    kind: OperationKind
    reason: str
    action_type: ActionType | None = None
    direction: Literal["increase", "decrease"] | None = None


class FeedbackOptimizer:
    """Generate adjacent, statically valid policy variants from evaluation feedback."""

    _ACTION_TARGETS = {
        "video_user_group": "video",
        "voice_user_group": "voice",
    }

    def __init__(
        self,
        simulation_config: SimulationConfig,
        action_library: ActionLibrary,
        neutral_parameters: NeutralParameterConfig | None = None,
    ) -> None:
        if simulation_config.optimization.allow_relax_hard_constraints:
            raise FeedbackOptimizationError(
                "feedback optimization cannot relax hard constraints"
            )
        self._config = simulation_config
        self._library = action_library
        if neutral_parameters is None:
            model_file = load_performance_model_config(
                simulation_config.performance_model.config_file
            )
            neutral_parameters = (
                model_file.performance_model.neutral_parameters
            )
        self._neutral = neutral_parameters
        self._definitions: dict[str, ActionDefinition] = {
            definition.type: definition for definition in action_library.actions
        }
        self._action_order = {
            definition.type: index
            for index, definition in enumerate(action_library.actions)
        }
        self._static_checker = StaticPolicyConstraintChecker(
            simulation_config,
            action_library,
        )
        self._seen_signatures: set[str] = set()

    @classmethod
    def from_project_config(
        cls,
        simulation_config: SimulationConfig,
        action_library: ActionLibrary,
    ) -> "FeedbackOptimizer":
        """Load the configured neutral action values used for absent actions."""

        model_file = load_performance_model_config(
            simulation_config.performance_model.config_file
        )
        return cls(
            simulation_config,
            action_library,
            model_file.performance_model.neutral_parameters,
        )

    def optimize(
        self,
        policy: CandidatePolicy,
        score: PolicyScore,
        *,
        feedback_iteration: int,
        best_score_history: Sequence[float] = (),
        evaluated_policies: Sequence[CandidatePolicy] = (),
        evaluated_signatures: Collection[str] = (),
    ) -> FeedbackOptimizationResult:
        """Create feedback and unique next-round variants for one parent policy."""

        self._validate_inputs(policy, score, feedback_iteration, best_score_history)
        self._seen_signatures.update(evaluated_signatures)
        self._seen_signatures.update(
            self.policy_signature(item) for item in evaluated_policies
        )
        self._seen_signatures.add(self.policy_signature(policy))

        feedback, operations = self._build_feedback(policy, score)
        terminal = self._terminal_status(
            score,
            feedback_iteration,
            best_score_history,
        )
        if terminal is not None:
            status, reason = terminal
            return self._result(
                feedback_iteration=feedback_iteration,
                status=status,
                stop_reason=reason,
                feedback=feedback,
            )

        candidates: list[CandidatePolicy] = []
        duplicate_count = 0
        energy_disabled = False
        local_signatures: set[str] = set()
        for operation in operations:
            candidate = self._apply_operation(
                policy,
                operation,
                next_round=policy.generationRound + 1,
            )
            if candidate is None:
                continue
            signature = self.policy_signature(candidate)
            if (
                signature in self._seen_signatures
                or signature in local_signatures
            ):
                duplicate_count += 1
                continue
            local_signatures.add(signature)
            candidates.append(candidate)
            energy_disabled = energy_disabled or (
                operation.kind == "disable_energy_objective"
            )

        maximum = self._config.generation.maximum_candidates_per_round
        candidates = candidates[:maximum]
        self._seen_signatures.update(
            self.policy_signature(candidate) for candidate in candidates
        )
        if not candidates:
            status = (
                OptimizationStatus.NO_FEASIBLE_POLICY
                if not score.feasible
                else OptimizationStatus.SEARCH_SPACE_EXHAUSTED
            )
            return self._result(
                feedback_iteration=feedback_iteration,
                status=status,
                stop_reason="search_space_exhausted",
                feedback=feedback,
                duplicate_count=duplicate_count,
            )

        return FeedbackOptimizationResult(
            feedbackIteration=feedback_iteration,
            status=OptimizationStatus.CONTINUE,
            stopReason=None,
            feedback=feedback,
            candidatePolicies=candidates,
            duplicateCandidatesSkipped=duplicate_count,
            energyObjectiveDisabled=energy_disabled,
        )

    def _build_feedback(
        self,
        policy: CandidatePolicy,
        score: PolicyScore,
    ) -> tuple[PolicyFeedback, list[_Operation]]:
        performance = score.performance
        reasons: list[str] = []
        violations = [
            check.violation or f"{check.metric}_constraint_violation"
            for check in score.constraintCheck.checks
            if not check.passed
        ]
        weak_metrics: list[WeakMetric] = []
        operations: list[_Operation] = []

        satisfaction_threshold = (
            self._config.sla.video.required_user_satisfaction_ratio
        )
        throughput_threshold = self._config.sla.video.throughput_threshold_mbps
        throughput_insufficient = (
            performance.videoUserSatisfactionRatio < satisfaction_threshold
            or performance.videoThroughputP05Mbps < throughput_threshold
        )
        if throughput_insufficient:
            reasons.append("video_throughput_insufficient")
            if performance.videoUserSatisfactionRatio < satisfaction_threshold:
                weak_metrics.append(
                    WeakMetric(
                        metric="videoUserSatisfactionRatio",
                        thresholdRef=(
                            "sla.video.required_user_satisfaction_ratio"
                        ),
                        gap=satisfaction_threshold
                        - performance.videoUserSatisfactionRatio,
                    )
                )
            if performance.videoThroughputP05Mbps < throughput_threshold:
                weak_metrics.append(
                    WeakMetric(
                        metric="videoThroughputP05Mbps",
                        thresholdRef="sla.video.throughput_threshold_mbps",
                        gap=throughput_threshold
                        - performance.videoThroughputP05Mbps,
                    )
                )
            operations.extend(
                [
                    self._adjust(
                        ActionType.UL_RESOURCE_RESERVE,
                        "increase",
                        "video_throughput_insufficient",
                    ),
                    self._adjust(
                        ActionType.SCHEDULING_WEIGHT_ADJUST,
                        "increase",
                        "video_throughput_insufficient",
                    ),
                ]
            )

        delay_threshold = self._config.sla.video.delay_p95_threshold_ms
        if performance.videoDelayP95Ms > delay_threshold:
            reasons.append("video_delay_excessive")
            weak_metrics.append(
                WeakMetric(
                    metric="videoDelayP95Ms",
                    thresholdRef="sla.video.delay_p95_threshold_ms",
                    gap=performance.videoDelayP95Ms - delay_threshold,
                )
            )
            operations.extend(
                [
                    self._adjust(
                        ActionType.SCHEDULING_WEIGHT_ADJUST,
                        "increase",
                        "video_delay_excessive",
                    ),
                    self._adjust(
                        ActionType.UL_RESOURCE_RESERVE,
                        "increase",
                        "video_delay_excessive",
                    ),
                ]
            )

        voice_quality_threshold = self._config.sla.voice.minimum_quality_score
        voice_degradation_threshold = (
            self._config.sla.voice.maximum_degradation_from_baseline
        )
        voice_violation = (
            performance.voiceQualityScore < voice_quality_threshold
            or performance.voiceQualityDegradation
            > voice_degradation_threshold
        )
        if voice_violation:
            reasons.append("voice_protection_violation")
            if performance.voiceQualityScore < voice_quality_threshold:
                weak_metrics.append(
                    WeakMetric(
                        metric="voiceQualityScore",
                        thresholdRef="sla.voice.minimum_quality_score",
                        gap=voice_quality_threshold
                        - performance.voiceQualityScore,
                    )
                )
            if (
                performance.voiceQualityDegradation
                > voice_degradation_threshold
            ):
                weak_metrics.append(
                    WeakMetric(
                        metric="voiceQualityDegradation",
                        thresholdRef=(
                            "sla.voice.maximum_degradation_from_baseline"
                        ),
                        gap=performance.voiceQualityDegradation
                        - voice_degradation_threshold,
                    )
                )
            operations.extend(
                [
                    self._adjust(
                        ActionType.VOICE_RESOURCE_PROTECT,
                        "increase",
                        "voice_protection_violation",
                    ),
                    self._adjust(
                        ActionType.UL_RESOURCE_RESERVE,
                        "decrease",
                        "voice_protection_violation",
                    ),
                    self._adjust(
                        ActionType.RAN_ENERGY_SAVING,
                        "decrease",
                        "voice_protection_violation",
                    ),
                ]
            )

        prb_threshold = self._config.resources.maximum_prb_utilization
        if performance.prbUtilization > prb_threshold:
            reasons.append("prb_overload")
            weak_metrics.append(
                WeakMetric(
                    metric="prbUtilization",
                    thresholdRef="resources.maximum_prb_utilization",
                    gap=performance.prbUtilization - prb_threshold,
                )
            )
            operations.append(
                self._adjust(
                    ActionType.UL_RESOURCE_RESERVE,
                    "decrease",
                    "prb_overload",
                )
            )
            for action in policy.actions:
                definition = self._definitions[action.type]
                if definition.isHighCostAction and not (
                    voice_violation
                    and action.type
                    == ActionType.VOICE_RESOURCE_PROTECT.value
                ):
                    operations.append(
                        _Operation(
                            kind="remove",
                            action_type=ActionType(action.type),
                            reason="prb_overload_remove_high_cost_action",
                        )
                    )

        if score.feasible and performance.ranEnergy > self._config.energy.baseline:
            reasons.append("ran_energy_excessive")
            weak_metrics.append(
                WeakMetric(
                    metric="ranEnergy",
                    thresholdRef="energy.baseline",
                    gap=performance.ranEnergy - self._config.energy.baseline,
                )
            )
            operations.extend(
                [
                    self._adjust(
                        ActionType.RAN_ENERGY_SAVING,
                        "increase",
                        "ran_energy_excessive",
                    ),
                    self._adjust(
                        ActionType.UL_RESOURCE_RESERVE,
                        "decrease",
                        "ran_energy_excessive",
                    ),
                ]
            )

        fairness_threshold = self._config.risk.normal_user_maximum_degradation
        if performance.normalUserPerformanceDegradation > fairness_threshold:
            reasons.append("normal_user_fairness_degradation")
            weak_metrics.append(
                WeakMetric(
                    metric="normalUserPerformanceDegradation",
                    thresholdRef="risk.normal_user_maximum_degradation",
                    gap=performance.normalUserPerformanceDegradation
                    - fairness_threshold,
                )
            )
            operations.extend(
                [
                    self._adjust(
                        ActionType.UL_RESOURCE_RESERVE,
                        "decrease",
                        "normal_user_fairness_degradation",
                    ),
                    self._adjust(
                        ActionType.SCHEDULING_WEIGHT_ADJUST,
                        "decrease",
                        "normal_user_fairness_degradation",
                    ),
                ]
            )

        bler_degradation = performance.riskComponents.get(
            "blerDegradation",
            0.0,
        )
        if bler_degradation > 0:
            reasons.append("video_bler_degradation")
            weak_metrics.append(
                WeakMetric(
                    metric="videoUplinkBlerMean",
                    thresholdRef="risk.bler_risk_scale",
                    gap=bler_degradation,
                )
            )
            operations.extend(
                [
                    self._adjust(
                        ActionType.RAN_ENERGY_SAVING,
                        "decrease",
                        "video_bler_degradation",
                    ),
                    self._adjust(
                        ActionType.UL_RESOURCE_RESERVE,
                        "decrease",
                        "video_bler_degradation",
                    ),
                ]
            )

        has_energy_objective = (
            "ran_energy_optimization" in policy.objectives
        )
        if (
            not score.feasible
            and has_energy_objective
            and self._config.optimization.allow_disable_energy_objective
        ):
            reasons.append("disable_energy_soft_objective")
            operations.append(
                _Operation(
                    kind="disable_energy_objective",
                    reason="hard_constraints_take_priority_over_energy",
                )
            )

        operations = self._deduplicate_operations(operations)
        parameter_updates = self._parameter_updates(operations)
        action_changes = self._action_changes(policy, operations)
        search_updates = self._search_space_updates(operations)
        unique_reasons = list(dict.fromkeys(reasons))
        return (
            PolicyFeedback(
                policyId=policy.policyId,
                generationRound=policy.generationRound,
                violations=list(dict.fromkeys(violations)),
                weakMetrics=self._deduplicate_weak_metrics(weak_metrics),
                suggestedParameterUpdates=parameter_updates,
                suggestedActionChanges=action_changes,
                searchSpaceUpdates=search_updates,
                feedbackReason=(
                    "|".join(unique_reasons)
                    if unique_reasons
                    else "no_feedback_adjustment_required"
                ),
            ),
            operations,
        )

    def _apply_operation(
        self,
        policy: CandidatePolicy,
        operation: _Operation,
        *,
        next_round: int,
    ) -> CandidatePolicy | None:
        actions = [action.model_copy(deep=True) for action in policy.actions]
        objectives = list(policy.objectives)
        operation_label = operation.kind

        if operation.kind == "adjust":
            if operation.action_type is None or operation.direction is None:
                raise FeedbackOptimizationError("invalid adjust operation")
            updated = self._adjust_action(
                policy,
                actions,
                operation.action_type,
                operation.direction,
            )
            if updated is None:
                return None
            actions = updated
            operation_label = (
                f"{operation.direction}_{operation.action_type.value}"
            )
        elif operation.kind == "remove":
            if operation.action_type is None:
                raise FeedbackOptimizationError("invalid remove operation")
            original_count = len(actions)
            actions = [
                action
                for action in actions
                if action.type != operation.action_type.value
            ]
            if len(actions) == original_count:
                return None
            operation_label = f"remove_{operation.action_type.value}"
        elif operation.kind == "disable_energy_objective":
            actions = [
                action
                for action in actions
                if action.type != ActionType.RAN_ENERGY_SAVING.value
            ]
            objectives = [
                objective
                for objective in objectives
                if objective != "ran_energy_optimization"
            ]
            if (
                len(actions) == len(policy.actions)
                and objectives == policy.objectives
            ):
                return None

        actions.sort(key=lambda action: self._action_order[action.type])
        if not self._static_checker.check(actions, policy.scope).accepted:
            return None
        parameters = {
            key: value
            for action in actions
            for key, value in action.parameters.items()
        }
        payload = policy.model_dump()
        payload.update(
            {
                "policyId": "PENDING-FEEDBACK-ID",
                "actions": [
                    action.model_dump(mode="json") for action in actions
                ],
                "parameters": parameters,
                "objectives": objectives,
                "generationRound": next_round,
                "status": "pending_evaluation",
                "parentPolicyId": policy.policyId,
                "generationReason": (
                    f"feedback:{operation.reason}:{operation_label}"
                ),
            }
        )
        candidate = CandidatePolicy.model_validate(payload)
        signature = self.policy_signature(candidate)
        candidate.policyId = (
            f"RAN-POLICY-R{next_round:02d}-FB-{signature[:10].upper()}"
        )
        return candidate

    def _adjust_action(
        self,
        policy: CandidatePolicy,
        actions: list[PolicyAction],
        action_type: ActionType,
        direction: Literal["increase", "decrease"],
    ) -> list[PolicyAction] | None:
        definition = self._definitions.get(action_type.value)
        if definition is None:
            raise FeedbackOptimizationError(
                f"action is not defined in action library: {action_type.value}"
            )
        parameter_name, parameter_definition = next(
            iter(definition.parameters.items())
        )
        values = resolve_config_reference(
            self._config,
            parameter_definition.valueSetRef,
        )
        if not isinstance(values, list) or not values:
            raise FeedbackOptimizationError(
                f"invalid action value set: {parameter_definition.valueSetRef}"
            )

        existing_index = next(
            (
                index
                for index, action in enumerate(actions)
                if action.type == action_type.value
            ),
            None,
        )
        if existing_index is None:
            current = self._neutral_value(parameter_name)
        else:
            current = actions[existing_index].parameters[parameter_name]
        next_value = self._adjacent_value(values, current, direction)
        if next_value is None:
            return None

        updated_action = PolicyAction(
            type=action_type,
            target=self._target_for(definition, policy),
            parameters={parameter_name: next_value},
        )
        if existing_index is None:
            actions.append(updated_action)
        else:
            actions[existing_index] = updated_action
        return actions

    def _target_for(
        self,
        definition: ActionDefinition,
        policy: CandidatePolicy,
    ) -> str:
        if definition.targetType == "cell":
            return policy.scope.cellIds[0]
        try:
            return self._ACTION_TARGETS[definition.targetType]
        except KeyError as exc:
            raise FeedbackOptimizationError(
                f"unsupported action target type: {definition.targetType}"
            ) from exc

    def _neutral_value(self, parameter_name: str) -> float:
        mapping = {
            "reservedPrbRatio": self._neutral.reserved_prb_ratio,
            "videoSchedulingWeight": self._neutral.video_scheduling_weight,
            "minimumVoicePrbRatio": self._neutral.minimum_voice_prb_ratio,
            "energySavingIntensity": self._neutral.energy_saving_intensity,
        }
        try:
            return mapping[parameter_name]
        except KeyError as exc:
            raise FeedbackOptimizationError(
                f"neutral value is not defined for parameter: {parameter_name}"
            ) from exc

    @staticmethod
    def _adjacent_value(
        values: list[float],
        current: object,
        direction: Literal["increase", "decrease"],
    ) -> float | None:
        if isinstance(current, bool) or not isinstance(current, (int, float)):
            raise FeedbackOptimizationError(
                "action parameter must be numeric for adjacent adjustment"
            )
        if direction == "increase":
            return next((value for value in values if value > current), None)
        return next(
            (value for value in reversed(values) if value < current),
            None,
        )

    def _parameter_updates(
        self,
        operations: Sequence[_Operation],
    ) -> list[SuggestedParameterUpdate]:
        updates: list[SuggestedParameterUpdate] = []
        for operation in operations:
            if (
                operation.kind != "adjust"
                or operation.action_type is None
                or operation.direction is None
            ):
                continue
            definition = self._definitions[operation.action_type.value]
            parameter, parameter_definition = next(
                iter(definition.parameters.items())
            )
            updates.append(
                SuggestedParameterUpdate(
                    parameter=parameter,
                    direction=operation.direction,
                    method="next_configured_value",
                    searchSpaceRef=parameter_definition.valueSetRef,
                )
            )
        unique: dict[tuple[str, str], SuggestedParameterUpdate] = {}
        for update in updates:
            unique[(update.parameter, str(update.direction))] = update
        return list(unique.values())

    @staticmethod
    def _action_changes(
        policy: CandidatePolicy,
        operations: Sequence[_Operation],
    ) -> SuggestedActionChanges:
        active = {action.type for action in policy.actions}
        add: list[ActionType] = []
        remove: list[ActionType] = []
        for operation in operations:
            if operation.action_type is None:
                continue
            if (
                operation.kind == "adjust"
                and operation.action_type.value not in active
                and operation.action_type not in add
            ):
                add.append(operation.action_type)
            if (
                operation.kind == "remove"
                and operation.action_type.value in active
                and operation.action_type not in remove
            ):
                remove.append(operation.action_type)
        if any(
            operation.kind == "disable_energy_objective"
            for operation in operations
        ):
            energy_action = ActionType.RAN_ENERGY_SAVING
            if energy_action.value in active and energy_action not in remove:
                remove.append(energy_action)
        return SuggestedActionChanges(add=add, remove=remove)

    @staticmethod
    def _search_space_updates(
        operations: Sequence[_Operation],
    ) -> list[SearchSpaceUpdate]:
        if not any(
            operation.kind == "disable_energy_objective"
            for operation in operations
        ):
            return []
        return [
            SearchSpaceUpdate(
                parameter="ran_energy_optimization",
                operation="disable_soft_objective",
                value=None,
                reason="hard_constraints_take_priority_over_energy",
            )
        ]

    def _terminal_status(
        self,
        score: PolicyScore,
        feedback_iteration: int,
        history: Sequence[float],
    ) -> tuple[OptimizationStatus, str] | None:
        optimization = self._config.optimization
        if score.feasible and score.totalScore >= optimization.score_threshold:
            return OptimizationStatus.CONVERGED, "feasible_score_threshold_reached"
        if self._has_stagnated([*history, score.totalScore]):
            return OptimizationStatus.CONVERGED, "best_score_improvement_stagnated"
        if feedback_iteration >= optimization.maximum_feedback_iterations:
            if score.feasible:
                return OptimizationStatus.MAX_ITERATIONS, "maximum_iterations_reached"
            return (
                OptimizationStatus.NO_FEASIBLE_POLICY,
                "maximum_iterations_reached_without_feasible_policy",
            )
        return None

    def _has_stagnated(self, scores: Sequence[float]) -> bool:
        rounds = self._config.optimization.convergence_rounds
        if len(scores) < rounds + 1:
            return False
        recent = scores[-(rounds + 1) :]
        return all(
            current - previous
            < self._config.optimization.minimum_score_improvement
            for previous, current in zip(recent, recent[1:])
        )

    @staticmethod
    def policy_signature(policy: CandidatePolicy) -> str:
        """Return a stable strategy signature independent of policy metadata."""

        canonical = {
            "cellIds": sorted(policy.scope.cellIds),
            "targetUserGroups": sorted(policy.scope.targetUserGroups),
            "objectives": sorted(policy.objectives),
            "actions": sorted(
                (
                    {
                        "type": action.type,
                        "target": action.target,
                        "parameters": dict(sorted(action.parameters.items())),
                    }
                    for action in policy.actions
                ),
                key=lambda item: (
                    str(item["type"]),
                    str(item["target"]),
                    json.dumps(item["parameters"], sort_keys=True),
                ),
            ),
        }
        serialized = json.dumps(
            canonical,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @staticmethod
    def _adjust(
        action_type: ActionType,
        direction: Literal["increase", "decrease"],
        reason: str,
    ) -> _Operation:
        return _Operation(
            kind="adjust",
            action_type=action_type,
            direction=direction,
            reason=reason,
        )

    @staticmethod
    def _deduplicate_operations(
        operations: Sequence[_Operation],
    ) -> list[_Operation]:
        return list(dict.fromkeys(operations))

    @staticmethod
    def _deduplicate_weak_metrics(
        metrics: Sequence[WeakMetric],
    ) -> list[WeakMetric]:
        unique: dict[tuple[str, str], WeakMetric] = {}
        for metric in metrics:
            key = (metric.metric, metric.thresholdRef)
            previous = unique.get(key)
            if previous is None or metric.gap > previous.gap:
                unique[key] = metric
        return list(unique.values())

    @staticmethod
    def _validate_inputs(
        policy: CandidatePolicy,
        score: PolicyScore,
        feedback_iteration: int,
        history: Sequence[float],
    ) -> None:
        if policy.policyId != score.policyId:
            raise FeedbackOptimizationError(
                "policyId must match between policy and score"
            )
        if feedback_iteration < 0:
            raise FeedbackOptimizationError(
                "feedback_iteration must not be negative"
            )
        if any(value < 0 or value > 1 for value in history):
            raise FeedbackOptimizationError(
                "best_score_history values must lie within [0, 1]"
            )

    @staticmethod
    def _result(
        *,
        feedback_iteration: int,
        status: OptimizationStatus,
        stop_reason: NonEmptyString,
        feedback: PolicyFeedback,
        duplicate_count: int = 0,
    ) -> FeedbackOptimizationResult:
        return FeedbackOptimizationResult(
            feedbackIteration=feedback_iteration,
            status=status,
            stopReason=stop_reason,
            feedback=feedback,
            candidatePolicies=[],
            duplicateCandidatesSkipped=duplicate_count,
            energyObjectiveDisabled=False,
        )
