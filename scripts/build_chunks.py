"""Build chunks from ingested paragraphs — Phase 2 machinery (C-006).

Chunks are derived data. This script can be re-run at will, and Phase 3 will run
it repeatedly with different configurations; each configuration's chunks are kept
under their own fingerprint so two can be compared without re-chunking.

No tuning happens here. The configuration comes from `survey.config`, whose
defaults are marked unjustified until an eval run backs them.

Usage:
    .\\.venv\\Scripts\\python.exe scripts/build_chunks.py
    .\\.venv\\Scripts\\python.exe scripts/build_chunks.py --strategy section
    .\\.venv\\Scripts\\python.exe scripts/build_chunks.py --include-holdout   # Phase 6 only
"""

from __future__ import annotations

import argparse
import sys
import time

import psycopg

from survey.chunking.chunker import STRATEGIES, ParagraphInput
from survey.config.config import ChunkingConfig, RunConfig, default_config
from survey.ingest import store


def load_paragraphs(
    conn: psycopg.Connection, corpus_id: str, include_holdout: bool
) -> dict[int, list[ParagraphInput]]:
    """Paragraphs grouped by paper, dev-set only unless explicitly overridden."""
    papers_source = "papers" if include_holdout else "v_dev_papers"
    sql = f"""
        SELECT g.id, g.paper_id, g.section_id, g.text, g.ordinal
        FROM paragraphs g
        JOIN {papers_source} p ON p.id = g.paper_id
        WHERE p.corpus_id = %s AND p.ingest_status = 'ok'
        ORDER BY g.paper_id, g.section_id, g.ordinal
    """
    by_paper: dict[int, list[ParagraphInput]] = {}
    with conn.cursor() as cur:
        cur.execute(sql, (corpus_id,))
        for pid, paper_id, section_id, text, ordinal in cur.fetchall():
            by_paper.setdefault(paper_id, []).append(
                ParagraphInput(
                    paragraph_id=pid,
                    paper_id=paper_id,
                    section_id=section_id,
                    text=text,
                    ordinal=ordinal,
                )
            )
    return by_paper


def clear_config(conn: psycopg.Connection, fingerprint: str) -> int:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM chunks WHERE config_fingerprint = %s", (fingerprint,))
        return cur.rowcount


def build(
    conn: psycopg.Connection,
    config: RunConfig,
    *,
    include_holdout: bool = False,
) -> tuple[int, int]:
    """Chunk the corpus under `config`. Returns (chunks, spans)."""
    fingerprint = config.fingerprint()
    chunker = STRATEGIES[config.chunking.strategy]
    by_paper = load_paragraphs(conn, config.corpus, include_holdout)

    removed = clear_config(conn, fingerprint)
    if removed:
        print(f"  replaced {removed} existing chunks for this configuration")

    total_chunks = total_spans = 0
    with conn.cursor() as cur:
        for paper_id, paragraphs in by_paper.items():
            if config.chunking.strategy == "paragraph":
                chunks = chunker(paragraphs)
            else:
                chunks = chunker(
                    paragraphs, chunk_tokens=config.chunking.chunk_tokens
                )

            for ordinal, chunk in enumerate(chunks):
                cur.execute(
                    "INSERT INTO chunks (paper_id, section_id, config_fingerprint, "
                    "strategy, ordinal, text, char_count) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                    (
                        paper_id,
                        chunk.section_id,
                        fingerprint,
                        chunk.strategy,
                        ordinal,
                        chunk.text,
                        chunk.char_count,
                    ),
                )
                chunk_id = cur.fetchone()[0]
                total_chunks += 1

                for span in chunk.spans:
                    cur.execute(
                        "INSERT INTO chunk_spans "
                        "(chunk_id, paragraph_id, char_start, char_end) "
                        "VALUES (%s,%s,%s,%s)",
                        (chunk_id, span.paragraph_id, span.char_start, span.char_end),
                    )
                    total_spans += 1
    conn.commit()
    return total_chunks, total_spans


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--strategy", default=None, choices=sorted(STRATEGIES))
    ap.add_argument("--chunk-tokens", type=int, default=None)
    ap.add_argument("--corpus", default="semcom")
    ap.add_argument(
        "--include-holdout",
        action="store_true",
        help="Phase 6 only. Chunks holdout papers as well as dev papers.",
    )
    args = ap.parse_args()

    config = default_config()
    config.corpus = args.corpus
    if args.strategy or args.chunk_tokens:
        config.chunking = ChunkingConfig(
            strategy=args.strategy or config.chunking.strategy,
            chunk_tokens=args.chunk_tokens or config.chunking.chunk_tokens,
            overlap_tokens=config.chunking.overlap_tokens,
        )

    if args.include_holdout:
        print("!! INCLUDING HOLDOUT PAPERS. This is a Phase 6 operation.")
        print("!! Any number produced from these chunks before Phase 6 is invalid.\n")

    print(f"strategy    : {config.chunking.strategy}")
    print(f"chunk tokens: {config.chunking.chunk_tokens}")
    print(f"fingerprint : {config.fingerprint()}")
    print()
    print(config.describe_unjustified())
    print()

    try:
        conn = psycopg.connect(store.dsn(), connect_timeout=10)
    except psycopg.OperationalError as exc:
        print(f"could not connect: {exc}", file=sys.stderr)
        print("Is the container up? 'docker compose up -d'", file=sys.stderr)
        return 1

    started = time.perf_counter()
    with conn:
        chunks, spans = build(conn, config, include_holdout=args.include_holdout)

    print(
        f"built {chunks} chunks with {spans} source spans "
        f"in {time.perf_counter() - started:.1f}s"
    )
    print("\nNo retrieval quality is claimed by this run. Chunking is not tuned")
    print("until it is measured against the hand-labelled eval set (CHECKPOINT 4).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
