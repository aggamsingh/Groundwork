"""Lexical retrieval tests.

Integration tests skip when Postgres is absent. RRF and query rewriting are pure
and always run.

These check that retrieval is *correct and safe* — the holdout never appears,
fusion behaves as defined, degenerate queries do not crash. They check nothing
about quality, which needs the hand-labelled eval set (C-006).
"""

from __future__ import annotations

import unittest

import psycopg

from survey.ingest import store
from survey.retrieval.lexical import (
    Retrieved,
    reciprocal_rank_fusion,
    search,
    to_or_query,
)


def _hit(chunk_id: int, rank: int, paper_id: int = 1) -> Retrieved:
    return Retrieved(
        chunk_id=chunk_id, paper_id=paper_id, score=1.0 / rank, text="t", rank=rank
    )


class TestOrQuery(unittest.TestCase):
    def test_joins_terms_with_or(self) -> None:
        self.assertEqual(to_or_query("semantic noise"), "semantic | noise")

    def test_strips_punctuation_that_would_break_to_tsquery(self) -> None:
        # to_tsquery raises on stray parentheses and colons; research questions
        # are full of both.
        self.assertEqual(
            to_or_query("What is BLEU-4 (1-gram) at 6 dB?"),
            "What | is | BLEU | 4 | 1 | gram | at | 6 | dB",
        )

    def test_empty_query(self) -> None:
        self.assertEqual(to_or_query("???"), "")


class TestReciprocalRankFusion(unittest.TestCase):
    def test_self_fusion_preserves_order(self) -> None:
        ranking = [_hit(10, 1), _hit(20, 2), _hit(30, 3)]
        fused = reciprocal_rank_fusion([ranking, ranking], top_k=3)
        self.assertEqual([f.chunk_id for f in fused], [10, 20, 30])

    def test_agreement_between_lists_outranks_a_single_top_hit(self) -> None:
        # Chunk 2 is second in both lists; chunk 1 is first in one and absent
        # from the other. RRF should prefer the consistently-good result:
        #   chunk 1 = 1/61            = 0.01639
        #   chunk 2 = 1/62 + 1/62     = 0.03226
        a = [_hit(1, 1), _hit(2, 2)]
        b = [_hit(3, 1), _hit(2, 2)]
        fused = reciprocal_rank_fusion([a, b], top_k=3)
        self.assertEqual(fused[0].chunk_id, 2)

    def test_scores_match_the_formula(self) -> None:
        a = [_hit(1, 1)]
        b = [_hit(1, 3)]
        fused = reciprocal_rank_fusion([a, b], k=60, top_k=1)
        self.assertAlmostEqual(fused[0].score, 1 / 61 + 1 / 63)

    def test_ranks_are_renumbered_from_one(self) -> None:
        a = [_hit(5, 1), _hit(6, 2), _hit(7, 3)]
        fused = reciprocal_rank_fusion([a], top_k=3)
        self.assertEqual([f.rank for f in fused], [1, 2, 3])

    def test_empty_input(self) -> None:
        self.assertEqual(reciprocal_rank_fusion([]), [])

    def test_k_changes_the_discount(self) -> None:
        a = [_hit(1, 1)]
        low = reciprocal_rank_fusion([a], k=1, top_k=1)[0].score
        high = reciprocal_rank_fusion([a], k=1000, top_k=1)[0].score
        self.assertGreater(low, high)


class TestSearchIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            # autocommit: these are read-only queries, and without it one failing
            # statement aborts the transaction and every later test in the class
            # fails with "current transaction is aborted" instead of its own
            # error — which hides the one failure that actually matters.
            cls.conn = psycopg.connect(
                store.dsn(), connect_timeout=3, autocommit=True
            )
        except psycopg.OperationalError:
            raise unittest.SkipTest("Postgres not running") from None
        with cls.conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM chunks")
            if cur.fetchone()[0] == 0:
                cls.conn.close()
                raise unittest.SkipTest("no chunks built")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.conn.close()

    def test_returns_ranked_results(self) -> None:
        results = search(self.conn, "semantic communication", top_k=5)
        self.assertGreater(len(results), 0)
        self.assertEqual([r.rank for r in results], list(range(1, len(results) + 1)))
        # ts_rank_cd is monotonically decreasing down the list by construction.
        scores = [r.score for r in results]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_never_returns_a_holdout_paper(self) -> None:
        # The property the whole split exists to protect. Checked against the
        # database rather than the view definition, so a broken view fails here.
        results = search(self.conn, "semantic", top_k=50)
        if not results:
            self.skipTest("no results to check")
        ids = sorted({r.paper_id for r in results})
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM corpus_split "
                "WHERE split = 'holdout' AND paper_id = ANY(%s)",
                (ids,),
            )
            self.assertEqual(cur.fetchone()[0], 0)

    def test_any_logic_recalls_where_all_logic_finds_nothing(self) -> None:
        # The behaviour that motivated exposing both: ANDing every term returns
        # nothing when no single chunk contains them all.
        query = "channel-aware training AWGN knowledge graph quantisation"
        strict = search(self.conn, query, top_k=5, term_logic="all")
        loose = search(self.conn, query, top_k=5, term_logic="any")
        self.assertGreaterEqual(len(loose), len(strict))

    def test_top_k_is_respected(self) -> None:
        self.assertLessEqual(len(search(self.conn, "semantic", top_k=3)), 3)

    def test_nonsense_query_returns_empty_not_error(self) -> None:
        self.assertEqual(search(self.conn, "zzzqqq-not-a-word", top_k=5), [])

    def test_punctuation_heavy_query_does_not_raise(self) -> None:
        # to_tsquery would raise on this; both paths must survive it.
        query = "What BLEU-4 (1-gram) at 6 dB: proposed?"
        search(self.conn, query, top_k=3, term_logic="all")
        search(self.conn, query, top_k=3, term_logic="any")

    def test_invalid_term_logic_raises(self) -> None:
        with self.assertRaises(ValueError):
            search(self.conn, "x", term_logic="sometimes")


if __name__ == "__main__":
    unittest.main()
