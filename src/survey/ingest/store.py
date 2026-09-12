"""Persist parsed papers into Postgres — tasks 1.2b and 1.3.

Idempotency rule: a paper is keyed by (corpus_id, external_id), and its content
by sha256. Re-ingesting an unchanged paper is a no-op; re-ingesting a changed one
replaces its structure wholesale rather than merging. Merging parsed structure is
not meaningful — paragraph ordinals shift, so a partial update would leave
citations pointing at text that moved.

Failures quarantine the paper rather than aborting the run: `ingest_status` goes
to 'quarantined' with the reason recorded, so failures are inspectable in SQL
instead of lost in a log (spec §5, Phase 1).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import psycopg

from survey.ingest.model import ParsedPaper

DEFAULT_DSN = "postgresql://survey:survey_local_dev@localhost:5433/survey"


def dsn() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_DSN)


@dataclass(slots=True)
class StoreResult:
    external_id: str
    action: str          # inserted | replaced | unchanged | quarantined
    paper_id: int | None = None
    reason: str | None = None


def ensure_corpus(conn: psycopg.Connection, corpus_id: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO corpora (id) VALUES (%s) ON CONFLICT (id) DO NOTHING",
            (corpus_id,),
        )


def _existing(
    conn: psycopg.Connection, corpus_id: str, external_id: str
) -> tuple[int, str | None, str | None, str] | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, sha256, parser, ingest_status FROM papers "
            "WHERE corpus_id = %s AND external_id = %s",
            (corpus_id, external_id),
        )
        return cur.fetchone()


def _clear_structure(conn: psycopg.Connection, paper_id: int) -> None:
    """Drop a paper's parsed structure. Cascades handle paragraphs and tables."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM citation_edges WHERE src_paper_id = %s", (paper_id,))
        cur.execute("DELETE FROM paper_tables WHERE paper_id = %s", (paper_id,))
        cur.execute("DELETE FROM paragraphs WHERE paper_id = %s", (paper_id,))
        cur.execute("DELETE FROM sections WHERE paper_id = %s", (paper_id,))


def _write_structure(
    conn: psycopg.Connection, paper_id: int, paper: ParsedPaper
) -> None:
    with conn.cursor() as cur:
        for section in paper.sections:
            cur.execute(
                "INSERT INTO sections (paper_id, parent_id, ordinal, depth, heading, kind) "
                "VALUES (%s, NULL, %s, %s, %s, %s) RETURNING id",
                (paper_id, section.ordinal, section.depth, section.heading, section.kind),
            )
            section_id = cur.fetchone()[0]

            for para in section.paragraphs:
                cur.execute(
                    "INSERT INTO paragraphs "
                    "(paper_id, section_id, ordinal, text, page_from, page_to) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (
                        paper_id,
                        section_id,
                        para.ordinal,
                        para.text,
                        para.page_from,
                        para.page_to,
                    ),
                )

        for table in paper.tables:
            cur.execute(
                "INSERT INTO paper_tables "
                "(paper_id, section_id, ordinal, label, caption, grid, page) "
                "VALUES (%s, NULL, %s, %s, %s, %s, %s)",
                (
                    paper_id,
                    table.ordinal,
                    table.label,
                    table.caption,
                    psycopg.types.json.Json(table.grid),
                    table.page,
                ),
            )

        # References become citation edges with an unresolved target; resolution
        # against the corpus is task 1.7 and runs after every paper is stored,
        # because a reference can point at a paper not yet ingested.
        for ref in paper.references:
            cur.execute(
                "INSERT INTO citation_edges "
                "(src_paper_id, dst_paper_id, raw_reference, ref_title, ref_doi, "
                "ref_arxiv_id, dst_external_id) "
                "VALUES (%s, NULL, %s, %s, %s, %s, NULL)",
                (paper_id, ref.raw, ref.title, ref.doi, ref.arxiv_id),
            )


def store(
    conn: psycopg.Connection,
    paper: ParsedPaper,
    *,
    sha256: str,
    corpus_id: str = "semcom",
    source_path: str | None = None,
    force: bool = False,
) -> StoreResult:
    """Insert or replace one parsed paper. Idempotent on unchanged content."""
    ensure_corpus(conn, corpus_id)
    row = _existing(conn, corpus_id, paper.external_id)

    # `ingest_status == 'ok'` is load-bearing, not belt-and-braces. A paper that
    # failed inside _write_structure already has its sha256 and parser recorded
    # from the papers INSERT, so a check on content alone calls it "unchanged" and
    # skips it on every later run — leaving it quarantined even after the bug that
    # broke it is fixed. Quarantined papers must always be retried. See P-002.
    if (
        row
        and row[1] == sha256
        and row[2] == paper.parser
        and row[3] == "ok"
        and not force
    ):
        return StoreResult(paper.external_id, "unchanged", paper_id=row[0])

    with conn.cursor() as cur:
        if row:
            paper_id = row[0]
            _clear_structure(conn, paper_id)
            cur.execute(
                "UPDATE papers SET title=%s, abstract=%s, year=%s, venue=%s, "
                "page_count=%s, doi=%s, arxiv_id=%s, source_path=%s, sha256=%s, parser=%s, "
                "parsed_at=now(), ingest_status='ok', failure_reason=NULL "
                "WHERE id=%s",
                (
                    paper.title,
                    paper.abstract,
                    paper.year,
                    paper.venue,
                    paper.page_count,
                    paper.doi,
                    paper.arxiv_id,
                    source_path,
                    sha256,
                    paper.parser,
                    paper_id,
                ),
            )
            action = "replaced"
        else:
            cur.execute(
                "INSERT INTO papers (corpus_id, external_id, title, abstract, year, "
                "venue, page_count, doi, arxiv_id, source_path, sha256, parser, "
                "parsed_at, ingest_status) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now(), 'ok') RETURNING id",
                (
                    corpus_id,
                    paper.external_id,
                    paper.title,
                    paper.abstract,
                    paper.year,
                    paper.venue,
                    paper.page_count,
                    paper.doi,
                    paper.arxiv_id,
                    source_path,
                    sha256,
                    paper.parser,
                ),
            )
            paper_id = cur.fetchone()[0]
            action = "inserted"

    _write_structure(conn, paper_id, paper)
    return StoreResult(paper.external_id, action, paper_id=paper_id)


def quarantine(
    conn: psycopg.Connection,
    external_id: str,
    reason: str,
    *,
    corpus_id: str = "semcom",
    sha256: str | None = None,
    source_path: str | None = None,
) -> StoreResult:
    """Record a parse failure so it is inspectable in SQL, not just in a log."""
    ensure_corpus(conn, corpus_id)
    row = _existing(conn, corpus_id, external_id)
    with conn.cursor() as cur:
        if row:
            _clear_structure(conn, row[0])
            cur.execute(
                "UPDATE papers SET ingest_status='quarantined', failure_reason=%s, "
                "parsed_at=now() WHERE id=%s",
                (reason[:2000], row[0]),
            )
            paper_id = row[0]
        else:
            cur.execute(
                "INSERT INTO papers (corpus_id, external_id, source_path, sha256, "
                "ingest_status, failure_reason, parsed_at) "
                "VALUES (%s,%s,%s,%s,'quarantined',%s, now()) RETURNING id",
                (corpus_id, external_id, source_path, sha256, reason[:2000]),
            )
            paper_id = cur.fetchone()[0]
    return StoreResult(external_id, "quarantined", paper_id=paper_id, reason=reason)


def set_split(
    conn: psycopg.Connection,
    holdout_ids: frozenset[str],
    *,
    corpus_id: str = "semcom",
    source_file: str = "eval/holdout_papers.txt",
) -> tuple[int, int]:
    """Populate corpus_split from the frozen holdout list. Returns (dev, holdout).

    This is what makes `v_dev_papers` non-empty, and therefore what makes the
    holdout guard real rather than decorative (D-004).
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, external_id FROM papers WHERE corpus_id = %s", (corpus_id,)
        )
        rows = cur.fetchall()
        dev = held = 0
        for paper_id, external_id in rows:
            split = "holdout" if external_id in holdout_ids else "dev"
            if split == "holdout":
                held += 1
            else:
                dev += 1
            cur.execute(
                "INSERT INTO corpus_split (paper_id, split, source_file) "
                "VALUES (%s,%s,%s) ON CONFLICT (paper_id) DO UPDATE "
                "SET split = EXCLUDED.split, source_file = EXCLUDED.source_file",
                (paper_id, split, source_file),
            )
    return dev, held
