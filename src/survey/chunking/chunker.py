"""Chunking — Phase 2 baseline and the structural variants Phase 3 will compare.

Built under C-006: every parameter here has a default, and **no default is
justified**. Chunk size, overlap and strategy are exactly the knobs Phase 3
measures one at a time. Nothing in this module claims one is better than another,
and the defaults exist only so the code can run at all.

The one thing that is NOT a free choice: every chunk carries the paragraph id and
character offsets it came from, so a retrieved chunk maps back to a citable span
(D-003). Chunking changes repeatedly during Phase 3; citations must not move when
it does, which is why spans are anchored to paragraphs rather than to chunks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# --- Unjustified defaults, pending eval (C-006) ---------------------------
# 512 tokens is the spec's naive baseline (§5, Phase 2), not a finding.
DEFAULT_CHUNK_TOKENS = 512
DEFAULT_OVERLAP_TOKENS = 0
# ~4 characters per token is the usual English rule of thumb. Used only to avoid
# a tokenizer dependency in the baseline; a real tokenizer replaces this when the
# embedding model is chosen, which is itself a Phase 3 decision.
CHARS_PER_TOKEN = 4

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\[])")


@dataclass(slots=True)
class SourceSpan:
    """Where a piece of chunk text came from. See D-003."""

    paragraph_id: int
    char_start: int
    char_end: int


@dataclass(slots=True)
class Chunk:
    text: str
    ordinal: int
    paper_id: int
    section_id: int | None
    # A chunk may span several paragraphs, so it carries a list of spans rather
    # than one range. Citation resolution later picks the span containing the
    # sentence it is citing.
    spans: list[SourceSpan] = field(default_factory=list)
    strategy: str = ""

    @property
    def char_count(self) -> int:
        return len(self.text)


@dataclass(slots=True)
class ParagraphInput:
    """A paragraph as stored, which is what chunking reads."""

    paragraph_id: int
    paper_id: int
    section_id: int | None
    text: str
    ordinal: int


def _token_estimate(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


def split_sentences(text: str) -> list[str]:
    """Split on sentence boundaries, conservatively.

    Deliberately crude, and deliberately NOT used to define citation spans:
    academic text breaks naive sentence splitting (citations, abbreviations,
    inline maths), and D-003 rejected sentence ids as a citation key for exactly
    that reason. Here a bad split costs a slightly awkward chunk boundary, which
    is recoverable; there it would have corrupted stored citations.
    """
    parts = _SENTENCE_END.split(text)
    return [p.strip() for p in parts if p.strip()]


def _word_boundary_cuts(
    text: str, start: int, end: int, budget: int
) -> list[tuple[int, int]]:
    """Cut text[start:end] into pieces no larger than budget, on whitespace.

    Returns offsets into the original text, not substrings, so the spans stay
    anchored to real source positions (D-003).
    """
    if end - start <= budget:
        return [(start, end)]

    cuts: list[tuple[int, int]] = []
    cursor = start
    while cursor < end:
        limit = min(cursor + budget, end)
        if limit < end:
            space = text.rfind(" ", cursor, limit)
            # No whitespace in a whole budget's worth of characters means an
            # unbroken run (a URL, a long identifier); cut it hard rather than
            # emitting something oversized.
            limit = space if space > cursor else limit
        cuts.append((cursor, limit))
        cursor = limit + 1 if text[limit : limit + 1] == " " else limit
    return cuts


def flat_chunks(
    paragraphs: list[ParagraphInput],
    chunk_tokens: int = DEFAULT_CHUNK_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
) -> list[Chunk]:
    """Fixed-size chunks that ignore structure — the spec's naive baseline.

    Paragraphs are concatenated in order and cut at a fixed size, crossing
    section boundaries freely. That is the point: it is the thing Phase 3's
    section-aware chunking is measured against (§5, Phase 3, item 1).
    """
    chunks: list[Chunk] = []
    if not paragraphs:
        return chunks

    budget = chunk_tokens * CHARS_PER_TOKEN
    overlap = overlap_tokens * CHARS_PER_TOKEN

    buffer: list[str] = []
    spans: list[SourceSpan] = []
    size = 0
    ordinal = 0

    def flush() -> None:
        nonlocal buffer, spans, size, ordinal
        if not buffer:
            return
        chunks.append(
            Chunk(
                text=" ".join(buffer),
                ordinal=ordinal,
                paper_id=paragraphs[0].paper_id,
                section_id=None,  # flat chunking does not respect sections
                spans=list(spans),
                strategy="flat",
            )
        )
        ordinal += 1
        if overlap and chunks[-1].text:
            tail = chunks[-1].text[-overlap:]
            buffer, size = [tail], len(tail)
            # The overlap tail is a copy of already-cited text; it carries no new
            # spans, so the next chunk's citations resolve to the original.
            spans = []
        else:
            buffer, spans, size = [], [], 0

    for para in paragraphs:
        text = para.text
        if size and size + len(text) > budget:
            flush()
        # A single paragraph longer than the budget is split on sentences rather
        # than mid-word.
        if len(text) > budget:
            offset = 0
            for sentence in split_sentences(text):
                start = text.find(sentence, offset)
                if start < 0:
                    start = offset
                end = start + len(sentence)
                offset = end
                # A "sentence" can still exceed the budget: table rows, equation
                # dumps and reference blocks arrive as long runs with no
                # terminal punctuation. Left whole, the embedding model would
                # truncate them silently, losing text with no error anywhere —
                # so cut on word boundaries as a last resort.
                for piece_start, piece_end in _word_boundary_cuts(
                    text, start, end, budget
                ):
                    piece = text[piece_start:piece_end]
                    if size and size + len(piece) > budget:
                        flush()
                    buffer.append(piece)
                    spans.append(
                        SourceSpan(para.paragraph_id, piece_start, piece_end)
                    )
                    size += len(piece)
            continue

        buffer.append(text)
        spans.append(SourceSpan(para.paragraph_id, 0, len(text)))
        size += len(text)

    flush()
    return chunks


def section_chunks(
    paragraphs: list[ParagraphInput],
    chunk_tokens: int = DEFAULT_CHUNK_TOKENS,
) -> list[Chunk]:
    """Chunks that never cross a section boundary (§5, Phase 3, item 1).

    Built now, measured later. Whether this beats flat chunking on this corpus is
    a Phase 3 question, and the answer is not assumed here.
    """
    chunks: list[Chunk] = []
    by_section: dict[int | None, list[ParagraphInput]] = {}
    for para in paragraphs:
        by_section.setdefault(para.section_id, []).append(para)

    ordinal = 0
    for section_id, group in by_section.items():
        group.sort(key=lambda p: p.ordinal)
        for chunk in flat_chunks(group, chunk_tokens=chunk_tokens):
            chunk.section_id = section_id
            chunk.ordinal = ordinal
            chunk.strategy = "section"
            chunks.append(chunk)
            ordinal += 1
    return chunks


def paragraph_chunks(paragraphs: list[ParagraphInput]) -> list[Chunk]:
    """One chunk per paragraph — the unit for small-to-big retrieval.

    Phase 3 item 3 embeds paragraphs and returns the enclosing subsection. This
    produces the embedding side of that; the return side is a retrieval concern.
    """
    return [
        Chunk(
            text=para.text,
            ordinal=i,
            paper_id=para.paper_id,
            section_id=para.section_id,
            spans=[SourceSpan(para.paragraph_id, 0, len(para.text))],
            strategy="paragraph",
        )
        for i, para in enumerate(paragraphs)
    ]


STRATEGIES = {
    "flat": flat_chunks,
    "section": section_chunks,
    "paragraph": paragraph_chunks,
}
