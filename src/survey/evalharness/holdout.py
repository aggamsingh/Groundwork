"""Holdout guard — CHECKPOINT 1 / D-004.

The holdout split is authored by the user in ``eval/holdout_papers.txt`` and is
never generated. This module only *reads* it, and refuses to let anything else
proceed if the file is missing, empty, or a stub.

Two guards exist. The database view ``v_dev_papers`` keeps holdout rows out of
query results by construction; this module is the second half, the check that
fails an eval run whose retrieved paper ids intersect the holdout list.

Stdlib only, on purpose: this runs in CI, and a guard that can fail to import
is not a guard.
"""

from __future__ import annotations

from pathlib import Path

HOLDOUT_FILE = Path("eval/holdout_papers.txt")

# Phase 6 is the only phase permitted to read holdout papers (spec §5).
HOLDOUT_UNLOCKED_FROM_PHASE = 6


class HoldoutError(RuntimeError):
    """Raised when the holdout is missing, unusable, or has been touched early."""


class HoldoutMissingError(HoldoutError):
    """The user has not yet produced the split. This is a human checkpoint."""


def _is_stub(path: Path) -> bool:
    """A ``*_STUB`` file is plumbing scaffolding and must never reach an eval run."""
    return "_STUB" in path.name.upper()


def load_holdout_ids(path: Path = HOLDOUT_FILE) -> frozenset[str]:
    """Read the frozen holdout list.

    Blank lines and ``#`` comments are ignored. Raises rather than returning an
    empty set: an empty holdout would silently disable the guard, which is the
    exact failure this module exists to prevent.
    """
    if _is_stub(path):
        raise HoldoutError(
            f"{path} is a stub. Stubs may be used for plumbing tests but never "
            "for an eval run. The real split is written by the user "
            "(CHECKPOINT 1 in CLAUDE.md)."
        )
    if not path.exists():
        raise HoldoutMissingError(
            f"{path} does not exist. This is CHECKPOINT 1: the user splits the "
            "corpus 2/3 dev / 1/3 holdout and freezes the list. It is not "
            "generated. Nothing in Phase 1 may run until it exists."
        )

    ids = {
        line.split("#", 1)[0].strip()
        for line in path.read_text(encoding="utf-8").splitlines()
    }
    ids.discard("")

    if not ids:
        raise HoldoutError(
            f"{path} exists but contains no paper ids. Refusing to treat an "
            "empty holdout as 'nothing held out' — that would disable the guard."
        )
    return frozenset(ids)


def assert_no_holdout(
    paper_ids: object,
    *,
    phase: int,
    context: str = "eval run",
    path: Path = HOLDOUT_FILE,
) -> None:
    """Fail if ``paper_ids`` touches the holdout before Phase 6.

    Call this at every boundary where papers enter a result: after retrieval,
    before generation, and at the top of any eval run.
    """
    if phase >= HOLDOUT_UNLOCKED_FROM_PHASE:
        return

    holdout = load_holdout_ids(path)
    leaked = sorted(holdout.intersection({str(p) for p in paper_ids}))
    if leaked:
        shown = ", ".join(leaked[:10])
        more = f" (+{len(leaked) - 10} more)" if len(leaked) > 10 else ""
        raise HoldoutError(
            f"Holdout leak in {context} at phase {phase}: {len(leaked)} held-out "
            f"paper(s) entered the result set: {shown}{more}. "
            "The holdout is not read or tuned against until Phase 6. "
            "Every number produced by this run is contaminated — discard it."
        )
