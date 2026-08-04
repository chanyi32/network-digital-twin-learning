"""Command-line entry points for experiment batches."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from experiments.config import ExperimentName, load_experiment_config
from experiments.runner import ExperimentRunner


DEFAULT_CONFIGS: dict[str, Path] = {
    name: Path(__file__).resolve().parent / "configs" / f"{name}.yaml"
    for name in (
        "baseline_e2e",
        "load_sweep",
        "feedback_compare",
        "weight_sensitivity",
    )
}


def run_entrypoint(
    experiment_name: ExperimentName | None = None,
    argv: Sequence[str] | None = None,
) -> int:
    """Run one named experiment or accept the name as a CLI argument."""

    parser = argparse.ArgumentParser(
        description="Run reproducible RAN intent simulation experiments."
    )
    if experiment_name is None:
        parser.add_argument(
            "experiment_name",
            choices=sorted(DEFAULT_CONFIGS),
        )
    parser.add_argument("--config", type=Path)
    parser.add_argument("--batch-id")
    parser.add_argument("--output-root", type=Path)
    arguments = parser.parse_args(argv)

    selected_name = experiment_name or arguments.experiment_name
    config_path = arguments.config or DEFAULT_CONFIGS[selected_name]
    config = load_experiment_config(config_path)
    if config.experiment_name != selected_name:
        parser.error(
            "experiment_name in YAML does not match the selected entry point"
        )
    result = ExperimentRunner(
        config,
        batch_id=arguments.batch_id,
        output_root=arguments.output_root,
    ).run(source_config_path=config_path)
    print(
        f"experiment={result.experiment_name} "
        f"batch_id={result.batch_id} "
        f"cases={result.successful_case_count}/{result.case_count} "
        f"output={result.batch_directory}"
    )
    return 0 if result.successful_case_count == result.case_count else 1
