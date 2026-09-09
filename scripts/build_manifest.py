"""Build corpus/manifest.csv from the PDFs in corpus/ — task 0.5.

The PDFs themselves are gitignored; this manifest is the committed record of
what the corpus contained, with a content hash per paper so re-ingestion is
idempotent and any past result is reproducible.

This does not choose the holdout split. That is the user's (CHECKPOINT 1).

Usage:
    python scripts/build_manifest.py [--corpus-dir corpus] [--out corpus/manifest.csv]
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import sys
from pathlib import Path

FIELDS = ["external_id", "filename", "sha256", "size_bytes"]


def sha256_of(path: Path, chunk_size: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


def external_id_from(path: Path) -> str:
    """Derive the paper's stable id from its filename.

    The id scheme is the user's choice (arXiv id / DOI / slug) and is fixed once
    eval labels reference it. Here it is simply the filename stem, so renaming a
    file to its arXiv id is all it takes to set the id.
    """
    return path.stem.strip()


def build(corpus_dir: Path, out: Path) -> int:
    pdfs = sorted(p for p in corpus_dir.glob("*.pdf") if p.is_file())
    if not pdfs:
        print(f"No PDFs found in {corpus_dir}/ — nothing to do.", file=sys.stderr)
        return 1

    rows = []
    seen: dict[str, str] = {}
    for pdf in pdfs:
        ext_id = external_id_from(pdf)
        if ext_id in seen:
            print(
                f"Duplicate external_id {ext_id!r}: {seen[ext_id]} and {pdf.name}",
                file=sys.stderr,
            )
            return 1
        seen[ext_id] = pdf.name
        rows.append(
            {
                "external_id": ext_id,
                "filename": pdf.name,
                "sha256": sha256_of(pdf),
                "size_bytes": pdf.stat().st_size,
            }
        )

    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} papers to {out}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus-dir", type=Path, default=Path("corpus"))
    ap.add_argument("--out", type=Path, default=Path("corpus/manifest.csv"))
    args = ap.parse_args()
    return build(args.corpus_dir, args.out)


if __name__ == "__main__":
    raise SystemExit(main())
