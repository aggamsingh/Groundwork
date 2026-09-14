"""Retrieval and answer metrics â€” Phase 2 harness.

Pure functions over (ranked results, relevant items). No corpus, no database, no
model. That is deliberate: these are the instruments, and an instrument should be
verifiable independently of what it measures. Every one here is checked in
`tests/test_metrics.py` against worked examples computed by hand, so a change
that breaks a formula fails immediately rather than quietly shifting a number
everything else is compared against.

Built before the eval set exists (C-006). The formulas are standard and do not
depend on the questions; the questions are the *input*, supplied later.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence


def recall_at_k(retrieved: Sequence[str], relevant: Iterable[str], k: int) -> float:
    """Share of relevant items appearing in the top k.

    Returns 0.0 when nothing is relevant. That case means the question was
    mislabelled â€” an answerable question with no supporting span â€” and scoring it
    as a perfect 1.0, which the "no relevant items" convention would give, hides
    a broken label behind a good number.
    """
    relevant_set = set(relevant)
    if not relevant_set or k <= 0:
        return 0.0
    hits = len(relevant_set.intersection(retrieved[:k]))
    return hits / len(relevant_set)


def precision_at_k(retrieved: Sequence[str], relevant: Iterable[str], k: int) -> float:
    if k <= 0:
        return 0.0
    top = retrieved[:k]
    if not top:
        return 0.0
    return len(set(relevant).intersection(top)) / len(top)


def hit_at_k(retrieved: Sequence[str], relevant: Iterable[str], k: int) -> float:
    """1.0 if any relevant item is in the top k.

    Distinct from recall, and worth reporting separately: a question whose answer
    lives in one span is answerable as soon as that span is retrieved, while a
    cross-paper comparison needs several. Recall alone conflates the two.
    """
    return 1.0 if set(relevant).intersection(retrieved[:k]) else 0.0


def reciprocal_rank(retrieved: Sequence[str], relevant: Iterable[str]) -> float:
    """1/rank of the first relevant item, 0.0 if none is retrieved."""
    relevant_set = set(relevant)
    for i, item in enumerate(retrieved, start=1):
        if item in relevant_set:
            return 1.0 / i
    return 0.0


def dcg(gains: Sequence[float]) -> float:
    """Discounted cumulative gain with the standard log2(i+1) discount."""
    return sum(g / math.log2(i + 1) for i, g in enumerate(gains, start=1))


def ndcg_at_k(
    retrieved: Sequence[str],
    relevance: dict[str, float],
    k: int,
) -> float:
    """nDCG@k against graded relevance.

    Graded rather than binary because the eval set will have degrees: a span that
    answers the question outright is not the same as one that contributes part of
    a cross-paper comparison. Binary relevance collapses that distinction, and it
    is exactly the distinction a reranker is supposed to learn.

    The ideal ranking is computed over ALL known-relevant items, not only those
    retrieved â€” otherwise a system that retrieves one relevant item and ranks it
    first scores 1.0 while missing nine others.
    """
    if k <= 0 or not relevance:
        return 0.0
    gains = [relevance.get(item, 0.0) for item in retrieved[:k]]
    ideal = sorted(relevance.values(), reverse=True)[:k]
    ideal_dcg = dcg(ideal)
    if ideal_dcg == 0.0:
        return 0.0
    return dcg(gains) / ideal_dcg


# --- Answer-level metrics -------------------------------------------------
#
# These take already-computed judgements rather than doing the judging. Whether a
# cited span entails a sentence is decided by the NLI verifier (Phase 4) or by
# the user (CHECKPOINT 5); this module only aggregates. Keeping the aggregation
# separate from the judging means the numbers can be recomputed from stored
# judgements without re-running a model.


def citation_faithfulness(entailed: Sequence[bool]) -> float:
    """Share of generated sentences whose cited span supports them.

    An answer with no sentences scores 0.0, not 1.0. A system that emits nothing
    is not perfectly faithful â€” it is a refusal, and refusals are measured by
    abstention metrics, where they count properly.
    """
    if not entailed:
        return 0.0
    return sum(1 for e in entailed if e) / len(entailed)


def abstention_recall(
    abstained: Sequence[bool], truly_unanswerable: Sequence[bool]
) -> float:
    """Share of genuinely unanswerable questions the system refused.

    Spec Definition of Done #4 requires >= 85%.
    """
    if len(abstained) != len(truly_unanswerable):
        raise ValueError("abstained and truly_unanswerable must align")
    total = sum(1 for u in truly_unanswerable if u)
    if total == 0:
        return 0.0
    correct = sum(1 for a, u in zip(abstained, truly_unanswerable, strict=True) if u and a)
    return correct / total


def false_refusal_rate(
    abstained: Sequence[bool], truly_unanswerable: Sequence[bool]
) -> float:
    """Share of ANSWERABLE questions the system wrongly refused.

    Reported alongside abstention recall, never instead of it. Abstention recall
    alone is trivially maximised by refusing everything, and a system that
    refuses everything is useless while scoring 100% on Definition of Done #4.
    Spec Phase 4 requires this number explicitly for that reason.
    """
    if len(abstained) != len(truly_unanswerable):
        raise ValueError("abstained and truly_unanswerable must align")
    answerable = sum(1 for u in truly_unanswerable if not u)
    if answerable == 0:
        return 0.0
    refused = sum(1 for a, u in zip(abstained, truly_unanswerable, strict=True) if not u and a)
    return refused / answerable


def aggregate(values: Iterable[float]) -> float:
    """Mean over questions, 0.0 when empty."""
    values = list(values)
    return sum(values) / len(values) if values else 0.0
