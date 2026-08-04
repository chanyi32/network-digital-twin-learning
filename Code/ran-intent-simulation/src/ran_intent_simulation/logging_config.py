"""Logging initialization helpers."""

from __future__ import annotations

import logging
from logging.config import dictConfig
from pathlib import Path


def configure_logging(
    *,
    level: int | str = logging.INFO,
    log_file: str | Path | None = None,
) -> logging.Logger:
    """Configure project logging and return the package logger."""

    handlers: dict[str, dict[str, object]] = {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
            "level": level,
        }
    }
    root_handlers = ["console"]

    if log_file is not None:
        path = Path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        handlers["file"] = {
            "class": "logging.FileHandler",
            "formatter": "standard",
            "level": level,
            "filename": str(path),
            "encoding": "utf-8",
        }
        root_handlers.append("file")

    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "standard": {
                    "format": "%(asctime)s %(levelname)s %(name)s: %(message)s",
                }
            },
            "handlers": handlers,
            "root": {
                "handlers": root_handlers,
                "level": level,
            },
        }
    )
    return get_logger()


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a logger inside the project namespace."""

    suffix = f".{name}" if name else ""
    return logging.getLogger(f"ran_intent_simulation{suffix}")

