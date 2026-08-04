"""Business-intent extraction interfaces and local rule implementation."""

from ran_intent_simulation.intent.base import IntentExtractor
from ran_intent_simulation.intent.rule_based import RuleBasedIntentExtractor

__all__ = ["IntentExtractor", "RuleBasedIntentExtractor"]
