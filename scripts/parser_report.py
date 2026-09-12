"""Parser quality report over the corpus — input to the Phase 1 bake-off (1.5).

Reports per-parser coverage of the things Phase 2 will depend on. These are
proxies, not ground truth: nobody has hand-labelled the correct title of 42
papers. They are comparable *between parsers on the same corpus*, which is what
a bake-off needs, and that is the only claim made for them.

Usage:
    uv run python scripts/parser_report.py [--parser pymupdf] [--limit N]
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
import time
from pathlib import Path

from survey.ingest import grobid_parser, hybrid_parser, pymupdf_parser
from survey.ingest.model import ParseError

PARSERS = {
    "pymupdf": pymupdf_parser.parse,
    "grobid": grobid_parser.parse,
    "hybrid": hybrid_parser.parse,
}

CORPUS = Path("corpus")


def _looks_like_title(title: str | None) -> bool:
    """Crude plausibility, not correctness: length, word count, no sentence end."""
    if not title:
        return False
    words = title.split()
    return 3 <= len(words) <= 30 and 15 <= len(title) <= 250 and not title.endswith(".")


def _run(parse, rows: list[dict]) -> tuple[list, list, list[float]]:
    ok, failed, durations = [], [], []
    for r in rows:
        started = time.perf_counter()
        try:
            paper = parse(CORPUS / r["filename"], r["external_id"])
        except ParseError as exc:
            failed.append((r["external_id"], str(exc)))
            continue
        except Exception as exc:  # a crash is a parser defect, not a bad PDF
            failed.append((r["external_id"], f"UNEXPECTED {type(exc).__name__}: {exc}"))
            continue
        durations.append(time.perf_counter() - started)
        ok.append(paper)
    return ok, failed, durations


def _metrics(ok: list, failed: list, durations: list[float], total: int) -> dict:
    if not ok:
        return {"hard failures": f"{len(failed)}/{total}"}
    n = len(ok)

    def pct(count: int) -> str:
        return f"{count}/{n} ({count / n:.0%})"

    return {
        "hard failures": f"{len(failed)}/{total} ({len(failed) / total:.0%})",
        "plausible title": pct(sum(_looks_like_title(p.title) for p in ok)),
        "abstract": pct(sum(bool(p.abstract) for p in ok)),
        "year": pct(sum(p.year is not None for p in ok)),
        "doi": pct(sum(bool(p.doi) for p in ok)),
        "venue": pct(sum(bool(p.venue) for p in ok)),
        ">=1 reference": pct(sum(len(p.references) > 0 for p in ok)),
        "structured refs": pct(sum(any(r.title for r in p.references) for p in ok)),
        ">=3 sections": pct(sum(len(p.sections) >= 3 for p in ok)),
        ">=1 table": pct(sum(len(p.tables) > 0 for p in ok)),
        "median paragraphs": f"{statistics.median(p.paragraph_count for p in ok):.0f}",
        "median chars": f"{statistics.median(p.char_count for p in ok):,.0f}",
        "median references": f"{statistics.median(len(p.references) for p in ok):.0f}",
        "median seconds": f"{statistics.median(durations):.2f}",
        "total seconds": f"{sum(durations):.0f}",
    }


def compare(rows: list[dict]) -> int:
    """Run every parser over the same papers and print a side-by-side table."""
    results = {}
    for name, parse in sorted(PARSERS.items()):
        print(f"running {name} over {len(rows)} papers...", flush=True)
        ok, failed, durations = _run(parse, rows)
        results[name] = (_metrics(ok, failed, durations, len(rows)), failed)

    names = sorted(results)
    width = max(len(k) for m, _ in results.values() for k in m)
    print(f"\n{'metric':<{width}}  " + "  ".join(f"{n:>18}" for n in names))
    print("-" * (width + 2 + 20 * len(names)))
    for key in results[names[0]][0]:
        row = "  ".join(f"{results[n][0].get(key, '-'):>18}" for n in names)
        print(f"{key:<{width}}  {row}")

    for name in names:
        failures = results[name][1]
        if failures:
            print(f"\n{name} failures ({len(failures)}):")
            for ext_id, why in failures:
                print(f"  {ext_id[:60]:<60} {why[:70]}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--parser", default="pymupdf", choices=sorted(PARSERS))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument(
        "--compare", action="store_true", help="run all parsers side by side"
    )
    args = ap.parse_args()

    rows = list(csv.DictReader((CORPUS / "manifest.csv").open(encoding="utf-8")))
    rows.sort(key=lambda r: r["external_id"])
    if args.limit:
        rows = rows[: args.limit]

    if args.compare:
        return compare(rows)

    parse = PARSERS[args.parser]

    ok, failed = [], []
    durations = []
    for r in rows:
        started = time.perf_counter()
        try:
            paper = parse(CORPUS / r["filename"], r["external_id"])
        except ParseError as exc:
            failed.append((r["external_id"], str(exc)))
            continue
        except Exception as exc:  # a crash is a parser defect, not a bad PDF
            failed.append((r["external_id"], f"UNEXPECTED {type(exc).__name__}: {exc}"))
            continue
        durations.append(time.perf_counter() - started)
        ok.append(paper)

    total = len(rows)
    print(f"parser: {args.parser}   papers: {total}")
    print(f"  hard failures      {len(failed)}/{total} ({len(failed) / total:.1%})")
    if not ok:
        return 1

    def pct(n: int) -> str:
        return f"{n}/{len(ok)} ({n / len(ok):.0%})"

    print(f"  plausible title    {pct(sum(_looks_like_title(p.title) for p in ok))}")
    print(f"  abstract found     {pct(sum(bool(p.abstract) for p in ok))}")
    print(f"  year found         {pct(sum(p.year is not None for p in ok))}")
    print(f"  doi found          {pct(sum(bool(p.doi) for p in ok))}")
    print(f"  venue found        {pct(sum(bool(p.venue) for p in ok))}")
    print(f"  >=1 reference      {pct(sum(len(p.references) > 0 for p in ok))}")
    print(f"  >=3 sections       {pct(sum(len(p.sections) >= 3 for p in ok))}")
    print(f"  >=1 table          {pct(sum(len(p.tables) > 0 for p in ok))}")

    paras = [p.paragraph_count for p in ok]
    chars = [p.char_count for p in ok]
    refs = [len(p.references) for p in ok]
    print(f"  median paragraphs  {statistics.median(paras):.0f}")
    print(f"  median chars       {statistics.median(chars):,.0f}")
    print(f"  median references  {statistics.median(refs):.0f}")
    print(f"  median parse time  {statistics.median(durations):.2f}s")
    print(f"  total parse time   {sum(durations):.1f}s")

    # Papers whose extraction looks thin relative to their length are where a
    # better parser should show its value, so name them rather than average them.
    suspicious = [
        p
        for p in ok
        if p.page_count and p.char_count / p.page_count < 1200
    ]
    if suspicious:
        print(f"\n  thin extraction ({len(suspicious)}): <1200 chars/page")
        for p in sorted(suspicious, key=lambda p: p.char_count / (p.page_count or 1)):
            print(
                f"    {p.external_id[:62]:<62} "
                f"{p.char_count / p.page_count:>6.0f} c/p  {p.page_count}p"
            )

    if failed:
        print(f"\n  failures ({len(failed)}):")
        for ext_id, why in failed:
            print(f"    {ext_id[:62]:<62} {why[:80]}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
