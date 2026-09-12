"""Table filter tests — D-013.

The shapes below are taken from real detector output on this corpus. The filters
are tuned for precision: a missed table is visible as an absence and its text is
still in the paragraphs, while a false table puts fabricated numbers into the
claim store looking exactly like real ones.
"""

from __future__ import annotations

import unittest

from survey.ingest.tables import _looks_tabular


class TestLooksTabular(unittest.TestCase):
    def test_accepts_a_real_results_table(self) -> None:
        # BVCS Table I, the case D-010 was written for.
        rows = [
            ["A pair of Text", "BLEU1", "BLEU2", "BLEU3", "BLEU4"],
            ["The system fails", "0.7143", "0.4880", "0.0000", "0.0000"],
            ["The door is open", "0.8750", "0.7906", "0.7491", "0.7071"],
            ["He is a bright boy", "0.7143", "0.4880", "0.0000", "0.0000"],
        ]
        self.assertTrue(_looks_tabular(rows))

    def test_rejects_diagram_debris(self) -> None:
        # A figure legend the detector reported as a 2x9 "table": fragments of a
        # diagram label split across mostly-empty columns.
        rows = [
            ["", "UT", "", "", "", "", "", "", ""],
            ["T\nT", "ransfo\nurbo\nRS", "rmer", "", "", "", "", "", ""],
        ]
        self.assertFalse(_looks_tabular(rows))

    def test_rejects_mostly_empty_grid(self) -> None:
        rows = [["Header", "", ""], ["", "", ""], ["value", "", ""]]
        self.assertFalse(_looks_tabular(rows))

    def test_rejects_single_column(self) -> None:
        self.assertFalse(_looks_tabular([["one"], ["two"], ["three"]]))

    def test_rejects_single_row(self) -> None:
        self.assertFalse(_looks_tabular([["Method", "BLEU", "SNR"]]))

    def test_accepts_dense_two_row_table(self) -> None:
        # Two rows is allowed when the cells are actually populated -- this is
        # the header-plus-one-row shape that real captioned tables take.
        rows = [
            ["Methods", "JPEG+LDPC", "Proposed MAE", "Ratio"],
            ["Number of symbols", "20432", "196", "0.95%"],
        ]
        self.assertTrue(_looks_tabular(rows))


if __name__ == "__main__":
    unittest.main()
