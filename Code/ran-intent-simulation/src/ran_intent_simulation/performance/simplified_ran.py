"""Config-driven, deterministic simplified single-cell RAN performance model."""

from __future__ import annotations

import logging
import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from ran_intent_simulation.config import (
    OutputBoundConfig,
    SimplifiedRANModelConfig,
    SimulationConfig,
    load_performance_model_config,
)
from ran_intent_simulation.exceptions import (
    MonotonicityViolationError,
    PerformanceEvaluationError,
)
from ran_intent_simulation.models.evaluation import (
    ClippedValue,
    MetricClippingSummary,
    PerformanceEvaluationBatch,
    PerformanceEvaluationInput,
    PolicyPerformanceResult,
    VideoUserPerformance,
)
from ran_intent_simulation.models.policy import (
    ActionLibrary,
    CandidatePolicy,
)
from ran_intent_simulation.models.ran_state import RANState
from ran_intent_simulation.performance.base import RANPerformanceEvaluator

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class _MutableClippingSummary:
    evaluation_count: int = 0
    clipped_count: int = 0
    maximum_magnitude: float = 0.0


class _ClippingCollector:
    def __init__(self, bounds: dict[str, OutputBoundConfig]) -> None:
        self._bounds = bounds
        self._summaries: dict[str, _MutableClippingSummary] = {}

    def record(
        self,
        metric: str,
        raw_value: float,
        *,
        bound_key: str,
    ) -> ClippedValue:
        if not math.isfinite(raw_value):
            raise PerformanceEvaluationError(
                f"non-finite raw model output for {metric}"
            )
        bound = self._bounds[bound_key]
        clipped = min(max(raw_value, bound.lowerBound), bound.upperBound)
        magnitude = abs(raw_value - clipped)
        was_clipped = magnitude > 1e-12
        summary = self._summaries.setdefault(
            metric, _MutableClippingSummary()
        )
        summary.evaluation_count += 1
        if was_clipped:
            summary.clipped_count += 1
            summary.maximum_magnitude = max(
                summary.maximum_magnitude, magnitude
            )
        return ClippedValue(
            rawValue=raw_value,
            clippedValue=clipped,
            wasClipped=was_clipped,
            lowerBound=bound.lowerBound,
            upperBound=bound.upperBound,
        )

    def summaries(self) -> dict[str, MetricClippingSummary]:
        return {
            metric: MetricClippingSummary(
                evaluationCount=value.evaluation_count,
                clippedCount=value.clipped_count,
                maximumClippingMagnitude=value.maximum_magnitude,
            )
            for metric, value in sorted(self._summaries.items())
        }


class SimplifiedRANPerformanceEvaluator(RANPerformanceEvaluator):
    """Evaluate relative trends only within the configured validation domain."""

    def __init__(
        self,
        simulation_config: SimulationConfig,
        model_config: SimplifiedRANModelConfig,
        action_library: ActionLibrary,
    ) -> None:
        if (
            simulation_config.performance_model.version
            != model_config.model_version
        ):
            raise PerformanceEvaluationError(
                "simulation and performance-model versions do not match"
            )
        self._simulation = simulation_config
        self._model = model_config
        self._random_seed = simulation_config.reproducibility.random_seed
        self._action_definitions = {
            action.type: action for action in action_library.actions
        }

    @classmethod
    def from_project_config(
        cls,
        simulation_config: SimulationConfig,
        action_library: ActionLibrary,
    ) -> "SimplifiedRANPerformanceEvaluator":
        """Load the explicitly referenced coefficient file."""

        model_file = load_performance_model_config(
            simulation_config.performance_model.config_file
        )
        return cls(
            simulation_config,
            model_file.performance_model,
            action_library,
        )

    def evaluate(
        self,
        evaluation_input: PerformanceEvaluationInput,
    ) -> PolicyPerformanceResult:
        if (
            evaluation_input.modelConfigVersion
            != self._model.coefficient_version
        ):
            raise PerformanceEvaluationError(
                "evaluation input coefficient version does not match"
            )
        state = evaluation_input.ranState
        policy = evaluation_input.candidatePolicy
        collector = _ClippingCollector(self._model.output_bounds)
        r, w, v, e = self._policy_parameters(policy)
        coefficients = self._model.coefficients

        phi = self._bounded(
            1 - coefficients.capacity.k_E * e,
            coefficients.capacity.phi_min,
            1,
        )
        raw_prb = (
            state.prbUtilization
            + coefficients.capacity.k_r * r
            + coefficients.capacity.k_v * v
        ) / phi
        prb_record = collector.record(
            "prbUtilization",
            raw_prb,
            bound_key="prbUtilization",
        )
        prb_after = prb_record.clippedValue
        overload = max(0.0, prb_after - coefficients.capacity.u_cong)

        video_results: list[VideoUserPerformance] = []
        throughput_values: list[float] = []
        delay_values: list[float] = []
        bler_values: list[float] = []
        for user in state.videoUsers:
            sinr_factor = self._bounded(
                1
                + coefficients.throughput.sinr_gain_per_db
                * (
                    user.meanSinrDb
                    - coefficients.throughput.sinr_reference_db
                ),
                coefficients.throughput.sinr_factor_min,
                coefficients.throughput.sinr_factor_max,
            )
            raw_throughput = (
                user.baselineUplinkThroughputMbps
                * (
                    1
                    + coefficients.throughput.alpha_r * r
                    + coefficients.throughput.alpha_w * (w - 1)
                )
                * phi
                / (1 + coefficients.throughput.alpha_c * overload)
                * sinr_factor
            )
            delay_denominator = (
                1
                + coefficients.delay.beta_r * r
                + coefficients.delay.beta_w * (w - 1)
            )
            if delay_denominator <= self._model.risk.epsilon:
                raise PerformanceEvaluationError(
                    "video delay denominator is not positive"
                )
            raw_delay = (
                user.baselineUplinkDelayMs
                * (
                    1
                    + coefficients.delay.beta_u
                    * max(0.0, prb_after - state.prbUtilization)
                    + coefficients.delay.beta_e * e
                )
                / delay_denominator
            )
            raw_bler = (
                user.baselineUplinkBler
                + coefficients.bler.chi_u * overload
                - coefficients.bler.chi_r * r
                - coefficients.bler.chi_w * (w - 1)
            )
            throughput_record = collector.record(
                "videoUplinkThroughputMbps",
                raw_throughput,
                bound_key="videoUplinkThroughputMbps",
            )
            delay_record = collector.record(
                "videoUplinkDelayMs",
                raw_delay,
                bound_key="videoUplinkDelayMs",
            )
            bler_record = collector.record(
                "videoUplinkBler",
                raw_bler,
                bound_key="videoUplinkBler",
            )
            throughput_values.append(throughput_record.clippedValue)
            delay_values.append(delay_record.clippedValue)
            bler_values.append(bler_record.clippedValue)
            video_results.append(
                VideoUserPerformance(
                    userId=user.userId,
                    videoUplinkThroughputMbps=throughput_record.clippedValue,
                    videoUplinkDelayMs=delay_record.clippedValue,
                    videoUplinkBler=bler_record.clippedValue,
                    outputDiagnostics={
                        "videoUplinkThroughputMbps": throughput_record,
                        "videoUplinkDelayMs": delay_record,
                        "videoUplinkBler": bler_record,
                    },
                )
            )

        quantile_method = self._simulation.statistics.quantile_method
        throughput_mean = float(np.mean(throughput_values))
        throughput_p05 = float(
            np.quantile(
                throughput_values,
                self._simulation.statistics.throughput_low_quantile,
                method=quantile_method,
            )
        )
        delay_mean = float(np.mean(delay_values))
        delay_p95 = float(
            np.quantile(
                delay_values,
                self._simulation.statistics.delay_high_quantile,
                method=quantile_method,
            )
        )
        bler_mean = float(np.mean(bler_values))
        satisfaction_ratio = sum(
            value >= self._simulation.sla.video.throughput_threshold_mbps
            for value in throughput_values
        ) / len(throughput_values)

        aggregate_records = {
            "videoUserSatisfactionRatio": collector.record(
                "videoUserSatisfactionRatio",
                satisfaction_ratio,
                bound_key="videoUserSatisfactionRatio",
            ),
            "videoThroughputMeanMbps": collector.record(
                "videoThroughputMeanMbps",
                throughput_mean,
                bound_key="videoUplinkThroughputMbps",
            ),
            "videoThroughputP05Mbps": collector.record(
                "videoThroughputP05Mbps",
                throughput_p05,
                bound_key="videoUplinkThroughputMbps",
            ),
            "videoDelayMeanMs": collector.record(
                "videoDelayMeanMs",
                delay_mean,
                bound_key="videoUplinkDelayMs",
            ),
            "videoDelayP95Ms": collector.record(
                "videoDelayP95Ms",
                delay_p95,
                bound_key="videoUplinkDelayMs",
            ),
            "videoUplinkBlerMean": collector.record(
                "videoUplinkBlerMean",
                bler_mean,
                bound_key="videoUplinkBler",
            ),
        }

        raw_voice = (
            state.voiceQualityScore
            + coefficients.voice.delta_v * v
            - coefficients.voice.delta_r * r
            - coefficients.voice.delta_e * e
            - coefficients.voice.delta_u * overload
        )
        voice_record = collector.record(
            "voiceQualityScore",
            raw_voice,
            bound_key="voiceQualityScore",
        )
        raw_voice_degradation = max(
            0.0, state.voiceQualityScore - voice_record.clippedValue
        )
        voice_degradation_record = collector.record(
            "voiceQualityDegradation",
            raw_voice_degradation,
            bound_key="voiceQualityDegradation",
        )

        high_cost_action_count = sum(
            self._action_definitions[action.type].isHighCostAction
            for action in policy.actions
        )
        raw_energy = state.baselineRanEnergy * (
            1
            - coefficients.energy.eta_e * e
            + coefficients.energy.eta_u
            * max(0.0, prb_after - state.prbUtilization)
            + coefficients.energy.eta_a * high_cost_action_count
        )
        energy_record = collector.record(
            "ranEnergy", raw_energy, bound_key="ranEnergy"
        )

        raw_normal_degradation = (
            coefficients.normal_user.zeta_r * r
            + coefficients.normal_user.zeta_w * (w - 1)
            + coefficients.normal_user.zeta_v * v
            + coefficients.normal_user.zeta_e * e
            + coefficients.normal_user.zeta_u
            * max(0.0, prb_after - state.prbUtilization)
        )
        normal_record = collector.record(
            "normalUserPerformanceDegradation",
            raw_normal_degradation,
            bound_key="normalUserPerformanceDegradation",
        )

        baseline_bler_mean = float(
            np.mean(
                [user.baselineUplinkBler for user in state.videoUsers]
            )
        )
        risk_records = self._risk_components(
            prb_after=prb_after,
            voice_after=voice_record.clippedValue,
            voice_degradation=voice_degradation_record.clippedValue,
            energy_intensity=e,
            active_action_count=len(policy.actions),
            normal_degradation=normal_record.clippedValue,
            bler_after=bler_mean,
            bler_baseline=baseline_bler_mean,
            collector=collector,
        )
        risk_values = {
            name: record.clippedValue
            for name, record in risk_records.items()
        }
        weights = coefficients.risk_weights
        raw_risk = (
            weights.omega_u * risk_values["overload"]
            + weights.omega_q
            * max(
                risk_values["voiceAbsoluteMargin"],
                risk_values["voiceBaselineDegradation"],
            )
            + weights.omega_e * risk_values["energyIntensity"]
            + weights.omega_a * risk_values["actionComplexity"]
            + weights.omega_f * risk_values["fairness"]
            + weights.omega_b * risk_values["blerDegradation"]
        )
        risk_record = collector.record(
            "riskScore", raw_risk, bound_key="riskScore"
        )

        output_diagnostics = {
            **aggregate_records,
            "prbUtilization": prb_record,
            "voiceQualityScore": voice_record,
            "voiceQualityDegradation": voice_degradation_record,
            "ranEnergy": energy_record,
            "normalUserPerformanceDegradation": normal_record,
            **{
                f"risk.{name}": record
                for name, record in risk_records.items()
            },
            "riskScore": risk_record,
        }
        summaries = collector.summaries()
        warnings = self._clipping_warnings(summaries)
        self._log_clipping_messages(summaries, warnings)

        return PolicyPerformanceResult(
            policyId=policy.policyId,
            generationRound=policy.generationRound,
            cellId=state.cellId,
            videoUsers=video_results,
            videoUserSatisfactionRatio=aggregate_records[
                "videoUserSatisfactionRatio"
            ].clippedValue,
            videoThroughputMeanMbps=aggregate_records[
                "videoThroughputMeanMbps"
            ].clippedValue,
            videoThroughputP05Mbps=aggregate_records[
                "videoThroughputP05Mbps"
            ].clippedValue,
            videoDelayMeanMs=aggregate_records[
                "videoDelayMeanMs"
            ].clippedValue,
            videoDelayP95Ms=aggregate_records[
                "videoDelayP95Ms"
            ].clippedValue,
            videoUplinkBlerMean=aggregate_records[
                "videoUplinkBlerMean"
            ].clippedValue,
            voiceQualityScore=voice_record.clippedValue,
            voiceQualityDegradation=voice_degradation_record.clippedValue,
            prbUtilization=prb_record.clippedValue,
            ranEnergy=energy_record.clippedValue,
            normalUserPerformanceDegradation=normal_record.clippedValue,
            riskScore=risk_record.clippedValue,
            riskComponents=risk_values,
            quantileMethod=quantile_method,
            performanceModelVersion=self._model.model_version,
            coefficientVersion=self._model.coefficient_version,
            randomSeed=self._random_seed,
            stochasticEnabled=self._model.stochastic_enabled,
            outputDiagnostics=output_diagnostics,
            clippingSummary=summaries,
            modelWarnings=warnings,
        )

    def evaluate_batch(
        self,
        ran_state: RANState,
        candidate_policies: Sequence[CandidatePolicy],
    ) -> PerformanceEvaluationBatch:
        if not candidate_policies:
            raise PerformanceEvaluationError(
                "candidate_policies must not be empty"
            )
        rounds = {policy.generationRound for policy in candidate_policies}
        if len(rounds) != 1:
            raise PerformanceEvaluationError(
                "one evaluation batch must use one generationRound"
            )
        results = [
            self.evaluate(
                PerformanceEvaluationInput(
                    ranState=ran_state,
                    candidatePolicy=policy,
                    modelConfigVersion=self._model.coefficient_version,
                )
            )
            for policy in candidate_policies
        ]
        summaries = self._aggregate_summaries(results)
        warnings = self._clipping_warnings(summaries)
        self._log_clipping_messages(summaries, warnings)
        return PerformanceEvaluationBatch(
            generationRound=next(iter(rounds)),
            results=results,
            clippingSummary=summaries,
            modelWarnings=warnings,
            performanceModelVersion=self._model.model_version,
            coefficientVersion=self._model.coefficient_version,
            randomSeed=self._random_seed,
            stochasticEnabled=self._model.stochastic_enabled,
        )

    def enforce_monotonicity_validation(
        self,
        violations: Sequence[str],
    ) -> list[str]:
        """Apply the configured fail-or-warn behavior to scoped validation."""

        if not violations:
            return []
        messages = [
            "configured-domain monotonicity violation: " + violation
            for violation in violations
        ]
        if self._model.fail_on_monotonicity_violation:
            raise MonotonicityViolationError("; ".join(messages))
        for message in messages:
            LOGGER.warning(message)
        return messages

    def _policy_parameters(
        self, policy: CandidatePolicy
    ) -> tuple[float, float, float, float]:
        neutral = self._model.neutral_parameters
        values = {
            "reservedPrbRatio": neutral.reserved_prb_ratio,
            "videoSchedulingWeight": neutral.video_scheduling_weight,
            "minimumVoicePrbRatio": neutral.minimum_voice_prb_ratio,
            "energySavingIntensity": neutral.energy_saving_intensity,
        }
        values.update(policy.parameters)
        return (
            float(values["reservedPrbRatio"]),
            float(values["videoSchedulingWeight"]),
            float(values["minimumVoicePrbRatio"]),
            float(values["energySavingIntensity"]),
        )

    def _risk_components(
        self,
        *,
        prb_after: float,
        voice_after: float,
        voice_degradation: float,
        energy_intensity: float,
        active_action_count: int,
        normal_degradation: float,
        bler_after: float,
        bler_baseline: float,
        collector: _ClippingCollector,
    ) -> dict[str, ClippedValue]:
        epsilon = self._model.risk.epsilon
        congestion = self._model.coefficients.capacity.u_cong
        voice_threshold = self._simulation.sla.voice.minimum_quality_score
        voice_margin = self._model.risk.voice_risk_margin
        maximum_voice_degradation = (
            self._simulation.sla.voice.maximum_degradation_from_baseline
        )
        normal_threshold = (
            self._simulation.risk.normal_user_maximum_degradation
        )
        energy_denominator = max(
            max(self._simulation.energy.saving_intensity_values), epsilon
        )
        raw_values = {
            "overload": (prb_after - congestion) / (1 - congestion),
            "voiceAbsoluteMargin": (
                voice_threshold + voice_margin - voice_after
            )
            / voice_margin,
            "voiceBaselineDegradation": voice_degradation
            / max(maximum_voice_degradation, epsilon),
            "energyIntensity": energy_intensity / energy_denominator,
            "actionComplexity": active_action_count
            / self._simulation.risk.maximum_active_action_count,
            "fairness": (
                normal_degradation - normal_threshold
            )
            / (1 - normal_threshold),
            "blerDegradation": max(0.0, bler_after - bler_baseline)
            / self._simulation.risk.bler_risk_scale,
        }
        return {
            name: collector.record(
                f"risk.{name}",
                raw,
                bound_key="riskComponent",
            )
            for name, raw in raw_values.items()
        }

    def _clipping_warnings(
        self,
        summaries: dict[str, MetricClippingSummary],
    ) -> list[str]:
        monitor = self._model.clipping_monitor
        warnings: list[str] = []
        for metric, summary in summaries.items():
            if (
                summary.evaluationCount
                >= monitor.warning_minimum_evaluations
                and summary.clippedCount / summary.evaluationCount
                >= monitor.warning_ratio
            ):
                warnings.append(
                    "performance model clipping ratio warning: "
                    f"metric={metric}, clipped={summary.clippedCount}, "
                    f"evaluated={summary.evaluationCount}"
                )
        return warnings

    @staticmethod
    def _log_clipping_messages(
        summaries: dict[str, MetricClippingSummary],
        messages: Sequence[str],
    ) -> None:
        """Log expected normalized-risk clipping below model-output clipping.

        ``modelWarnings`` remains unchanged for artifact compatibility.  The
        logger level communicates whether clipping is an expected boundary
        guard (normalized risk/utility) or a physical model-output condition
        requiring operator attention.
        """

        summary_by_message = {
            (
                "performance model clipping ratio warning: "
                f"metric={metric}, clipped={summary.clippedCount}, "
                f"evaluated={summary.evaluationCount}"
            ): metric
            for metric, summary in summaries.items()
        }
        for message in messages:
            metric = summary_by_message[message]
            if metric.startswith("risk.") or metric == "riskScore":
                LOGGER.info(message)
            else:
                LOGGER.warning(message)

    @staticmethod
    def _aggregate_summaries(
        results: Sequence[PolicyPerformanceResult],
    ) -> dict[str, MetricClippingSummary]:
        aggregate: dict[str, _MutableClippingSummary] = {}
        for result in results:
            for metric, summary in result.clippingSummary.items():
                target = aggregate.setdefault(
                    metric, _MutableClippingSummary()
                )
                target.evaluation_count += summary.evaluationCount
                target.clipped_count += summary.clippedCount
                target.maximum_magnitude = max(
                    target.maximum_magnitude,
                    summary.maximumClippingMagnitude,
                )
        return {
            metric: MetricClippingSummary(
                evaluationCount=value.evaluation_count,
                clippedCount=value.clipped_count,
                maximumClippingMagnitude=value.maximum_magnitude,
            )
            for metric, value in sorted(aggregate.items())
        }

    @staticmethod
    def _bounded(value: float, lower: float, upper: float) -> float:
        if not math.isfinite(value):
            raise PerformanceEvaluationError("non-finite intermediate value")
        return min(max(value, lower), upper)
