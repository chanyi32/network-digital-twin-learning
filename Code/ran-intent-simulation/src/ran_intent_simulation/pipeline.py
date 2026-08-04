"""End-to-end, single-cell RAN intent simulation pipeline."""

from __future__ import annotations

import math
import logging
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypeVar

import pandas as pd
import numpy as np

from ran_intent_simulation import __version__
from ran_intent_simulation.config import (
    PerformanceModelFile,
    SimplifiedRANModelConfig,
    SimulationConfig,
    StatisticsConfig,
    load_performance_model_config,
    load_simulation_config,
)
from ran_intent_simulation.exceptions import (
    DataValidationError,
    PipelineStageError,
)
from ran_intent_simulation.feedback import (
    FeedbackOptimizationResult,
    FeedbackOptimizer,
)
from ran_intent_simulation.intent import RuleBasedIntentExtractor
from ran_intent_simulation.io import (
    load_action_library,
    load_intent_samples,
    load_ran_state_samples,
    load_sla_templates,
    sha256_file,
    write_csv,
    write_json,
)
from ran_intent_simulation.models.evaluation import (
    PolicyPerformanceResult,
    PolicyScore,
)
from ran_intent_simulation.models.intent import IntentExtractionInput
from ran_intent_simulation.models.policy import (
    ActionLibrary,
    CandidatePolicy,
)
from ran_intent_simulation.models.ran_state import RANState, VideoUserState
from ran_intent_simulation.models.translation import (
    ConfigurationRefs,
    IntentTranslationInput,
    SLATemplate,
    TranslatedRANIntent,
)
from ran_intent_simulation.performance import SimplifiedRANPerformanceEvaluator
from ran_intent_simulation.policy import CandidatePolicyGenerator
from ran_intent_simulation.scoring import PolicyScorer
from ran_intent_simulation.scoring.normalization import (
    normalize_cost,
    normalize_gain,
)
from ran_intent_simulation.translation import StaticIntentTranslator


ResultT = TypeVar("ResultT")
LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PipelinePaths:
    """All externally supplied files used by one reproducible run."""

    simulation_config: Path = Path("config/simulation_config.yaml")
    action_library: Path = Path("config/action_library.json")
    sla_templates: Path = Path("config/sla_templates.json")
    intent_samples: Path = Path("data/intent_samples.json")
    event_database: Path = Path("data/event_database.json")
    venue_cell_mapping: Path = Path("data/venue_cell_mapping.json")
    ran_state_samples: Path = Path("data/ran_state_samples.csv")

    def input_files(self, performance_model: Path) -> dict[str, Path]:
        return {
            "simulationConfig": self.simulation_config,
            "performanceModelConfig": performance_model,
            "actionLibrary": self.action_library,
            "slaTemplates": self.sla_templates,
            "intentSamples": self.intent_samples,
            "eventDatabase": self.event_database,
            "venueCellMapping": self.venue_cell_mapping,
            "ranStateSamples": self.ran_state_samples,
        }


@dataclass(frozen=True, slots=True)
class PipelineRunResult:
    """Small programmatic handoff after all detailed artifacts are written."""

    runId: str
    runDirectory: Path
    status: str
    roundsCompleted: int
    finalArtifact: Path


class SimulationPipeline:
    """Run the complete RAN-only intent decision and feedback loop."""

    _SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")

    def __init__(
        self,
        *,
        paths: PipelinePaths | None = None,
        results_root: str | Path = "results",
        run_id: str | None = None,
        intent_id: str | None = None,
        scenario_id: str | None = None,
    ) -> None:
        self.paths = paths or PipelinePaths()
        self.results_root = Path(results_root)
        self.run_id = run_id or datetime.now(timezone.utc).strftime(
            "run-%Y%m%dT%H%M%S-%fZ"
        )
        if not self._SAFE_RUN_ID.fullmatch(self.run_id):
            raise ValueError(
                "run_id may contain only letters, digits, dot, underscore, and dash"
            )
        self.intent_id = intent_id
        self.scenario_id = scenario_id
        self.run_directory = self.results_root / self.run_id
        self._active_stage = "initialization"

    def run(self) -> PipelineRunResult:
        """Execute all modules, persist every round, and return the final artifact."""

        if self.run_directory.exists() and any(self.run_directory.iterdir()):
            raise PipelineStageError(
                "initialization",
                f"run directory already contains files: {self.run_directory}",
            )
        self.run_directory.mkdir(parents=True, exist_ok=True)
        manifest: dict[str, Any] = {
            "runId": self.run_id,
            "startedAt": datetime.now(timezone.utc).isoformat(),
            "completedAt": None,
            "codeVersion": __version__,
            "status": "running",
            "outcome": None,
            "errorSummary": None,
            "roundsCompleted": 0,
            "inputFiles": {},
            "inputFileHashes": {},
            "versions": {},
            "feedbackEnabled": True,
            "feedbackIterations": 0,
            "generationRounds": 0,
            "terminationReason": None,
        }

        try:
            config = self._stage(
                "configuration_loading",
                lambda: load_simulation_config(self.paths.simulation_config),
            )
            performance_file = self._stage(
                "performance_configuration_loading",
                lambda: load_performance_model_config(
                    config.performance_model.config_file
                ),
            )
            input_files = self.paths.input_files(
                Path(config.performance_model.config_file)
            )
            hashes = self._stage(
                "input_hashing",
                lambda: {
                    name: sha256_file(path)
                    for name, path in input_files.items()
                },
            )
            action_library = self._stage(
                "action_library_loading",
                lambda: load_action_library(
                    self.paths.action_library,
                    config,
                ),
            )
            sla_template = self._stage(
                "sla_template_loading",
                lambda: load_sla_templates(
                    self.paths.sla_templates,
                    config,
                ),
            )
            manifest["inputFiles"] = {
                name: str(path) for name, path in input_files.items()
            }
            manifest["inputFileHashes"] = hashes
            manifest["versions"] = self._version_manifest(
                config,
                performance_file,
                action_library,
                sla_template,
            )
            manifest["randomSeed"] = config.reproducibility.random_seed
            manifest["feedbackEnabled"] = (
                config.optimization.feedback_enabled
            )

            extraction_input = self._stage(
                "intent_input_loading",
                self._load_intent_input,
            )
            structured_intent = self._stage(
                "intent_extraction",
                lambda: RuleBasedIntentExtractor(
                    config.intent_extraction
                ).extract(extraction_input),
            )
            self._stage(
                "intent_extraction_output",
                lambda: write_json(
                    self.run_directory / "extracted_intents.json",
                    [structured_intent],
                ),
            )

            refs = ConfigurationRefs(
                eventDatabase=str(self.paths.event_database),
                venueCellMapping=str(self.paths.venue_cell_mapping),
                slaTemplates=str(self.paths.sla_templates),
                resourceConstraints=str(self.paths.simulation_config),
            )
            translated_intent = self._stage(
                "intent_translation",
                lambda: StaticIntentTranslator.from_configuration_refs(
                    refs
                ).translate(
                    IntentTranslationInput(
                        structuredIntent=structured_intent,
                        configurationRefs=refs,
                    )
                ),
            )
            if translated_intent.translationStatus != "ready":
                raise PipelineStageError(
                    "intent_translation",
                    "translationStatus is blocked; "
                    f"unresolvedItems={translated_intent.unresolvedItems}",
                )
            self._stage(
                "intent_translation_output",
                lambda: write_json(
                    self.run_directory / "translated_intents.json",
                    [translated_intent],
                ),
            )

            ran_state = self._stage(
                "ran_state_loading",
                lambda: self._load_ran_state(config, translated_intent),
            )
            policies = self._stage(
                "policy_generation",
                lambda: CandidatePolicyGenerator(
                    config,
                    action_library,
                ).generate(translated_intent).policies,
            )
            evaluator = SimplifiedRANPerformanceEvaluator(
                config,
                performance_file.performance_model,
                action_library,
            )
            scorer = PolicyScorer(config)
            optimizer = (
                FeedbackOptimizer(
                    config,
                    action_library,
                    performance_file.performance_model.neutral_parameters,
                )
                if config.optimization.feedback_enabled
                else None
            )

            all_feasible: list[tuple[PolicyScore, CandidatePolicy]] = []
            all_scores: list[PolicyScore] = []
            all_policies: dict[str, CandidatePolicy] = {}
            best_score_history: list[float] = []
            rounds_completed = 0
            feedback_iterations = 0
            termination_reason = "search_space_exhausted"

            while policies:
                round_number = policies[0].generationRound
                if any(
                    policy.generationRound != round_number
                    for policy in policies
                ):
                    raise PipelineStageError(
                        "policy_generation",
                        "one pipeline round contains multiple generationRound values",
                    )
                batch = self._stage(
                    "performance_evaluation",
                    lambda: evaluator.evaluate_batch(ran_state, policies),
                )
                scores = self._stage(
                    "policy_scoring",
                    lambda: scorer.score_and_rank(policies, batch.results),
                )
                self._log_hard_constraint_clipping_changes(scores)
                policy_by_id = {
                    policy.policyId: policy for policy in policies
                }
                all_policies.update(policy_by_id)
                self._log_top_policy_clipping_change(
                    scores,
                    policy_by_id,
                    config,
                    performance_file.performance_model,
                    scope=f"round_{round_number:03d}",
                )
                for score in scores:
                    if score.feasible:
                        all_feasible.append(
                            (score, policy_by_id[score.policyId])
                        )
                all_scores.extend(scores)
                round_best = max(
                    (score.totalScore for score in scores),
                    default=0.0,
                )

                if not config.optimization.feedback_enabled:
                    self._stage(
                        "round_output",
                        lambda: self._write_round(
                            round_number,
                            policies,
                            batch.results,
                            scores,
                            None,
                            batch.modelWarnings,
                        ),
                    )
                    rounds_completed += 1
                    manifest["roundsCompleted"] = rounds_completed
                    manifest["generationRounds"] = rounds_completed
                    termination_reason = "feedback_disabled"
                    break

                if optimizer is None:
                    raise PipelineStageError(
                        "feedback_optimization",
                        "feedback optimizer is unavailable while feedback is enabled",
                    )
                parent_score = self._select_feedback_parent(scores)
                parent_policy = policy_by_id[parent_score.policyId]
                feedback_result = self._stage(
                    "feedback_optimization",
                    lambda: optimizer.optimize(
                        parent_policy,
                        parent_score,
                        feedback_iteration=round_number,
                        best_score_history=best_score_history,
                    ),
                )
                best_score_history.append(round_best)
                self._stage(
                    "round_output",
                    lambda: self._write_round(
                        round_number,
                        policies,
                        batch.results,
                        scores,
                        feedback_result,
                        batch.modelWarnings,
                    ),
                )
                rounds_completed += 1
                manifest["roundsCompleted"] = rounds_completed
                manifest["generationRounds"] = rounds_completed

                if feedback_result.status != "continue":
                    termination_reason = (
                        feedback_result.stopReason
                        or str(feedback_result.status)
                    )
                    break
                feedback_iterations += 1
                policies = feedback_result.candidatePolicies

            final_artifact: Path
            if all_feasible:
                best_score, best_policy = sorted(
                    all_feasible,
                    key=self._recommendation_key,
                )[0]
                model_warnings = self._recommended_policy_model_warnings(
                    best_score
                )
                self._log_final_recommendation_clipping_change(
                    best_policy.policyId,
                    all_scores,
                    all_policies,
                    config,
                    performance_file.performance_model,
                )
                for warning in model_warnings:
                    LOGGER.warning(warning)
                final_artifact = self.run_directory / "final_recommendation.json"
                self._stage(
                    "final_recommendation_output",
                    lambda: write_json(
                        final_artifact,
                        {
                            "status": "recommended",
                            "terminationReason": termination_reason,
                            "policy": best_policy,
                            "score": best_score,
                            "modelWarning": model_warnings,
                        },
                    ),
                )
                outcome = "feasible_policy_recommended"
                status = "completed"
            else:
                final_artifact = self.run_directory / "no_feasible_policy.json"
                self._stage(
                    "no_feasible_policy_output",
                    lambda: write_json(
                        final_artifact,
                        self._no_feasible_payload(
                            all_scores,
                            rounds_completed,
                            termination_reason,
                        ),
                    ),
                )
                outcome = "no_feasible_policy"
                status = "completed_no_feasible_policy"

            manifest.update(
                {
                    "status": status,
                    "outcome": outcome,
                    "completedAt": datetime.now(timezone.utc).isoformat(),
                    "roundsCompleted": rounds_completed,
                    "generationRounds": rounds_completed,
                    "feedbackIterations": feedback_iterations,
                    "terminationReason": termination_reason,
                }
            )
            self._stage(
                "run_manifest_output",
                lambda: write_json(
                    self.run_directory / "run_manifest.json",
                    manifest,
                ),
            )
            return PipelineRunResult(
                runId=self.run_id,
                runDirectory=self.run_directory,
                status=status,
                roundsCompleted=rounds_completed,
                finalArtifact=final_artifact,
            )
        except Exception as exc:
            manifest.update(
                {
                    "status": "failed",
                    "completedAt": datetime.now(timezone.utc).isoformat(),
                    "errorSummary": {
                        "stage": getattr(exc, "stage", self._active_stage),
                        "type": type(exc).__name__,
                        "message": str(exc),
                    },
                }
            )
            try:
                write_json(self.run_directory / "run_manifest.json", manifest)
            except Exception as manifest_exc:
                raise PipelineStageError(
                    "run_manifest_output",
                    "unable to record pipeline failure; "
                    f"original_error={exc}",
                ) from manifest_exc
            if isinstance(exc, PipelineStageError):
                raise
            raise PipelineStageError(self._active_stage, str(exc)) from exc

    def _load_intent_input(self) -> IntentExtractionInput:
        samples = load_intent_samples(self.paths.intent_samples)
        if self.intent_id is None:
            sample = samples[0]
        else:
            matches = [
                sample
                for sample in samples
                if sample.intentId == self.intent_id
            ]
            if len(matches) != 1:
                raise DataValidationError(
                    f"intentId must match exactly one sample: {self.intent_id}"
                )
            sample = matches[0]
        return IntentExtractionInput(
            intentId=sample.intentId,
            originalText=sample.originalText,
            requestTime=sample.requestTime,
            context=None,
        )

    def _load_ran_state(
        self,
        config: SimulationConfig,
        translated: TranslatedRANIntent,
    ) -> RANState:
        frame = load_ran_state_samples(
            self.paths.ran_state_samples,
            config,
        )
        state = ran_state_from_frame(
            frame,
            statistics=config.statistics,
            scenario_id=self.scenario_id,
        )
        if translated.scope is None:
            raise DataValidationError("translated intent has no RAN scope")
        if translated.scope.cellIds != [state.cellId]:
            raise DataValidationError(
                "translated target cell does not match RAN state cell"
            )
        return state

    def _write_round(
        self,
        round_number: int,
        policies: Sequence[CandidatePolicy],
        performance_results: Sequence[PolicyPerformanceResult],
        scores: Sequence[PolicyScore],
        feedback: FeedbackOptimizationResult | None,
        model_warnings: Sequence[str],
    ) -> None:
        round_directory = (
            self.run_directory / f"round_{round_number:03d}"
        )
        write_json(round_directory / "candidate_policies.json", policies)
        write_json(
            round_directory / "performance_results.json",
            performance_results,
        )
        write_csv(
            round_directory / "performance_results.csv",
            self._performance_rows(performance_results),
        )
        write_csv(
            round_directory / "constraint_checks.csv",
            self._constraint_rows(scores),
        )
        write_csv(
            round_directory / "policy_scores.csv",
            self._score_rows(scores),
        )
        write_json(round_directory / "ranked_policies.json", scores)
        if feedback is not None:
            write_json(round_directory / "feedback.json", feedback)
        feasible_scores = [score for score in scores if score.feasible]
        write_json(
            round_directory / "round_summary.json",
            {
                "generationRound": round_number,
                "candidateCount": len(policies),
                "feasibleCount": len(feasible_scores),
                "infeasibleCount": len(scores) - len(feasible_scores),
                "bestPolicyId": (
                    feasible_scores[0].policyId if feasible_scores else None
                ),
                "bestTotalScore": (
                    feasible_scores[0].totalScore
                    if feasible_scores
                    else 0.0
                ),
                "feedbackStatus": (
                    feedback.status if feedback is not None else "disabled"
                ),
                "modelWarnings": list(model_warnings),
            },
        )

    @staticmethod
    def _performance_rows(
        results: Sequence[PolicyPerformanceResult],
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for result in results:
            for user in result.videoUsers:
                rows.append(
                    {
                        "policyId": result.policyId,
                        "generationRound": result.generationRound,
                        "cellId": result.cellId,
                        "userId": user.userId,
                        "videoUplinkThroughputMbps": (
                            user.videoUplinkThroughputMbps
                        ),
                        "videoUplinkDelayMs": user.videoUplinkDelayMs,
                        "videoUplinkBler": user.videoUplinkBler,
                        "videoUserSatisfactionRatio": (
                            result.videoUserSatisfactionRatio
                        ),
                        "videoThroughputMeanMbps": (
                            result.videoThroughputMeanMbps
                        ),
                        "videoThroughputP05Mbps": (
                            result.videoThroughputP05Mbps
                        ),
                        "videoDelayMeanMs": result.videoDelayMeanMs,
                        "videoDelayP95Ms": result.videoDelayP95Ms,
                        "videoUplinkBlerMean": result.videoUplinkBlerMean,
                        "voiceQualityScore": result.voiceQualityScore,
                        "voiceQualityDegradation": (
                            result.voiceQualityDegradation
                        ),
                        "prbUtilization": result.prbUtilization,
                        "ranEnergy": result.ranEnergy,
                        "normalUserPerformanceDegradation": (
                            result.normalUserPerformanceDegradation
                        ),
                        "riskScore": result.riskScore,
                        "riskComponents": result.riskComponents,
                    }
                )
        return rows

    @staticmethod
    def _constraint_rows(
        scores: Sequence[PolicyScore],
    ) -> list[dict[str, Any]]:
        return [
            {
                "policyId": score.policyId,
                "feasible": score.feasible,
                "metric": check.metric,
                "operator": check.operator,
                "thresholdRef": check.thresholdRef,
                "actualValue": check.actualValue,
                "thresholdValue": check.thresholdValue,
                "passed": check.passed,
                "violation": check.violation,
            }
            for score in scores
            for check in score.constraintCheck.checks
        ]

    @staticmethod
    def _score_rows(
        scores: Sequence[PolicyScore],
    ) -> list[dict[str, Any]]:
        return [
            {
                "policyId": score.policyId,
                "generationRound": score.performance.generationRound,
                "feasible": score.feasible,
                "serviceScore": score.serviceScore,
                "energyScore": score.energyScore,
                "resourceScore": score.resourceScore,
                "riskScore": score.riskScore,
                "totalScore": score.totalScore,
                "rank": score.rank,
                "normalizedMetrics": score.normalizedMetrics,
                "scoreConfigVersion": score.scoreConfigVersion,
            }
            for score in scores
        ]

    @staticmethod
    def _select_feedback_parent(
        scores: Sequence[PolicyScore],
    ) -> PolicyScore:
        if not scores:
            raise DataValidationError("cannot optimize an empty score collection")
        feasible = [score for score in scores if score.feasible]
        if feasible:
            return min(feasible, key=lambda score: score.rank or math.inf)
        return sorted(
            scores,
            key=lambda score: (
                -score.serviceScore,
                -score.resourceScore,
                -score.riskScore,
                score.performance.prbUtilization,
                score.policyId,
            ),
        )[0]

    @staticmethod
    def _recommendation_key(
        item: tuple[PolicyScore, CandidatePolicy],
    ) -> tuple[float, float, float, float, int, str]:
        score, policy = item
        return (
            -round(score.totalScore, 12),
            score.performance.prbUtilization,
            score.performance.riskScore,
            score.performance.ranEnergy,
            len(policy.actions),
            policy.policyId,
        )

    @staticmethod
    def _recommended_policy_model_warnings(
        score: PolicyScore,
    ) -> list[str]:
        """Describe non-risk output clipping on the recommended policy."""

        clipped_outputs = [
            (
                metric,
                record.rawValue,
                record.clippedValue,
            )
            for metric, record in score.performance.outputDiagnostics.items()
            if record.wasClipped
            and not metric.startswith("risk.")
            and metric != "riskScore"
        ]
        if not clipped_outputs:
            return []
        details = ", ".join(
            f"{metric}(raw={raw:g}, clipped={clipped:g})"
            for metric, raw, clipped in sorted(clipped_outputs)
        )
        return [
            "recommended policy contains non-risk performance output "
            f"clipping: {details}"
        ]

    @staticmethod
    def _log_hard_constraint_clipping_changes(
        scores: Sequence[PolicyScore],
    ) -> None:
        """Emit ERROR when a model-output clip changes a hard decision."""

        comparisons = {
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
        for score in scores:
            diagnostics = score.performance.outputDiagnostics
            for check in score.constraintCheck.checks:
                record = diagnostics.get(check.metric)
                if record is None or not record.wasClipped:
                    continue
                comparison = comparisons[str(check.operator)]
                raw_passed = comparison(
                    record.rawValue,
                    check.thresholdValue,
                )
                if raw_passed != check.passed:
                    LOGGER.error(
                        "performance clipping changed hard-constraint "
                        "decision: policyId=%s, metric=%s, raw=%s, "
                        "clipped=%s, threshold=%s, operator=%s",
                        score.policyId,
                        check.metric,
                        record.rawValue,
                        record.clippedValue,
                        check.thresholdValue,
                        check.operator,
                    )

    @classmethod
    def _log_top_policy_clipping_change(
        cls,
        scores: Sequence[PolicyScore],
        policies: dict[str, CandidatePolicy],
        config: SimulationConfig,
        model: SimplifiedRANModelConfig,
        *,
        scope: str,
    ) -> None:
        actual = next(
            (score.policyId for score in scores if score.rank == 1),
            None,
        )
        counterfactual = cls._raw_clipping_order(
            scores,
            policies,
            config,
            model,
        )
        raw_top = counterfactual[0] if counterfactual else None
        if actual != raw_top:
            LOGGER.error(
                "performance clipping changed top policy: scope=%s, "
                "rawTopPolicyId=%s, clippedTopPolicyId=%s",
                scope,
                raw_top,
                actual,
            )

    @classmethod
    def _log_final_recommendation_clipping_change(
        cls,
        recommended_policy_id: str,
        scores: Sequence[PolicyScore],
        policies: dict[str, CandidatePolicy],
        config: SimulationConfig,
        model: SimplifiedRANModelConfig,
    ) -> None:
        counterfactual = cls._raw_clipping_order(
            scores,
            policies,
            config,
            model,
        )
        raw_top = counterfactual[0] if counterfactual else None
        if recommended_policy_id != raw_top:
            LOGGER.error(
                "performance clipping changed final recommendation: "
                "rawPolicyId=%s, clippedPolicyId=%s",
                raw_top,
                recommended_policy_id,
            )

    @classmethod
    def _raw_clipping_order(
        cls,
        scores: Sequence[PolicyScore],
        policies: dict[str, CandidatePolicy],
        config: SimulationConfig,
        model: SimplifiedRANModelConfig,
    ) -> list[str]:
        """Rank feasible policies using raw diagnostic values, read-only."""

        ranked: list[tuple[tuple[object, ...], str]] = []
        for score in scores:
            policy = policies[score.policyId]
            raw = cls._raw_clipping_score(score, policy, config, model)
            if raw is None:
                continue
            total, prb, risk, energy = raw
            tie_values: dict[str, object] = {
                "resource_cost": prb,
                "risk": risk,
                "ran_energy": energy,
                "action_count": len(policy.actions),
                "policy_id": policy.policyId,
            }
            key = (
                -round(total, 12),
                *(
                    tie_values[name]
                    for name in config.scoring.tie_break_order
                ),
            )
            ranked.append((key, policy.policyId))
        return [policy_id for _, policy_id in sorted(ranked)]

    @staticmethod
    def _raw_clipping_score(
        score: PolicyScore,
        policy: CandidatePolicy,
        config: SimulationConfig,
        model: SimplifiedRANModelConfig,
    ) -> tuple[float, float, float, float] | None:
        diagnostics = score.performance.outputDiagnostics

        def raw(metric: str, clipped: float) -> float:
            record = diagnostics.get(metric)
            return record.rawValue if record is not None else clipped

        for check in score.constraintCheck.checks:
            actual = raw(check.metric, check.actualValue)
            passed = {
                ">=": actual >= check.thresholdValue,
                "<=": actual <= check.thresholdValue,
                ">": actual > check.thresholdValue,
                "<": actual < check.thresholdValue,
                "==": math.isclose(
                    actual,
                    check.thresholdValue,
                    rel_tol=0.0,
                    abs_tol=1e-12,
                ),
            }[str(check.operator)]
            if not passed:
                return None

        performance = score.performance
        risk_components = {
            name: raw(
                f"risk.{name}",
                performance.riskComponents[name],
            )
            for name in performance.riskComponents
        }
        weights = model.coefficients.risk_weights
        policy_risk = (
            weights.omega_u * risk_components["overload"]
            + weights.omega_q
            * max(
                risk_components["voiceAbsoluteMargin"],
                risk_components["voiceBaselineDegradation"],
            )
            + weights.omega_e * risk_components["energyIntensity"]
            + weights.omega_a * risk_components["actionComplexity"]
            + weights.omega_f * risk_components["fairness"]
            + weights.omega_b * risk_components["blerDegradation"]
        )
        prb = raw("prbUtilization", performance.prbUtilization)
        energy = raw("ranEnergy", performance.ranEnergy)
        bounds = config.scoring.normalization_bounds
        normalized = {
            "satisfaction": normalize_gain(
                raw(
                    "videoUserSatisfactionRatio",
                    performance.videoUserSatisfactionRatio,
                ),
                bounds.video_user_satisfaction_ratio,
            ),
            "throughput": normalize_gain(
                raw(
                    "videoThroughputP05Mbps",
                    performance.videoThroughputP05Mbps,
                ),
                bounds.video_throughput_p05_mbps,
            ),
            "delay": normalize_cost(
                raw("videoDelayP95Ms", performance.videoDelayP95Ms),
                bounds.video_delay_p95_ms,
            ),
            "bler": normalize_cost(
                raw(
                    "videoUplinkBlerMean",
                    performance.videoUplinkBlerMean,
                ),
                bounds.video_uplink_bler_mean,
            ),
            "voice": normalize_gain(
                raw("voiceQualityScore", performance.voiceQualityScore),
                bounds.voice_quality_score,
            ),
            "energy": normalize_gain(
                (config.energy.baseline - energy)
                / config.energy.baseline,
                bounds.energy_saving_ratio,
            ),
            "prb": normalize_cost(
                prb,
                bounds.prb_utilization,
            ),
            "complexity": normalize_cost(
                len(policy.actions),
                bounds.action_complexity,
            ),
            "risk": normalize_cost(
                policy_risk,
                bounds.policy_risk,
            ),
        }
        service_weights = config.scoring.service_weights
        service = (
            service_weights.satisfaction * normalized["satisfaction"]
            + service_weights.throughput_p05 * normalized["throughput"]
            + service_weights.delay_p95 * normalized["delay"]
            + service_weights.bler * normalized["bler"]
            + service_weights.voice_quality * normalized["voice"]
        )
        resource_weights = config.scoring.resource_weights
        resource = (
            resource_weights.prb_utilization * normalized["prb"]
            + resource_weights.control_complexity
            * normalized["complexity"]
        )
        scoring_weights = config.scoring.weights
        total = (
            scoring_weights.service * service
            + scoring_weights.energy * normalized["energy"]
            + scoring_weights.resource * resource
            + scoring_weights.risk * normalized["risk"]
        )
        return min(1.0, max(0.0, total)), prb, policy_risk, energy

    @staticmethod
    def _no_feasible_payload(
        scores: Sequence[PolicyScore],
        rounds_completed: int,
        termination_reason: str,
    ) -> dict[str, Any]:
        minimum_gaps: dict[str, float] = {}
        violations: set[str] = set()
        for score in scores:
            for check in score.constraintCheck.checks:
                if check.passed:
                    continue
                gap = _constraint_gap(
                    str(check.operator),
                    check.actualValue,
                    check.thresholdValue,
                )
                current = minimum_gaps.get(check.metric)
                minimum_gaps[check.metric] = (
                    gap if current is None else min(current, gap)
                )
                if check.violation:
                    violations.add(check.violation)
        return {
            "status": "no_feasible_policy",
            "terminationReason": termination_reason,
            "roundsCompleted": rounds_completed,
            "attemptedPolicyCount": len(scores),
            "minimumViolationGaps": minimum_gaps,
            "violationReasons": sorted(violations),
            "hardConstraintsRelaxed": False,
            "recommendation": (
                "Manually review the SLA assumptions, RAN state, or configured "
                "action capability; no hard constraint was relaxed."
            ),
        }

    @staticmethod
    def _version_manifest(
        config: SimulationConfig,
        performance: PerformanceModelFile,
        action_library: ActionLibrary,
        sla_template: SLATemplate,
    ) -> dict[str, str]:
        return {
            "simulationConfigSchema": config.schema_version,
            "actionLibrary": action_library.version,
            "slaTemplate": sla_template.templateVersion,
            "performanceModelImplementation": (
                performance.performance_model.model_version
            ),
            "performanceCoefficientVersion": (
                performance.performance_model.coefficient_version
            ),
            "scoringConfig": config.scoring.version,
        }

    def _stage(
        self,
        name: str,
        operation: Callable[[], ResultT],
    ) -> ResultT:
        self._active_stage = name
        try:
            return operation()
        except PipelineStageError:
            raise
        except Exception as exc:
            raise PipelineStageError(name, str(exc)) from exc


def ran_state_from_frame(
    frame: pd.DataFrame,
    *,
    statistics: StatisticsConfig,
    scenario_id: str | None = None,
) -> RANState:
    """Aggregate one scenario using the required validated statistics config."""

    scenario_ids = list(dict.fromkeys(frame["scenarioId"].astype(str)))
    selected_id = scenario_id or scenario_ids[0]
    selected = frame[frame["scenarioId"].astype(str) == selected_id]
    if selected.empty:
        raise DataValidationError(f"unknown RAN scenarioId: {selected_id}")

    video = selected[selected["userType"] == "video"]
    throughput = video["baselineUplinkThroughputMbps"].astype(float).to_numpy()
    delay = video["baselineUplinkDelayMs"].astype(float).to_numpy()
    bler = video["baselineUplinkBler"].astype(float).to_numpy()
    first = selected.iloc[0]
    return RANState(
        timestamp=pd.Timestamp(first["timestamp"]).to_pydatetime(),
        cellId=str(first["cellId"]),
        cellLoad=float(first["cellLoad"]),
        prbUtilization=float(first["prbUtilization"]),
        availablePrbRatio=float(first["availablePrbRatio"]),
        videoUserCount=int((selected["userType"] == "video").sum()),
        voiceUserCount=int((selected["userType"] == "voice").sum()),
        normalUserCount=int((selected["userType"] == "normal").sum()),
        videoUsers=[
            VideoUserState(
                userId=str(row["userId"]),
                baselineUplinkThroughputMbps=float(
                    row["baselineUplinkThroughputMbps"]
                ),
                baselineUplinkDelayMs=float(row["baselineUplinkDelayMs"]),
                baselineUplinkBler=float(row["baselineUplinkBler"]),
                meanSinrDb=float(row["meanSinrDb"]),
            )
            for _, row in video.iterrows()
        ],
        videoThroughputMeanMbps=float(np.mean(throughput)),
        videoThroughputP05Mbps=float(
            np.quantile(
                throughput,
                statistics.throughput_low_quantile,
                method=statistics.quantile_method,
            )
        ),
        videoDelayMeanMs=float(np.mean(delay)),
        videoDelayP95Ms=float(
            np.quantile(
                delay,
                statistics.delay_high_quantile,
                method=statistics.quantile_method,
            )
        ),
        videoUplinkBlerMean=float(np.mean(bler)),
        voiceQualityScore=float(first["baselineVoiceQuality"]),
        baselineRanEnergy=float(first["baselineRanEnergy"]),
        meanSinrDb=float(first["meanSinrDb"]),
        normalUserPerformanceIndex=float(
            first["baselineNormalUserPerformance"]
        ),
        quantileMethod=statistics.quantile_method,
    )


def _constraint_gap(
    operator: str,
    actual: float,
    threshold: float,
) -> float:
    if operator in {">=", ">"}:
        return max(0.0, threshold - actual)
    if operator in {"<=", "<"}:
        return max(0.0, actual - threshold)
    return abs(actual - threshold)
