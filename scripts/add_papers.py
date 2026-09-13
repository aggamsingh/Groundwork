"""Add papers to the corpus from a folder — dedupe, then update the manifest.

Written for the corpus growth to ~120 papers (C-001). The first import was done
with throwaway code; this does the same job repeatably and catches the failure
modes that import actually hit:

  - byte-identical duplicates (6 pairs in the first 50 files)
  - same paper, different bytes — re-downloaded, differing only in embedded
    metadata (D-006)
  - a preprint of a paper already present in published form (D-007), which is the
    dangerous one: had those two straddled the dev/holdout split, the system
    would have been tuned on the exact content the holdout exists to test

and one that could not arise the first time, because there was no split yet:

  - a NEW paper duplicating a HOLDOUT paper. New papers join the dev side
    (C-001), so a duplicate of a held-out paper puts the same content on both
    sides of the split. That is silent contamination, and this refuses it.

Dry run by default; --apply copies files and rewrites the manifest.

Usage:
    uv run python scripts/add_papers.py "C:/path/to/folder"
    uv run python scripts/add_papers.py "C:/path/to/folder" --apply
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

from survey.evalharness.holdout import HoldoutMissingError, load_holdout_ids

CORPUS = Path("corpus")
MANIFEST = CORPUS / "manifest.csv"
PROVENANCE = CORPUS / "provenance.json"
# Papers deliberately removed, keyed by content hash. Without this a later import
# from the same source folder silently re-adds them: the first dry run of this
# script tried to restore the arXiv preprint removed by D-007, because its slug
# shares no prefix with the published version's and nothing recorded the removal.
# A deletion that is not written down is a deletion that gets undone.
EXCLUDED = CORPUS / "excluded.csv"
FIELDS = ["external_id", "filename", "sha256", "size_bytes"]

# A title this similar to an existing one is the same paper under another name.
TITLE_PREFIX_WORDS = 8


def slug(name: str) -> str:
    s = re.sub(r"^\s*\d+[.)]\s*", "", name).lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return re.sub(r"-+", "-", s).strip("-")[:80].strip("-")


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def title_key(external_id: str) -> str:
    """First N words of a slug, for spotting preprint/published pairs."""
    return "-".join(external_id.split("-")[:TITLE_PREFIX_WORDS])


def load_existing() -> list[dict]:
    if not MANIFEST.exists():
        return []
    return list(csv.DictReader(MANIFEST.open(encoding="utf-8")))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("source", type=Path, help="folder of PDFs to add")
    ap.add_argument("--apply", action="store_true", help="actually copy and update")
    args = ap.parse_args()

    if not args.source.is_dir():
        print(f"not a folder: {args.source}", file=sys.stderr)
        return 1

    existing = load_existing()
    by_sha = {r["sha256"]: r["external_id"] for r in existing}
    by_id = {r["external_id"] for r in existing}
    by_title = {title_key(r["external_id"]): r["external_id"] for r in existing}

    try:
        holdout = load_holdout_ids()
    except HoldoutMissingError:
        holdout = frozenset()
        print("WARNING: no frozen holdout; contamination checks are off\n")

    incoming = sorted(p for p in args.source.glob("*.pdf") if p.is_file())
    if not incoming:
        print(f"no PDFs in {args.source}", file=sys.stderr)
        return 1

    plan: list[tuple[Path, str, str]] = []
    skipped: list[tuple[str, str]] = []
    blocked: list[tuple[str, str]] = []
    seen_sha: dict[str, str] = {}

    excluded: dict[str, dict] = {}
    if EXCLUDED.exists():
        excluded = {
            r["sha256"]: r for r in csv.DictReader(EXCLUDED.open(encoding="utf-8"))
        }

    for path in incoming:
        digest = sha256_of(path)
        ext_id = slug(path.stem)

        if digest in excluded:
            row = excluded[digest]
            skipped.append(
                (path.name, f"deliberately excluded ({row['decision']}): {row['reason'][:70]}")
            )
            continue
        if digest in by_sha:
            skipped.append((path.name, f"already in corpus as {by_sha[digest]}"))
            continue
        if digest in seen_sha:
            skipped.append((path.name, f"duplicate of {seen_sha[digest]} in this batch"))
            continue
        if ext_id in by_id:
            skipped.append((path.name, f"id {ext_id} already exists (different bytes)"))
            continue

        near = by_title.get(title_key(ext_id))
        if near:
            # Same leading title words, different id: a preprint/published pair,
            # or the same paper saved twice. Refuse rather than guess -- but if
            # the twin is held out, say so loudly, because that is contamination
            # rather than untidiness.
            if near in holdout:
                blocked.append(
                    (path.name, f"looks like HOLDOUT paper {near} — would put the "
                                "same content on both sides of the split")
                )
            else:
                skipped.append((path.name, f"looks like existing paper {near}"))
            continue

        seen_sha[digest] = ext_id
        by_id.add(ext_id)
        by_title[title_key(ext_id)] = ext_id
        plan.append((path, ext_id, digest))

    print(f"source      : {args.source}")
    print(f"incoming    : {len(incoming)} files")
    print(f"already have: {len(existing)} papers\n")

    for name, why in blocked:
        print(f"  [BLOCKED] {name[:58]:<58} {why}")
    for name, why in skipped:
        print(f"  [skip]    {name[:58]:<58} {why}")
    for path, ext_id, _ in plan:
        print(f"  [add]     {path.name[:58]:<58} -> {ext_id}")

    print(f"\nwould add {len(plan)}, skip {len(skipped)}, block {len(blocked)}")
    print(f"corpus would go from {len(existing)} to {len(existing) + len(plan)} papers")

    if blocked:
        print("\nBlocked entries are potential holdout contamination. Resolve them")
        print("before adding: they are not skippable noise.")

    if not args.apply:
        print("\nDry run. Re-run with --apply to copy files and update the manifest.")
        return 1 if blocked else 0

    if blocked:
        print("\nRefusing to apply while holdout contamination is unresolved.")
        return 1

    CORPUS.mkdir(exist_ok=True)
    provenance = (
        json.loads(PROVENANCE.read_text(encoding="utf-8"))
        if PROVENANCE.exists()
        else {}
    )
    rows = list(existing)
    for path, ext_id, digest in plan:
        dest = CORPUS / f"{ext_id}.pdf"
        shutil.copy2(path, dest)
        rows.append(
            {
                "external_id": ext_id,
                "filename": dest.name,
                "sha256": digest,
                "size_bytes": dest.stat().st_size,
            }
        )
        provenance[ext_id] = {"kept": path.name, "source_files": [path.name]}

    rows.sort(key=lambda r: r["external_id"])
    with MANIFEST.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    PROVENANCE.write_text(json.dumps(provenance, indent=2), encoding="utf-8")

    print(f"\nadded {len(plan)} papers; manifest now has {len(rows)}")
    print("next: uv run python scripts/ingest.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
