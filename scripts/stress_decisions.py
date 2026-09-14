"""Adversarially test the project's standing decisions against real data.

Unit tests check that code does what it was written to do. This checks whether
the *decisions* hold on the actual corpus — which is different, and is where
P-002, P-003 and D-017 were all found.

Every check names the decision it attacks and states what would falsify it. A
check that cannot fail is not included.

Usage:
    .\\.venv\\Scripts\\python.exe scripts/stress_decisions.py
"""

from __future__ import annotations

import csv
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

import psycopg

from survey.evalharness.holdout import load_holdout_ids
from survey.ingest import store
from survey.retrieval.lexical import search

Finding = tuple[str, bool, str]  # (decision, passed, detail)


def check_span_integrity(conn: psycopg.Connection) -> list[Finding]:
    """D-003: a span must slice its source paragraph back out.

    Falsified if any stored span's offsets do not lie inside its paragraph, or
    if the text they select is not present in the chunk that cites them. This is
    the property every citation in the finished system rests on.
    """
    out: list[Finding] = []
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM chunk_spans s JOIN paragraphs g "
            "ON g.id = s.paragraph_id "
            "WHERE s.char_start < 0 OR s.char_end > length(g.text)"
        )
        bad_range = cur.fetchone()[0]
        out.append(
            (
                "D-003",
                bad_range == 0,
                f"spans with offsets outside their paragraph: {bad_range}",
            )
        )

        # Does the span text actually appear in the chunk that cites it?
        cur.execute(
            "SELECT c.text, g.text, s.char_start, s.char_end "
            "FROM chunk_spans s "
            "JOIN chunks c ON c.id = s.chunk_id "
            "JOIN paragraphs g ON g.id = s.paragraph_id "
            "ORDER BY random() LIMIT 400"
        )
        checked = mismatched = 0
        examples: list[str] = []
        for chunk_text, para_text, start, end in cur.fetchall():
            checked += 1
            sliced = para_text[start:end].strip()
            if not sliced:
                continue
            # Chunks join paragraphs with a space and de-hyphenate, so compare on
            # collapsed whitespace rather than requiring byte equality.
            if " ".join(sliced.split()) not in " ".join(chunk_text.split()):
                mismatched += 1
                if len(examples) < 3:
                    examples.append(sliced[:60])
        detail = f"sampled {checked} spans, {mismatched} did not appear in their chunk"
        if examples:
            detail += f" (e.g. {examples[0]!r})"
        out.append(("D-003", mismatched == 0, detail))
    return out


def check_holdout_containment(conn: psycopg.Connection) -> list[Finding]:
    """D-004: no holdout paper may be reachable through a dev view.

    Falsified if either view exposes a holdout paper, if the split does not
    cover every paper, or if any source file queries `chunks`/`papers` directly
    where it should use the view.
    """
    out: list[Finding] = []
    with conn.cursor() as cur:
        for view, join in (
            ("v_dev_papers", "s.paper_id = v.id"),
            ("v_dev_chunks", "s.paper_id = v.paper_id"),
        ):
            cur.execute(
                f"SELECT count(*) FROM {view} v JOIN corpus_split s ON {join} "
                "WHERE s.split = 'holdout'"
            )
            leaked = cur.fetchone()[0]
            out.append((
                "D-004", leaked == 0, f"{view} exposes {leaked} holdout rows"
            ))

        cur.execute(
            "SELECT count(*) FROM papers p LEFT JOIN corpus_split s "
            "ON s.paper_id = p.id WHERE s.paper_id IS NULL"
        )
        unassigned = cur.fetchone()[0]
        out.append((
            "D-004", unassigned == 0,
            f"papers with no split assignment: {unassigned}",
        ))

        # The split in the database must match the frozen file, or the guard is
        # protecting a different set of papers than the user chose.
        holdout_ids = load_holdout_ids()
        cur.execute(
            "SELECT p.external_id FROM papers p JOIN corpus_split s "
            "ON s.paper_id = p.id WHERE s.split = 'holdout'"
        )
        db_holdout = {r[0] for r in cur.fetchall()}
        out.append((
            "D-004", db_holdout == set(holdout_ids),
            f"db holdout ({len(db_holdout)}) vs frozen file ({len(holdout_ids)}): "
            f"{'identical' if db_holdout == set(holdout_ids) else 'DIFFERENT'}",
        ))

    # Static check: retrieval code must not read the unguarded tables.
    offenders = []
    for path in Path("src/survey/retrieval").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        # Allow the explicit include_holdout branch, which is named and audited.
        stripped = text.replace('"chunks" if include_holdout else "v_dev_chunks"', "")
        if re.search(r"FROM\s+chunks\b", stripped, re.I):
            offenders.append(path.name)
    out.append((
        "D-004", not offenders,
        f"retrieval modules selecting FROM chunks directly: {offenders or 'none'}",
    ))
    return out


def check_duplicate_papers(conn: psycopg.Connection) -> list[Finding]:
    """D-006/D-007: the corpus contains no duplicate papers.

    Falsified by two papers sharing a normalised title, a DOI, or an arXiv id.
    Titles now come from the parser, so this tests the dedupe decision against
    better evidence than the filenames it was originally made on.
    """
    out: list[Finding] = []
    with conn.cursor() as cur:
        for column in ("doi", "arxiv_id"):
            cur.execute(
                f"SELECT {column}, count(*) c FROM papers "
                f"WHERE {column} IS NOT NULL GROUP BY 1 HAVING count(*) > 1"
            )
            dupes = cur.fetchall()
            out.append((
                "D-007", not dupes,
                f"papers sharing a {column}: {len(dupes)}"
                + (f" {dupes[:2]}" if dupes else ""),
            ))

        cur.execute("SELECT external_id, title FROM papers WHERE title IS NOT NULL")
        rows = cur.fetchall()

    def norm(t: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()

    seen: dict[str, str] = {}
    collisions: list[tuple[str, str]] = []
    for ext_id, title in rows:
        key = norm(title)
        if key in seen and seen[key] != ext_id:
            collisions.append((seen[key], ext_id))
        seen[key] = ext_id
    out.append((
        "D-006", not collisions,
        f"papers sharing a normalised title: {len(collisions)}"
        + (f" {collisions[:2]}" if collisions else ""),
    ))
    return out


def check_citation_precision(conn: psycopg.Connection) -> list[Finding]:
    """D-015/P-003: a resolved citation edge must point at the right paper.

    Falsified if a resolved edge's reference text does not contain the target
    paper's title as a phrase, or if any edge points at its own source paper.
    """
    out: list[Finding] = []
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM citation_edges WHERE dst_paper_id = src_paper_id"
        )
        self_cites = cur.fetchone()[0]
        out.append((
            "D-015", self_cites == 0, f"edges pointing at their own source: {self_cites}"
        ))

        cur.execute(
            "SELECT e.ref_title, e.raw_reference, p.title "
            "FROM citation_edges e JOIN papers p ON p.id = e.dst_paper_id "
            "WHERE e.dst_paper_id IS NOT NULL"
        )
        rows = cur.fetchall()

    def norm(t: str) -> str:
        return " ".join(re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).split())

    unsupported = []
    for ref_title, raw, target_title in rows:
        haystack = norm(ref_title) + " " + norm(raw)
        needle = norm(target_title)
        if not needle:
            continue
        # Allow the same trimmed-tail tolerance the matcher uses for
        # line-broken titles.
        words = needle.split()
        if needle not in haystack and (
            len(words) < 8 or " ".join(words[:-2]) not in haystack
        ):
            unsupported.append((target_title or "")[:50])
    out.append((
        "D-015", not unsupported,
        f"resolved edges whose reference does not contain the target title: "
        f"{len(unsupported)} of {len(rows)}"
        + (f" (e.g. {unsupported[0]!r})" if unsupported else ""),
    ))
    return out


def check_table_quality(conn: psycopg.Connection) -> list[Finding]:
    """D-013/D-017: stored tables must be tables, not prose or page furniture.

    Falsified by a stored table whose cells look like running headers or
    sentences — the failure mode that got the whitespace detector reverted.
    """
    out: list[Finding] = []
    with conn.cursor() as cur:
        cur.execute("SELECT label, caption, grid FROM paper_tables")
        rows = cur.fetchall()

    # An earlier version of this check flagged "3+ cells over 90 characters" as
    # prose. Inspecting the hits showed they were genuine survey tables with
    # descriptive columns ("Description", "Hybrid Components"), so the check was
    # measuring cell length rather than correctness and has been replaced.
    #
    # What the inspection DID reveal is row merging: Attention Table 4 has one
    # cell reading '88.3 90.4 90.4 91.7' and another holding four separate row
    # labels. Four results have lost their row association — the P-004 failure
    # the schema was designed around, and the one that matters for numeric
    # extraction.
    merged = []
    huge = []
    numeric_run = re.compile(r"\d+\.\d+(?:\s+\d+\.\d+){2,}")
    for label, _caption, grid in rows:
        body = grid.get("rows") or []
        cols = grid.get("col_count") or 0
        if any(
            isinstance(cell, str) and numeric_run.search(cell)
            for row in body
            for cell in row
        ):
            merged.append(label or "(unlabelled)")
        if len(body) > 40 or cols > 12:
            huge.append(f"{label or '(unlabelled)'} {len(body)}x{cols}")

    # This is a known limitation of the line-based detector, not a regression,
    # and it will not reach zero without the layout model D-017 concluded is
    # needed. Failing forever would train everyone to ignore this suite, so the
    # measured baseline is recorded and only a WORSENING fails. See D-023.
    MERGED_BASELINE = 7
    out.append((
        "D-023", len(merged) <= MERGED_BASELINE,
        f"tables with 3+ numbers merged into one cell (lost row association): "
        f"{len(merged)} of {len(rows)}, baseline {MERGED_BASELINE}"
        + (f" {merged[:3]}" if merged else ""),
    ))
    out.append((
        "D-013", not huge,
        f"implausibly large tables (>40 rows or >12 cols): {len(huge)}"
        + (f" {huge[:2]}" if huge else ""),
    ))
    return out


def check_fts_behaviour(conn: psycopg.Connection) -> list[Finding]:
    """D-022: quantify how often AND-logic returns nothing.

    Not pass/fail on quality — that needs the eval set. This measures the
    behaviour the decision was left open on, so the eventual choice is informed
    by a number rather than by the one example that prompted it.
    """
    queries = [
        "semantic communication",
        "channel-aware training AWGN",
        "BLEU score",
        "knowledge graph semantic noise robustness",
        "deep learning joint source channel coding",
        "transformer encoder quantisation satellite",
        "semantic similarity metric validation human judgement",
        "energy efficiency spectral efficiency tradeoff",
    ]
    empty_all = empty_any = 0
    for q in queries:
        if not search(conn, q, top_k=5, term_logic="all"):
            empty_all += 1
        if not search(conn, q, top_k=5, term_logic="any"):
            empty_any += 1
    return [(
        "D-022", True,
        f"MEASUREMENT (not pass/fail): of {len(queries)} probe queries, "
        f"term_logic=all returned nothing for {empty_all}, any for {empty_any}",
    )]


def check_chunk_coverage(conn: psycopg.Connection) -> list[Finding]:
    """C-006/D-016: chunking must not drop or duplicate paragraph text.

    Falsified if a dev paragraph contributes to no chunk, or if chunk text is
    empty.
    """
    out: list[Finding] = []
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM paragraphs g "
            "JOIN v_dev_papers p ON p.id = g.paper_id "
            "LEFT JOIN chunk_spans s ON s.paragraph_id = g.id "
            "WHERE s.id IS NULL"
        )
        orphaned = cur.fetchone()[0]
        out.append((
            "C-006", orphaned == 0,
            f"dev paragraphs contributing to no chunk: {orphaned}",
        ))

        cur.execute("SELECT count(*) FROM chunks WHERE length(trim(text)) = 0")
        empty = cur.fetchone()[0]
        out.append(("C-006", empty == 0, f"empty chunks: {empty}"))

        cur.execute(
            "SELECT count(*) FROM chunks c JOIN corpus_split s "
            "ON s.paper_id = c.paper_id WHERE s.split = 'holdout'"
        )
        holdout_chunks = cur.fetchone()[0]
        out.append((
            "D-004", holdout_chunks == 0,
            f"chunks built from holdout papers: {holdout_chunks}",
        ))
    return out


def check_manifest_consistency(conn: psycopg.Connection) -> list[Finding]:
    """D-005/P-005: the committed manifest must match what is on disk and in the
    database, and deliberate exclusions must still be excluded."""
    out: list[Finding] = []
    manifest = list(csv.DictReader(Path("corpus/manifest.csv").open(encoding="utf-8")))
    manifest_ids = {r["external_id"] for r in manifest}

    on_disk = {p.stem for p in Path("corpus").glob("*.pdf")}
    out.append((
        "D-005", manifest_ids == on_disk,
        f"manifest ({len(manifest_ids)}) vs PDFs on disk ({len(on_disk)}): "
        f"{'match' if manifest_ids == on_disk else 'MISMATCH'}",
    ))

    with conn.cursor() as cur:
        cur.execute("SELECT external_id FROM papers")
        db_ids = {r[0] for r in cur.fetchall()}
    out.append((
        "D-005", manifest_ids == db_ids,
        f"manifest vs database ({len(db_ids)}): "
        f"{'match' if manifest_ids == db_ids else 'MISMATCH'}",
    ))

    ids = [r["external_id"] for r in manifest]
    dupes = [i for i, c in Counter(ids).items() if c > 1]
    out.append(("D-005", not dupes, f"duplicate ids in manifest: {dupes or 'none'}"))

    excluded_path = Path("corpus/excluded.csv")
    if excluded_path.exists():
        excluded = {
            r["sha256"] for r in csv.DictReader(excluded_path.open(encoding="utf-8"))
        }
        present = {r["sha256"] for r in manifest} & excluded
        out.append((
            "D-019", not present,
            f"deliberately excluded papers back in the corpus: {len(present)}",
        ))

    # P-005: the records about the corpus must actually be committed.
    tracked = subprocess.run(
        ["git", "ls-files", "corpus/"], capture_output=True, text=True
    ).stdout.split()
    for required in ("corpus/manifest.csv", "corpus/provenance.json"):
        out.append((
            "P-005", required in tracked, f"{required} tracked in git: "
            f"{required in tracked}",
        ))
    return out


CHECKS = [
    check_span_integrity,
    check_holdout_containment,
    check_duplicate_papers,
    check_citation_precision,
    check_table_quality,
    check_chunk_coverage,
    check_manifest_consistency,
    check_fts_behaviour,
]


def main() -> int:
    try:
        conn = psycopg.connect(store.dsn(), connect_timeout=10, autocommit=True)
    except psycopg.OperationalError as exc:
        print(f"could not connect: {exc}", file=sys.stderr)
        return 1

    findings: list[Finding] = []
    with conn:
        for check in CHECKS:
            try:
                findings.extend(check(conn))
            except Exception as exc:  # a broken check is itself a finding
                findings.append(
                    (check.__name__, False, f"CHECK CRASHED: {type(exc).__name__}: {exc}")
                )

    print("Stress-testing standing decisions against the live corpus\n")
    failed = 0
    for decision, passed, detail in findings:
        mark = "ok  " if passed else "FAIL"
        if not passed:
            failed += 1
        print(f"  [{mark}] {decision:<7} {detail}")

    print()
    if failed:
        print(f"{failed} of {len(findings)} checks failed.")
        return 1
    print(f"All {len(findings)} checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
