"""Deterministic JSON/CSV writers and input-file hashing."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from ran_intent_simulation.exceptions import DataLoadingError


def sha256_file(path: str | Path) -> str:
    """Return the SHA-256 digest of one required input file."""

    input_path = Path(path)
    if not input_path.is_file():
        raise DataLoadingError(f"Cannot hash missing input file: {input_path}")
    digest = hashlib.sha256()
    try:
        with input_path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise DataLoadingError(f"Unable to hash input file: {input_path}") from exc
    return digest.hexdigest()


def write_json(path: str | Path, value: Any) -> Path:
    """Atomically write UTF-8, pretty, stable-key JSON."""

    output_path = Path(path)
    serialized = json.dumps(
        _jsonable(value),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        allow_nan=False,
    )
    _atomic_write_text(output_path, f"{serialized}\n")
    return output_path


def write_csv(
    path: str | Path,
    rows: Sequence[Mapping[str, Any]],
    *,
    fieldnames: Sequence[str] | None = None,
) -> Path:
    """Atomically write analysis-oriented CSV with deterministic columns."""

    output_path = Path(path)
    if fieldnames is None:
        fieldnames = list(rows[0]) if rows else []
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8-sig",
            newline="",
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
            writer = csv.DictWriter(
                stream,
                fieldnames=list(fieldnames),
                extrasaction="raise",
            )
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {
                        key: _csv_value(row.get(key))
                        for key in fieldnames
                    }
                )
        os.replace(temporary_path, output_path)
    except (OSError, csv.Error, ValueError) as exc:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise DataLoadingError(f"Unable to write CSV: {output_path}") from exc
    return output_path


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
            stream.write(content)
        os.replace(temporary_path, path)
    except OSError as exc:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise DataLoadingError(f"Unable to write JSON: {path}") from exc


def _jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    return value


def _csv_value(value: Any) -> Any:
    converted = _jsonable(value)
    if isinstance(converted, (dict, list)):
        return json.dumps(
            converted,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    return converted
