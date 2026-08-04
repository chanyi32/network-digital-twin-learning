"""Static candidate checks that intentionally exclude performance SLA."""

from __future__ import annotations

from dataclasses import dataclass

from ran_intent_simulation.config import SimulationConfig
from ran_intent_simulation.io.validators import resolve_config_reference
from ran_intent_simulation.models.policy import (
    ActionLibrary,
    ActionType,
    PolicyAction,
    PolicyScope,
)


@dataclass(frozen=True, slots=True)
class StaticConstraintResult:
    """Result of the first failing static rule, if any."""

    accepted: bool
    reason: str | None = None


class StaticPolicyConstraintChecker:
    """Validate capability, configured values, conflicts, and resource totals."""

    def __init__(
        self,
        simulation_config: SimulationConfig,
        action_library: ActionLibrary,
    ) -> None:
        self._config = simulation_config
        self._definitions = {
            definition.type: definition for definition in action_library.actions
        }
        self._declared_conflicts = {
            conflict
            for definition in action_library.actions
            for conflict in definition.conflicts
        }

    def check(
        self,
        actions: list[PolicyAction],
        scope: PolicyScope,
    ) -> StaticConstraintResult:
        """Apply documented static filters in a stable order."""

        action_types = [action.type for action in actions]
        if len(action_types) != len(set(action_types)):
            return StaticConstraintResult(False, "duplicate_action_type")

        for action in actions:
            definition = self._definitions.get(action.type)
            if definition is None:
                return StaticConstraintResult(False, "unsupported_action")
            if set(action.parameters) != set(definition.parameters):
                return StaticConstraintResult(False, "action_parameter_schema")
            for parameter_name, parameter_definition in definition.parameters.items():
                configured_values = resolve_config_reference(
                    self._config, parameter_definition.valueSetRef
                )
                if action.parameters[parameter_name] not in configured_values:
                    return StaticConstraintResult(
                        False, "parameter_not_in_configured_space"
                    )
            if not self._target_is_supported(
                definition.targetType, action.target, scope
            ):
                return StaticConstraintResult(False, "unsupported_action_target")

        by_type = {action.type: action for action in actions}
        conflict = self._check_action_conflicts(by_type, scope)
        if conflict is not None:
            return StaticConstraintResult(False, conflict)

        reserved = self._parameter_value(
            by_type, ActionType.UL_RESOURCE_RESERVE, "reservedPrbRatio"
        )
        voice = self._parameter_value(
            by_type, ActionType.VOICE_RESOURCE_PROTECT, "minimumVoicePrbRatio"
        )
        if reserved + voice > self._config.resources.maximum_prb_utilization:
            return StaticConstraintResult(
                False, "reserved_and_voice_prb_exceeds_resource_limit"
            )
        return StaticConstraintResult(True)

    @staticmethod
    def _target_is_supported(
        target_type: str,
        target: str,
        scope: PolicyScope,
    ) -> bool:
        if target_type == "video_user_group":
            return target == "video" and "video" in scope.targetUserGroups
        if target_type == "voice_user_group":
            return target == "voice" and "voice" in scope.targetUserGroups
        if target_type == "cell":
            return target == scope.cellIds[0]
        return False

    def _check_action_conflicts(
        self,
        by_type: dict[str, PolicyAction],
        scope: PolicyScope,
    ) -> str | None:
        scheduling = by_type.get(ActionType.SCHEDULING_WEIGHT_ADJUST.value)
        voice = by_type.get(ActionType.VOICE_RESOURCE_PROTECT.value)
        if (
            "high_video_weight_without_voice_protection"
            in self._declared_conflicts
            and scheduling is not None
            and "voice" in scope.targetUserGroups
            and voice is None
        ):
            configured_weights = self._config.action_space.video_scheduling_weight
            if scheduling.parameters["videoSchedulingWeight"] > min(
                configured_weights
            ):
                return "high_video_weight_without_voice_protection"

        reserve = by_type.get(ActionType.UL_RESOURCE_RESERVE.value)
        energy = by_type.get(ActionType.RAN_ENERGY_SAVING.value)
        if (
            "high_energy_saving_with_high_prb_reserve"
            in self._declared_conflicts
            and reserve is not None
            and energy is not None
        ):
            reserve_space = self._config.action_space.reserved_prb_ratio
            energy_space = self._config.energy.saving_intensity_values
            if (
                reserve.parameters["reservedPrbRatio"]
                == max(reserve_space)
                and energy.parameters["energySavingIntensity"]
                == max(energy_space)
                and max(reserve_space) > min(reserve_space)
                and max(energy_space) > min(energy_space)
            ):
                return "high_energy_saving_with_high_prb_reserve"
        return None

    @staticmethod
    def _parameter_value(
        by_type: dict[str, PolicyAction],
        action_type: ActionType,
        parameter_name: str,
    ) -> float:
        action = by_type.get(action_type.value)
        if action is None:
            return 0.0
        value = action.parameters[parameter_name]
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return 0.0
        return float(value)
