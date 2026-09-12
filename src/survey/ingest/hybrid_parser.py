"""Hybrid parser — GROBID for structure, PyMuPDF for tables and dates.

The Phase 1 bake-off (D-014) produced no outright winner. GROBID wins decisively
on abstracts (100% vs 15%), structured references (100% vs 0%) and speed; PyMuPDF
wins on tables (40% vs 0% — the CRF GROBID image has no table model at all) and
on publication year (100% vs 35%, because it will take any year printed on page 1
where GROBID reports only what it can attribute).

Tables are a Phase 1 exit criterion, so a GROBID-only pipeline cannot pass. This
module takes each parser's strengths rather than picking a loser.

Fallback is genuine, not decorative: if GROBID is unreachable or fails on a paper,
the whole parse falls back to PyMuPDF, which had 0% hard failures over the corpus.
A degraded parse beats a quarantined paper.
"""

from __future__ import annotations

from pathlib import Path

import pymupdf

from survey.ingest import grobid_parser, pymupdf_parser
from survey.ingest.model import ParsedPaper, ParseError
from survey.ingest.tables import extract_tables

PARSER_NAME = "hybrid"


def _page_count(path: Path) -> int | None:
    try:
        with pymupdf.open(path) as doc:
            return doc.page_count
    except Exception:
        return None


def parse(path: Path, external_id: str) -> ParsedPaper:
    try:
        paper = grobid_parser.parse(path, external_id)
    except ParseError:
        # GROBID down, busy, or defeated by this PDF. PyMuPDF alone is worse but
        # complete, and a paper parsed imperfectly is worth more than one missing.
        paper = pymupdf_parser.parse(path, external_id)
        paper.parser = f"{PARSER_NAME}:pymupdf-only"
        return paper

    paper.parser = PARSER_NAME
    paper.page_count = paper.page_count or _page_count(path)

    # Tables: GROBID's CRF image extracts none, so these come from PyMuPDF.
    try:
        with pymupdf.open(path) as doc:
            paper.tables = extract_tables(doc)
    except Exception:
        paper.tables = []

    # Venue: GROBID never supplies it without `consolidateHeader`, so this is
    # always a gap rather than sometimes one. Reading page 1 alone avoids paying
    # for a second full parse on every paper just to fill one field.
    if not paper.venue:
        paper.venue = pymupdf_parser.venue_from_pdf(path)

    # Year: GROBID reports a date only when it can attribute one, which is right
    # for a bibliographic tool and wrong for us — we would rather have the year
    # printed on the page than a null. Only fills a gap; never overrides GROBID.
    if paper.year is None:
        try:
            fallback = pymupdf_parser.parse(path, external_id)
        except ParseError:
            fallback = None
        if fallback is not None:
            paper.year = fallback.year
            paper.venue = paper.venue or fallback.venue
            paper.doi = paper.doi or fallback.doi
            if not paper.title:
                paper.title = fallback.title

    return paper
