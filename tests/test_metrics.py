"""Metric tests — every expected value computed by hand, shown in the test.

These are the instruments the whole project is judged with. A formula that
silently changes would move every number reported after it, including numbers
already written into phase reports, and nothing else would catch it.
"""

from __future__ import annotations

import math
import unittest

from survey.evalharness.metrics import (
    abstention_recall,
    aggregate,
    citation_faithfulness,
    dcg,
    false_refusal_rate,
    hit_at_k,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)


class TestRecall(unittest.TestCase):
    def test_partial_recall(self) -> None:
        # 2 of 4 relevant items are in the top 5.
        retrieved = ["a", "x", "b", "y", "z"]
        relevant = ["a", "b", "c", "d"]
        self.assertEqual(recall_at_k(retrieved, relevant, 5), 0.5)

    def test_k_truncates(self) -> None:
        retrieved = ["x", "y", "a"]
        self.assertEqual(recall_at_k(retrieved, ["a"], 2), 0.0)
        self.assertEqual(recall_at_k(retrieved, ["a"], 3), 1.0)

    def test_no_relevant_items_scores_zero_not_one(self) -> None:
        # A question labelled answerable with no supporting span is a broken
        # label. The "vacuously perfect" convention would score it 1.0 and hide
        # the breakage behind a good number.
        self.assertEqual(recall_at_k(["a", "b"], [], 5), 0.0)

    def test_duplicates_in_retrieved_do_not_inflate(self) -> None:
        self.assertEqual(recall_at_k(["a", "a", "a"], ["a", "b"], 3), 0.5)


class TestPrecisionAndHit(unittest.TestCase):
    def test_precision(self) -> None:
        # 2 relevant in a top-4 list.
        self.assertEqual(precision_at_k(["a", "x", "b", "y"], ["a", "b"], 4), 0.5)

    def test_precision_short_list_divides_by_list_length(self) -> None:
        # Only 2 results exist though k=5; dividing by k would under-report.
        self.assertEqual(precision_at_k(["a", "b"], ["a", "b"], 5), 1.0)

    def test_hit_is_binary(self) -> None:
        self.assertEqual(hit_at_k(["x", "a"], ["a", "b"], 2), 1.0)
        self.assertEqual(hit_at_k(["x", "y"], ["a", "b"], 2), 0.0)

    def test_hit_and_recall_differ(self) -> None:
        # One of two spans found: answerable for a lookup, incomplete for a
        # comparison. The two metrics must not collapse into each other.
        retrieved, relevant = ["a", "x"], ["a", "b"]
        self.assertEqual(hit_at_k(retrieved, relevant, 2), 1.0)
        self.assertEqual(recall_at_k(retrieved, relevant, 2), 0.5)


class TestReciprocalRank(unittest.TestCase):
    def test_first_relevant_at_rank_three(self) -> None:
        self.assertAlmostEqual(reciprocal_rank(["x", "y", "a"], ["a"]), 1 / 3)

    def test_none_retrieved(self) -> None:
        self.assertEqual(reciprocal_rank(["x", "y"], ["a"]), 0.0)

    def test_takes_the_first_not_the_best(self) -> None:
        self.assertEqual(reciprocal_rank(["b", "a"], ["a", "b"]), 1.0)


class TestNdcg(unittest.TestCase):
    def test_dcg_matches_hand_calculation(self) -> None:
        # gains 3, 2, 1 at ranks 1, 2, 3:
        #   3/log2(2) + 2/log2(3) + 1/log2(4) = 3 + 1.26186 + 0.5
        expected = 3 / 1.0 + 2 / math.log2(3) + 1 / 2.0
        self.assertAlmostEqual(dcg([3, 2, 1]), expected)

    def test_perfect_ranking_is_one(self) -> None:
        relevance = {"a": 3.0, "b": 2.0, "c": 1.0}
        self.assertAlmostEqual(ndcg_at_k(["a", "b", "c"], relevance, 3), 1.0)

    def test_reversed_ranking_scores_below_one(self) -> None:
        relevance = {"a": 3.0, "b": 2.0, "c": 1.0}
        value = ndcg_at_k(["c", "b", "a"], relevance, 3)
        self.assertLess(value, 1.0)
        # DCG = 1 + 2/log2(3) + 3/2 ; IDCG = 3 + 2/log2(3) + 1/2
        expected = (1 + 2 / math.log2(3) + 1.5) / (3 + 2 / math.log2(3) + 0.5)
        self.assertAlmostEqual(value, expected)

    def test_ideal_uses_all_relevant_items_not_only_retrieved(self) -> None:
        # One relevant item retrieved and ranked first, nine missed. Computing
        # the ideal over retrieved items only would score this a perfect 1.0.
        relevance = {f"r{i}": 1.0 for i in range(10)}
        value = ndcg_at_k(["r0"], relevance, 10)
        self.assertLess(value, 0.5)

    def test_irrelevant_results_contribute_nothing(self) -> None:
        relevance = {"a": 1.0}
        self.assertAlmostEqual(
            ndcg_at_k(["a", "junk", "junk2"], relevance, 3),
            ndcg_at_k(["a"], relevance, 3),
        )


class TestAnswerMetrics(unittest.TestCase):
    def test_faithfulness(self) -> None:
        self.assertAlmostEqual(
            citation_faithfulness([True, True, False, True]), 0.75
        )

    def test_empty_answer_is_not_perfectly_faithful(self) -> None:
        # Emitting nothing is a refusal, and refusals are scored by the
        # abstention metrics, not by getting a free 1.0 here.
        self.assertEqual(citation_faithfulness([]), 0.0)

    def test_abstention_recall(self) -> None:
        # 3 unanswerable, 2 correctly refused.
        abstained = [True, False, True, False]
        unanswerable = [True, True, True, False]
        self.assertAlmostEqual(abstention_recall(abstained, unanswerable), 2 / 3)

    def test_false_refusal_rate(self) -> None:
        # 2 answerable, 1 wrongly refused.
        abstained = [True, False, True]
        unanswerable = [False, False, True]
        self.assertAlmostEqual(false_refusal_rate(abstained, unanswerable), 0.5)

    def test_refusing_everything_is_caught_by_false_refusal_rate(self) -> None:
        # The failure mode the pair exists to expose: perfect abstention recall,
        # and a system that answers nothing.
        abstained = [True, True, True, True]
        unanswerable = [True, False, False, False]
        self.assertEqual(abstention_recall(abstained, unanswerable), 1.0)
        self.assertEqual(false_refusal_rate(abstained, unanswerable), 1.0)

    def test_misaligned_inputs_raise(self) -> None:
        with self.assertRaises(ValueError):
            abstention_recall([True], [True, False])


class TestAggregate(unittest.TestCase):
    def test_mean(self) -> None:
        self.assertAlmostEqual(aggregate([1.0, 0.0, 0.5]), 0.5)

    def test_empty(self) -> None:
        self.assertEqual(aggregate([]), 0.0)


if __name__ == "__main__":
    unittest.main()
