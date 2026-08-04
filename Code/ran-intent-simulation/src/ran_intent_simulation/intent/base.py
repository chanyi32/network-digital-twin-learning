"""Replaceable interface for business-intent extraction."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ran_intent_simulation.models.intent import (
    IntentExtractionInput,
    StructuredIntent,
)


class IntentExtractor(ABC):
    """Convert one validated natural-language request into a stable contract."""

    @abstractmethod
    def extract(self, extraction_input: IntentExtractionInput) -> StructuredIntent:
        """Extract a structured, RAN-oriented business intent."""
