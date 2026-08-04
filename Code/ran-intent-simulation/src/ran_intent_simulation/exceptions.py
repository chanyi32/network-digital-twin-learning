"""Project-specific exception hierarchy."""


class RANIntentSimulationError(Exception):
    """Base exception for the RAN intent simulation project."""


class ConfigurationError(RANIntentSimulationError):
    """Base exception for configuration failures."""


class ConfigurationFileNotFoundError(ConfigurationError):
    """Raised when a requested configuration file does not exist."""


class ConfigurationValidationError(ConfigurationError):
    """Raised when configuration content cannot be parsed or validated."""


class DataError(RANIntentSimulationError):
    """Base exception for external simulation-data failures."""


class DataFileNotFoundError(DataError):
    """Raised when a requested simulation-data file does not exist."""


class DataLoadingError(DataError):
    """Raised when serialized input cannot be decoded."""


class DataValidationError(DataError):
    """Raised when decoded input violates a data contract."""


class SingleCellValidationError(DataValidationError):
    """Raised when a single run contains zero or multiple cell identifiers."""


class IntentExtractionError(RANIntentSimulationError):
    """Base exception for deterministic intent-extraction failures."""


class UnsupportedIntentError(IntentExtractionError):
    """Raised when no supported first-version intent can be identified."""


class IntentTranslationError(RANIntentSimulationError):
    """Base exception for static intent-translation failures."""


class RepositoryLookupError(IntentTranslationError):
    """Raised when a required static repository entry cannot be resolved."""


class AmbiguousRepositoryMatchError(RepositoryLookupError):
    """Raised when static data does not identify exactly one entry."""


class PolicyGenerationError(RANIntentSimulationError):
    """Raised when candidate policies cannot be generated from valid inputs."""


class PerformanceEvaluationError(RANIntentSimulationError):
    """Raised when the simplified RAN evaluator cannot produce a valid result."""


class MonotonicityViolationError(PerformanceEvaluationError):
    """Raised when configured-domain monotonicity validation fails."""


class ScoringError(RANIntentSimulationError):
    """Base exception for hard-constraint and policy-scoring failures."""


class ConstraintEvaluationError(ScoringError):
    """Raised when a hard constraint cannot be evaluated."""


class NormalizationError(ScoringError):
    """Raised when fixed normalization bounds or inputs are invalid."""


class FeedbackOptimizationError(RANIntentSimulationError):
    """Raised when feedback optimization inputs or configuration are invalid."""


class PipelineError(RANIntentSimulationError):
    """Base exception for end-to-end pipeline failures."""


class PipelineStageError(PipelineError):
    """Add the failing module name while preserving the original exception."""

    def __init__(self, stage: str, message: str) -> None:
        self.stage = stage
        super().__init__(f"{stage} failed: {message}")
