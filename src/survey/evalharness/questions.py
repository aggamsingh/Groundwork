"""Eval question set — loading, validation, and the stub guard.

The questions are CHECKPOINT 4: written by the user, never generated (D-002).
This module loads and validates them; it does not create them.

Format is JSONL, one question per line, so the file diffs cleanly in git and a
single malformed line names itself by line number instead of breaking the whole
file.

The stub guard is the load-bearing part. A `*_STUB` file may be used to exercise
the harness, and `load_questions` refuses to return it unless the caller passes
`allow_stub=True` — which the eval runner never does. The failure mode this
prevents is the one CLAUDE.md names: plumbing scaffolding quietly becoming the
thing a reported number was computed on.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

# The five types the spec requires (section 5, Phase 2).
QUESTION_TYPES = frozenset(
    {
        "single_paper_lookup",
        "cross_paper_comparison",
        "numeric_extraction",
        "contradiction",
        "unanswerable",
    }
)

QUESTIONS_DIR = Path("eval/questions")


class QuestionSetError(RuntimeError):
    """The question set is missing, malformed, or a stub."""


class StubQuestionSetError(QuestionSetError):
    """A stub was loaded where real questions are required."""


@dataclass(slots=True)
class SupportingSpan:
    """Where the answer lives. Paragraph-anchored, per D-003."""

    paper_external_id: str
    paragraph_id: int | None = None
    char_start: int | None = None
    char_end: int | None = None
    quote: str | None = None
    # Graded relevance for nDCG. 1.0 = answers the question on its own.
    relevance: float = 1.0


@dataclass(slots=True)
class Question:
    id: str
    question: str
    type: str
    answer: str | None = None
    spans: list[SupportingSpan] = field(default_factory=list)
    notes: str = ""

    @property
    def is_unanswerable(self) -> bool:
        return self.type == "unanswerable"

    @property
    def relevant_papers(self) -> set[str]:
        return {s.paper_external_id for s in self.spans}


def _parse_question(raw: dict, line_no: int, path: Path) -> Question:
    def fail(message: str) -> None:
        raise QuestionSetError(f"{path}:{line_no}: {message}")

    for required in ("id", "question", "type"):
        if not raw.get(required):
            fail(f"missing required field {required!r}")

    if raw["type"] not in QUESTION_TYPES:
        fail(
            f"unknown type {raw['type']!r}; expected one of "
            + ", ".join(sorted(QUESTION_TYPES))
        )

    spans = [
        SupportingSpan(
            paper_external_id=s["paper_external_id"],
            paragraph_id=s.get("paragraph_id"),
            char_start=s.get("char_start"),
            char_end=s.get("char_end"),
            quote=s.get("quote"),
            relevance=float(s.get("relevance", 1.0)),
        )
        for s in raw.get("spans", [])
    ]

    question = Question(
        id=str(raw["id"]),
        question=raw["question"],
        type=raw["type"],
        answer=raw.get("answer"),
        spans=spans,
        notes=raw.get("notes", ""),
    )

    # An answerable question with no supporting span cannot be scored: retrieval
    # recall would be 0.0 by definition (see metrics.recall_at_k), so it would
    # drag every reported number down while looking like a system failure rather
    # than a labelling gap.
    if not question.is_unanswerable and not spans:
        fail(
            f"question {question.id!r} is type {question.type!r} but has no "
            "supporting spans; an answerable question needs at least one"
        )
    if question.is_unanswerable and spans:
        fail(
            f"question {question.id!r} is unanswerable but lists supporting "
            "spans; one of the two is wrong"
        )
    return question


def is_stub(path: Path) -> bool:
    return "_STUB" in path.name.upper()


def load_questions(
    path: Path, *, allow_stub: bool = False
) -> list[Question]:
    """Load and validate a question set.

    Refuses stubs unless explicitly permitted. The eval runner never permits
    them, so a stub cannot silently become the basis of a reported number.
    """
    if is_stub(path) and not allow_stub:
        raise StubQuestionSetError(
            f"{path} is a STUB question set. It exists to exercise the harness "
            "and must never produce a reported number. The real set is written "
            "by the user (CHECKPOINT 4)."
        )
    if not path.exists():
        raise QuestionSetError(
            f"{path} does not exist. The eval set is CHECKPOINT 4: 60 questions "
            "hand-labelled by the user, with supporting spans."
        )

    questions: list[Question] = []
    seen_ids: set[str] = set()
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            raise QuestionSetError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
        question = _parse_question(raw, line_no, path)
        if question.id in seen_ids:
            raise QuestionSetError(f"{path}:{line_no}: duplicate id {question.id!r}")
        seen_ids.add(question.id)
        questions.append(question)

    if not questions:
        raise QuestionSetError(f"{path} contains no questions")
    return questions


def summarise(questions: list[Question]) -> dict[str, int]:
    counts = dict.fromkeys(sorted(QUESTION_TYPES), 0)
    for q in questions:
        counts[q.type] += 1
    return counts


def check_coverage(questions: list[Question]) -> list[str]:
    """Warnings about the shape of a question set.

    Returned rather than raised: a thin set is the user's call to make, but it
    must be visible in the report rather than discovered when a per-type number
    turns out to rest on one question.
    """
    warnings: list[str] = []
    counts = summarise(questions)
    for qtype, count in counts.items():
        if count == 0:
            warnings.append(f"no {qtype} questions; that metric will be undefined")
        elif count < 3:
            warnings.append(
                f"only {count} {qtype} question(s); per-type numbers will be "
                "extremely noisy"
            )
    if len(questions) < 60:
        warnings.append(
            f"{len(questions)} questions; the spec requires 60 for the Phase 2 "
            "baseline (CHECKPOINT 4)"
        )
    return warnings
