"""Run the eval harness — spec section 5, Phase 2: "eval runs by one command".

    .\\.venv\\Scripts\\python.exe scripts/run_eval.py

Refuses to run without a real question set. `--smoke` exercises the plumbing
against the STUB set and prints no metrics, because a number computed from a stub
is worse than no number: it looks like a result.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import psycopg

from survey.config.config import default_config
from survey.evalharness.questions import (
    QUESTIONS_DIR,
    QuestionSetError,
    check_coverage,
    load_questions,
    summarise,
)
from survey.evalharness.runner import run_eval
from survey.ingest import store

DEFAULT_QUESTIONS = QUESTIONS_DIR / "v1.jsonl"
STUB_QUESTIONS = QUESTIONS_DIR / "smoke_STUB.jsonl"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    ap.add_argument("--top-k", type=int, default=None)
    ap.add_argument("--out", type=Path, default=None, help="write the report as JSON")
    ap.add_argument(
        "--smoke",
        action="store_true",
        help="exercise the harness on the STUB set; prints no metrics",
    )
    args = ap.parse_args()

    config = default_config()
    if args.top_k:
        config.retrieval.top_k = args.top_k

    path = STUB_QUESTIONS if args.smoke else args.questions
    try:
        questions = load_questions(path, allow_stub=args.smoke)
    except QuestionSetError as exc:
        print(f"{exc}", file=sys.stderr)
        return 1

    print(f"questions   : {len(questions)} from {path}")
    print(f"by type     : {summarise(questions)}")
    print()
    print(config.describe_unjustified())
    print()

    try:
        conn = psycopg.connect(store.dsn(), connect_timeout=10, autocommit=True)
    except psycopg.OperationalError as exc:
        print(f"could not connect: {exc}", file=sys.stderr)
        return 1

    with conn:
        report = run_eval(conn, questions, config)

    if args.smoke:
        # Deliberately no metrics. The harness ran; that is the whole claim.
        answered = len(report.per_question)
        print(
            f"SMOKE RUN OK: retrieval executed for {answered} question(s), "
            "metrics computed and discarded."
        )
        print("No numbers are reported from a STUB set (CHECKPOINT 4, D-002).")
        for result in report.per_question[:3]:
            print(
                f"  {result.question_id}: retrieved "
                f"{len(result.retrieved_papers)} paper(s)"
            )
        return 0

    report.warnings.extend(check_coverage(questions))
    print("\n".join(report.summary_lines()))

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(
                {
                    "config_fingerprint": report.config_fingerprint,
                    "config": config.model_dump(),
                    "question_count": report.question_count,
                    "top_k": report.top_k,
                    "overall": report.overall,
                    "by_type": report.by_type,
                    "warnings": report.warnings,
                    "per_question": [
                        {
                            "id": r.question_id,
                            "type": r.question_type,
                            "retrieved": r.retrieved_papers,
                            "relevant": r.relevant_papers,
                            "recall_at_k": r.recall_at_k,
                            "ndcg_at_k": r.ndcg_at_k,
                        }
                        for r in report.per_question
                    ],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"\nreport written to {args.out}")

    print(
        "\nThese are retrieval numbers for ONE configuration. They are not a "
        "comparison and nothing here is tuned (C-006)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
