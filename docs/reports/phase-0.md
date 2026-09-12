# Phase 0 — Scope lock and skeleton

**Status: COMPLETE** · opened 2026-09-09 · closed 2026-09-13

## Exit criteria

Amended by C-003; the gold table moved to a Phase 2 entry gate.

| Criterion | Status | Evidence |
|---|---|---|
| Holdout split committed and untouchable | met | `eval/holdout_papers.txt`, frozen 2026-09-09, 14/42. Two guards: `v_dev_papers` view and `assert_no_holdout` |
| Extraction schema frozen, dated | met | `schema/semcom.yaml` v2, frozen 2026-09-13, 16 fields |
| `docker compose up` works | met | Postgres 16 + pgvector 0.8.6, 7 tables, view queryable, vector ops verified |
| ~~Gold comparison table frozen~~ | deferred | C-003 — Phase 2 entry gate |

## What was built

- Repo skeleton: one module per retrieval hop, so no abstraction buries the pipeline.
- `src/survey/db/schema.sql` — 7 tables. Structure only; no chunking baked in.
  Tables keep header hierarchy in a `grid` jsonb so column-to-condition mapping
  survives, which is the failure the spec's own P-004 example describes.
- `survey.evalharness.holdout` — the leak guard. Refuses missing, empty and
  `*_STUB` holdout files.
- `survey.extraction.schema` — loader with a frozen gate; a draft schema cannot
  be extracted against.
- `scripts/build_manifest.py`, `scripts/check_env.py`, `scripts/init_db.py`.
- 26 tests, ruff clean, `uv.lock` pinned on Python 3.11.9.

## Corpus

50 files → **42 unique papers**, 28 development / 14 holdout.

Three collapses, in increasing order of subtlety: 6 byte-identical duplicate
pairs; 1 same-title pair differing by 156 bytes of embedded metadata (D-006);
and 1 arXiv preprint of a paper already present in its published IEEE form
(D-007), found only by extracting first-page text.

That last one is the one that mattered. Had the preprint and the published
version landed on opposite sides of the split, the system would have been tuned
on the exact content the holdout exists to test, and nothing would have surfaced
it. The holdout would have been silently worthless from day one.

## What surprised me

**The user's vocabulary beat the induced one.** The taxonomy inferred from
abstracts (D-009) was superseded within four days by the user's own review
matrix (D-011), which carried four comparability axes the induction missed
entirely: encoder provenance, transmission scheme, channel-aware training, and
failure mode. The lesson is not that induction is useless — it is that induction
from abstracts, over a corpus where 6 of 28 PDFs were not even text-extractable,
is a weak prior next to someone who has read the papers. Worth remembering in
Phase 5, where schema induction is a deliverable and will be measured against
exactly this frozen schema.

**"BLEU" is not a number.** Text SemCom papers plot BLEU-1 through BLEU-4 on one
figure. Without recording n-gram order, the contradiction detector would compare
across orders, see a large gap, and report a conflict between two papers that
agree — manufacturing the confident error this project exists to prevent. Caught
at schema design (D-010) rather than at Phase 4, where it would have presented
as a mysterious excess of contradictions.

**A flat contradiction threshold is wrong in both directions.** 10% relative on
a BLEU of 0.90 tolerates a 0.09 gap; 10% of 30 dB PSNR is 3 dB. Relative
tolerance only means something for ratio-scale quantities. Replaced with
per-metric absolute tolerances.

**The environment cost more than the code.** P-001 — Docker installed fine but
the engine never started, because Docker Desktop on Windows Home requires WSL2
and WSL was absent. Two wrong hypotheses first. Then, after WSL was installed
and the machine rebooted, the engine wedged on first boot and needed a full
teardown (`wsl --shutdown`) before it would answer. Both are now caught in
seconds by `scripts/check_env.py` instead of a 4-minute silent timeout.

## Deviations from spec

| | |
|---|---|
| C-001 | Corpus seeded at 42, not ~120. Grows before Phase 2; new papers join the **dev** side only. |
| C-002 | Gold table is a hand-built subset — the survey it was to be exported from is not yet written. |
| C-003 | Gold table deferred from Phase 0 exit to a Phase 2 entry gate. |

## Numbers

No eval numbers. Phase 0 produces no retrieval or generation, so there is nothing
to measure. The first number in this project is the Phase 2 baseline.

## Carried into Phase 1

1. **6 of 28 dev PDFs are not text-extractable** by a naive stream decoder —
   embedded font encodings. This is a concrete requirement for the parser
   bake-off, not an incidental annoyance: a parser that fails on 21% of the
   corpus fails the phase.
2. `year` must come from parsed documents, never PDF creation dates — several
   are download dates (one 2013 paper reports 2024).
3. `survey-mini` is decidable from page count, which the parser has for free.
4. DOIs, once extracted, go in a **separate column**; `external_id` stays the
   slug (D-005), because eval labels will key off it.
5. The corpus-growth reminder to ~120 papers is owed at Phase 1 close.

## Open questions

| ID | Question | Blocks |
|---|---|---|
| Q-B3 | Which generator API is available? | Phase 2 |
| Q-B4 | GPU and VRAM? | Phase 4 NLI verifier, Phase 5 LoRA adapter |
| Q-B7 | Rename spec to `PROJECT_SPEC.md`? | cosmetic |
