"""Replaceable performance-evaluation interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from ran_intent_simulation.models.evaluation import (
    PerformanceEvaluationBatch,
    PerformanceEvaluationInput,
    PolicyPerformanceResult,
)
from ran_intent_simulation.models.policy import CandidatePolicy
from ran_intent_simulation.models.ran_state import RANState


class RANPerformanceEvaluator(ABC):
    """Common boundary for the simplified model and a future twin adapter."""

    @abstractmethod
    def evaluate(
        self,
        evaluation_input: PerformanceEvaluationInput,
    ) -> PolicyPerformanceResult:
        """Evaluate one candidate policy against one fixed RAN state."""

    @abstractmethod
    def evaluate_batch(
        self,
        ran_state: RANState,
        candidate_policies: Sequence[CandidatePolicy],
    ) -> PerformanceEvaluationBatch:
        """Evaluate one candidate generation round and aggregate diagnostics."""
