"""Typed, read-only repositories for static translation data."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ran_intent_simulation.config import SimulationConfig
from ran_intent_simulation.exceptions import (
    AmbiguousRepositoryMatchError,
    RepositoryLookupError,
)
from ran_intent_simulation.io.loaders import (
    load_event_database,
    load_sla_templates,
    load_venue_cell_mapping,
)
from ran_intent_simulation.models.translation import (
    ConfigurationRefs,
    EventRecord,
    SLATemplate,
    VenueCellMapping,
)


@dataclass(frozen=True, slots=True)
class EventRepository:
    """Read-only event records with deterministic unique selection."""

    records: tuple[EventRecord, ...]

    @classmethod
    def from_file(cls, path: str | Path) -> "EventRepository":
        return cls(tuple(load_event_database(path)))

    def find_unique(
        self,
        *,
        event_type: str | None = None,
        venue_id: str | None = None,
    ) -> EventRecord:
        candidates = [
            record
            for record in self.records
            if (event_type is None or record.eventType == event_type)
            and (venue_id is None or record.venueId == venue_id)
        ]
        if not candidates:
            raise RepositoryLookupError("no event matches the translated intent")
        if len(candidates) != 1:
            raise AmbiguousRepositoryMatchError(
                "event lookup requires exactly one static match"
            )
        return candidates[0]


@dataclass(frozen=True, slots=True)
class VenueCellMappingRepository:
    """Read-only venue mapping with strict single-cell records."""

    records: tuple[VenueCellMapping, ...]

    @classmethod
    def from_file(cls, path: str | Path) -> "VenueCellMappingRepository":
        return cls(tuple(load_venue_cell_mapping(path)))

    def get_by_venue_id(self, venue_id: str) -> VenueCellMapping:
        candidates = [
            record for record in self.records if record.venueId == venue_id
        ]
        if not candidates:
            raise RepositoryLookupError(
                f"no venue-cell mapping found for venueId={venue_id}"
            )
        if len(candidates) != 1:
            raise AmbiguousRepositoryMatchError(
                f"venueId={venue_id} does not map uniquely"
            )
        mapping = candidates[0]
        if len(mapping.cellIds) != 1:
            raise AmbiguousRepositoryMatchError(
                "first-version translation requires exactly one selected cellId"
            )
        return mapping


@dataclass(frozen=True, slots=True)
class SLATemplateRepository:
    """Read-only SLA template repository."""

    template: SLATemplate

    @classmethod
    def from_file(
        cls,
        path: str | Path,
        simulation_config: SimulationConfig,
    ) -> "SLATemplateRepository":
        return cls(load_sla_templates(path, simulation_config))

    def get_for_scenario(self, scenario: str) -> SLATemplate:
        if self.template.scenario != scenario:
            raise RepositoryLookupError(
                f"no SLA template found for scenario={scenario}"
            )
        return self.template


@dataclass(frozen=True, slots=True)
class StaticTranslationRepositories:
    """All static repositories required by first-version translation."""

    events: EventRepository
    venueMappings: VenueCellMappingRepository
    slaTemplates: SLATemplateRepository

    @classmethod
    def from_configuration_refs(
        cls,
        refs: ConfigurationRefs,
        simulation_config: SimulationConfig,
    ) -> "StaticTranslationRepositories":
        return cls(
            events=EventRepository.from_file(refs.eventDatabase),
            venueMappings=VenueCellMappingRepository.from_file(
                refs.venueCellMapping
            ),
            slaTemplates=SLATemplateRepository.from_file(
                refs.slaTemplates, simulation_config
            ),
        )
