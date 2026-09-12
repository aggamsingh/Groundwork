# Phase tracker

Status flags: `NOT STARTED` · `IN PROGRESS` · `BLOCKED` · **`BLOCKED ON HUMAN`** · `COMPLETE`

`BLOCKED ON HUMAN` means the work is waiting on one of the six human-gated
checkpoints in CLAUDE.md. Claude does not unblock these by generating the artifact.

A phase moves to `COMPLETE` only when every exit criterion is met and
`docs/reports/phase-N.md` is committed. Do not proceed without meeting exit criteria.

| Phase | Title | Days | Status |
|---|---|---|---|
| 0 | Scope lock and skeleton | 1 | **COMPLETE** (2026-09-13) |
| 1 | Ingestion and corpus store | 2–4 | IN PROGRESS |
| 2 | Naive baseline and eval harness | 5–7 | NOT STARTED |
| 3 | Retrieval upgrades, measured one at a time | 8–12 | NOT STARTED |
| 4 | Groundedness and abstention | 13–15 | NOT STARTED |
| 5 | Per-corpus adaptation | 16–20 | NOT STARTED |
| 6 | Generalization and hardening | 21–24 | NOT STARTED |
| 7 | Daily-use readiness | 25–28 | NOT STARTED |

---

## Phase 0 — Scope lock and skeleton

**Status:** COMPLETE — opened 2026-09-09, closed 2026-09-13.
Report: `docs/reports/phase-0.md`.

**Exit criteria (amended by C-003):** holdout split committed and untouchable;
schema frozen; `docker compose up` works. The gold table moved to a Phase 2
entry gate.

| # | Task | Status | Blocked by |
|---|---|---|---|
| 0.1 | `CLAUDE.md` + four docs logs | COMPLETE | — |
| 0.2 | `pyproject.toml` (uv), `.gitignore`, `.env.example`, package skeleton — **verified: uv.lock resolves on Python 3.11.9, 23 tests pass, ruff clean** | COMPLETE | — |
| 0.3 | `docker compose up` verified: Postgres 16, pgvector 0.8.6, 7 tables, view queryable | COMPLETE | — |
| 0.4 | `db/schema.sql` — applied and verified against live Postgres | COMPLETE | — |
| 0.5 | Seed corpus: 42 unique papers copied, `corpus/manifest.csv` committed (50 files → 42, see D-006/D-007) | COMPLETE | — |
| 0.6a | Holdout split — **FROZEN 2026-09-09**, 14 holdout / 28 dev, chosen by the user | COMPLETE | — |
| 0.6b | CI leak guard `survey.evalharness.holdout` + 12 unit tests, loading the frozen split | COMPLETE | — |
| 0.7 | `schema/semcom.yaml` v2 — **FROZEN 2026-09-13** on the user's vocabulary (D-011) | COMPLETE | — |
| ~~0.8~~ | Gold table — **deferred to a Phase 2 entry gate (C-003)**. Not a Phase 0 blocker. | DEFERRED | — |
| 0.9 | DECISIONS D-001, D-002, D-003, D-004 all written 2026-09-09 | COMPLETE | — |
| 0.10 | Exit check + `docs/reports/phase-0.md` | COMPLETE | — |

### Open questions blocking Phase 0

| ID | Question | Blocks |
|---|---|---|
| ~~Q-B2~~ | ~~Gold table — does it exist?~~ **Resolved 2026-09-13: no survey written yet; a 10-paper review matrix exists. Deferred (C-003).** | — |
| Q-B3 | Which generator API is available? | Phase 2 |
| Q-B4 | GPU available, and how much VRAM? | Phase 4 / 5 architecture |
| ~~Q-B5~~ | ~~Holdout split — random or stratified?~~ **Resolved: the user chooses the papers. Claude does not generate the split.** | — |
| Q-B6 | Schema — does the user want a Claude draft to edit, or write from scratch? (Either way the frozen file is theirs.) | 0.7 |
| Q-B7 | Rename spec to `PROJECT_SPEC.md`, or keep current name? | cosmetic |
| ~~Q-B8~~ | ~~Docker/uv/Python 3.11 not installed~~ **Resolved 2026-09-09: all three installed. Docker engine still blocked on WSL (P-001).** | — |

---

## Phase 1 — Ingestion and corpus store

**Status:** IN PROGRESS — started 2026-09-13.

**Carried in from Phase 0** (see `docs/reports/phase-0.md`): `year` must come from
parsed text, not PDF creation dates. DOIs go in a separate column; `external_id`
stays the slug (D-005). The "unreadable PDFs" finding was retracted — see above.

**Exit criteria:** all 42 seeded papers ingested (was 120 — see C-001), <5% hard parse failures, failures inspectable,
tables preserved as tables, re-running ingestion is idempotent.

### Tasks

Baseline first: the simplest ingest that runs end to end lands before any parser
comparison, so the bake-off is measured against something rather than debated.

| # | Task | Status |
|---|---|---|
| 1.1 | Parser candidates chosen and justified (D-012) | COMPLETE |
| 1.2a | PyMuPDF parser + quality report over 42 papers (0% failures) | COMPLETE |
| 1.2b | Persist parsed output to Postgres | IN PROGRESS |
| 1.3 | Ingest is idempotent (re-run changes nothing) + per-paper quarantine on failure | NOT STARTED |
| 1.4 | GROBID service in docker-compose; adapter to the same storage interface | NOT STARTED |
| 1.5 | Bake-off harness: both parsers over 20 papers, scored, winner recorded | NOT STARTED |
| 1.6 | Table extraction — tables preserved as tables, header hierarchy intact | NOT STARTED |
| 1.7 | Citation edges into `citation_edges`, resolved to corpus papers where possible | NOT STARTED |
| 1.8 | Async job pipeline: queue, progress, resumable | NOT STARTED |
| 1.9 | Full run over 42 papers; failures inspectable | NOT STARTED |
| 1.10 | Corpus-growth reminder to the user (~120 papers) | NOT STARTED |
| 1.11 | Exit check + `docs/reports/phase-1.md` | NOT STARTED |

**~~The 21% problem~~ — retracted 2026-09-13.** The naive decoder failed on 11 of
42, but PyMuPDF reads all 42 cleanly. The finding measured my throwaway
extractor, not the corpus. No parser requirement follows from it.

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

### Entry gates — all three are ground truth for the same baseline

1. **Corpus at ~120 papers** (C-001). Do not measure the baseline on 42.
2. **CHECKPOINT 3 — `eval/gold_table_semcom.csv`** (C-003, deferred from Phase 0).
   Rows must come from the DEVELOPMENT set only; a gold row for a holdout paper
   means tuning against the holdout. Never synthesized.
3. **CHECKPOINT 4 — 60 hand-labelled questions** with supporting spans across the
   five types. Claude does not generate them.

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
