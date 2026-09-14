"""Chunking tests.

What these check is that chunking is *correct and reversible* â€” text is not lost,
spans point back at real source offsets, sections are respected where they are
meant to be. What they deliberately do NOT check is whether any strategy is
better: that is a Phase 3 measurement against the user's eval questions (C-006).
"""

from __future__ import annotations

import unittest

from survey.chunking.chunker import (
    CHARS_PER_TOKEN,
    ParagraphInput,
    flat_chunks,
    paragraph_chunks,
    section_chunks,
    split_sentences,
)


def para(pid: int, text: str, section_id: int | None = 1, ordinal: int = 0):
    return ParagraphInput(
        paragraph_id=pid, paper_id=7, section_id=section_id, text=text, ordinal=ordinal
    )


class TestSentenceSplit(unittest.TestCase):
    def test_splits_on_sentence_boundaries(self) -> None:
        text = "The channel is AWGN. We train for 100 epochs. Results follow."
        self.assertEqual(len(split_sentences(text)), 3)

    def test_does_not_split_on_decimals(self) -> None:
        # "0.75" must not become two sentences; numbers are everywhere here.
        text = "BLEU reached 0.75 at 6 dB. That is the headline."
        self.assertEqual(len(split_sentences(text)), 2)

    def test_empty(self) -> None:
        self.assertEqual(split_sentences("   "), [])


class TestFlatChunks(unittest.TestCase):
    def test_no_text_is_lost(self) -> None:
        paragraphs = [para(i, f"Paragraph number {i} with some content.") for i in range(20)]
        chunks = flat_chunks(paragraphs, chunk_tokens=10)
        joined = " ".join(c.text for c in chunks)
        for p in paragraphs:
            self.assertIn(p.text, joined)

    def test_respects_the_size_budget(self) -> None:
        paragraphs = [para(i, "word " * 50) for i in range(10)]
        budget = 20 * CHARS_PER_TOKEN
        chunks = flat_chunks(paragraphs, chunk_tokens=20)
        for chunk in chunks:
            self.assertLessEqual(chunk.char_count, budget)

    def test_unpunctuated_run_is_cut_on_word_boundaries(self) -> None:
        # Table rows, equation dumps and reference blocks arrive as long runs
        # with no terminal punctuation. Left whole they would be silently
        # truncated by the embedding model â€” text lost with no error anywhere.
        text = "word " * 100
        budget = 20 * CHARS_PER_TOKEN
        chunks = flat_chunks([para(1, text)], chunk_tokens=20)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(chunk.char_count, budget)
            self.assertNotIn("wor ", chunk.text)  # never cut mid-word

    def test_unbroken_run_with_no_spaces_is_still_bounded(self) -> None:
        # A URL or long identifier offers no whitespace to cut on; it must still
        # not produce an oversized chunk.
        text = "x" * 500
        budget = 20 * CHARS_PER_TOKEN
        chunks = flat_chunks([para(1, text)], chunk_tokens=20)
        for chunk in chunks:
            self.assertLessEqual(chunk.char_count, budget)

    def test_spans_point_at_real_source_text(self) -> None:
        text = "Semantic communication transmits meaning rather than bits."
        chunks = flat_chunks([para(42, text)], chunk_tokens=512)
        self.assertEqual(len(chunks), 1)
        span = chunks[0].spans[0]
        self.assertEqual(span.paragraph_id, 42)
        # The span must slice the ORIGINAL paragraph back out. This is the
        # property citations depend on (D-003); if it breaks, every citation
        # points somewhere plausible and wrong.
        self.assertEqual(text[span.char_start : span.char_end], text)

    def test_long_paragraph_is_split_on_sentences_not_mid_word(self) -> None:
        sentences = [f"Sentence number {i} says something." for i in range(40)]
        long_text = " ".join(sentences)
        chunks = flat_chunks([para(1, long_text)], chunk_tokens=20)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            # No chunk should start or end mid-word.
            self.assertFalse(chunk.text.startswith(" "))
            self.assertNotIn("  ", chunk.text)

    def test_spans_of_a_split_paragraph_slice_correctly(self) -> None:
        sentences = [f"Fact {i} is stated here clearly." for i in range(30)]
        long_text = " ".join(sentences)
        chunks = flat_chunks([para(9, long_text)], chunk_tokens=15)
        for chunk in chunks:
            for span in chunk.spans:
                sliced = long_text[span.char_start : span.char_end]
                self.assertIn(sliced, chunk.text)

    def test_empty_input(self) -> None:
        self.assertEqual(flat_chunks([]), [])

    def test_flat_chunking_crosses_sections(self) -> None:
        # The naive baseline is *supposed* to ignore structure; that is what
        # Phase 3's section-aware variant is measured against.
        paragraphs = [
            para(1, "Intro text here.", section_id=1),
            para(2, "Method text here.", section_id=2),
        ]
        chunks = flat_chunks(paragraphs, chunk_tokens=512)
        self.assertEqual(len(chunks), 1)
        self.assertIsNone(chunks[0].section_id)


class TestSectionChunks(unittest.TestCase):
    def test_never_crosses_a_section_boundary(self) -> None:
        paragraphs = [
            para(1, "Intro one.", section_id=1, ordinal=0),
            para(2, "Intro two.", section_id=1, ordinal=1),
            para(3, "Method one.", section_id=2, ordinal=0),
        ]
        chunks = section_chunks(paragraphs, chunk_tokens=512)
        self.assertEqual(len(chunks), 2)
        sections = {c.section_id for c in chunks}
        self.assertEqual(sections, {1, 2})
        for chunk in chunks:
            if chunk.section_id == 1:
                self.assertNotIn("Method", chunk.text)

    def test_ordinals_are_unique_and_sequential(self) -> None:
        paragraphs = [para(i, f"Text {i}.", section_id=i % 3) for i in range(9)]
        chunks = section_chunks(paragraphs, chunk_tokens=512)
        ordinals = [c.ordinal for c in chunks]
        self.assertEqual(ordinals, list(range(len(chunks))))


class TestParagraphChunks(unittest.TestCase):
    def test_one_chunk_per_paragraph(self) -> None:
        paragraphs = [para(i, f"Paragraph {i}.") for i in range(5)]
        chunks = paragraph_chunks(paragraphs)
        self.assertEqual(len(chunks), 5)
        for chunk, p in zip(chunks, paragraphs, strict=True):
            self.assertEqual(chunk.text, p.text)
            self.assertEqual(chunk.spans[0].paragraph_id, p.paragraph_id)

    def test_span_covers_the_whole_paragraph(self) -> None:
        text = "A single paragraph of text."
        chunk = paragraph_chunks([para(3, text)])[0]
        span = chunk.spans[0]
        self.assertEqual(text[span.char_start : span.char_end], text)


if __name__ == "__main__":
    unittest.main()
