"""Ingest the corpus into Postgres — tasks 1.2b, 1.3, 1.9.

Resumable and idempotent: unchanged papers are skipped, failures are quarantined
rather than aborting the run, and each paper commits on its own so an interrupted
run loses at most one paper.

Usage:
    uv run python scripts/ingest.py                # ingest everything
    uv run python scripts/ingest.py --force        # re-parse even if unchanged
    uv run python scripts/ingest.py --limit 5
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import psycopg

from survey.evalharness.holdout import load_holdout_ids
from survey.ingest import citations, hybrid_parser, pymupdf_parser, store
from survey.ingest.model import ParseError

PARSERS = {
    "hybrid": hybrid_parser.parse,
    "pymupdf": pymupdf_parser.parse,
}
CORPUS = Path("corpus")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--parser", default="hybrid", choices=sorted(PARSERS))
    ap.add_argument("--corpus", default="semcom")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--force", action="store_true", help="re-parse unchanged papers")
    ap.add_argument("--dsn", default=store.dsn())
    args = ap.parse_args()

    manifest = CORPUS / "manifest.csv"
    if not manifest.exists():
        print(f"{manifest} missing - run scripts/build_manifest.py", file=sys.stderr)
        return 1

    rows = sorted(
        csv.DictReader(manifest.open(encoding="utf-8")),
        key=lambda r: r["external_id"],
    )
    if args.limit:
        rows = rows[: args.limit]

    parse = PARSERS[args.parser]
    counts = {"inserted": 0, "replaced": 0, "unchanged": 0, "quarantined": 0}
    started = time.perf_counter()

    try:
        conn = psycopg.connect(args.dsn, connect_timeout=10)
    except psycopg.OperationalError as exc:
        print(f"could not connect: {exc}", file=sys.stderr)
        print("Is the container up? 'docker compose up -d'", file=sys.stderr)
        return 1

    with conn:
        for i, row in enumerate(rows, 1):
            ext_id = row["external_id"]
            path = CORPUS / row["filename"]
            # Skip before parsing, not after. The manifest already carries the
            # content hash, so an unchanged paper costs a single query instead of
            # ~17s of parsing.
            if not args.force and store.is_unchanged(
                conn, ext_id, row["sha256"], args.parser, corpus_id=args.corpus
            ):
                counts["unchanged"] += 1
                print(f"  [{i:>3}/{len(rows)}] {'unchanged':<11} {ext_id[:60]}")
                continue

            try:
                paper = parse(path, ext_id)
                result = store.store(
                    conn,
                    paper,
                    sha256=row["sha256"],
                    corpus_id=args.corpus,
                    source_path=str(path),
                    force=args.force,
                )
            except (ParseError, Exception) as exc:
                # A storage failure aborts the transaction, so the quarantine
                # write would land in a poisoned one. Roll back first.
                conn.rollback()
                reason = (
                    str(exc)
                    if isinstance(exc, ParseError)
                    else f"UNEXPECTED {type(exc).__name__}: {exc}"
                )
                result = store.quarantine(
                    conn,
                    ext_id,
                    reason,
                    corpus_id=args.corpus,
                    sha256=row["sha256"],
                    source_path=str(path),
                )
            # Commit per paper: an interrupted run loses at most one paper,
            # which is what makes the run resumable rather than restartable.
            conn.commit()

            counts[result.action] += 1
            marker = "!" if result.action == "quarantined" else " "
            print(f"{marker} [{i:>3}/{len(rows)}] {result.action:<11} {ext_id[:60]}")

        # Citation resolution runs over the whole corpus at once: a reference can
        # point at a paper ingested later in this same run.
        stats = citations.resolve(conn, corpus_id=args.corpus)
        conn.commit()
        print(
            f"\ncitations: {stats.resolved}/{stats.total} resolved "
            f"({stats.by_doi} by doi, {stats.by_arxiv} by arxiv, "
            f"{stats.by_title} by title), "
            f"{stats.unresolved} point outside the corpus"
        )
        if stats.self_citations_dropped:
            print(f"           {stats.self_citations_dropped} self-citations dropped")

        # The split must be applied after ingestion, since it keys off paper ids.
        # Without this v_dev_papers is empty and the holdout guard is decorative.
        try:
            holdout = load_holdout_ids()
            dev, held = store.set_split(conn, holdout, corpus_id=args.corpus)
            conn.commit()
            print(f"\nsplit applied: {dev} dev / {held} holdout")
        except Exception as exc:
            print(f"\nWARNING: split not applied: {exc}", file=sys.stderr)
            return 1

    elapsed = time.perf_counter() - started
    print(
        f"done in {elapsed:.1f}s: "
        + ", ".join(f"{v} {k}" for k, v in counts.items() if v)
    )
    if counts["quarantined"]:
        print(
            f"\n{counts['quarantined']} quarantined. Inspect with:\n"
            "  SELECT external_id, failure_reason FROM papers "
            "WHERE ingest_status = 'quarantined';"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
