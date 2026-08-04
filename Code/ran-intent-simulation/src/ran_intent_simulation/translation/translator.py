"""Static-data-backed translation from business semantics to RAN requirements."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import timedelta

from ran_intent_simulation.config import (
    SimulationConfig,
    load_simulation_config,
)
from ran_intent_simulation.exceptions import RepositoryLookupError
from ran_intent_simulation.models.intent import (
    StructuredIntent,
    UnresolvedItem,
)
from ran_intent_simulation.models.translation import (
    ConfigurationRefs,
    EffectiveTime,
    IntentTranslationInput,
    ObjectiveRelationship,
    PerUserCondition,
    RANObjective,
    RANScope,
    SLAConstraint,
    SLATemplate,
    TargetUserRule,
    TranslatedRANIntent,
)
from ran_intent_simulation.translation.repositories import (
    StaticTranslationRepositories,
)


class IntentTranslator(ABC):
    """Replaceable translation contract."""

    @abstractmethod
    def translate(
        self, translation_input: IntentTranslationInput
    ) -> TranslatedRANIntent:
        """Translate one structured intent into RAN-only requirements."""


class StaticIntentTranslator(IntentTranslator):
    """First-version translator backed only by checked-in static files."""

    _HARD_CONSTRAINT_NAMES = {
        "videoUserSatisfactionRatio": "video_user_satisfaction",
        "videoDelayP95Ms": "video_delay_p95",
        "voiceQualityScore": "voice_quality_absolute",
        "voiceQualityDegradation": "voice_quality_degradation",
        "prbUtilization": "prb_limit",
    }
    _VIDEO_METRICS = {
        "videoUserSatisfactionRatio",
        "videoDelayP95Ms",
    }
    _VOICE_METRICS = {
        "voiceQualityScore",
        "voiceQualityDegradation",
    }

    def __init__(
        self,
        simulation_config: SimulationConfig,
        repositories: StaticTranslationRepositories,
    ) -> None:
        self._config = simulation_config
        self._repositories = repositories

    @classmethod
    def from_configuration_refs(
        cls, refs: ConfigurationRefs
    ) -> "StaticIntentTranslator":
        config = load_simulation_config(refs.resourceConstraints)
        repositories = StaticTranslationRepositories.from_configuration_refs(
            refs, config
        )
        return cls(config, repositories)

    def translate(
        self, translation_input: IntentTranslationInput
    ) -> TranslatedRANIntent:
        structured = translation_input.structuredIntent
        intent_names = {item.type for item in structured.intentTypes}
        has_service_assurance = "service_assurance" in intent_names
        has_energy_optimization = "energy_optimization" in intent_names
        has_service_protection = "service_protection" in intent_names

        event = self._resolve_event(structured)
        mapping = self._resolve_mapping(event.venueId) if event is not None else None
        target_user_rules = self._build_target_user_rules(
            structured,
            has_service_protection=has_service_protection,
        )
        scope = self._build_scope(event, mapping, target_user_rules)
        objectives = self._build_objectives(
            has_service_assurance=has_service_assurance,
            has_energy_optimization=has_energy_optimization,
            has_service_protection=has_service_protection,
        )
        sla_template = self._resolve_sla_template()
        constraints = self._build_sla_constraints(
            sla_template,
            has_service_assurance=has_service_assurance,
            has_service_protection=has_service_protection,
        )
        relationship = self._build_objective_relationship(
            objectives, constraints
        )
        unresolved = self._update_unresolved_items(
            structured,
            event_resolved=event is not None,
            scope_resolved=scope is not None,
            target_rules=target_user_rules,
            constraints=constraints,
            has_service_assurance=has_service_assurance,
            has_service_protection=has_service_protection,
        )
        status = (
            "blocked"
            if any(item.severity == "blocking" for item in unresolved)
            else "ready"
        )

        return TranslatedRANIntent(
            schemaVersion=structured.schemaVersion,
            intentId=structured.intentId,
            scope=scope,
            ranObjectives=objectives,
            slaConstraints=constraints,
            objectiveRelationship=relationship,
            unresolvedItems=unresolved,
            translationStatus=status,
        )

    def _resolve_event(self, structured: StructuredIntent):
        time_slot = structured.extractedSemantics.timeExpression
        if time_slot is None:
            return None
        event_type = "concert" if "???" in structured.originalText else None
        try:
            return self._repositories.events.find_unique(event_type=event_type)
        except RepositoryLookupError:
            return None

    def _resolve_mapping(self, venue_id: str):
        try:
            return self._repositories.venueMappings.get_by_venue_id(venue_id)
        except RepositoryLookupError:
            return None

    def _resolve_sla_template(self) -> SLATemplate:
        return self._repositories.slaTemplates.get_for_scenario(
            "concert_uplink_assurance"
        )

    def _build_scope(self, event, mapping, target_user_rules):
        if event is None or mapping is None or not target_user_rules:
            return None
        effective_time = EffectiveTime(
            eventStartTime=event.startTime,
            eventEndTime=event.endTime,
            effectiveStartTime=event.startTime
            - timedelta(minutes=self._config.time.pre_effective_minutes),
            effectiveEndTime=event.endTime
            + timedelta(minutes=self._config.time.post_effective_minutes),
            preWindowRef="time.pre_effective_minutes",
            postWindowRef="time.post_effective_minutes",
            source="event_database",
        )
        return RANScope(
            effectiveTime=effective_time,
            venueId=event.venueId,
            gnbIds=mapping.gnbIds,
            cellIds=mapping.cellIds,
            carrierIds=mapping.carrierIds,
            targetUserRules=target_user_rules,
            source="venue_cell_mapping",
        )

    @staticmethod
    def _build_target_user_rules(
        structured: StructuredIntent,
        *,
        has_service_protection: bool,
    ) -> list[TargetUserRule]:
        rules: list[TargetUserRule] = []
        if structured.extractedSemantics.targetService is not None:
            rules.append(
                TargetUserRule(
                    group="video",
                    serviceType="uplink_video",
                    source="static_user_identification_rule",
                )
            )
        if has_service_protection:
            rules.append(
                TargetUserRule(
                    group="voice",
                    serviceType="voice_service",
                    source="static_user_identification_rule",
                )
            )
        return rules

    @staticmethod
    def _build_objectives(
        *,
        has_service_assurance: bool,
        has_energy_optimization: bool,
        has_service_protection: bool,
    ) -> list[RANObjective]:
        objectives: list[RANObjective] = []
        if has_service_assurance:
            objectives.append(
                RANObjective(
                    name="video_uplink_assurance",
                    priority="primary",
                    source="business_intent_mapping",
                )
            )
        if has_energy_optimization:
            objectives.append(
                RANObjective(
                    name="ran_energy_optimization",
                    priority="secondary",
                    source="business_intent_mapping",
                )
            )
        if has_service_protection:
            objectives.append(
                RANObjective(
                    name="voice_service_protection",
                    priority="mandatory",
                    source="business_intent_mapping",
                )
            )
        return objectives

    def _build_sla_constraints(
        self,
        template: SLATemplate,
        *,
        has_service_assurance: bool,
        has_service_protection: bool,
    ) -> list[SLAConstraint]:
        constraints: list[SLAConstraint] = []
        for item in template.constraints:
            if item.metric in self._VIDEO_METRICS and not has_service_assurance:
                continue
            if item.metric in self._VOICE_METRICS and not has_service_protection:
                continue
            per_user_condition = None
            if (
                item.perUserMetric is not None
                and item.perUserThresholdRef is not None
            ):
                per_user_condition = PerUserCondition(
                    metric=item.perUserMetric,
                    operator=item.operator,
                    thresholdRef=item.perUserThresholdRef,
                )
            constraints.append(
                SLAConstraint(
                    metric=item.metric,
                    operator=item.operator,
                    thresholdRef=item.thresholdRef,
                    perUserCondition=per_user_condition,
                    source="sla_templates",
                )
            )
        return constraints

    def _build_objective_relationship(
        self,
        objectives: list[RANObjective],
        constraints: list[SLAConstraint],
    ) -> ObjectiveRelationship:
        objective_names = [objective.name for objective in objectives]
        if "video_uplink_assurance" in objective_names:
            primary = "video_uplink_assurance"
        elif "voice_service_protection" in objective_names:
            primary = "voice_service_protection"
        else:
            primary = "ran_energy_optimization"

        secondary = [
            name
            for name in (
                "ran_energy_optimization",
                "resource_efficiency",
                "risk_reduction",
            )
            if name != primary
        ]
        hard_constraints = [
            self._HARD_CONSTRAINT_NAMES[constraint.metric]
            for constraint in constraints
            if constraint.metric in self._HARD_CONSTRAINT_NAMES
        ]
        return ObjectiveRelationship(
            hardConstraints=hard_constraints,
            primaryObjective=primary,
            secondaryObjectives=secondary,
            source="business_intent_and_static_constraints",
        )

    @staticmethod
    def _update_unresolved_items(
        structured: StructuredIntent,
        *,
        event_resolved: bool,
        scope_resolved: bool,
        target_rules: list[TargetUserRule],
        constraints: list[SLAConstraint],
        has_service_assurance: bool,
        has_service_protection: bool,
    ) -> list[UnresolvedItem]:
        resolved_codes = {"objective_weights"}
        if event_resolved:
            resolved_codes.add("exact_time_period")
        if scope_resolved:
            resolved_codes.add("ran_scope")
        if any(rule.group == "video" for rule in target_rules):
            resolved_codes.add("video_service_identification")

        constraint_metrics = {constraint.metric for constraint in constraints}
        if (
            has_service_assurance
            and StaticIntentTranslator._VIDEO_METRICS.issubset(
                constraint_metrics
            )
        ):
            resolved_codes.add("uplink_experience_slo")
        if (
            has_service_protection
            and StaticIntentTranslator._VOICE_METRICS.issubset(
                constraint_metrics
            )
        ):
            resolved_codes.add("voice_protection_threshold")

        remaining = [
            item
            for item in structured.unresolvedItems
            if item.code not in resolved_codes
        ]
        required_blocking: list[str] = []
        if not event_resolved:
            required_blocking.append("exact_time_period")
        if not scope_resolved:
            required_blocking.append("ran_scope")
        if (
            has_service_assurance
            and "uplink_experience_slo" not in resolved_codes
        ):
            required_blocking.append("uplink_experience_slo")
        if (
            has_service_protection
            and "voice_protection_threshold" not in resolved_codes
        ):
            required_blocking.append("voice_protection_threshold")

        existing_codes = {item.code for item in remaining}
        remaining.extend(
            UnresolvedItem(code=code, severity="blocking")
            for code in required_blocking
            if code not in existing_codes
        )
        return remaining
