"""GROBID parser — the Phase 1 challenger (task 1.4).

Emits the same `ParsedPaper` as the PyMuPDF baseline, so the bake-off compares
parsers rather than storage code.

GROBID is a service, not a library, so it brings failure modes the baseline does
not have: the container may be down, slow to start, or return a 503 while its
models load. Those are reported as `ParseError` like any other parse failure —
a paper GROBID cannot handle is quarantined, not silently dropped.

TEI namespace handling is explicit throughout. GROBID returns TEI-XML in the
`http://www.tei-c.org/ns/1.0` namespace, and forgetting it yields empty results
that look exactly like a paper with no content.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from xml.etree import ElementTree as ET

import urllib3

from survey.ingest.model import (
    ParsedPaper,
    ParsedParagraph,
    ParsedReference,
    ParsedSection,
    ParseError,
)

PARSER_NAME = "grobid"
TEI = {"tei": "http://www.tei-c.org/ns/1.0"}

DEFAULT_URL = "http://localhost:8070"
# GROBID is slow on long surveys; several of these papers are 40 pages.
TIMEOUT_SECONDS = 180

_http = urllib3.PoolManager(timeout=urllib3.Timeout(total=TIMEOUT_SECONDS))


def base_url() -> str:
    return os.environ.get("GROBID_URL", DEFAULT_URL).rstrip("/")


def is_alive(url: str | None = None) -> bool:
    try:
        resp = _http.request(
            "GET", f"{url or base_url()}/api/isalive", timeout=urllib3.Timeout(total=5)
        )
    except Exception:
        return False
    return resp.status == 200


def _text(node: ET.Element | None) -> str:
    """All text under a node, whitespace-collapsed.

    `itertext` rather than `.text`: TEI marks up citations and formulas inline,
    so `.text` stops at the first `<ref>` and silently truncates the sentence.
    """
    if node is None:
        return ""
    return " ".join("".join(node.itertext()).split())


def _clean(text: str | None) -> str | None:
    if text is None:
        return None
    return text.replace("\x00", "") or None


def fetch_tei(path: Path, url: str | None = None) -> str:
    """POST the PDF to GROBID and return TEI-XML."""
    endpoint = f"{url or base_url()}/api/processFulltextDocument"
    try:
        resp = _http.request(
            "POST",
            endpoint,
            fields={
                "input": (path.name, path.read_bytes(), "application/pdf"),
                # Ask for structured reference data and coordinates; without
                # consolidation, which would call external services per paper.
                "consolidateHeader": "0",
                "consolidateCitations": "0",
                "segmentSentences": "0",
            },
        )
    except Exception as exc:
        raise ParseError(f"{path.name}: GROBID unreachable at {endpoint}: {exc}") from exc

    if resp.status == 503:
        raise ParseError(f"{path.name}: GROBID busy (503) - models still loading?")
    if resp.status != 200:
        raise ParseError(f"{path.name}: GROBID returned HTTP {resp.status}")
    return resp.data.decode("utf-8", "replace")


def parse_tei(tei_xml: str, external_id: str, page_count: int | None = None) -> ParsedPaper:
    """Convert GROBID TEI-XML into a ParsedPaper."""
    try:
        root = ET.fromstring(tei_xml)
    except ET.ParseError as exc:
        raise ParseError(f"{external_id}: GROBID returned unparseable TEI: {exc}") from exc

    paper = ParsedPaper(
        external_id=external_id, parser=PARSER_NAME, page_count=page_count
    )

    header = root.find(".//tei:teiHeader", TEI)
    if header is not None:
        paper.title = _clean(_text(header.find(".//tei:titleStmt/tei:title", TEI)))
        paper.venue = _clean(
            _text(header.find(".//tei:monogr/tei:title[@level='j']", TEI))
        ) or _clean(_text(header.find(".//tei:monogr/tei:title[@level='m']", TEI)))

        date = header.find(".//tei:publicationStmt/tei:date", TEI)
        when = (date.get("when") if date is not None else None) or _text(date)
        if m := re.search(r"(19|20)\d{2}", when or ""):
            paper.year = int(m.group(0))

        for idno in header.findall(".//tei:idno", TEI):
            kind = (idno.get("type") or "").upper()
            if kind == "DOI" and not paper.doi:
                paper.doi = _clean(_text(idno))
            elif kind == "ARXIV" and not paper.arxiv_id:
                paper.arxiv_id = _clean(_text(idno))

    abstract = root.find(".//tei:profileDesc//tei:abstract", TEI)
    paper.abstract = _clean(_text(abstract)) or None

    sections: list[ParsedSection] = []
    if paper.abstract:
        sections.append(
            ParsedSection(
                heading="Abstract",
                ordinal=0,
                depth=0,
                kind="abstract",
                paragraphs=[ParsedParagraph(text=paper.abstract, ordinal=0)],
            )
        )

    body = root.find(".//tei:text/tei:body", TEI)
    if body is not None:
        for div in body.findall("tei:div", TEI):
            head = div.find("tei:head", TEI)
            heading = _clean(_text(head)) or None
            # GROBID puts the section number in @n rather than in the text.
            number = head.get("n") if head is not None else None
            if heading and number:
                heading = f"{number} {heading}"

            paragraphs = []
            for i, p in enumerate(div.findall("tei:p", TEI)):
                text = _clean(_text(p))
                if text and len(text) > 1:
                    paragraphs.append(ParsedParagraph(text=text, ordinal=i))

            if not paragraphs and not heading:
                continue
            sections.append(
                ParsedSection(
                    heading=heading,
                    ordinal=len(sections),
                    depth=(number or "").count(".") if number else 0,
                    kind="body",
                    paragraphs=paragraphs,
                )
            )

    paper.sections = sections
    paper.references = _references(root)
    return paper


def _references(root: ET.Element) -> list[ParsedReference]:
    """Structured references — the thing GROBID is actually for.

    The baseline splits a reference section on `[n]` markers and keeps the raw
    string. GROBID returns title, DOI and arXiv id as fields, which is what makes
    citation resolution identity-based rather than phrase-matched (see P-003).
    """
    refs: list[ParsedReference] = []
    for i, bibl in enumerate(root.findall(".//tei:listBibl/tei:biblStruct", TEI)):
        title = _clean(_text(bibl.find(".//tei:title[@level='a']", TEI))) or _clean(
            _text(bibl.find(".//tei:title", TEI))
        )
        doi = arxiv = None
        for idno in bibl.findall(".//tei:idno", TEI):
            kind = (idno.get("type") or "").upper()
            if kind == "DOI":
                doi = _clean(_text(idno))
            elif kind == "ARXIV":
                arxiv = _clean(_text(idno))

        raw = _clean(_text(bibl)) or title
        if not raw:
            continue
        refs.append(
            ParsedReference(
                raw=raw[:2000], ordinal=i, title=title, doi=doi, arxiv_id=arxiv
            )
        )
    return refs


def parse(path: Path, external_id: str) -> ParsedPaper:
    tei = fetch_tei(path)
    paper = parse_tei(tei, external_id)
    if not paper.sections:
        raise ParseError(f"{external_id}: GROBID returned no body sections")
    return paper
