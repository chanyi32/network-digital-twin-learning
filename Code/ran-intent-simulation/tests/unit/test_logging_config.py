"""Tests for logging initialization."""

import logging
from pathlib import Path

from ran_intent_simulation.logging_config import configure_logging, get_logger


def test_configure_logging_returns_project_logger(tmp_path: Path) -> None:
    """Logging can be initialized with a UTF-8 file handler."""

    log_path = tmp_path / "skeleton.log"
    logger = configure_logging(level="DEBUG", log_file=log_path)
    logger.info("skeleton")

    assert logger.name == "ran_intent_simulation"
    assert get_logger("test").name == "ran_intent_simulation.test"
    assert logging.getLogger().level == logging.DEBUG
    assert log_path.exists()

