"""Parser output types.

Every parser produces these, so the bake-off compares parsers rather than
comparing storage code, and swapping a parser cannot change the database shape.

Deliberately free of chunking: paragraphs are stored as the parser found them.
Chunking is a Phase 3 concern that reads from these, never reshapes them
(spec §5, Phase 1).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ParsedParagraph:
    text: str
    ordinal: int
    page_from: int | None = None
    page_to: int | None = None


@dataclass(slots=True)
class ParsedSection:
    heading: str | None
    ordinal: int
    depth: int
    kind: str | None = None          # abstract | body | references | ...
    paragraphs: list[ParsedParagraph] = field(default_factory=list)


@dataclass(slots=True)
class ParsedTable:
    ordinal: int
    label: str | None                # "Table 2"
    caption: str | None
    grid: dict                       # rows/cells + multi-row header structure
    page: int | None = None
    section_ordinal: int | None = None


@dataclass(slots=True)
class ParsedReference:
    raw: str
    ordinal: int
    # Resolved against the corpus later; the parser only reports what it read.
    doi: str | None = None
    arxiv_id: str | None = None
    title: str | None = None


@dataclass(slots=True)
class ParsedPaper:
    """One paper as some parser saw it."""

    external_id: str
    parser: str                      # which parser produced this
    title: str | None = None
    abstract: str | None = None
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    page_count: int | None = None
    sections: list[ParsedSection] = field(default_factory=list)
    tables: list[ParsedTable] = field(default_factory=list)
    references: list[ParsedReference] = field(default_factory=list)

    # --- quality signals, used by the bake-off rather than stored as truth ---
    @property
    def paragraph_count(self) -> int:
        return sum(len(s.paragraphs) for s in self.sections)

    @property
    def char_count(self) -> int:
        return sum(len(p.text) for s in self.sections for p in s.paragraphs)


class ParseError(RuntimeError):
    """A paper could not be parsed. Quarantined, never silently skipped."""
