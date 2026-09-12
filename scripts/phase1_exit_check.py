"""Verify Phase 1 exit criteria against the live database — task 1.11.

Spec §5, Phase 1:
  - 120 papers ingested (42, amended by C-001)
  - <5% hard parse failures
  - failures inspectable
  - tables preserved as tables
  - re-running ingestion is idempotent

Checked mechanically rather than by eye, for the same reason the holdout guard is
mechanical: a criterion confirmed by looking at output is confirmed once, by
someone who wanted it to pass.

Usage:
    uv run python scripts/phase1_exit_check.py
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import psycopg

from survey.evalharness.holdout import load_holdout_ids
from survey.ingest import store

CORPUS = Path("corpus")
MAX_FAILURE_RATE = 0.05


def check(conn: psycopg.Connection, corpus_id: str = "semcom") -> list[tuple[bool, str]]:
    results: list[tuple[bool, str]] = []
    manifest = list(csv.DictReader((CORPUS / "manifest.csv").open(encoding="utf-8")))
    expected = len(manifest)

    with conn.cursor() as cur:
        cur.execute(
            "SELECT ingest_status, count(*) FROM papers WHERE corpus_id=%s GROUP BY 1",
            (corpus_id,),
        )
        by_status = dict(cur.fetchall())
        total = sum(by_status.values())
        quarantined = by_status.get("quarantined", 0)

        results.append(
            (
                total == expected,
                f"all manifest papers ingested: {total}/{expected}",
            )
        )
        rate = quarantined / total if total else 1.0
        results.append(
            (
                rate < MAX_FAILURE_RATE,
                f"hard parse failures under 5%: {quarantined}/{total} ({rate:.1%})",
            )
        )

        # "Failures inspectable" means a reason is queryable, not merely logged.
        cur.execute(
            "SELECT count(*) FROM papers WHERE corpus_id=%s AND "
            "ingest_status='quarantined' AND failure_reason IS NULL",
            (corpus_id,),
        )
        unexplained = cur.fetchone()[0]
        results.append(
            (
                unexplained == 0,
                f"every failure has a reason in SQL: {unexplained} unexplained",
            )
        )

        cur.execute(
            "SELECT count(*), count(distinct paper_id) FROM paper_tables t "
            "JOIN papers p ON p.id=t.paper_id WHERE p.corpus_id=%s",
            (corpus_id,),
        )
        n_tables, n_papers_with_tables = cur.fetchone()
        results.append(
            (
                n_tables > 0,
                f"tables preserved as tables: {n_tables} tables "
                f"across {n_papers_with_tables} papers",
            )
        )

        # A table is only "preserved as a table" if its structure survived: a
        # header kept separate from at least one body row. The original check
        # demanded two body rows and failed on two genuine single-row tables
        # ("The number of transmitted symbols for one image" is a header and one
        # row), so it was measuring the wrong thing.
        cur.execute(
            "SELECT count(*) FROM paper_tables t JOIN papers p ON p.id=t.paper_id "
            "WHERE p.corpus_id=%s AND (t.grid->'rows') IS NOT NULL "
            "AND jsonb_array_length(t.grid->'rows') >= 1 "
            "AND (t.grid->'header') IS NOT NULL",
            (corpus_id,),
        )
        structured = cur.fetchone()[0]
        results.append(
            (
                structured == n_tables,
                f"every table has a header and >=1 body row: {structured}/{n_tables}",
            )
        )

        cur.execute(
            "SELECT count(*) FROM sections s JOIN papers p ON p.id=s.paper_id "
            "WHERE p.corpus_id=%s",
            (corpus_id,),
        )
        n_sections = cur.fetchone()[0]
        cur.execute(
            "SELECT count(*) FROM paragraphs g JOIN papers p ON p.id=g.paper_id "
            "WHERE p.corpus_id=%s",
            (corpus_id,),
        )
        n_paragraphs = cur.fetchone()[0]
        results.append(
            (
                n_sections > 0 and n_paragraphs > 0,
                f"section-aware storage: {n_sections} sections, "
                f"{n_paragraphs} paragraphs",
            )
        )

        cur.execute(
            "SELECT count(*) FILTER (WHERE dst_paper_id IS NOT NULL), count(*) "
            "FROM citation_edges e JOIN papers p ON p.id=e.src_paper_id "
            "WHERE p.corpus_id=%s",
            (corpus_id,),
        )
        resolved, all_edges = cur.fetchone()
        results.append(
            (
                all_edges > 0,
                f"citation graph: {all_edges} edges, {resolved} resolved in-corpus",
            )
        )

        # The holdout guard is only real if the split is actually loaded.
        cur.execute(
            "SELECT split, count(*) FROM corpus_split s JOIN papers p ON p.id=s.paper_id "
            "WHERE p.corpus_id=%s GROUP BY 1",
            (corpus_id,),
        )
        splits = dict(cur.fetchall())
        holdout_ids = load_holdout_ids()
        results.append(
            (
                splits.get("holdout", 0) == len(holdout_ids),
                f"split loaded: {splits.get('dev', 0)} dev / "
                f"{splits.get('holdout', 0)} holdout "
                f"(file says {len(holdout_ids)})",
            )
        )

        cur.execute(
            "SELECT count(*) FROM v_dev_papers v JOIN corpus_split s "
            "ON s.paper_id=v.id WHERE s.split='holdout'"
        )
        leaked = cur.fetchone()[0]
        results.append((leaked == 0, f"no holdout paper in v_dev_papers: {leaked}"))

    return results


def main() -> int:
    try:
        conn = psycopg.connect(store.dsn(), connect_timeout=10)
    except psycopg.OperationalError as exc:
        print(f"could not connect: {exc}", file=sys.stderr)
        return 1

    with conn:
        results = check(conn)

    print("Phase 1 exit criteria\n")
    for passed, message in results:
        print(f"  [{'ok  ' if passed else 'FAIL'}] {message}")

    failed = [m for ok, m in results if not ok]
    if failed:
        print(f"\n{len(failed)} criterion/criteria not met.")
        return 1
    print("\nAll Phase 1 exit criteria met.")
    print("NOTE: idempotency is verified by re-running scripts/ingest.py and")
    print("      confirming every paper reports 'unchanged'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
