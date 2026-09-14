"""Eval runner — config in, numbers out.

Retrieval is scored at PAPER level here, not chunk level. Deliberate: the user's
supporting spans name a paper and a location in it, and chunk ids change every
time chunking changes (which Phase 3 does eight times). Scoring on chunk ids
would make Phase 2's numbers incomparable with Phase 3's — which is exactly what
the baseline exists to prevent. Span-level scoring arrives when spans can be
resolved to stored paragraph offsets, and is a separate, finer metric.

Nothing here decides anything. It measures a configuration supplied by the
caller and reports per-type breakdowns alongside the headline, because an
average over five question types hides which type is failing.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import psycopg

from survey.config.config import RunConfig
from survey.evalharness import metrics
from survey.evalharness.questions import Question
from survey.retrieval.lexical import Retrieved, search


@dataclass(slots=True)
class QuestionResult:
    question_id: str
    question_type: str
    retrieved_papers: list[str]
    relevant_papers: list[str]
    recall_at_k: float
    hit_at_k: float
    precision_at_k: float
    reciprocal_rank: float
    ndcg_at_k: float


@dataclass(slots=True)
class EvalReport:
    config_fingerprint: str
    question_count: int
    top_k: int
    overall: dict[str, float] = field(default_factory=dict)
    by_type: dict[str, dict[str, float]] = field(default_factory=dict)
    per_question: list[QuestionResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def summary_lines(self) -> list[str]:
        lines = [
            f"config      : {self.config_fingerprint}",
            f"questions   : {self.question_count}   top_k: {self.top_k}",
            "",
            "overall (paper-level retrieval):",
        ]
        lines.extend(f"  {k:<16} {v:.3f}" for k, v in sorted(self.overall.items()))
        if self.by_type:
            lines.append("")
            lines.append("by question type:")
            for qtype, values in sorted(self.by_type.items()):
                counted = int(values.get("n", 0))
                lines.append(f"  {qtype} (n={counted})")
                lines.extend(
                    f"    {k:<14} {v:.3f}"
                    for k, v in sorted(values.items())
                    if k != "n"
                )
        if self.warnings:
            lines.append("")
            lines.append("warnings:")
            lines.extend(f"  ! {w}" for w in self.warnings)
        return lines


RetrieverFn = Callable[[str, int], list[Retrieved]]


def _paper_ids(
    conn: psycopg.Connection, retrieved: list[Retrieved]
) -> list[str]:
    """Map retrieved chunks to external paper ids, preserving rank order."""
    if not retrieved:
        return []
    ids = list({r.paper_id for r in retrieved})
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, external_id FROM papers WHERE id = ANY(%s)", (ids,)
        )
        lookup = dict(cur.fetchall())

    ordered: list[str] = []
    for item in retrieved:
        external = lookup.get(item.paper_id)
        # De-duplicate: several chunks from one paper are one retrieved paper,
        # and counting them separately would inflate precision.
        if external and external not in ordered:
            ordered.append(external)
    return ordered


def default_retriever(
    conn: psycopg.Connection, config: RunConfig
) -> RetrieverFn:
    """Lexical retrieval bound to a config. Dense retrieval is not available yet."""

    def retrieve(question: str, top_k: int) -> list[Retrieved]:
        return search(
            conn,
            question,
            top_k=top_k,
            corpus_id=config.corpus,
            config_fingerprint=config.fingerprint(),
        )

    return retrieve


def run_eval(
    conn: psycopg.Connection,
    questions: list[Question],
    config: RunConfig,
    *,
    retriever: RetrieverFn | None = None,
    chunk_multiplier: int = 4,
) -> EvalReport:
    """Score a retrieval configuration against a question set.

    `chunk_multiplier` fetches more chunks than top_k papers, because several
    chunks routinely come from one paper and truncating at top_k chunks would
    measure fewer than top_k papers.
    """
    retrieve = retriever or default_retriever(conn, config)
    top_k = config.retrieval.top_k

    results: list[QuestionResult] = []
    for question in questions:
        if question.is_unanswerable:
            # Unanswerable questions measure abstention, not retrieval. Scoring
            # them here would report recall 0.0 for correct behaviour.
            continue

        retrieved = retrieve(question.question, top_k * chunk_multiplier)
        papers = _paper_ids(conn, retrieved)[:top_k]
        relevant = sorted(question.relevant_papers)
        relevance = {
            span.paper_external_id: span.relevance for span in question.spans
        }

        results.append(
            QuestionResult(
                question_id=question.id,
                question_type=question.type,
                retrieved_papers=papers,
                relevant_papers=relevant,
                recall_at_k=metrics.recall_at_k(papers, relevant, top_k),
                hit_at_k=metrics.hit_at_k(papers, relevant, top_k),
                precision_at_k=metrics.precision_at_k(papers, relevant, top_k),
                reciprocal_rank=metrics.reciprocal_rank(papers, relevant),
                ndcg_at_k=metrics.ndcg_at_k(papers, relevance, top_k),
            )
        )

    report = EvalReport(
        config_fingerprint=config.fingerprint(),
        question_count=len(questions),
        top_k=top_k,
        per_question=results,
    )

    if results:
        report.overall = {
            "recall_at_k": metrics.aggregate(r.recall_at_k for r in results),
            "hit_at_k": metrics.aggregate(r.hit_at_k for r in results),
            "precision_at_k": metrics.aggregate(r.precision_at_k for r in results),
            "mrr": metrics.aggregate(r.reciprocal_rank for r in results),
            "ndcg_at_k": metrics.aggregate(r.ndcg_at_k for r in results),
        }
        by_type: dict[str, list[QuestionResult]] = {}
        for result in results:
            by_type.setdefault(result.question_type, []).append(result)
        report.by_type = {
            qtype: {
                "n": float(len(group)),
                "recall_at_k": metrics.aggregate(r.recall_at_k for r in group),
                "hit_at_k": metrics.aggregate(r.hit_at_k for r in group),
                "mrr": metrics.aggregate(r.reciprocal_rank for r in group),
                "ndcg_at_k": metrics.aggregate(r.ndcg_at_k for r in group),
            }
            for qtype, group in by_type.items()
        }

    answered = len(results)
    if answered < len(questions):
        report.warnings.append(
            f"{len(questions) - answered} unanswerable question(s) excluded from "
            "retrieval metrics; they measure abstention, which needs generation"
        )
    return report
