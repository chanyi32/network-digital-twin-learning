"""Hard-constraint evaluation for candidate RAN policies."""

from __future__ import annotations

import math
from collections.abc import Callable

from ran_intent_simulation.config import SimulationConfig
from ran_intent_simulation.exceptions import ConstraintEvaluationError, DataValidationError
from ran_intent_simulation.io.validators import resolve_config_reference
from ran_intent_simulation.models.evaluation import (
    ConstraintCheck,
    ConstraintCheckResult,
    PolicyPerformanceResult,
)
from ran_intent_simulation.models.policy import CandidatePolicy


Comparison = Callable[[float, float], bool]

_COMPARISONS: dict[str, Comparison] = {
    ">=": lambda actual, threshold: actual >= threshold,
    "<=": lambda actual, threshold: actual <= threshold,
    ">": lambda actual, threshold: actual > threshold,
    "<": lambda actual, threshold: actual < threshold,
    "==": lambda actual, threshold: math.isclose(
        actual,
        threshold,
        rel_tol=0.0,
        abs_tol=1e-12,
    ),
}


class HardConstraintChecker:
    """Evaluate every declared hard constraint without short-circuiting."""

    def __init__(self, simulation_config: SimulationConfig) -> None:
        self._simulation_config = simulation_config

    def check(
        self,
        policy: CandidatePolicy,
        performance: PolicyPerformanceResult,
    ) -> ConstraintCheck:
        """Return all constraint outcomes for one policy-performance pair."""

        if policy.policyId != performance.policyId:
            raise ConstraintEvaluationError(
                "policyId must match between candidate policy and performance result"
            )

        checks = [
            self._evaluate_constraint(
                metric=constraint.metric,
                operator=str(constraint.operator),
                threshold_ref=constraint.thresholdRef,
                performance=performance,
            )
            for constraint in policy.hardConstraints
        ]
        return ConstraintCheck(
            policyId=policy.policyId,
            checks=checks,
            feasible=all(check.passed for check in checks),
        )

    def _evaluate_constraint(
        self,
        *,
        metric: str,
        operator: str,
        threshold_ref: str,
        performance: PolicyPerformanceResult,
    ) -> ConstraintCheckResult:
        if metric not in PolicyPerformanceResult.model_fields:
            raise ConstraintEvaluationError(
                f"unsupported hard-constraint metric: {metric}"
            )

        actual = getattr(performance, metric)
        if isinstance(actual, bool) or not isinstance(actual, (int, float)):
            raise ConstraintEvaluationError(
                f"hard-constraint metric must be numeric: {metric}"
            )

        try:
            threshold = resolve_config_reference(
                self._simulation_config,
                threshold_ref,
            )
        except DataValidationError as exc:
            raise ConstraintEvaluationError(str(exc)) from exc
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
            raise ConstraintEvaluationError(
                f"hard-constraint threshold must be numeric: {threshold_ref}"
            )

        comparison = _COMPARISONS.get(operator)
        if comparison is None:
            raise ConstraintEvaluationError(
                f"unsupported hard-constraint operator: {operator}"
            )

        actual_value = float(actual)
        threshold_value = float(threshold)
        passed = comparison(actual_value, threshold_value)
        violation = None
        if not passed:
            violation = (
                f"{metric}={actual_value:g} violates {operator} "
                f"{threshold_value:g} ({threshold_ref})"
            )
        return ConstraintCheckResult(
            metric=metric,
            operator=operator,
            thresholdRef=threshold_ref,
            actualValue=actual_value,
            thresholdValue=threshold_value,
            passed=passed,
            violation=violation,
        )
