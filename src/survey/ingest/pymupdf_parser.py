"""PyMuPDF parser — the Phase 1 baseline.

Baseline first (CLAUDE.md): the simplest parser that runs end to end lands before
GROBID, so the bake-off has something to be measured against rather than being
an argument between two unmeasured options.

What it does honestly: text, page mapping, paragraph splitting, heading detection
by font size, reference-list capture.

What it does badly, and is expected to lose on: tables (it sees text runs, not
cells), multi-column ordering in dense two-column layouts, and reference parsing
into structured fields. Those are precisely what GROBID exists for, and the
bake-off should show it.
"""

from __future__ import annotations

import re
import statistics
from pathlib import Path

import pymupdf

from survey.ingest.model import (
    ParsedPaper,
    ParsedParagraph,
    ParsedReference,
    ParsedSection,
    ParseError,
)
from survey.ingest.tables import extract_tables

PARSER_NAME = "pymupdf"

# Headings in this corpus: "II. SYSTEM MODEL", "3.2 Channel Model", "Abstract".
_NUMBERED = re.compile(r"^\s*(\d+(\.\d+)*|[IVXLC]+)[.)]?\s+\S")
_KNOWN_HEADINGS = {
    "abstract",
    "introduction",
    "related work",
    "background",
    "system model",
    "methodology",
    "method",
    "experiments",
    "experimental results",
    "results",
    "evaluation",
    "discussion",
    "conclusion",
    "conclusions",
    "references",
    "acknowledgment",
    "acknowledgments",
    "acknowledgement",
    "acknowledgements",
}
_DOI = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+\b")
_ARXIV = re.compile(r"arXiv:\s*(\d{4}\.\d{4,5})", re.I)
# Non-capturing: a capture group makes findall return "19"/"20", not the year.
_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")


def _section_kind(heading: str | None) -> str | None:
    if not heading:
        return None
    h = heading.lower().strip(" .:0123456789ivxlc")
    if h.startswith("abstract"):
        return "abstract"
    if h.startswith("reference"):
        return "references"
    if h.startswith("acknowled"):
        return "acknowledgements"
    return "body"


def _is_heading(text: str, size: float, body_size: float, bold: bool) -> bool:
    """A line is a heading if it is short and either larger, bold, or recognisable.

    Font size alone is unreliable: captions and affiliations are often larger
    than body text. Requiring shortness first removes most of those.
    """
    stripped = text.strip()
    if not (2 <= len(stripped) <= 120):
        return False
    if stripped.endswith((".", ",", ";")) and not _NUMBERED.match(stripped):
        return False
    # The vertical arXiv stamp down the margin of page 1 is set large and short,
    # so every size-based rule below would call it a heading.
    if _ARXIV_STAMP.match(stripped):
        return False

    normalised = stripped.lower().strip(" .:0123456789ivxlc")
    if normalised in _KNOWN_HEADINGS:
        return True
    if size > body_size * 1.12:
        return True
    if bold and size >= body_size * 0.98 and _NUMBERED.match(stripped):
        return True
    # ALL CAPS short lines are headings in IEEE two-column layouts -- but so are
    # figure axis labels (BLEU, SER, AWGN, CSI), which are single words. Requiring
    # two words removes those without losing real headings, which are phrases.
    return bool(
        8 <= len(stripped) <= 60
        and stripped.isupper()
        and len(stripped.split()) >= 2
        and sum(c.isalpha() for c in stripped) >= 6
    )


def _lines(doc: pymupdf.Document) -> list[tuple[str, float, bool, int]]:
    """Flatten to (text, font_size, is_bold, page_number), in reading order."""
    out: list[tuple[str, float, bool, int]] = []
    for page_no in range(doc.page_count):
        blocks = doc[page_no].get_text("dict")["blocks"]
        for block in blocks:
            if block.get("type") != 0:  # 0 = text
                continue
            for line in block.get("lines", []):
                spans = line.get("spans", [])
                if not spans:
                    continue
                text = (_clean("".join(s.get("text", "") for s in spans)) or "").strip()
                if not text:
                    continue
                size = max(s.get("size", 0.0) for s in spans)
                bold = any("bold" in s.get("font", "").lower() for s in spans)
                out.append((text, size, bold, page_no + 1))
    return out


def _clean(text: str | None) -> str | None:
    """Strip NUL bytes and other control characters.

    Some PDFs in this corpus carry NUL inside text runs. Postgres rejects 0x00 in
    text columns outright, so a paper that parses perfectly well is quarantined at
    the storage layer for a reason that has nothing to do with parsing. Cleaning
    belongs here, where the artifact originates, not in the store.
    """
    if text is None:
        return None
    cleaned = text.replace("\x00", "")
    if any(ord(c) < 32 and c not in "\t\n\r" for c in cleaned):
        cleaned = "".join(c for c in cleaned if ord(c) >= 32 or c in "\t\n\r")
    return cleaned


def _flush(buffer: list[str], pages: list[int], ordinal: int) -> ParsedParagraph | None:
    text = " ".join(buffer).strip()
    # De-hyphenate across line breaks: "commu- nication" -> "communication".
    text = re.sub(r"(\w)-\s+(\w)", r"\1\2", text)
    text = " ".join(text.split())
    if len(text) < 2:
        return None
    return ParsedParagraph(
        text=text, ordinal=ordinal, page_from=min(pages), page_to=max(pages)
    )


def parse(path: Path, external_id: str) -> ParsedPaper:
    try:
        doc = pymupdf.open(path)
    except Exception as exc:  # pymupdf raises a variety of types
        raise ParseError(f"{external_id}: could not open PDF: {exc}") from exc

    with doc:
        if doc.page_count == 0:
            raise ParseError(f"{external_id}: PDF has no pages")

        lines = _lines(doc)
        if not lines:
            raise ParseError(
                f"{external_id}: no extractable text - scanned or image-only PDF"
            )

        sizes = [size for _, size, _, _ in lines]
        body_size = statistics.median(sizes)

        paper = ParsedPaper(
            external_id=external_id, parser=PARSER_NAME, page_count=doc.page_count
        )

        paper.title = _guess_title(lines)
        paper.tables = extract_tables(doc)

        sections: list[ParsedSection] = []
        current = ParsedSection(heading=None, ordinal=0, depth=0, kind="frontmatter")
        buffer: list[str] = []
        buf_pages: list[int] = []
        para_ordinal = 0
        in_references = False
        reference_lines: list[str] = []

        for text, size, bold, page_no in lines:
            if _is_heading(text, size, body_size, bold):
                para = _flush(buffer, buf_pages or [page_no], para_ordinal)
                if para:
                    current.paragraphs.append(para)
                    para_ordinal += 1
                buffer, buf_pages = [], []

                # A heading wrapped across two lines must not become two sections.
                # If the section we are in has a heading but took no content, this
                # line is almost certainly its continuation, so fold it in.
                if (
                    current.heading
                    and not current.paragraphs
                    and len(current.heading) < 70
                ):
                    current.heading = " ".join((current.heading + " " + text).split())
                    if current.kind is None:
                        current.kind = _section_kind(current.heading)
                    continue

                if current.paragraphs or current.heading:
                    sections.append(current)
                kind = _section_kind(text)
                in_references = kind == "references"
                depth = text.count(".") if _NUMBERED.match(text) else 0
                current = ParsedSection(
                    heading=" ".join(text.split()),
                    ordinal=len(sections),
                    depth=min(depth, 3),
                    kind=kind,
                )
                para_ordinal = 0
                continue

            if in_references:
                reference_lines.append(text)
                continue

            buffer.append(text)
            buf_pages.append(page_no)
            # A line ending in sentence punctuation and short enough to be a
            # paragraph end; crude, but paragraph boundaries in PDFs are crude.
            if text.endswith((".", "?", "!")) and len(" ".join(buffer)) > 200:
                para = _flush(buffer, buf_pages, para_ordinal)
                if para:
                    current.paragraphs.append(para)
                    para_ordinal += 1
                buffer, buf_pages = [], []

        para = _flush(buffer, buf_pages or [doc.page_count], para_ordinal)
        if para:
            current.paragraphs.append(para)
        if current.paragraphs or current.heading:
            sections.append(current)

        paper.sections = sections
        paper.references = _split_references(reference_lines)

        paper.abstract = _find_abstract(sections)

        head = " ".join(t for t, _, _, p in lines if p == 1)
        if m := _DOI.search(head):
            paper.doi = m.group(0).rstrip(".")
        years = [int(y) for y in _YEAR.findall(head)]
        if years:
            # Publication year, not a citation year: take the latest plausible.
            paper.year = max(y for y in years if y <= 2030)

    return paper


_ARXIV_STAMP = re.compile(r"^\s*arXiv:\s*\d{4}\.\d{4,5}", re.I)
# IEEE style runs the abstract inline: "Abstract—With the advent of 6G ...".
_INLINE_ABSTRACT = re.compile(r"^\s*abstract\s*[-–—:]{0,2}\s*", re.I)
_INDEX_TERMS = re.compile(r"\b(index terms|keywords)\s*[-–—:]", re.I)


def _find_abstract(sections: list[ParsedSection]) -> str | None:
    """The abstract is a heading in some papers and inline text in others.

    Both forms appear in this corpus, so look for a section of kind `abstract`
    first and fall back to a paragraph that begins with the word.
    """
    for sec in sections:
        if sec.kind == "abstract" and sec.paragraphs:
            return sec.paragraphs[0].text

    # Fall back: scan the first few paragraphs for an inline "Abstract—".
    scanned = 0
    for sec in sections:
        for para in sec.paragraphs:
            if scanned >= 8:
                return None
            scanned += 1
            if _INLINE_ABSTRACT.match(para.text):
                text = _INLINE_ABSTRACT.sub("", para.text, count=1)
                # Stop at "Index Terms" / "Keywords", which follow the abstract.
                if m := _INDEX_TERMS.search(text):
                    text = text[: m.start()]
                return text.strip() or None
    return None


def _guess_title(lines: list[tuple[str, float, bool, int]]) -> str | None:
    """Largest text on page 1 that actually looks like a title.

    Taking the largest glyph outright fails on this corpus: drop caps ("W", "B")
    and the vertical arXiv stamp are often the biggest things on the page. So
    candidate sizes are tried largest-first and the first plausible one wins.
    """
    page1 = [ln for ln in lines if ln[3] == 1]
    if not page1:
        return None

    for size in sorted({round(s, 1) for _, s, _, _ in page1}, reverse=True):
        group = [
            t
            for t, s, _, _ in page1
            if abs(s - size) < 0.5 and not _ARXIV_STAMP.match(t)
        ]
        candidate = " ".join(" ".join(group).split())
        # A drop cap set at title size gets glued to the front: "r We propose...".
        # Only lowercase: "A" and "I" are real words and start real titles
        # ("A Survey on ..."), which an unrestricted rule silently truncates.
        candidate = re.sub(r"^[a-z]\s+(?=[A-Z])", "", candidate)
        if _INLINE_ABSTRACT.match(candidate):
            continue  # this size band is the abstract, not the title
        # A title is a phrase, not a dropped capital or a running header.
        if len(candidate) >= 15 and len(candidate.split()) >= 3:
            return candidate[:400]
    return None


def _split_references(lines: list[str]) -> list[ParsedReference]:
    """Split a reference section into entries on [n] markers.

    Falls back to one entry per line when no markers are present, which is wrong
    for wrapped entries but honest about it - structured reference parsing is
    GROBID's job, and this baseline exists partly to show the difference.
    """
    if not lines:
        return []
    joined = " ".join(lines)
    parts = re.split(r"\s*\[(\d{1,3})\]\s*", joined)
    entries: list[str] = []
    if len(parts) > 2:
        for i in range(1, len(parts) - 1, 2):
            entries.append(parts[i + 1].strip())
    else:
        entries = [ln.strip() for ln in lines if len(ln.strip()) > 20]

    refs = []
    for i, raw in enumerate(entries):
        if not raw:
            continue
        doi = _DOI.search(raw)
        arxiv = _ARXIV.search(raw)
        refs.append(
            ParsedReference(
                raw=raw[:2000],
                ordinal=i,
                doi=doi.group(0).rstrip(".") if doi else None,
                arxiv_id=arxiv.group(1) if arxiv else None,
            )
        )
    return refs
