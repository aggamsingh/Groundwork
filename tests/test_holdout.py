"""The holdout guard is the mechanism protecting the project's headline number,
so its failure modes are tested more carefully than its success path."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from survey.evalharness.holdout import (
    HoldoutError,
    HoldoutMissingError,
    assert_no_holdout,
    load_holdout_ids,
)


class TestLoadHoldoutIds(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def write(self, name: str, content: str) -> Path:
        path = self.tmp / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_parses_ids_ignoring_blanks_and_comments(self) -> None:
        path = self.write(
            "holdout_papers.txt",
            "# frozen 2026-09-09\n2201.01389\n\n  2106.09327  \n"
            "10.1109/TWC.2021.3078618  # trailing comment\n",
        )
        self.assertEqual(
            load_holdout_ids(path),
            frozenset({"2201.01389", "2106.09327", "10.1109/TWC.2021.3078618"}),
        )

    def test_missing_file_is_a_checkpoint_not_a_crash(self) -> None:
        with self.assertRaises(HoldoutMissingError) as ctx:
            load_holdout_ids(self.tmp / "nope.txt")
        self.assertIn("CHECKPOINT 1", str(ctx.exception))

    def test_empty_holdout_is_rejected(self) -> None:
        # An empty set would make assert_no_holdout vacuously pass forever.
        path = self.write("holdout_papers.txt", "# nothing yet\n\n")
        with self.assertRaises(HoldoutError):
            load_holdout_ids(path)

    def test_stub_file_is_refused(self) -> None:
        path = self.write("holdout_papers_STUB.txt", "2201.01389\n")
        with self.assertRaises(HoldoutError) as ctx:
            load_holdout_ids(path)
        self.assertIn("stub", str(ctx.exception).lower())


class TestAssertNoHoldout(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "holdout_papers.txt"
        self.path.write_text("held_a\nheld_b\n", encoding="utf-8")

    def test_clean_result_set_passes(self) -> None:
        assert_no_holdout(["dev_1", "dev_2"], phase=3, path=self.path)

    def test_leak_raises_and_names_the_papers(self) -> None:
        with self.assertRaises(HoldoutError) as ctx:
            assert_no_holdout(["dev_1", "held_b"], phase=3, path=self.path)
        message = str(ctx.exception)
        self.assertIn("held_b", message)
        self.assertNotIn("held_a", message)  # only what actually leaked
        self.assertIn("contaminated", message)

    def test_ids_are_compared_as_strings(self) -> None:
        path = self.path.with_name("numeric.txt")
        path.write_text("1234\n", encoding="utf-8")
        with self.assertRaises(HoldoutError):
            assert_no_holdout([1234], phase=2, path=path)

    def test_phase_6_unlocks_the_holdout(self) -> None:
        assert_no_holdout(["held_a"], phase=6, path=self.path)

    def test_missing_holdout_blocks_any_earlier_phase(self) -> None:
        with self.assertRaises(HoldoutMissingError):
            assert_no_holdout(["dev_1"], phase=1, path=self.path.with_name("absent.txt"))


if __name__ == "__main__":
    unittest.main()
