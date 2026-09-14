"""Question-set loading and the stub guard.

The stub guard is the important one. CLAUDE.md permits `*_STUB` scaffolding only
with "a failing check that prevents any eval run from using it", and this is that
check.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from survey.evalharness.questions import (
    QuestionSetError,
    StubQuestionSetError,
    check_coverage,
    is_stub,
    load_questions,
    summarise,
)

GOOD = {
    "id": "q1",
    "question": "What channel model does DeepSC evaluate under?",
    "type": "single_paper_lookup",
    "answer": "AWGN and Rayleigh",
    "spans": [{"paper_external_id": "deep-learning-enabled", "relevance": 1.0}],
}


class QuestionFileTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def write(self, rows: list[dict], name: str = "v1.jsonl") -> Path:
        path = self.dir / name
        path.write_text(
            "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8"
        )
        return path


class TestStubGuard(QuestionFileTestCase):
    def test_stub_is_refused_by_default(self) -> None:
        path = self.write([GOOD], name="smoke_STUB.jsonl")
        with self.assertRaises(StubQuestionSetError) as ctx:
            load_questions(path)
        self.assertIn("CHECKPOINT 4", str(ctx.exception))

    def test_stub_loads_only_when_explicitly_allowed(self) -> None:
        path = self.write([GOOD], name="smoke_STUB.jsonl")
        self.assertEqual(len(load_questions(path, allow_stub=True)), 1)

    def test_stub_detection_is_case_insensitive(self) -> None:
        self.assertTrue(is_stub(Path("a_stub.jsonl")))
        self.assertTrue(is_stub(Path("a_STUB.jsonl")))
        self.assertFalse(is_stub(Path("v1.jsonl")))


class TestValidation(QuestionFileTestCase):
    def test_loads_a_valid_question(self) -> None:
        questions = load_questions(self.write([GOOD]))
        self.assertEqual(questions[0].id, "q1")
        self.assertEqual(questions[0].relevant_papers, {"deep-learning-enabled"})

    def test_missing_file_names_the_checkpoint(self) -> None:
        with self.assertRaises(QuestionSetError) as ctx:
            load_questions(self.dir / "absent.jsonl")
        self.assertIn("CHECKPOINT 4", str(ctx.exception))

    def test_unknown_type_is_rejected(self) -> None:
        with self.assertRaises(QuestionSetError) as ctx:
            load_questions(self.write([{**GOOD, "type": "trivia"}]))
        self.assertIn("unknown type", str(ctx.exception))

    def test_answerable_question_without_spans_is_rejected(self) -> None:
        # Would score recall 0.0 by definition, dragging every number down while
        # looking like a retrieval failure rather than a labelling gap.
        with self.assertRaises(QuestionSetError) as ctx:
            load_questions(self.write([{**GOOD, "spans": []}]))
        self.assertIn("supporting spans", str(ctx.exception))

    def test_unanswerable_question_with_spans_is_rejected(self) -> None:
        bad = {**GOOD, "type": "unanswerable"}
        with self.assertRaises(QuestionSetError) as ctx:
            load_questions(self.write([bad]))
        self.assertIn("unanswerable", str(ctx.exception))

    def test_unanswerable_without_spans_is_fine(self) -> None:
        row = {"id": "u1", "question": "Anything?", "type": "unanswerable"}
        self.assertEqual(len(load_questions(self.write([row]))), 1)

    def test_duplicate_ids_are_rejected(self) -> None:
        with self.assertRaises(QuestionSetError) as ctx:
            load_questions(self.write([GOOD, GOOD]))
        self.assertIn("duplicate id", str(ctx.exception))

    def test_bad_json_names_the_line(self) -> None:
        path = self.dir / "v1.jsonl"
        path.write_text(json.dumps(GOOD) + "\n{not json\n", encoding="utf-8")
        with self.assertRaises(QuestionSetError) as ctx:
            load_questions(path)
        self.assertIn(":2:", str(ctx.exception))

    def test_comments_and_blank_lines_are_skipped(self) -> None:
        path = self.dir / "v1.jsonl"
        path.write_text(
            "// a comment\n\n" + json.dumps(GOOD) + "\n", encoding="utf-8"
        )
        self.assertEqual(len(load_questions(path)), 1)

    def test_empty_file_is_rejected(self) -> None:
        path = self.dir / "v1.jsonl"
        path.write_text("// only a comment\n", encoding="utf-8")
        with self.assertRaises(QuestionSetError):
            load_questions(path)


class TestCoverage(QuestionFileTestCase):
    def test_warns_about_missing_types(self) -> None:
        warnings = check_coverage(load_questions(self.write([GOOD])))
        joined = " ".join(warnings)
        self.assertIn("no contradiction questions", joined)
        self.assertIn("no unanswerable questions", joined)

    def test_warns_when_below_the_required_count(self) -> None:
        warnings = check_coverage(load_questions(self.write([GOOD])))
        self.assertTrue(any("requires 60" in w for w in warnings))

    def test_summarise_counts_every_type(self) -> None:
        counts = summarise(load_questions(self.write([GOOD])))
        self.assertEqual(counts["single_paper_lookup"], 1)
        self.assertEqual(counts["contradiction"], 0)


class TestShippedStub(unittest.TestCase):
    def test_repo_stub_is_refused(self) -> None:
        path = Path("eval/questions/smoke_STUB.jsonl")
        if not path.exists():
            self.skipTest("stub not present")
        with self.assertRaises(StubQuestionSetError):
            load_questions(path)


if __name__ == "__main__":
    unittest.main()
