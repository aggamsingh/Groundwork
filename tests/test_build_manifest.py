from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_manifest import build  # noqa: E402


class TestBuildManifest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.corpus = self.tmp / "corpus"
        self.corpus.mkdir()
        self.out = self.tmp / "manifest.csv"

    def test_hashes_each_pdf_and_uses_stem_as_id(self) -> None:
        (self.corpus / "2201.01389.pdf").write_bytes(b"%PDF-1.4 alpha")
        (self.corpus / "2106.09327.pdf").write_bytes(b"%PDF-1.4 beta")

        self.assertEqual(build(self.corpus, self.out), 0)
        with self.out.open(encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))

        self.assertEqual([r["external_id"] for r in rows], ["2106.09327", "2201.01389"])
        self.assertEqual(len({r["sha256"] for r in rows}), 2)
        self.assertTrue(all(len(r["sha256"]) == 64 for r in rows))

    def test_identical_content_is_reproducible(self) -> None:
        (self.corpus / "a.pdf").write_bytes(b"same")
        build(self.corpus, self.out)
        first = self.out.read_text(encoding="utf-8")
        build(self.corpus, self.out)
        self.assertEqual(first, self.out.read_text(encoding="utf-8"))

    def test_empty_corpus_reports_failure(self) -> None:
        self.assertEqual(build(self.corpus, self.out), 1)


if __name__ == "__main__":
    unittest.main()
