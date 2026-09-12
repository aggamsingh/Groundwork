"""Bring up the corpus store and verify it — task 0.3.

Applies src/survey/db/schema.sql to the running Postgres and checks that the
things Phase 1 depends on actually exist: the pgvector extension, every table,
and the v_dev_papers view that keeps holdout papers out of query results (D-004).

The schema is also mounted into the container as an init script, so a fresh
volume applies it automatically. This script exists for the case that matters
more in practice: an existing volume, where the init hook does not re-run.

Idempotent - safe to run repeatedly.

Usage:
    uv run python scripts/init_db.py [--dsn postgresql://...]
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import psycopg

SCHEMA = Path("src/survey/db/schema.sql")

EXPECTED_TABLES = {
    "corpora",
    "papers",
    "corpus_split",
    "sections",
    "paragraphs",
    "paper_tables",
    "citation_edges",
}

DEFAULT_DSN = "postgresql://survey:survey_local_dev@localhost:5433/survey"


def apply_schema(conn: psycopg.Connection) -> None:
    """Apply schema.sql. Objects already present are left alone."""
    sql = SCHEMA.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        try:
            cur.execute(sql)
        except psycopg.errors.DuplicateTable:
            conn.rollback()
            print("  schema already applied - skipping")
            return
        except psycopg.errors.DuplicateObject:
            conn.rollback()
            print("  schema objects already present - skipping")
            return
    conn.commit()
    print("  schema applied")


# Columns added to `papers` after the initial schema shipped. schema.sql runs
# only on a fresh volume, so an existing database needs these applied explicitly.
# Kept as plain idempotent DDL rather than a migration framework: at this size a
# framework would be more machinery than the problem deserves.
MIGRATIONS = [
    "ALTER TABLE papers ADD COLUMN IF NOT EXISTS venue text",
    "ALTER TABLE papers ADD COLUMN IF NOT EXISTS page_count int",
    "ALTER TABLE papers ADD COLUMN IF NOT EXISTS doi text",
    "ALTER TABLE papers ADD COLUMN IF NOT EXISTS arxiv_id text",
    "CREATE INDEX IF NOT EXISTS papers_doi_idx ON papers (doi)",
]


def migrate(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        for statement in MIGRATIONS:
            cur.execute(statement)
    conn.commit()
    print(f"  {len(MIGRATIONS)} migrations applied (idempotent)")


def verify(conn: psycopg.Connection) -> list[str]:
    problems: list[str] = []
    with conn.cursor() as cur:
        cur.execute("SELECT extname FROM pg_extension WHERE extname = 'vector'")
        if cur.fetchone() is None:
            problems.append(
                "pgvector extension missing - is the image pgvector/pgvector:pg16?"
            )
        else:
            cur.execute("SELECT extversion FROM pg_extension WHERE extname='vector'")
            print(f"  pgvector {cur.fetchone()[0]}")

        cur.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
        )
        found = {r[0] for r in cur.fetchall()}
        missing = EXPECTED_TABLES - found
        if missing:
            problems.append(f"missing tables: {', '.join(sorted(missing))}")
        else:
            print(f"  {len(EXPECTED_TABLES)} tables present")

        cur.execute(
            "SELECT 1 FROM information_schema.views "
            "WHERE table_schema='public' AND table_name='v_dev_papers'"
        )
        if cur.fetchone() is None:
            problems.append(
                "v_dev_papers view missing - this is the holdout guard (D-004)"
            )
        else:
            # Prove it is queryable, not merely defined.
            cur.execute("SELECT count(*) FROM v_dev_papers")
            print(f"  v_dev_papers queryable ({cur.fetchone()[0]} dev papers)")

        # A vector round-trip: the extension being installed is not the same as
        # it working, and this is the one operation the whole system depends on.
        cur.execute("SELECT '[1,2,3]'::vector <-> '[1,2,4]'::vector")
        dist = cur.fetchone()[0]
        if abs(dist - 1.0) > 1e-9:
            problems.append(f"vector distance returned {dist}, expected 1.0")
        else:
            print("  vector distance operator works")

    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dsn", default=os.environ.get("DATABASE_URL", DEFAULT_DSN))
    args = ap.parse_args()

    if not SCHEMA.exists():
        print(f"{SCHEMA} not found - run from the repo root.", file=sys.stderr)
        return 1

    print(f"connecting to {args.dsn.split('@')[-1]}")
    try:
        with psycopg.connect(args.dsn, connect_timeout=10) as conn:
            apply_schema(conn)
            migrate(conn)
            problems = verify(conn)
    except psycopg.OperationalError as exc:
        print(f"\ncould not connect: {exc}", file=sys.stderr)
        print(
            "Is the container up? 'docker compose up -d', then "
            "'uv run python scripts/check_env.py'.",
            file=sys.stderr,
        )
        return 1

    if problems:
        print("\nFAILED:")
        for p in problems:
            print(f"  - {p}")
        return 1

    print("\nCorpus store is up and verified. Task 0.3 satisfied.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
