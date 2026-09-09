# Phase tracker

Status flags: `NOT STARTED` · `IN PROGRESS` · `BLOCKED` · **`BLOCKED ON HUMAN`** · `COMPLETE`

`BLOCKED ON HUMAN` means the work is waiting on one of the six human-gated
checkpoints in CLAUDE.md. Claude does not unblock these by generating the artifact.

A phase moves to `COMPLETE` only when every exit criterion is met and
`docs/reports/phase-N.md` is committed. Do not proceed without meeting exit criteria.

| Phase | Title | Days | Status |
|---|---|---|---|
| 0 | Scope lock and skeleton | 1 | IN PROGRESS |
| 1 | Ingestion and corpus store | 2–4 | NOT STARTED |
| 2 | Naive baseline and eval harness | 5–7 | NOT STARTED |
| 3 | Retrieval upgrades, measured one at a time | 8–12 | NOT STARTED |
| 4 | Groundedness and abstention | 13–15 | NOT STARTED |
| 5 | Per-corpus adaptation | 16–20 | NOT STARTED |
| 6 | Generalization and hardening | 21–24 | NOT STARTED |
| 7 | Daily-use readiness | 25–28 | NOT STARTED |

---

## Phase 0 — Scope lock and skeleton

**Status:** IN PROGRESS (started 2026-09-09)

**Exit criteria:** holdout split committed and untouchable; schema and gold table
frozen; `docker compose up` works.

| # | Task | Status | Blocked by |
|---|---|---|---|
| 0.1 | `CLAUDE.md` + four docs logs | COMPLETE | — |
| 0.2 | `pyproject.toml` (uv), `.gitignore`, `.env.example`, package skeleton | COMPLETE | — |
| 0.3 | `docker-compose.yml`: Postgres 16 + pgvector — **written, not yet smoke-tested (Docker not installed)** | IN PROGRESS | Q-B8 |
| 0.4 | `db/schema.sql`: papers, sections, paragraphs, tables, citation_edges, corpus_split, `v_dev_papers` | COMPLETE (unverified until 0.3 runs) | — |
| 0.5 | Seed corpus: 42 unique papers copied, `corpus/manifest.csv` committed (50 files → 42, see D-006/D-007) | COMPLETE | — |
| 0.6a | **User** splits 2/3 dev / 1/3 holdout → `eval/holdout_papers.txt`, confirms frozen | **BLOCKED ON HUMAN** | **CHECKPOINT 1** |
| 0.6b | CI leak guard `survey.evalharness.holdout` + 12 unit tests | COMPLETE (awaits real split to load) | — |
| 0.7 | **User** writes and freezes `schema/semcom.yaml` (dated); Claude may draft for editing | **BLOCKED ON HUMAN** | **CHECKPOINT 2** |
| 0.8 | **User** exports `eval/gold_table_semcom.csv` from their survey — never synthesized | **BLOCKED ON HUMAN** | **CHECKPOINT 3** |
| 0.9 | DECISIONS D-001, D-002, D-003, D-004 all written 2026-09-09 | COMPLETE | — |
| 0.10 | Exit check + `docs/reports/phase-0.md` | NOT STARTED | 0.3, 0.6a, 0.7, 0.8 |

### Open questions blocking Phase 0

| ID | Question | Blocks |
|---|---|---|
| Q-B2 | Gold comparison table — does it exist, in what form? | 0.8, and Phase 0 exit |
| Q-B3 | Which generator API is available? | Phase 2 |
| Q-B4 | GPU available, and how much VRAM? | Phase 4 / 5 architecture |
| ~~Q-B5~~ | ~~Holdout split — random or stratified?~~ **Resolved: the user chooses the papers. Claude does not generate the split.** | — |
| Q-B6 | Schema — does the user want a Claude draft to edit, or write from scratch? (Either way the frozen file is theirs.) | 0.7 |
| Q-B7 | Rename spec to `PROJECT_SPEC.md`, or keep current name? | cosmetic |
| Q-B8 | **Docker and uv are not installed; only Python 3.14 is present (spec wants 3.11).** Install them? | 0.3, and Phase 0 exit |

---

## Phase 1 — Ingestion and corpus store

**Status:** NOT STARTED — **do not begin until the user says so, and not before
CHECKPOINT 1 clears:** `eval/holdout_papers.txt` must exist and the user must have
confirmed the split is frozen. This is a hard refusal, not a reminder.

**Exit criteria:** all 42 seeded papers ingested (was 120 — see C-001), <5% hard parse failures, failures inspectable,
tables preserved as tables, re-running ingestion is idempotent.

Task list to be planned when Phase 0 closes. Per the working agreement, later phases
are not planned in advance.

### ⚠ Reminder owed at Phase 1 close — grow the corpus to ~120 papers

The user asked on 2026-09-09 to be reminded of this after Phase 1. Per C-001 the
corpus was seeded at 43 papers so ingestion work could start immediately, on the
commitment that it reaches ~120 **before the Phase 2 baseline is measured**.
New papers join the **dev** side only — the holdout is frozen once and never extended.
This is a Phase 2 entry gate, not a suggestion: a ~15-paper holdout cannot support
the Phase 6 headline number.

---

## Phase 2 — Naive baseline and eval harness

**Status:** NOT STARTED

**Entry gate:** corpus at ~120 papers (C-001). Do not measure the baseline on 43.

**CHECKPOINT 4 lands here:** the user hand-labels 60 questions with supporting spans
across the five types. Claude does not generate them.

**Exit criteria:** baseline numbers recorded in `docs/reports/phase-2.md` and committed.
Eval runs by one command. This phase produces the number everything else is measured
against — it is hard-gated and must not be shortcut.

---

## Phase 3 — Retrieval upgrades, measured one at a time

**Status:** NOT STARTED

**Entry gate — CHECKPOINT 4:** no Phase 3 technique is implemented until ≥ 60
human-labelled questions exist *and* the baseline has been evaluated on them.
Auto-generated questions are a Phase 5 artifact and never substitute.

**Exit criteria:** an ablation table with a row per technique and its delta, including
any negative deltas. Overall improvement over baseline on every metric.

---

## Phase 4 — Groundedness and abstention

**Status:** NOT STARTED

**CHECKPOINT 5 lands here:** the user hand-checks a sample of answers against cited
spans. The NLI verifier does not certify itself.

**Exit criteria:** faithfulness ≥ 95% on a human-checked sample, abstention recall ≥ 85%,
and a measured false-refusal rate on answerable questions.

Per spec §6, this phase is the last thing to be cut.

---

## Phase 5 — Per-corpus adaptation

**Status:** NOT STARTED — cuttable if time runs short.

**Exit criteria:** induced pipeline recovers ≥ N% of hand-tuned performance on SemCom,
stated as a number.

---

## Phase 6 — Generalization and hardening

**Status:** NOT STARTED — cuttable if time runs short.

**Exit criteria:** three unseen corpora working, holdout numbers recorded, CI gate
demonstrated failing on a deliberately introduced regression (screenshot it).

**The SemCom holdout is opened here and nowhere earlier.**

---

## Phase 7 — Daily-use readiness

**Status:** NOT STARTED

**CHECKPOINT 6 lands here:** three real survey sessions, logged by the user in
`docs/USAGE_LOG.md`. Cannot be simulated.

**Exit criteria:** the system is trusted enough to use by default, and the failure
modes are documented rather than surprising.
