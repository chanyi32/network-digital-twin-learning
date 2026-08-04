"""Pydantic models and the YAML configuration loading entry point."""

from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from ran_intent_simulation.exceptions import (
    ConfigurationFileNotFoundError,
    ConfigurationValidationError,
)
from ran_intent_simulation.models.common import ensure_timezone_aware
from ran_intent_simulation.models.ran_state import RANState, VideoUserState


class StrictModel(BaseModel):
    """Base model that rejects unknown configuration keys."""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        allow_inf_nan=False,
    )


class VideoSLAConfig(StrictModel):
    """Video-service SLA assumptions."""

    throughput_threshold_mbps: float = Field(gt=0)
    required_user_satisfaction_ratio: float = Field(ge=0, le=1)
    delay_p95_threshold_ms: float = Field(gt=0)


class VoiceSLAConfig(StrictModel):
    """Voice-service protection assumptions."""

    minimum_quality_score: float = Field(ge=0, le=1)
    maximum_degradation_from_baseline: float = Field(ge=0, le=1)


class SLAConfig(StrictModel):
    """Configured SLA assumptions."""

    video: VideoSLAConfig
    voice: VoiceSLAConfig


class ResourceConfig(StrictModel):
    """RAN resource constraints."""

    maximum_prb_utilization: float = Field(gt=0, le=1)


class ValidationConfig(StrictModel):
    """Technical input-consistency tolerances."""

    available_prb_ratio_tolerance: float = Field(ge=0, lt=1)


class IntentExtractionConfidenceConfig(StrictModel):
    """Configured confidence values emitted by deterministic extraction rules."""

    service_assurance_intent: float = Field(ge=0, le=1)
    energy_optimization_intent: float = Field(ge=0, le=1)
    service_protection_intent: float = Field(ge=0, le=1)
    time_expression: float = Field(ge=0, le=1)
    location_expression: float = Field(ge=0, le=1)
    target_object: float = Field(ge=0, le=1)
    target_service: float = Field(ge=0, le=1)
    assurance_target: float = Field(ge=0, le=1)
    optimization_goal: float = Field(ge=0, le=1)
    protected_service: float = Field(ge=0, le=1)
    modifier: float = Field(ge=0, le=1)
    negation: float = Field(ge=0, le=1)


class IntentExtractionConfig(StrictModel):
    """Version and confidence configuration for rule-based extraction."""

    schema_version: str = Field(min_length=1)
    extraction_method: Literal["rule_based_v1"]
    confidence: IntentExtractionConfidenceConfig


QuantileMethod = Literal[
    "inverted_cdf",
    "averaged_inverted_cdf",
    "closest_observation",
    "interpolated_inverted_cdf",
    "hazen",
    "weibull",
    "linear",
    "median_unbiased",
    "normal_unbiased",
    "lower",
    "higher",
    "midpoint",
    "nearest",
]


class StatisticsConfig(StrictModel):
    """User-level aggregation settings."""

    throughput_low_quantile: float = Field(ge=0, le=1)
    delay_high_quantile: float = Field(ge=0, le=1)
    quantile_method: QuantileMethod


class RiskConfig(StrictModel):
    """Soft-risk thresholds."""

    normal_user_maximum_degradation: float = Field(ge=0, lt=1)
    bler_risk_scale: float = Field(gt=0, le=1)
    maximum_active_action_count: int = Field(gt=0)


class TimeWindowConfig(StrictModel):
    """Policy effective-time offsets."""

    pre_effective_minutes: int = Field(ge=0)
    post_effective_minutes: int = Field(ge=0)


class GenerationConfig(StrictModel):
    """Candidate-generation limits."""

    maximum_candidates_per_round: int = Field(gt=0)


class OptimizationConfig(StrictModel):
    """Feedback and convergence controls."""

    feedback_enabled: bool = True
    maximum_feedback_iterations: int = Field(gt=0)
    convergence_rounds: int = Field(gt=0)
    minimum_score_improvement: float = Field(ge=0)
    score_threshold: float = Field(ge=0, le=1)
    allow_disable_energy_objective: bool
    allow_expand_action_space: bool
    allow_relax_hard_constraints: Literal[False]


class ScoringWeights(StrictModel):
    """Top-level scoring weights."""

    service: float = Field(ge=0, le=1)
    energy: float = Field(ge=0, le=1)
    resource: float = Field(ge=0, le=1)
    risk: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_sum(self) -> "ScoringWeights":
        """Require normalized weights."""

        total = self.service + self.energy + self.resource + self.risk
        if not math.isclose(total, 1.0, rel_tol=0.0, abs_tol=1e-9):
            raise ValueError("scoring weights must sum to 1.0")
        return self


class ServiceScoringWeights(StrictModel):
    satisfaction: float = Field(ge=0, le=1)
    throughput_p05: float = Field(ge=0, le=1)
    delay_p95: float = Field(ge=0, le=1)
    bler: float = Field(ge=0, le=1)
    voice_quality: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_sum(self) -> "ServiceScoringWeights":
        total = (
            self.satisfaction
            + self.throughput_p05
            + self.delay_p95
            + self.bler
            + self.voice_quality
        )
        if not math.isclose(total, 1.0, rel_tol=0.0, abs_tol=1e-9):
            raise ValueError("service scoring weights must sum to 1.0")
        return self


class ResourceScoringWeights(StrictModel):
    prb_utilization: float = Field(ge=0, le=1)
    control_complexity: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_sum(self) -> "ResourceScoringWeights":
        if not math.isclose(
            self.prb_utilization + self.control_complexity,
            1.0,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise ValueError("resource scoring weights must sum to 1.0")
        return self


class ScoringNormalizationBound(StrictModel):
    minimum: float
    maximum: float

    @model_validator(mode="after")
    def validate_order(self) -> "ScoringNormalizationBound":
        if self.maximum <= self.minimum:
            raise ValueError(
                "scoring normalization maximum must exceed minimum"
            )
        return self


class ScoringNormalizationConfig(StrictModel):
    video_user_satisfaction_ratio: ScoringNormalizationBound
    video_throughput_p05_mbps: ScoringNormalizationBound
    video_delay_p95_ms: ScoringNormalizationBound
    video_uplink_bler_mean: ScoringNormalizationBound
    voice_quality_score: ScoringNormalizationBound
    energy_saving_ratio: ScoringNormalizationBound
    prb_utilization: ScoringNormalizationBound
    action_complexity: ScoringNormalizationBound
    policy_risk: ScoringNormalizationBound


class ScoringConfig(StrictModel):
    """Scoring and deterministic tie-break settings."""

    version: str = Field(min_length=1)
    weights: ScoringWeights
    service_weights: ServiceScoringWeights
    resource_weights: ResourceScoringWeights
    normalization_bounds: ScoringNormalizationConfig
    tie_break_order: list[str] = Field(min_length=1)

    @field_validator("tie_break_order")
    @classmethod
    def validate_tie_break_order(cls, values: list[str]) -> list[str]:
        allowed = {
            "resource_cost",
            "risk",
            "ran_energy",
            "action_count",
            "policy_id",
        }
        if len(values) != len(set(values)) or set(values) != allowed:
            raise ValueError(
                "tie_break_order must contain each supported key exactly once"
            )
        return values


class EnergyConfig(StrictModel):
    """Normalized RAN-energy assumptions."""

    baseline: float = Field(gt=0)
    saving_intensity_values: list[float] = Field(min_length=1)

    @field_validator("saving_intensity_values")
    @classmethod
    def validate_saving_intensities(cls, values: list[float]) -> list[float]:
        return _validate_ordered_unique_values(
            values, "saving_intensity_values", minimum=0.0, maximum=1.0
        )


class ActionSpaceConfig(StrictModel):
    """Discrete first-version action parameter spaces."""

    reserved_prb_ratio: list[float] = Field(min_length=1)
    video_scheduling_weight: list[float] = Field(min_length=1)
    minimum_voice_prb_ratio: list[float] = Field(min_length=1)

    @field_validator("reserved_prb_ratio", "minimum_voice_prb_ratio")
    @classmethod
    def validate_ratio_spaces(
        cls, values: list[float], info: Any
    ) -> list[float]:
        return _validate_ordered_unique_values(
            values, info.field_name, minimum=0.0, maximum=1.0
        )

    @field_validator("video_scheduling_weight")
    @classmethod
    def validate_weight_space(
        cls, values: list[float], info: Any
    ) -> list[float]:
        return _validate_ordered_unique_values(
            values, info.field_name, minimum=0.0
        )


class ReproducibilityConfig(StrictModel):
    """Reproducibility controls."""

    random_seed: int


class PerformanceModelConfig(StrictModel):
    """Reference to a required versioned performance-model file."""

    version: str = Field(min_length=1)
    config_file: str = Field(min_length=1)


class NeutralParameterConfig(StrictModel):
    reserved_prb_ratio: float
    video_scheduling_weight: float
    minimum_voice_prb_ratio: float
    energy_saving_intensity: float

    @model_validator(mode="after")
    def validate_baseline_identity(self) -> "NeutralParameterConfig":
        if (
            self.reserved_prb_ratio != 0
            or self.video_scheduling_weight != 1
            or self.minimum_voice_prb_ratio != 0
            or self.energy_saving_intensity != 0
        ):
            raise ValueError("neutral parameters must be r=0, w=1, v=0, e=0")
        return self


class CapacityCoefficientConfig(StrictModel):
    k_E: float = Field(ge=0)
    phi_min: float = Field(gt=0, le=1)
    k_r: float = Field(ge=0)
    k_v: float = Field(ge=0)
    u_cong: float = Field(ge=0, lt=1)


class ThroughputCoefficientConfig(StrictModel):
    alpha_r: float = Field(ge=0)
    alpha_w: float = Field(ge=0)
    alpha_c: float = Field(ge=0)
    sinr_gain_per_db: float = Field(ge=0)
    sinr_reference_db: float
    sinr_factor_min: float = Field(gt=0)
    sinr_factor_max: float = Field(gt=0)

    @model_validator(mode="after")
    def validate_factor_bounds(self) -> "ThroughputCoefficientConfig":
        if not self.sinr_factor_min <= 1 <= self.sinr_factor_max:
            raise ValueError("SINR factor bounds must contain 1")
        return self


class DelayCoefficientConfig(StrictModel):
    beta_u: float = Field(ge=0)
    beta_e: float = Field(ge=0)
    beta_r: float = Field(ge=0)
    beta_w: float = Field(ge=0)


class BlerCoefficientConfig(StrictModel):
    chi_u: float = Field(ge=0)
    chi_r: float = Field(ge=0)
    chi_w: float = Field(ge=0)


class VoiceCoefficientConfig(StrictModel):
    delta_v: float = Field(ge=0)
    delta_r: float = Field(ge=0)
    delta_e: float = Field(ge=0)
    delta_u: float = Field(ge=0)


class EnergyCoefficientConfig(StrictModel):
    eta_e: float = Field(ge=0)
    eta_u: float = Field(ge=0)
    eta_a: float = Field(ge=0)


class NormalUserCoefficientConfig(StrictModel):
    zeta_r: float = Field(ge=0)
    zeta_w: float = Field(ge=0)
    zeta_v: float = Field(ge=0)
    zeta_e: float = Field(ge=0)
    zeta_u: float = Field(ge=0)


class RiskWeightConfig(StrictModel):
    omega_u: float = Field(ge=0, le=1)
    omega_q: float = Field(ge=0, le=1)
    omega_e: float = Field(ge=0, le=1)
    omega_a: float = Field(ge=0, le=1)
    omega_f: float = Field(ge=0, le=1)
    omega_b: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_sum(self) -> "RiskWeightConfig":
        total = sum(
            (
                self.omega_u,
                self.omega_q,
                self.omega_e,
                self.omega_a,
                self.omega_f,
                self.omega_b,
            )
        )
        if not math.isclose(total, 1.0, rel_tol=0.0, abs_tol=1e-9):
            raise ValueError("performance-model risk weights must sum to 1")
        return self


class ModelCoefficientConfig(StrictModel):
    capacity: CapacityCoefficientConfig
    throughput: ThroughputCoefficientConfig
    delay: DelayCoefficientConfig
    bler: BlerCoefficientConfig
    voice: VoiceCoefficientConfig
    energy: EnergyCoefficientConfig
    normal_user: NormalUserCoefficientConfig
    risk_weights: RiskWeightConfig


class PerformanceRiskConfig(StrictModel):
    epsilon: float = Field(gt=0)
    voice_risk_margin: float = Field(gt=0, le=1)
    bler_risk_scale_ref: Literal["risk.bler_risk_scale"]
    maximum_active_action_count_ref: Literal[
        "risk.maximum_active_action_count"
    ]


class OutputBoundConfig(StrictModel):
    lowerBound: float
    upperBound: float

    @model_validator(mode="after")
    def validate_order(self) -> "OutputBoundConfig":
        if self.upperBound <= self.lowerBound:
            raise ValueError("output upperBound must exceed lowerBound")
        return self


class ClippingMonitorConfig(StrictModel):
    warning_ratio: float = Field(gt=0, le=1)
    warning_minimum_evaluations: int = Field(gt=0)


class MonotonicityScenarioConfig(StrictModel):
    scenarioId: str = Field(min_length=1)
    timestamp: datetime
    cellId: str = Field(min_length=1)
    cellLoad: float
    prbUtilization: float
    availablePrbRatio: float
    videoUserCount: int
    voiceUserCount: int
    normalUserCount: int
    videoThroughputMeanMbps: float
    videoThroughputP05Mbps: float
    videoDelayMeanMs: float
    videoDelayP95Ms: float
    videoUplinkBlerMean: float
    voiceQualityScore: float
    baselineRanEnergy: float
    meanSinrDb: float
    normalUserPerformanceIndex: float
    videoUsers: list[VideoUserState]

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, value: datetime) -> datetime:
        return ensure_timezone_aware(value)

    @model_validator(mode="after")
    def validate_as_ran_state(self) -> "MonotonicityScenarioConfig":
        RANState.model_validate(
            {
                key: value
                for key, value in self.model_dump().items()
                if key != "scenarioId"
            }
            | {"quantileMethod": "validation_only_not_used_for_aggregation"}
        )
        return self

    def to_ran_state(
        self,
        quantile_method: QuantileMethod,
    ) -> RANState:
        """Convert the configured validation scenario to the domain model."""

        return RANState.model_validate(
            {
                key: value
                for key, value in self.model_dump().items()
                if key != "scenarioId"
            }
            | {"quantileMethod": quantile_method}
        )


class SimplifiedRANModelConfig(StrictModel):
    model_version: Literal["simplified-ran-v1"]
    coefficient_version: str = Field(min_length=1)
    scope: Literal["single_cell_ran_only"]
    applicability: str = Field(min_length=1)
    stochastic_enabled: Literal[False]
    fail_on_monotonicity_violation: bool
    neutral_parameters: NeutralParameterConfig
    coefficients: ModelCoefficientConfig
    risk: PerformanceRiskConfig
    output_bounds: dict[str, OutputBoundConfig]
    clipping_monitor: ClippingMonitorConfig
    formula_definitions: dict[str, str]
    monotonicity_validation_scenarios: list[MonotonicityScenarioConfig] = Field(
        min_length=3
    )

    @model_validator(mode="after")
    def validate_required_outputs_and_scenarios(
        self,
    ) -> "SimplifiedRANModelConfig":
        required_bounds = {
            "prbUtilization",
            "videoUplinkThroughputMbps",
            "videoUplinkDelayMs",
            "videoUplinkBler",
            "videoUserSatisfactionRatio",
            "voiceQualityScore",
            "voiceQualityDegradation",
            "ranEnergy",
            "normalUserPerformanceDegradation",
            "riskComponent",
            "riskScore",
        }
        if set(self.output_bounds) != required_bounds:
            raise ValueError("performance_model.output_bounds keys are incomplete")
        scenario_ids = [
            scenario.scenarioId
            for scenario in self.monotonicity_validation_scenarios
        ]
        if len(scenario_ids) != len(set(scenario_ids)):
            raise ValueError("monotonicity scenario IDs must be unique")
        return self


class PerformanceModelFile(StrictModel):
    schema_version: str = Field(min_length=1)
    parameter_nature: Literal["simulation_assumption"]
    status: Literal["confirmed_for_simplified_simulation_v1"]
    performance_model: SimplifiedRANModelConfig


class SimulationConfig(StrictModel):
    """Root simulation configuration."""

    schema_version: str = Field(min_length=1)
    parameter_nature: Literal["simulation_assumption"]
    sla: SLAConfig
    resources: ResourceConfig
    validation: ValidationConfig
    intent_extraction: IntentExtractionConfig
    statistics: StatisticsConfig
    risk: RiskConfig
    time: TimeWindowConfig
    generation: GenerationConfig
    optimization: OptimizationConfig
    scoring: ScoringConfig
    energy: EnergyConfig
    action_space: ActionSpaceConfig
    reproducibility: ReproducibilityConfig
    performance_model: PerformanceModelConfig


def _validate_ordered_unique_values(
    values: list[float],
    field_name: str,
    *,
    minimum: float,
    maximum: float | None = None,
) -> list[float]:
    """Validate a deterministic numeric search space without supplying values."""

    if any(value < minimum for value in values):
        raise ValueError(f"{field_name} contains a value below {minimum}")
    if maximum is not None and any(value > maximum for value in values):
        raise ValueError(f"{field_name} contains a value above {maximum}")
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must not contain duplicates")
    if values != sorted(values):
        raise ValueError(f"{field_name} must be ordered ascending")
    return values


def load_simulation_config(path: str | Path) -> SimulationConfig:
    """Load and validate a YAML simulation configuration file."""

    config_path = Path(path)
    if not config_path.is_file():
        raise ConfigurationFileNotFoundError(
            f"Configuration file not found: {config_path}"
        )

    try:
        raw_data: Any = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigurationValidationError(
            f"Unable to read YAML configuration: {config_path}"
        ) from exc

    if not isinstance(raw_data, dict):
        raise ConfigurationValidationError(
            f"Configuration root must be a mapping: {config_path}"
        )

    try:
        return SimulationConfig.model_validate(raw_data)
    except ValidationError as exc:
        raise ConfigurationValidationError(
            f"Invalid simulation configuration: {config_path}"
        ) from exc


def load_performance_model_config(
    path: str | Path,
) -> PerformanceModelFile:
    """Load the complete versioned simplified-RAN model configuration."""

    config_path = Path(path)
    if not config_path.is_file():
        raise ConfigurationFileNotFoundError(
            f"Performance model configuration not found: {config_path}"
        )
    try:
        raw_data: Any = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigurationValidationError(
            f"Unable to read performance model YAML: {config_path}"
        ) from exc
    try:
        return PerformanceModelFile.model_validate(raw_data)
    except ValidationError as exc:
        raise ConfigurationValidationError(
            f"Invalid performance model configuration: {config_path}"
        ) from exc
