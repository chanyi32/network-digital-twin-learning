"""Constraint-first candidate-policy scoring and deterministic ranking."""

from __future__ import annotations

from collections.abc import Sequence

from ran_intent_simulation.config import SimulationConfig
from ran_intent_simulation.exceptions import ScoringError
from ran_intent_simulation.models.evaluation import PolicyPerformanceResult, PolicyScore
from ran_intent_simulation.models.policy import CandidatePolicy
from ran_intent_simulation.scoring.constraints import HardConstraintChecker
from ran_intent_simulation.scoring.normalization import normalize_cost, normalize_gain


class PolicyScorer:
    """Score evaluated policies without mutating policies or performance results."""

    def __init__(self, simulation_config: SimulationConfig) -> None:
        self._simulation_config = simulation_config
        self._constraint_checker = HardConstraintChecker(simulation_config)

    def score_and_rank(
        self,
        policies: Sequence[CandidatePolicy],
        performance_results: Sequence[PolicyPerformanceResult],
    ) -> list[PolicyScore]:
        """Score matching inputs, rank feasible policies, and leave infeasible ranks null."""

        policy_by_id = self._index_unique(policies, "candidate policy")
        performance_by_id = self._index_unique(
            performance_results,
            "performance result",
        )
        if set(policy_by_id) != set(performance_by_id):
            missing_results = sorted(set(policy_by_id) - set(performance_by_id))
            unknown_results = sorted(set(performance_by_id) - set(policy_by_id))
            raise ScoringError(
                "policy/performance ID sets differ; "
                f"missing_results={missing_results}, "
                f"unknown_results={unknown_results}"
            )

        scores = [
            self._score_one(policy, performance_by_id[policy_id])
            for policy_id, policy in sorted(policy_by_id.items())
        ]
        feasible = sorted(
            (score for score in scores if score.feasible),
            key=lambda score: self._ranking_key(
                score,
                policy_by_id[score.policyId],
            ),
        )
        for rank, score in enumerate(feasible, start=1):
            score.rank = rank

        infeasible = sorted(
            (score for score in scores if not score.feasible),
            key=lambda score: score.policyId,
        )
        return [*feasible, *infeasible]

    def _score_one(
        self,
        policy: CandidatePolicy,
        performance: PolicyPerformanceResult,
    ) -> PolicyScore:
        # Hard constraints deliberately precede every scoring calculation.
        constraint_check = self._constraint_checker.check(policy, performance)
        normalized = self._normalize_metrics(policy, performance)
        scoring = self._simulation_config.scoring

        service = (
            scoring.service_weights.satisfaction
            * normalized["videoUserSatisfactionRatio"]
            + scoring.service_weights.throughput_p05
            * normalized["videoThroughputP05Mbps"]
            + scoring.service_weights.delay_p95
            * normalized["videoDelayP95Ms"]
            + scoring.service_weights.bler
            * normalized["videoUplinkBlerMean"]
            + scoring.service_weights.voice_quality
            * normalized["voiceQualityScore"]
        )
        energy = normalized["energySavingRatio"]
        resource = (
            scoring.resource_weights.prb_utilization
            * normalized["prbUtilization"]
            + scoring.resource_weights.control_complexity
            * normalized["actionComplexity"]
        )
        risk = normalized["policyRisk"]

        if constraint_check.feasible:
            weights = scoring.weights
            total = (
                weights.service * service
                + weights.energy * energy
                + weights.resource * resource
                + weights.risk * risk
            )
            total = min(1.0, max(0.0, total))
        else:
            # Benefits in energy or any other soft objective cannot compensate
            # for a failed hard constraint.
            total = 0.0

        return PolicyScore(
            policyId=policy.policyId,
            constraintCheck=constraint_check,
            feasible=constraint_check.feasible,
            performance=performance,
            normalizedMetrics=normalized,
            serviceScore=service,
            energyScore=energy,
            resourceScore=resource,
            riskScore=risk,
            totalScore=total,
            rank=None,
            scoreConfigVersion=scoring.version,
        )

    def _normalize_metrics(
        self,
        policy: CandidatePolicy,
        performance: PolicyPerformanceResult,
    ) -> dict[str, float]:
        bounds = self._simulation_config.scoring.normalization_bounds
        baseline_energy = self._simulation_config.energy.baseline
        energy_saving_ratio = (
            baseline_energy - performance.ranEnergy
        ) / baseline_energy
        return {
            "videoUserSatisfactionRatio": normalize_gain(
                performance.videoUserSatisfactionRatio,
                bounds.video_user_satisfaction_ratio,
            ),
            "videoThroughputP05Mbps": normalize_gain(
                performance.videoThroughputP05Mbps,
                bounds.video_throughput_p05_mbps,
            ),
            "videoDelayP95Ms": normalize_cost(
                performance.videoDelayP95Ms,
                bounds.video_delay_p95_ms,
            ),
            "videoUplinkBlerMean": normalize_cost(
                performance.videoUplinkBlerMean,
                bounds.video_uplink_bler_mean,
            ),
            "voiceQualityScore": normalize_gain(
                performance.voiceQualityScore,
                bounds.voice_quality_score,
            ),
            "energySavingRatio": normalize_gain(
                energy_saving_ratio,
                bounds.energy_saving_ratio,
            ),
            "prbUtilization": normalize_cost(
                performance.prbUtilization,
                bounds.prb_utilization,
            ),
            "actionComplexity": normalize_cost(
                len(policy.actions),
                bounds.action_complexity,
            ),
            "policyRisk": normalize_cost(
                performance.riskScore,
                bounds.policy_risk,
            ),
        }

    def _ranking_key(
        self,
        score: PolicyScore,
        policy: CandidatePolicy,
    ) -> tuple[object, ...]:
        tie_values: dict[str, object] = {
            "resource_cost": score.performance.prbUtilization,
            "risk": score.performance.riskScore,
            "ran_energy": score.performance.ranEnergy,
            "action_count": len(policy.actions),
            "policy_id": score.policyId,
        }
        configured_ties = tuple(
            tie_values[key]
            for key in self._simulation_config.scoring.tie_break_order
        )
        return (-round(score.totalScore, 12), *configured_ties)

    @staticmethod
    def _index_unique(
        items: Sequence[CandidatePolicy] | Sequence[PolicyPerformanceResult],
        item_name: str,
    ) -> dict[str, CandidatePolicy | PolicyPerformanceResult]:
        indexed: dict[str, CandidatePolicy | PolicyPerformanceResult] = {}
        for item in items:
            if item.policyId in indexed:
                raise ScoringError(f"duplicate {item_name} policyId: {item.policyId}")
            indexed[item.policyId] = item
        return indexed
