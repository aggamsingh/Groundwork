"""Citation matching tests — P-003.

Every false positive below was produced by the first implementation (bag-of-words
token overlap) against the real corpus, and every true positive is a real
reference string from it. A wrong edge is worse than a missing one: Phase 5 mines
this graph for reranker training pairs.
"""

from __future__ import annotations

import unittest

from survey.ingest.citations import title_in_reference


class TestTruePositives(unittest.TestCase):
    def test_matches_exact_quoted_title(self) -> None:
        self.assertTrue(
            title_in_reference(
                "Deep Learning Enabled Semantic Communication Systems",
                'H. Xie, Z. Qin, G. Y. Li, and B.-H. Juang, "Deep learning enabled '
                'semantic communication systems," IEEE Trans. Signal Process., 2021.',
            )
        )

    def test_matches_across_curly_quotes_and_accents(self) -> None:
        self.assertTrue(
            title_in_reference(
                "Efficient Estimation of Word Representations in Vector Space",
                "T. Mikolov, K. Chen, G. S. Corrado, and J. B. Dean, ‘‘Efficient "
                "estimation of word representations in vector space,’’ in Proc. ICLR.",
            )
        )

    def test_matches_title_hyphenated_across_a_line_break(self) -> None:
        self.assertTrue(
            title_in_reference(
                "Deep Learning Enabled Semantic Communication Systems",
                'H. Xie et al., "Deep Learning Enabled Semantic Commu- nication '
                'Systems," IEEE Trans. Signal Process., 2021.',
            )
        )

    def test_matches_colon_subtitle(self) -> None:
        self.assertTrue(
            title_in_reference(
                "Engineering Semantic Communication: A Survey",
                'D. Wheeler and B. Natarajan, "Engineering semantic communication: '
                'A survey," IEEE Access, vol. 11, 2023.',
            )
        )


class TestFalsePositives(unittest.TestCase):
    """Each of these was a wrong edge in the database before P-003 was fixed."""

    def test_shared_vocabulary_is_not_a_match(self) -> None:
        # Every content word of the corpus title appears in this reference to a
        # completely unrelated paper.
        self.assertFalse(
            title_in_reference(
                "Engineering Semantic Communication: A Survey",
                'M. R. Bloch, "Covert communication over noisy channels: A '
                'resolvability perspective," IEEE Trans. Inf. Theory, 2016.',
            )
        )

    def test_near_miss_title_is_not_a_match(self) -> None:
        # "Cognitive ... driven by knowledge graph" vs "Robust ... driven by
        # knowledge graph": near-identical token sets, different papers.
        self.assertFalse(
            title_in_reference(
                "Robust Semantic Communication Driven by Knowledge Graph",
                'F. Zhou, Y. Li, X. Zhang, Q. Wu, X. Lei, and R. Q. Hu, "Cognitive '
                'semantic communication systems driven by knowledge graph," 2022.',
            )
        )

    def test_prefix_of_a_longer_title_is_not_a_match(self) -> None:
        # The corpus title is a strict prefix of a different real paper's title.
        # This is why the phrase match checks for a boundary after the needle.
        self.assertFalse(
            title_in_reference(
                "Deep Learning Enabled Semantic Communication Systems",
                'H. Zhang, S. Shao, M. Tao, X. Bi, and K. B. Letaief, "Deep '
                "learning-enabled semantic communication systems with task-unaware "
                'transmitter and dynamic data," IEEE J. Sel. Areas Commun., 2023.',
            )
        )

    def test_qualified_title_is_not_a_match(self) -> None:
        self.assertFalse(
            title_in_reference(
                "Semantic Communications: Principles and Challenges",
                'Z. Yang, M. Chen, G. Li, Y. Yang, and Z. Zhang, "Secure semantic '
                'communications: Fundamentals and challenges," IEEE Netw., 2024.',
            )
        )

    def test_short_generic_title_is_refused(self) -> None:
        # Below MIN_TITLE_TOKENS a title cannot identify a paper by phrase alone.
        self.assertFalse(
            title_in_reference("Semantic Communication", "anything at all here")
        )


if __name__ == "__main__":
    unittest.main()
