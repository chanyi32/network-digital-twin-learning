"""Deterministic first-version policy templates."""

from __future__ import annotations

from dataclasses import dataclass

from ran_intent_simulation.models.policy import ActionType
from ran_intent_simulation.models.translation import TranslatedRANIntent


@dataclass(frozen=True, slots=True)
class PolicyTemplate:
    """Ordered action composition with a stable priority."""

    templateId: str
    priority: int
    actionTypes: tuple[ActionType, ...]


def build_policy_templates(
    translated_intent: TranslatedRANIntent,
) -> tuple[PolicyTemplate, ...]:
    """Map translated RAN objectives to a deterministic template sequence."""

    objective_names = {
        objective.name for objective in translated_intent.ranObjectives
    }
    has_assurance = "video_uplink_assurance" in objective_names
    has_voice_protection = "voice_service_protection" in objective_names
    has_energy = "ran_energy_optimization" in objective_names

    templates: list[PolicyTemplate] = [
        PolicyTemplate(templateId="baseline", priority=0, actionTypes=())
    ]
    voice_actions = (
        (ActionType.VOICE_RESOURCE_PROTECT,) if has_voice_protection else ()
    )

    assurance_templates: list[PolicyTemplate] = []
    if has_assurance:
        assurance_templates = [
            PolicyTemplate(
                templateId="scheduling_assurance",
                priority=10,
                actionTypes=(
                    ActionType.SCHEDULING_WEIGHT_ADJUST,
                    *voice_actions,
                ),
            ),
            PolicyTemplate(
                templateId="resource_assurance",
                priority=20,
                actionTypes=(
                    ActionType.UL_RESOURCE_RESERVE,
                    *voice_actions,
                ),
            ),
            PolicyTemplate(
                templateId="joint_assurance",
                priority=30,
                actionTypes=(
                    ActionType.UL_RESOURCE_RESERVE,
                    ActionType.SCHEDULING_WEIGHT_ADJUST,
                    *voice_actions,
                ),
            ),
        ]
        templates.extend(assurance_templates)
    elif has_voice_protection:
        templates.append(
            PolicyTemplate(
                templateId="voice_protection",
                priority=10,
                actionTypes=(ActionType.VOICE_RESOURCE_PROTECT,),
            )
        )

    if has_energy:
        if assurance_templates:
            for offset, template in enumerate(assurance_templates, start=1):
                templates.append(
                    PolicyTemplate(
                        templateId=f"{template.templateId}_with_energy",
                        priority=30 + offset * 10,
                        actionTypes=(
                            *template.actionTypes,
                            ActionType.RAN_ENERGY_SAVING,
                        ),
                    )
                )
        else:
            templates.append(
                PolicyTemplate(
                    templateId="energy_optimization",
                    priority=20,
                    actionTypes=(ActionType.RAN_ENERGY_SAVING,),
                )
            )

    return tuple(sorted(templates, key=lambda item: (item.priority, item.templateId)))
