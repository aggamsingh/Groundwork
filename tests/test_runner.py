"""Eval runner tests, using a fake retriever.

A fake rather than the database, because what is being tested is the scoring
logic: whether a known retrieval produces the expected numbers. Using real
retrieval would test two things at once and tell you neither.
"""

from __future__ import annotations

import unittest
from unittest import mock

from survey.config.config import RunConfig
from survey.evalharness.questions import Question, SupportingSpan
from survey.evalharness.runner import run_eval
from survey.retrieval.lexical import Retrieved


def question(qid: str, qtype: str, papers: list[str], relevance: float = 1.0):
    return Question(
        id=qid,
        question=f"question {qid}",
        type=qtype,
        spans=[SupportingSpan(paper_external_id=p, relevance=relevance) for p in papers],
    )


class FakeConn:
    """Stands in for psycopg, mapping internal ids to external ids."""

    def __init__(self, lookup: dict[int, str]):
        self.lookup = lookup

    def cursor(self):
        outer = self

        class Cur:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def execute(self, sql, params=None):
                ids = params[0] if params else []
                self.rows = [(i, outer.lookup[i]) for i in ids if i in outer.lookup]

            def fetchall(self):
                return self.rows

        return Cur()


def retriever_returning(paper_ids: list[int]):
    def retrieve(_question: str, _top_k: int) -> list[Retrieved]:
        return [
            Retrieved(chunk_id=100 + i, paper_id=pid, score=1.0 / (i + 1), text="t",
                      rank=i + 1)
            for i, pid in enumerate(paper_ids)
        ]

    return retrieve


class TestRunEval(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = FakeConn({1: "paper-a", 2: "paper-b", 3: "paper-c"})
        self.config = RunConfig()
        self.config.retrieval.top_k = 3

    def test_perfect_retrieval_scores_one(self) -> None:
        report = run_eval(
            self.conn,
            [question("q1", "single_paper_lookup", ["paper-a"])],
            self.config,
            retriever=retriever_returning([1]),
        )
        self.assertEqual(report.overall["recall_at_k"], 1.0)
        self.assertEqual(report.overall["hit_at_k"], 1.0)
        self.assertEqual(report.overall["mrr"], 1.0)

    def test_missed_retrieval_scores_zero(self) -> None:
        report = run_eval(
            self.conn,
            [question("q1", "single_paper_lookup", ["paper-a"])],
            self.config,
            retriever=retriever_returning([2, 3]),
        )
        self.assertEqual(report.overall["recall_at_k"], 0.0)
        self.assertEqual(report.overall["mrr"], 0.0)

    def test_rank_two_gives_reciprocal_rank_one_half(self) -> None:
        report = run_eval(
            self.conn,
            [question("q1", "single_paper_lookup", ["paper-a"])],
            self.config,
            retriever=retriever_returning([2, 1]),
        )
        self.assertAlmostEqual(report.overall["mrr"], 0.5)

    def test_repeated_chunks_from_one_paper_count_once(self) -> None:
        # Several chunks from the same paper are ONE retrieved paper. Counting
        # them separately would inflate precision.
        report = run_eval(
            self.conn,
            [question("q1", "single_paper_lookup", ["paper-a"])],
            self.config,
            retriever=retriever_returning([1, 1, 1]),
        )
        self.assertEqual(report.per_question[0].retrieved_papers, ["paper-a"])
        self.assertAlmostEqual(report.overall["precision_at_k"], 1.0)

    def test_unanswerable_questions_are_excluded_from_retrieval_metrics(self) -> None:
        # Scoring them would report recall 0.0 for correct behaviour.
        questions = [
            question("q1", "single_paper_lookup", ["paper-a"]),
            Question(id="q2", question="?", type="unanswerable"),
        ]
        report = run_eval(
            self.conn, questions, self.config, retriever=retriever_returning([1])
        )
        self.assertEqual(len(report.per_question), 1)
        self.assertEqual(report.question_count, 2)
        self.assertEqual(report.overall["recall_at_k"], 1.0)
        self.assertTrue(any("unanswerable" in w for w in report.warnings))

    def test_per_type_breakdown_is_reported(self) -> None:
        # An average over five question types hides which type is failing.
        questions = [
            question("q1", "single_paper_lookup", ["paper-a"]),
            question("q2", "cross_paper_comparison", ["paper-b", "paper-c"]),
        ]
        report = run_eval(
            self.conn, questions, self.config, retriever=retriever_returning([1])
        )
        self.assertEqual(report.by_type["single_paper_lookup"]["recall_at_k"], 1.0)
        self.assertEqual(report.by_type["cross_paper_comparison"]["recall_at_k"], 0.0)

    def test_partial_recall_on_a_comparison_question(self) -> None:
        report = run_eval(
            self.conn,
            [question("q1", "cross_paper_comparison", ["paper-a", "paper-b"])],
            self.config,
            retriever=retriever_returning([1, 3]),
        )
        self.assertAlmostEqual(report.overall["recall_at_k"], 0.5)
        self.assertEqual(report.overall["hit_at_k"], 1.0)

    def test_empty_question_set_produces_no_metrics(self) -> None:
        report = run_eval(self.conn, [], self.config, retriever=retriever_returning([]))
        self.assertEqual(report.overall, {})

    def test_fingerprint_is_recorded_on_the_report(self) -> None:
        report = run_eval(
            self.conn,
            [question("q1", "single_paper_lookup", ["paper-a"])],
            self.config,
            retriever=retriever_returning([1]),
        )
        self.assertEqual(report.config_fingerprint, self.config.fingerprint())

    def test_retriever_is_asked_for_more_chunks_than_top_k(self) -> None:
        # Several chunks routinely come from one paper, so asking for exactly
        # top_k chunks would measure fewer than top_k papers.
        spy = mock.Mock(side_effect=retriever_returning([1]))
        run_eval(
            self.conn,
            [question("q1", "single_paper_lookup", ["paper-a"])],
            self.config,
            retriever=spy,
        )
        _, requested = spy.call_args[0]
        self.assertGreater(requested, self.config.retrieval.top_k)


if __name__ == "__main__":
    unittest.main()
