"""Command-line entry point for the end-to-end RAN intent simulation."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from ran_intent_simulation.exceptions import RANIntentSimulationError
from ran_intent_simulation.logging_config import configure_logging
from ran_intent_simulation.pipeline import PipelinePaths, SimulationPipeline


def build_parser() -> argparse.ArgumentParser:
    """Build the project command-line parser."""

    parser = argparse.ArgumentParser(
        description="Run the single-cell RAN intent simulation pipeline."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/simulation_config.yaml"),
        help="Path to simulation_config.yaml.",
    )
    parser.add_argument(
        "--action-library",
        type=Path,
        default=Path("config/action_library.json"),
    )
    parser.add_argument(
        "--sla-templates",
        type=Path,
        default=Path("config/sla_templates.json"),
    )
    parser.add_argument(
        "--intent-samples",
        type=Path,
        default=Path("data/intent_samples.json"),
    )
    parser.add_argument(
        "--event-database",
        type=Path,
        default=Path("data/event_database.json"),
    )
    parser.add_argument(
        "--venue-cell-mapping",
        type=Path,
        default=Path("data/venue_cell_mapping.json"),
    )
    parser.add_argument(
        "--ran-state-samples",
        type=Path,
        default=Path("data/ran_state_samples.csv"),
    )
    parser.add_argument(
        "--results-root",
        type=Path,
        default=Path("results"),
    )
    parser.add_argument("--run-id")
    parser.add_argument("--intent-id")
    parser.add_argument("--scenario-id")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the pipeline and return a process-compatible status code."""

    args = build_parser().parse_args(argv)
    logger = configure_logging(level=args.log_level)

    try:
        result = SimulationPipeline(
            paths=PipelinePaths(
                simulation_config=args.config,
                action_library=args.action_library,
                sla_templates=args.sla_templates,
                intent_samples=args.intent_samples,
                event_database=args.event_database,
                venue_cell_mapping=args.venue_cell_mapping,
                ran_state_samples=args.ran_state_samples,
            ),
            results_root=args.results_root,
            run_id=args.run_id,
            intent_id=args.intent_id,
            scenario_id=args.scenario_id,
        ).run()
    except RANIntentSimulationError as exc:
        logger.error("%s", exc)
        return 2

    logger.info(
        "Simulation completed: run_id=%s status=%s rounds=%s output=%s",
        result.runId,
        result.status,
        result.roundsCompleted,
        result.finalArtifact,
    )
    return 0
