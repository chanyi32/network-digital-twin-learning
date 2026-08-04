"""Deterministic first-version business-intent extractor."""

from __future__ import annotations

import re
from collections.abc import Iterable
from re import Match

from ran_intent_simulation.config import IntentExtractionConfig
from ran_intent_simulation.exceptions import UnsupportedIntentError
from ran_intent_simulation.intent.base import IntentExtractor
from ran_intent_simulation.models.intent import (
    ExtractedSemantics,
    IntentExtractionInput,
    IntentType,
    LogicalRelations,
    SemanticRelation,
    SemanticSlot,
    StructuredIntent,
    UnresolvedItem,
)


class RuleBasedIntentExtractor(IntentExtractor):
    """Extract the documented concert-assurance intent using local rules only."""

    _TIME_PATTERN = re.compile(
        r"(?:??|??|??|??|??|??[????????]|?[????????])?"
        r"(?:?)?(?:???|??)?(?:??|??|??)"
    )
    _LOCATION_PATTERN = re.compile(
        r"(?:???|???|??|?????)(?:?|??|??)?"
    )
    _VIDEO_PATTERN = re.compile(r"(?:????|????|??)")
    _UPLINK_PATTERN = re.compile(r"(?:????|??????|????|??)")
    _ENERGY_PATTERN = re.compile(
        r"(?:(?:??|???|????)?"
        r"(?:??|??|??)(?:RAN|?????|??)???|??)"
    )
    _VOICE_PATTERN = re.compile(r"(?:????|????|??)")
    _ASSURANCE_PATTERN = re.compile(r"(?:??|??|??|??|??)")
    _PROTECTION_PATTERN = re.compile(
        r"(?:(?:???|??|??|??|??).{0,8}(?:????|????|??)"
        r"|(?:????|????|??).{0,8}(?:????|??))"
    )
    _BEST_EFFORT_PATTERN = re.compile(r"(?:??|???|????)")
    _NON_DEGRADATION_PATTERN = re.compile(r"(?:???|????)")
    _CONJUNCTION_PATTERN = re.compile(r"(?:??|??|?)")

    def __init__(self, config: IntentExtractionConfig) -> None:
        self._config = config

    def extract(self, extraction_input: IntentExtractionInput) -> StructuredIntent:
        """Apply ordered local rules and return the stable extraction schema."""

        text = self._normalize_text(extraction_input.originalText)
        matches = {
            "time": self._TIME_PATTERN.search(text),
            "location": self._LOCATION_PATTERN.search(text),
            "video": self._VIDEO_PATTERN.search(text),
            "uplink": self._UPLINK_PATTERN.search(text),
            "energy": self._ENERGY_PATTERN.search(text),
            "voice": self._VOICE_PATTERN.search(text),
            "assurance": self._ASSURANCE_PATTERN.search(text),
            "protection": self._PROTECTION_PATTERN.search(text),
            "best_effort": self._BEST_EFFORT_PATTERN.search(text),
            "non_degradation": self._NON_DEGRADATION_PATTERN.search(text),
            "conjunction": self._CONJUNCTION_PATTERN.search(text),
        }

        has_service_assurance = bool(
            matches["assurance"] and (matches["video"] or matches["uplink"])
        )
        has_energy_optimization = matches["energy"] is not None
        has_service_protection = bool(
            matches["voice"] and matches["protection"]
        )

        intent_types = self._build_intent_types(
            has_service_assurance,
            has_energy_optimization,
            has_service_protection,
        )
        if not intent_types:
            raise UnsupportedIntentError(
                "no supported RAN intent was identified in originalText"
            )

        semantics = self._build_semantics(
            matches, has_service_protection=has_service_protection
        )
        relations = self._build_relations(
            semantics,
            has_service_assurance=has_service_assurance,
            has_energy_optimization=has_energy_optimization,
            has_service_protection=has_service_protection,
        )
        unresolved_items = self._build_unresolved_items(
            semantics,
            has_service_assurance=has_service_assurance,
            has_energy_optimization=has_energy_optimization,
            has_service_protection=has_service_protection,
        )

        combination = (
            "conjunction"
            if matches["conjunction"] is not None or len(intent_types) > 1
            else "single_intent"
        )
        logical_relations = LogicalRelations(
            combination=combination,
            energyOptimizationType=(
                "soft_objective" if has_energy_optimization else None
            ),
            voiceProtectionType=(
                "hard_constraint" if has_service_protection else None
            ),
        )

        return StructuredIntent(
            schemaVersion=self._config.schema_version,
            intentId=extraction_input.intentId,
            originalText=extraction_input.originalText,
            intentTypes=intent_types,
            extractedSemantics=semantics,
            semanticRelations=relations,
            logicalRelations=logical_relations,
            unresolvedItems=unresolved_items,
            extractionMethod=self._config.extraction_method,
        )

    @staticmethod
    def _normalize_text(text: str) -> str:
        return re.sub(r"\s+", "", text).replace("?", ",").replace("?", ".")

    def _build_intent_types(
        self,
        has_service_assurance: bool,
        has_energy_optimization: bool,
        has_service_protection: bool,
    ) -> list[IntentType]:
        confidence = self._config.confidence
        intent_types: list[IntentType] = []
        if has_service_assurance:
            intent_types.append(
                IntentType(
                    type="service_assurance",
                    confidence=confidence.service_assurance_intent,
                )
            )
        if has_energy_optimization:
            intent_types.append(
                IntentType(
                    type="energy_optimization",
                    confidence=confidence.energy_optimization_intent,
                )
            )
        if has_service_protection:
            intent_types.append(
                IntentType(
                    type="service_protection",
                    confidence=confidence.service_protection_intent,
                )
            )
        return intent_types

    def _build_semantics(
        self,
        matches: dict[str, Match[str] | None],
        *,
        has_service_protection: bool,
    ) -> ExtractedSemantics:
        confidence = self._config.confidence
        video_match = matches["video"]
        return ExtractedSemantics(
            timeExpression=self._slot(
                matches["time"],
                normalized_value=None,
                source="explicit_text",
                confidence=confidence.time_expression,
            ),
            locationExpression=self._slot(
                matches["location"],
                normalized_value="stadium",
                source="dictionary_normalization",
                confidence=confidence.location_expression,
            ),
            targetObject=self._slot(
                video_match,
                normalized_value="video_users",
                source="normalized_from_explicit_text",
                confidence=confidence.target_object,
            ),
            targetService=self._slot(
                video_match,
                normalized_value="uplink_video",
                source="normalized_from_explicit_text",
                confidence=confidence.target_service,
            ),
            assuranceTarget=self._slot(
                matches["uplink"],
                normalized_value="uplink_experience",
                source="explicit_text",
                confidence=confidence.assurance_target,
            ),
            optimizationGoal=self._slot(
                matches["energy"],
                normalized_value="minimize_ran_energy",
                source="explicit_text",
                confidence=confidence.optimization_goal,
            ),
            protectedService=self._slot(
                matches["voice"] if has_service_protection else None,
                normalized_value="voice_service",
                source="explicit_text",
                confidence=confidence.protected_service,
            ),
            modifier=self._slot(
                matches["best_effort"],
                normalized_value="best_effort",
                source="explicit_text",
                confidence=confidence.modifier,
            ),
            negation=self._slot(
                matches["non_degradation"],
                normalized_value="non_degradation",
                source="explicit_text",
                confidence=confidence.negation,
            ),
        )

    @staticmethod
    def _slot(
        match: Match[str] | None,
        *,
        normalized_value: str | None,
        source: str,
        confidence: float,
    ) -> SemanticSlot | None:
        if match is None:
            return None
        return SemanticSlot(
            rawText=match.group(0),
            normalizedValue=normalized_value,
            source=source,
            confidence=confidence,
        )

    @staticmethod
    def _build_relations(
        semantics: ExtractedSemantics,
        *,
        has_service_assurance: bool,
        has_energy_optimization: bool,
        has_service_protection: bool,
    ) -> list[SemanticRelation]:
        relations: list[SemanticRelation] = []
        if has_service_assurance:
            relations.append(
                SemanticRelation(
                    relation="assure", object="video_uplink_experience"
                )
            )
        if has_energy_optimization:
            relations.append(
                SemanticRelation(
                    relation="minimize",
                    object="ran_energy_consumption",
                    modifier=(
                        "best_effort" if semantics.modifier is not None else None
                    ),
                )
            )
        if has_service_protection:
            relations.append(
                SemanticRelation(
                    relation="protect",
                    object="voice_service",
                    constraintType="non_degradation",
                )
            )
        if semantics.timeExpression is not None:
            relations.append(
                SemanticRelation(relation="temporal_scope", object="intent")
            )
        if semantics.locationExpression is not None:
            relations.append(
                SemanticRelation(relation="spatial_scope", object="intent")
            )
        return relations

    @staticmethod
    def _build_unresolved_items(
        semantics: ExtractedSemantics,
        *,
        has_service_assurance: bool,
        has_energy_optimization: bool,
        has_service_protection: bool,
    ) -> list[UnresolvedItem]:
        unresolved: list[UnresolvedItem] = [
            UnresolvedItem(code="exact_time_period", severity="blocking"),
            UnresolvedItem(code="ran_scope", severity="blocking"),
        ]
        if semantics.targetService is None:
            unresolved.append(
                UnresolvedItem(
                    code="video_service_identification", severity="blocking"
                )
            )
        if has_service_assurance:
            unresolved.append(
                UnresolvedItem(code="uplink_experience_slo", severity="blocking")
            )
        if has_service_protection:
            unresolved.append(
                UnresolvedItem(
                    code="voice_protection_threshold", severity="blocking"
                )
            )
        if has_energy_optimization or has_service_assurance:
            unresolved.append(
                UnresolvedItem(code="objective_weights", severity="non_blocking")
            )
        return RuleBasedIntentExtractor._deduplicate_unresolved(unresolved)

    @staticmethod
    def _deduplicate_unresolved(
        items: Iterable[UnresolvedItem],
    ) -> list[UnresolvedItem]:
        by_code: dict[str, UnresolvedItem] = {}
        for item in items:
            by_code.setdefault(item.code, item)
        return list(by_code.values())
