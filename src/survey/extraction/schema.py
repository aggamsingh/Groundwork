"""Extraction schema loading — CHECKPOINT 2 / D-002.

The schema is authored and frozen by the user. Claude may propose a draft, but a
draft must never be used: extracting against provisional field definitions would
produce a claim store and comparison tables whose meaning changes underneath
every number already recorded against them.

So the guard is mechanical rather than advisory — ``load_schema`` refuses any
schema whose ``status`` is not ``frozen``.

Stdlib plus PyYAML only; this runs in CI.
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Any

import yaml

SCHEMA_DIR = Path("schema")

ABSENCE_VALUES = ("not_reported", "not_applicable", "not_extracted")


class SchemaError(RuntimeError):
    """The schema is missing, malformed, or not frozen."""


class SchemaNotFrozenError(SchemaError):
    """The schema is still a draft. This is a human checkpoint, not a bug."""


def schema_path(corpus: str, schema_dir: Path = SCHEMA_DIR) -> Path:
    return schema_dir / f"{corpus}.yaml"


def load_schema(corpus: str = "semcom", schema_dir: Path = SCHEMA_DIR) -> dict[str, Any]:
    """Load and validate the frozen extraction schema for ``corpus``."""
    path = schema_path(corpus, schema_dir)
    if not path.exists():
        raise SchemaError(
            f"{path} does not exist. This is CHECKPOINT 2: the user writes and "
            "freezes the extraction schema."
        )

    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:  # pragma: no cover - message pass-through
        raise SchemaError(f"{path} is not valid YAML: {exc}") from exc

    if not isinstance(doc, dict):
        raise SchemaError(f"{path} must contain a YAML mapping at the top level.")

    status = doc.get("status")
    if status != "frozen":
        raise SchemaNotFrozenError(
            f"{path} has status {status!r}, not 'frozen'. A draft schema is a "
            "proposal for the user to edit (CHECKPOINT 2) and must not be "
            "extracted against: field definitions that shift would silently "
            "change the meaning of every number already stored against them."
        )

    if not doc.get("frozen_date"):
        raise SchemaError(
            f"{path} is marked frozen but has no frozen_date. The spec requires "
            "the schema be frozen with a date (§5, Phase 0)."
        )
    _check_date(doc["frozen_date"], path)

    fields = doc.get("fields")
    if not isinstance(fields, list) or not fields:
        raise SchemaError(f"{path} defines no fields.")

    seen: set[str] = set()
    for i, field in enumerate(fields):
        if not isinstance(field, dict):
            raise SchemaError(f"{path}: field #{i} is not a mapping.")
        for required in ("name", "type", "cardinality"):
            if not field.get(required):
                raise SchemaError(
                    f"{path}: field #{i} ({field.get('name', '?')}) is missing "
                    f"{required!r}."
                )
        name = field["name"]
        if name in seen:
            raise SchemaError(f"{path}: duplicate field name {name!r}.")
        seen.add(name)
        if field["cardinality"] not in ("one", "many"):
            raise SchemaError(
                f"{path}: field {name!r} has cardinality "
                f"{field['cardinality']!r}; expected 'one' or 'many'."
            )

    missing = set(doc.get("comparison_table_default_columns") or []) - seen
    if missing:
        raise SchemaError(
            f"{path}: comparison_table_default_columns names undefined field(s): "
            f"{', '.join(sorted(missing))}."
        )

    return doc


def _check_date(value: object, path: Path) -> None:
    if isinstance(value, _dt.date):
        return
    try:
        _dt.date.fromisoformat(str(value))
    except ValueError as exc:
        raise SchemaError(
            f"{path}: frozen_date {value!r} is not an ISO date (YYYY-MM-DD)."
        ) from exc


def field_names(schema: dict[str, Any]) -> list[str]:
    return [f["name"] for f in schema["fields"]]
