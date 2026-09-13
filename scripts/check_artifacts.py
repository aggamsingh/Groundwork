"""Check the project's frozen artifacts are intact — CI guard.

These files cannot be regenerated: the holdout split is the user's one-time
choice, the schema is their frozen vocabulary, and the gold table will be their
hand-built ground truth. Each is protected by a rule written in CLAUDE.md, and a
rule that nothing checks is a rule that erodes.

What this does NOT check: whether the *contents* are correct. Nothing can check
that. It checks that the artifacts still exist, still parse, are still marked
frozen, and still agree with each other.

Usage:
    uv run python scripts/check_artifacts.py
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

from survey.evalharness.holdout import HoldoutMissingError, load_holdout_ids
from survey.extraction.schema import SchemaError, load_schema

MANIFEST = Path("corpus/manifest.csv")
GOLD_TABLE = Path("eval/gold_table_semcom.csv")


def _check_holdout(problems: list[str], notes: list[str]) -> frozenset[str]:
    try:
        ids = load_holdout_ids()
    except HoldoutMissingError:
        problems.append("eval/holdout_papers.txt is missing (CHECKPOINT 1)")
        return frozenset()
    except Exception as exc:
        problems.append(f"holdout unusable: {exc}")
        return frozenset()

    header = Path("eval/holdout_papers.txt").read_text(encoding="utf-8")[:400]
    if "FROZEN" not in header.upper():
        problems.append(
            "eval/holdout_papers.txt has lost its FROZEN marker — the file may "
            "have been regenerated rather than edited"
        )
    notes.append(f"holdout: {len(ids)} papers, frozen")
    return ids


def _check_manifest(problems: list[str], notes: list[str], holdout: frozenset[str]):
    if not MANIFEST.exists():
        problems.append("corpus/manifest.csv is missing")
        return
    rows = list(csv.DictReader(MANIFEST.open(encoding="utf-8")))
    ids = {r["external_id"] for r in rows}

    if len(ids) != len(rows):
        problems.append("corpus/manifest.csv has duplicate external_id values")

    # Every held-out paper must still be in the corpus. If one disappears, the
    # split silently shrinks and the Phase 6 number is computed on fewer papers
    # than it claims.
    missing = sorted(holdout - ids)
    if missing:
        problems.append(
            f"{len(missing)} holdout paper(s) are no longer in the manifest: "
            + ", ".join(missing[:5])
        )

    notes.append(f"manifest: {len(rows)} papers, {len(holdout & ids)} of them holdout")


def _check_schema(problems: list[str], notes: list[str]) -> None:
    try:
        schema = load_schema("semcom")
    except SchemaError as exc:
        problems.append(f"schema/semcom.yaml: {exc}")
        return

    # verdict/status are the user's editorial judgements, not paper properties
    # (D-011). If they ever migrate into `fields`, extraction starts being scored
    # on something no system can produce.
    names = {f["name"] for f in schema["fields"]}
    for editorial in ("verdict", "status"):
        if editorial in names:
            problems.append(
                f"schema: {editorial!r} is an extraction field; it belongs in "
                "human_only_columns (D-011)"
            )

    critical = [f for f in schema["fields"] if f.get("priority") == "critical"]
    if not any(f["name"] == "metric_validated" for f in critical):
        problems.append(
            "schema: metric_validated has lost its `priority: critical` marker "
            "(D-011 — the user calls it the spine of the survey's Section IV)"
        )

    notes.append(
        f"schema: frozen {schema['frozen_date']}, {len(schema['fields'])} fields"
    )


def _check_gold_table(notes: list[str], holdout: frozenset[str]) -> list[str]:
    """The gold table is deferred to a Phase 2 gate (C-003), so absence is fine."""
    problems: list[str] = []
    if not GOLD_TABLE.exists():
        notes.append("gold table: not yet present (deferred by C-003)")
        return problems

    rows = list(csv.DictReader(GOLD_TABLE.open(encoding="utf-8")))
    key = "external_id" if rows and "external_id" in rows[0] else None
    if key is None:
        problems.append("gold table has no external_id column")
        return problems

    leaked = sorted({r[key] for r in rows} & holdout)
    if leaked:
        problems.append(
            f"gold table contains {len(leaked)} HOLDOUT paper(s): "
            + ", ".join(leaked[:5])
            + " — tuning against these defeats the split"
        )
    notes.append(f"gold table: {len(rows)} rows, no holdout papers")
    return problems


def main() -> int:
    problems: list[str] = []
    notes: list[str] = []

    holdout = _check_holdout(problems, notes)
    _check_manifest(problems, notes, holdout)
    _check_schema(problems, notes)
    problems.extend(_check_gold_table(notes, holdout))

    for note in notes:
        print(f"  [ok  ] {note}")
    for problem in problems:
        print(f"  [FAIL] {problem}")

    if problems:
        print(f"\n{len(problems)} artifact problem(s).")
        return 1
    print("\nFrozen artifacts intact.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
