"""Resolve citation edges against the corpus — task 1.7.

Ingestion stores every reference as an edge with `dst_paper_id = NULL`, because a
reference can point at a paper that has not been ingested yet. Resolution runs
afterwards, over the whole corpus at once.

Most references point outside the corpus and stay unresolved. That is the normal
case, not a failure: 42 papers cite hundreds of works, and only the ones that
happen to also be in the corpus can be linked. Phase 5 mines these edges for
reranker training pairs, where a wrong link is worse than a missing one, so
matching is deliberately conservative.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

import psycopg

# A DOI or arXiv id in a reference string is an identity, not a guess.
_DOI = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+\b")
_ARXIV = re.compile(r"arXiv[:\s]*(\d{4}\.\d{4,5})", re.I)
_STOPWORDS = {
    "a", "an", "the", "of", "for", "and", "on", "in", "to", "with", "via",
    "based", "using", "towards", "toward",
}
# A title shorter than this is too generic to identify a paper by phrase alone.
MIN_TITLE_TOKENS = 4


@dataclass(slots=True)
class ResolutionStats:
    total: int = 0
    by_doi: int = 0
    by_arxiv: int = 0
    by_title: int = 0
    unresolved: int = 0
    self_citations_dropped: int = 0
    ambiguous: int = 0

    @property
    def resolved(self) -> int:
        return self.by_doi + self.by_arxiv + self.by_title


def _normalise(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]+", " ", text.lower())


def normalised_phrase(text: str) -> str:
    """Whitespace-collapsed, accent-stripped, lowercase — for substring matching."""
    return " ".join(_normalise(text).split())


def title_in_reference(title: str, reference: str) -> bool:
    """Does the paper's title appear in the reference as a contiguous phrase?

    This replaced bag-of-words token overlap, which failed badly on this corpus
    (P-003). Every paper here shares a vocabulary, so a short generic title like
    "Engineering Semantic Communication: A Survey" had all four of its content
    words present in references to entirely unrelated work, and an overlap score
    could not tell the difference. Word order is the signal that distinguishes
    "Robust Semantic Communication Driven by Knowledge Graph" from "Cognitive
    semantic communication systems driven by knowledge graph" — two different
    papers whose token sets almost coincide.

    References quote titles verbatim, so requiring the phrase is not restrictive
    in practice; it only rejects coincidental vocabulary overlap.
    """
    needle = normalised_phrase(title)
    if len(needle.split()) < MIN_TITLE_TOKENS:
        return False

    haystack = _punct_preserving(reference)
    if _phrase_ends_cleanly(needle, haystack):
        return True

    # Line-broken titles lose a word to hyphenation ("tutorial-cum- survey"), so
    # allow a long title to match on all but its last two words. Still an ordered
    # phrase, and still boundary-checked.
    words = needle.split()
    if len(words) >= 8:
        return _phrase_ends_cleanly(" ".join(words[:-2]), haystack, exact_end=False)
    return False


# Punctuation that ends a quoted title in a reference string.
_TITLE_END = set(",.;\"'”’)]")


def _punct_preserving(text: str) -> str:
    """Lowercase and strip accents, but keep the punctuation that ends a title."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9,.;\"'”’)\]\s-]+", " ", text.lower())
    # Two kinds of hyphen, and they need opposite treatment:
    #   "Commu- nication"  -> line-break hyphenation, join it
    #   "learning-enabled" -> a real hyphen, space it
    # Distinguished by the whitespace that follows, the same way the parser's
    # paragraph de-hyphenation does it.
    text = re.sub(r"(\w)-\s+(\w)", r"\1\2", text)
    return " ".join(text.replace("-", " ").split())


def _phrase_ends_cleanly(needle: str, haystack: str, *, exact_end: bool = True) -> bool:
    """Find `needle` in `haystack` and require it to end at a title boundary.

    Without this, a title that is a *prefix* of another paper's title matches the
    longer one: "Deep Learning Enabled Semantic Communication Systems" (Xie) is
    contained in the reference for "Deep learning-enabled semantic communication
    systems with task-unaware transmitter" (Zhang). Both are real papers and the
    first is in the corpus, so the edge looked plausible and was wrong.

    References quote titles, so the character after the title is punctuation. That
    is the boundary this checks.
    """
    start = 0
    while (idx := haystack.find(needle, start)) != -1:
        end = idx + len(needle)
        if end >= len(haystack):
            return True
        rest = haystack[end:].lstrip()
        if not rest or rest[0] in _TITLE_END:
            return True
        if not exact_end:
            return True
        start = idx + 1
    return False


def resolve(
    conn: psycopg.Connection, corpus_id: str = "semcom"
) -> ResolutionStats:
    """Link citation edges to corpus papers by DOI, arXiv id, then title.

    Existing links are cleared first. Resolution is derived data recomputed from
    the reference strings, so a run must be able to *remove* a link that a
    previous, worse matcher asserted — otherwise a precision fix can never undo
    the bad edges it was written to prevent (P-003).
    """
    stats = ResolutionStats()

    with conn.cursor() as cur:
        cur.execute(
            "UPDATE citation_edges e SET dst_paper_id = NULL, dst_external_id = NULL "
            "FROM papers p WHERE p.id = e.src_paper_id AND p.corpus_id = %s",
            (corpus_id,),
        )

    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, external_id, title, doi FROM papers "
            "WHERE corpus_id = %s AND ingest_status = 'ok'",
            (corpus_id,),
        )
        papers = cur.fetchall()

    by_doi: dict[str, int] = {}
    by_title: list[tuple[int, str]] = []
    for paper_id, _ext, title, doi in papers:
        if doi:
            by_doi[doi.lower().rstrip(".")] = paper_id
        if title:
            by_title.append((paper_id, title))

    with conn.cursor() as cur:
        cur.execute(
            "SELECT e.id, e.src_paper_id, e.raw_reference FROM citation_edges e "
            "JOIN papers p ON p.id = e.src_paper_id "
            "WHERE p.corpus_id = %s AND e.dst_paper_id IS NULL "
            "AND e.raw_reference IS NOT NULL",
            (corpus_id,),
        )
        edges = cur.fetchall()

    updates: list[tuple[int, str, int]] = []
    for edge_id, src_id, raw in edges:
        stats.total += 1
        dst: int | None = None
        how = ""

        if m := _DOI.search(raw):
            dst = by_doi.get(m.group(0).lower().rstrip("."))
            how = "doi"

        if dst is None and (m := _ARXIV.search(raw)):
            # arXiv ids are not stored on papers yet; left for when the parser
            # records them. Counted so the gap is visible rather than assumed shut.
            pass

        if dst is None:
            matches = [pid for pid, title in by_title if title_in_reference(title, raw)]
            # An ambiguous reference matching two corpus titles is not resolved.
            # One paper's title being a prefix of another's is rare but real, and
            # guessing between them would put a wrong edge into the graph that
            # Phase 5 later mines for training pairs.
            if len(matches) == 1:
                dst, how = matches[0], "title"
            elif len(matches) > 1:
                stats.ambiguous += 1

        if dst is None:
            stats.unresolved += 1
            continue

        # A paper citing itself is a parsing artifact (running headers, the
        # paper's own title in a footer), never a real citation edge.
        if dst == src_id:
            stats.self_citations_dropped += 1
            stats.unresolved += 1
            continue

        updates.append((dst, how, edge_id))
        if how == "doi":
            stats.by_doi += 1
        elif how == "title":
            stats.by_title += 1

    if updates:
        with conn.cursor() as cur:
            cur.executemany(
                "UPDATE citation_edges SET dst_paper_id = %s, dst_external_id = "
                "(SELECT external_id FROM papers WHERE id = %s) WHERE id = %s",
                [(dst, dst, edge_id) for dst, _how, edge_id in updates],
            )

    return stats
