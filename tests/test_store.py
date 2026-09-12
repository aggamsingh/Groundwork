"""Storage tests. Integration: skipped when Postgres is not running.

Written around P-002 — a quarantined paper could never be retried, because the
idempotency check compared content only and a paper that failed *during* storage
already had its sha256 and parser recorded.
"""

from __future__ import annotations

import unittest

import psycopg

from survey.ingest import store
from survey.ingest.model import ParsedPaper, ParsedParagraph, ParsedSection

CORPUS = "test_corpus"


def _paper(external_id: str = "test-paper", text: str = "Hello world.") -> ParsedPaper:
    return ParsedPaper(
        external_id=external_id,
        parser="pymupdf",
        title="A Test Paper",
        year=2026,
        page_count=1,
        sections=[
            ParsedSection(
                heading="I. INTRODUCTION",
                ordinal=0,
                depth=0,
                kind="body",
                paragraphs=[ParsedParagraph(text=text, ordinal=0, page_from=1, page_to=1)],
            )
        ],
    )


def _connect() -> psycopg.Connection | None:
    try:
        return psycopg.connect(store.dsn(), connect_timeout=3)
    except psycopg.OperationalError:
        return None


class StoreTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        conn = _connect()
        if conn is None:
            raise unittest.SkipTest("Postgres not running - integration test skipped")
        cls.conn = conn

    @classmethod
    def tearDownClass(cls) -> None:
        cls.conn.close()

    def setUp(self) -> None:
        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM papers WHERE corpus_id = %s", (CORPUS,))
            cur.execute("DELETE FROM corpora WHERE id = %s", (CORPUS,))
        self.conn.commit()
        self.addCleanup(self._cleanup)

    def _cleanup(self) -> None:
        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM papers WHERE corpus_id = %s", (CORPUS,))
            cur.execute("DELETE FROM corpora WHERE id = %s", (CORPUS,))
        self.conn.commit()

    def _status(self, external_id: str = "test-paper") -> str:
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT ingest_status FROM papers WHERE corpus_id=%s AND external_id=%s",
                (CORPUS, external_id),
            )
            return cur.fetchone()[0]


class TestIdempotency(StoreTestCase):
    def test_insert_then_unchanged(self) -> None:
        first = store.store(self.conn, _paper(), sha256="abc", corpus_id=CORPUS)
        self.conn.commit()
        self.assertEqual(first.action, "inserted")

        second = store.store(self.conn, _paper(), sha256="abc", corpus_id=CORPUS)
        self.conn.commit()
        self.assertEqual(second.action, "unchanged")
        self.assertEqual(first.paper_id, second.paper_id)

    def test_changed_content_replaces_structure(self) -> None:
        store.store(self.conn, _paper(text="Original."), sha256="abc", corpus_id=CORPUS)
        self.conn.commit()
        result = store.store(
            self.conn, _paper(text="Rewritten."), sha256="def", corpus_id=CORPUS
        )
        self.conn.commit()
        self.assertEqual(result.action, "replaced")

        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT text FROM paragraphs WHERE paper_id = %s", (result.paper_id,)
            )
            texts = [r[0] for r in cur.fetchall()]
        # Replaced wholesale, not merged: stale paragraphs would leave citations
        # pointing at text that has moved.
        self.assertEqual(texts, ["Rewritten."])

    def test_force_reparses_unchanged_content(self) -> None:
        store.store(self.conn, _paper(), sha256="abc", corpus_id=CORPUS)
        self.conn.commit()
        result = store.store(
            self.conn, _paper(), sha256="abc", corpus_id=CORPUS, force=True
        )
        self.conn.commit()
        self.assertEqual(result.action, "replaced")


class TestQuarantineRetry(StoreTestCase):
    """P-002: a quarantined paper must always be retried."""

    def test_quarantined_paper_is_retried_even_with_matching_sha(self) -> None:
        # Reproduce the exact shape of the bug: the paper was stored successfully
        # first (so sha256 and parser are recorded), then quarantined afterwards.
        store.store(self.conn, _paper(), sha256="abc", corpus_id=CORPUS)
        self.conn.commit()
        store.quarantine(self.conn, "test-paper", "boom", corpus_id=CORPUS)
        self.conn.commit()
        self.assertEqual(self._status(), "quarantined")

        # Same content, same parser. The old check said "unchanged" and the paper
        # stayed quarantined forever, even once the underlying bug was fixed.
        result = store.store(self.conn, _paper(), sha256="abc", corpus_id=CORPUS)
        self.conn.commit()

        self.assertNotEqual(result.action, "unchanged")
        self.assertEqual(self._status(), "ok")

    def test_quarantine_clears_stale_structure(self) -> None:
        result = store.store(self.conn, _paper(), sha256="abc", corpus_id=CORPUS)
        self.conn.commit()
        store.quarantine(self.conn, "test-paper", "boom", corpus_id=CORPUS)
        self.conn.commit()

        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM paragraphs WHERE paper_id = %s", (result.paper_id,)
            )
            # A quarantined paper must not leave half-written text queryable.
            self.assertEqual(cur.fetchone()[0], 0)

    def test_failure_reason_is_recorded(self) -> None:
        store.quarantine(self.conn, "test-paper", "NUL bytes", corpus_id=CORPUS)
        self.conn.commit()
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT failure_reason FROM papers WHERE corpus_id=%s", (CORPUS,)
            )
            self.assertIn("NUL", cur.fetchone()[0])


if __name__ == "__main__":
    unittest.main()
