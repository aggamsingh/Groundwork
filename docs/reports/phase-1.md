# Phase 1 — Ingestion and corpus store

**Status: COMPLETE** · opened 2026-09-13 · closed 2026-09-13

## Exit criteria

| Criterion | Status | Evidence |
|---|---|---|
| 42 papers ingested (120 amended by C-001) | met | 42/42 `ok`, 0 quarantined |
| <5% hard parse failures | met | 0% |
| Failures inspectable | met | `ingest_status` + `failure_reason` queryable in SQL |
| Tables preserved as tables | met | 47 tables, header kept separate from body |
| Re-running ingestion is idempotent | met | second run: 42 `unchanged` in **3.8s** |

Verified by `scripts/phase1_exit_check.py` rather than by eye — a criterion
confirmed by looking at output is confirmed once, by someone who wanted it to pass.

## What was built

- `survey.ingest.model` — parser-agnostic `ParsedPaper` types. Every parser emits
  these, so the bake-off compares parsers rather than storage code.
- `pymupdf_parser` — the baseline. Headings by font size, paragraph assembly,
  de-hyphenation, reference splitting.
- `grobid_parser` — TEI adapter for the challenger, in a `bakeoff` compose profile.
- `hybrid_parser` — the adopted default (D-014).
- `tables` — table extraction tuned for precision (D-013).
- `citations` — citation graph resolution, identity-first (D-015).
- `store` — idempotent persistence with per-paper quarantine.
- `scripts/ingest.py`, `scripts/parser_report.py`, `scripts/phase1_exit_check.py`.

## The bake-off — no winner

Both parsers over the same 20 papers. The hybrid column is the adopted default.

| metric | grobid | **hybrid** | pymupdf |
|---|---|---|---|
| hard failures | 0% | **0%** | 0% |
| plausible title | 95% | **95%** | 100% |
| abstract | 100% | **100%** | 15% |
| year | 35% | **100%** | 100% |
| doi | 75% | **75%** | 75% |
| structured refs | 100% | **100%** | 0% |
| ≥3 sections | 100% | **100%** | 100% |
| ≥1 table | 0% | **40%** | 40% |
| median chars | 34,513 | **34,513** | 42,170 |
| median seconds | 2.64 | **12.52** | 6.76 |

GROBID cannot extract tables at all — the CRF image has no table model — and
"tables preserved as tables" is an exit criterion, so a GROBID-only pipeline
could not have closed this phase. PyMuPDF alone gives up structured references,
which is what makes citation resolution identity-based instead of inferential.
Recorded as C-004, since the spec expected a single winner.

Two numbers in that table are weaker than they look, and are reported as such:
`venue` is 0% for **both** parsers, which means the extraction is broken rather
than the data absent; and `plausible title` measures shape, not correctness —
nobody has hand-labelled the true title of 42 papers.

The hybrid is the slowest option, because papers where GROBID reports no year are
parsed twice. See C-005 for why that matters later.

## Corpus after ingestion

| | |
|---|---|
| papers | 42 (`ok`), 0 quarantined |
| sections | 978 |
| paragraphs | 3,798 |
| tables | 47 across 18 papers |
| citation edges | 3,161 stored, **123 resolved in-corpus** (7 doi, 21 arXiv, 95 title) |
| abstracts | 41/42 (98%) — was 7/42 (17%) on the baseline |
| years | 42/42 |
| DOIs | 29/42 |
| split | 28 dev / 14 holdout, 0 holdout papers visible in `v_dev_papers` |

## What surprised me

**Every significant bug was found by looking at output, not by a test failing.**
The tests passed throughout. The quarantine bug, the wrong citation links and the
resolution regression were all found by sampling what was actually in the
database. That is the transferable lesson of this phase.

**A plausible aggregate hid a broken component.** Citation resolution reported
216 links, which looked reasonable, and a third of them pointed at the wrong
paper (P-003). A resolution *rate* is not a correctness measure. Had it shipped,
Phase 5 would have mined reranker training pairs from a graph where one edge in
three was fabricated, and it would have surfaced weeks later as unexplained
reranker underperformance.

**Word order is the whole signal in a single-topic corpus.** Bag-of-words
matching cannot distinguish "Robust Semantic Communication Driven by Knowledge
Graph" from "Cognitive semantic communication systems driven by knowledge
graph". Raising the similarity threshold would not have helped — the false
matches scored 1.0. This is worth carrying into Phase 3: any retrieval technique
scored on token overlap will have the same blind spot on this corpus.

**Twice in one phase, a dead service was mistaken for a slow-starting one**
(P-001 Docker, P-004 GROBID). Both times the fix was seconds away once `docker
ps -a` and `docker logs` were actually run. This is now written down as a pattern
rather than two unrelated incidents.

**The exit check caught a criterion I had written wrong.** It flagged 3 of 48
tables as structurally thin. Two turned out to be genuine captioned tables with a
header and one data row — the criterion demanding two body rows was measuring the
wrong thing. The third was diagram debris. Had I only tightened the extractor, I
would have discarded real tables; had I only relaxed the criterion, I would have
kept the debris. Inspecting the three rather than picking a side is what
separated them, and the discriminator — every genuine single-row table here is
captioned, the debris is not — was only visible by looking.

**Adding a better parser made a downstream number worse.** The hybrid improved
every parsing metric and dropped resolved citations from 101 to 20, because
GROBID's raw reference string reads differently from the baseline's (D-015). An
upstream improvement can degrade a downstream consumer that was tuned to the old
output — the reason the working agreement measures before and after.

## Deviations from spec

| | |
|---|---|
| C-004 | Bake-off records a hybrid, not a winner |
| C-005 | No async job queue; progress, quarantine and resumability without one |

## Problems logged

| | |
|---|---|
| P-002 | A quarantined paper could never be retried |
| P-003 | A third of resolved citation edges pointed at the wrong paper |
| P-004 | GROBID crashed on a JDK cgroup v2 probe under WSL2 |

## Numbers

Still no eval numbers. Phase 1 produces no retrieval or generation, so there is
nothing to measure against. The first number in this project remains the Phase 2
baseline.

## Carried into Phase 2

1. **The corpus must reach ~120 papers before the baseline is measured** (C-001).
   This is a hard Phase 2 entry gate, not a preference.
2. **Ingestion is too slow for the target corpus size** (C-005). A full run is
   ~16s per paper, so 100 papers is ~28 minutes against Definition of Done #7's
   20-minute budget. Re-runs are now near-instant (unchanged papers are skipped
   before parsing, 42 papers in 3.8s), but that does not help a first ingest,
   which is what the criterion measures. Parallelism or the deferred queue is
   needed before it can be claimed.
3. `venue` extraction is broken in both parsers and needs fixing before it is
   used as a comparison-table column.
4. Paragraph counts dropped from 5,121 (baseline) to 3,798 (hybrid). GROBID
   filters running headers and figure captions the baseline swept in — likely an
   improvement in quality, but it is unverified and worth a spot check before
   chunking decisions are made on top of it.
5. Table extraction is precision-tuned at 43% coverage. If Phase 2 numeric
   questions turn out to need the missing tables, that trade is the first thing
   to revisit.
