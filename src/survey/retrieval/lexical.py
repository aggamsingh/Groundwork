"""Lexical retrieval over chunks, via Postgres full-text search.

Spec section 4 allows BM25 "via Postgres full-text search, or a local rank_bm25
index if FTS proves inadequate", to be decided in Phase 2 with a measurement.
This is the FTS side, so that measurement can happen.

An honesty note that matters for every report downstream: `ts_rank_cd` is **not**
BM25. It is a different lexical scoring function — it has no document-length
saturation term and no tunable k1/b. Calling it BM25 out of habit would make the
Phase 3 ablation table claim something untrue about what was run, so the mode is
named `fts` throughout and only a real BM25 implementation may be called bm25.

Reads `v_dev_chunks`, never `chunks`, so holdout papers cannot enter a result set
(D-004).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import psycopg


@dataclass(slots=True)
class Retrieved:
    chunk_id: int
    paper_id: int
    score: float
    text: str
    rank: int


# websearch_to_tsquery handles quoted phrases and OR/-, and — unlike
# to_tsquery — never raises on punctuation a user might type. Research questions
# contain hyphens, parentheses and colons constantly.
#
# It also ANDs every term, which is consequential: "channel-aware training AWGN"
# returns nothing on this corpus, because no single chunk contains all three.
# `term_logic="any"` ORs them instead, trading precision for recall.
#
# WHICH IS BETTER IS UNMEASURED (C-006). Both are implemented, neither is
# preferred, and the default below is the conservative one rather than the
# chosen one. This is precisely the kind of question the hand-labelled eval set
# exists to settle.
DEFAULT_TERM_LOGIC = "all"


def to_or_query(query: str) -> str:
    """Rewrite a natural-language query into an OR'd tsquery expression.

    Punctuation is stripped rather than escaped: `to_tsquery` raises on stray
    parentheses and colons, and research questions are full of them.
    """
    terms = re.findall(r"[A-Za-z0-9]+", query)
    return " | ".join(terms)


def search(
    conn: psycopg.Connection,
    query: str,
    *,
    top_k: int = 5,
    corpus_id: str = "semcom",
    config_fingerprint: str | None = None,
    term_logic: str = DEFAULT_TERM_LOGIC,
    include_holdout: bool = False,
) -> list[Retrieved]:
    """Rank dev-set chunks against a query by lexical overlap.

    `include_holdout` exists for Phase 6 and defaults to False. It is a keyword
    argument with an explicit name rather than a table parameter, so that reading
    any call site tells you whether the holdout is in play.
    """
    if term_logic not in ("all", "any"):
        raise ValueError(f"term_logic must be 'all' or 'any', got {term_logic!r}")

    source = "chunks" if include_holdout else "v_dev_chunks"
    if term_logic == "all":
        query_fn, query_text = "websearch_to_tsquery", query
    else:
        query_fn, query_text = "to_tsquery", to_or_query(query)
        if not query_text:
            return []

    sql = f"""
        SELECT c.id, c.paper_id, c.text,
               ts_rank_cd(c.text_search, q) AS score
        FROM {source} c
        JOIN papers p ON p.id = c.paper_id,
             {query_fn}('english', %(query)s) AS q
        WHERE p.corpus_id = %(corpus)s
          AND c.text_search @@ q
          -- Cast required: Postgres cannot infer the type of a NULL parameter
          -- used only in an IS NULL test.
          AND (%(fingerprint)s::text IS NULL
               OR c.config_fingerprint = %(fingerprint)s::text)
        ORDER BY score DESC, c.id
        LIMIT %(limit)s
    """

    with conn.cursor() as cur:
        cur.execute(
            sql,
            {
                "query": query_text,
                "corpus": corpus_id,
                "fingerprint": config_fingerprint,
                "limit": top_k,
            },
        )
        rows = cur.fetchall()

    return [
        Retrieved(chunk_id=r[0], paper_id=r[1], text=r[2], score=float(r[3]), rank=i)
        for i, r in enumerate(rows, start=1)
    ]


def reciprocal_rank_fusion(
    rankings: list[list[Retrieved]],
    *,
    k: int = 60,
    top_k: int = 5,
) -> list[Retrieved]:
    """Fuse several ranked lists by reciprocal rank (Phase 3 item 4).

    score = sum over lists of 1 / (k + rank)

    RRF is used because it needs no score calibration between retrievers, which
    matters here: `ts_rank_cd` and cosine similarity are on unrelated scales and
    a weighted sum of them would be arithmetic on incomparable quantities.

    k=60 is the value from the original RRF paper. It has NOT been tuned on this
    corpus and is a config parameter for that reason (C-006).
    """
    scores: dict[int, float] = {}
    best: dict[int, Retrieved] = {}

    for ranking in rankings:
        for item in ranking:
            scores[item.chunk_id] = scores.get(item.chunk_id, 0.0) + 1.0 / (
                k + item.rank
            )
            # Keep whichever copy ranked highest, for its text and paper_id.
            if item.chunk_id not in best or item.rank < best[item.chunk_id].rank:
                best[item.chunk_id] = item

    ordered = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    return [
        Retrieved(
            chunk_id=chunk_id,
            paper_id=best[chunk_id].paper_id,
            text=best[chunk_id].text,
            score=score,
            rank=i,
        )
        for i, (chunk_id, score) in enumerate(ordered[:top_k], start=1)
    ]
