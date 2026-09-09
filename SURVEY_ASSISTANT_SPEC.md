# Survey Assistant — Project Specification & Claude Code Bootstrap

> **How to use this file.** Create an empty repo, drop this file in as `PROJECT_SPEC.md`, open Claude Code in that directory, and paste the block in §0 as your first message. Everything after §0 is the spec Claude Code will read and work from.

---

## §0 — PASTE THIS INTO CLAUDE CODE AS YOUR FIRST MESSAGE

```
Read PROJECT_SPEC.md in full before doing anything else.

You are helping me build a corpus-adaptive research QA system over academic papers.
I will use it for real literature surveys, not as a demo. Read the spec's goals,
non-goals, success criteria, and working agreement carefully.

Before writing any code, do these four things and stop for my review:

1. Restate the project in 10 lines: what it does, what it explicitly does not do,
   and the measurable definition of done.
2. List every assumption you are making that the spec does not settle, and mark
   each as (a) you'll pick a default, or (b) you need my answer.
3. Propose the repo structure and the tech stack, flagging any place you disagree
   with the spec's stack choices and why.
4. Propose the Phase 0 task list only. Do not plan later phases yet.

Then create these files and nothing else:
  - CLAUDE.md          (working agreement, distilled from §2 of the spec)
  - docs/DECISIONS.md  (decision log, format in §3)
  - docs/PROBLEMS.md   (problem log, format in §3)
  - docs/CHANGELOG.md  (plan-change log, format in §3)
  - docs/PHASES.md     (phase tracker, one section per phase, status flags)

Do not start Phase 1 until I say so. Do not write ingestion code yet.

Standing rules for this entire project:
- Every non-obvious decision gets an entry in docs/DECISIONS.md, written at the
  time of the decision, not retroactively.
- Every bug that costs more than 15 minutes gets an entry in docs/PROBLEMS.md
  including the wrong hypothesis I or you held first.
- Any deviation from the spec gets an entry in docs/CHANGELOG.md before it is
  implemented, not after.
- No retrieval or generation change is merged without an eval run before and
  after, with the delta recorded.
- Ask me before expanding scope. Never silently add a feature.
```

---

## §1 — What this is

A question-answering system over a corpus of academic papers I upload (60–120 at a time). I ask questions; it answers with a citation on every claim, and refuses when the corpus does not contain the answer. It adapts itself to whatever domain the corpus is from.

**Primary user: me.** Single-user, self-hosted. No accounts, no billing, no multi-tenancy beyond keeping separate corpora isolated.

**Primary use: my own survey papers.** By the end I must be able to upload a fresh corpus on a new topic and rely on the answers well enough to cite from them after a quick span check.

### Goals

- Cross-paper QA with span-level citations on every sentence.
- Verified groundedness: a post-generation check that each cited span actually supports the sentence.
- Explicit refusal when retrieval is insufficient.
- Structured extraction of per-paper fields (method, datasets, metrics, reported numbers, limitations) with "not reported" as a first-class value.
- Comparison tables across a chosen subset of papers and fields, every cell grounded or abstained.
- Contradiction surfacing where two papers disagree on the same setup.
- Per-corpus adaptation so a new domain works without me hand-configuring it.

### Non-goals (do not build these)

- Writing survey prose. The system produces answers, tables, and citations. I write the paper.
- Figure or diagram understanding.
- Multi-user, auth, billing, sharing.
- Multilingual corpora.
- Fine-tuning a generator model.
- A polished frontend. Functional UI only.

### Definition of done

All of the following must be true:

| # | Criterion |
|---|---|
| 1 | Naive RAG baseline exists with recorded numbers on the SemCom eval set |
| 2 | Final system beats that baseline on every reported metric, with a per-technique ablation table |
| 3 | Claim-level faithfulness ≥ 95% (cited span entails the sentence, human-checked on a sample) |
| 4 | Abstention recall ≥ 85% on the unanswerable question set |
| 5 | Numeric extraction accuracy measured separately and reported |
| 6 | A fresh corpus from an unfamiliar domain runs end to end with no code changes |
| 7 | Ingest + adapt of 100 papers completes in under 20 minutes, cost per corpus known |
| 8 | Eval suite runs in CI and blocks merges on regression |
| 9 | I have used it for real survey work for at least three sessions and logged what broke |

---

## §2 — Working agreement with Claude Code

**Scope discipline.** The non-goals list is binding. Propose, never assume.

**Measure before and after.** No retrieval, chunking, prompt, or generation change ships without an eval run on both sides and the delta written down. If a change does not help, it is reverted and the negative result is recorded. Negative results are project output, not failures.

**Baseline first, always.** Within any phase, the simplest version that runs end to end comes before the sophisticated one.

**Explain before implementing.** For any non-trivial component, state the approach and the alternative you rejected in two or three sentences, then implement. This goes in DECISIONS.md.

**No hidden frameworks.** I must be able to explain every retrieval hop in an interview. Do not introduce an abstraction that buries the pipeline. Prefer explicit code over framework magic.

**Small commits, real messages.** One logical change per commit. Message states what changed and the eval delta if any.

**Ask when the spec is silent.** Do not invent requirements.

**Speed.** I am relying on you for the coding. Move fast on plumbing, parsing, harness, CI, dashboards, UI. Slow down and involve me on: the extraction schema, eval question labelling, reranker training-pair construction, routing logic, and any debugging where retrieval returns something wrong.

---

## §3 — Documentation protocol

Three logs, appended to continuously. These are as important as the code.

### docs/DECISIONS.md

```
## D-007 — Parent-document retrieval granularity
Date: YYYY-MM-DD
Phase: 3
Decision: Embed paragraph-level units, return enclosing subsection to generator.
Alternatives considered: fixed 512-token chunks; whole-section embedding.
Reasoning: paragraph embeddings retrieve precisely; sections generate better.
Section-level embeddings diluted the signal in a quick test (recall@10 0.61 vs 0.74).
Evidence: eval run 2026-xx-xx, logged in MLflow as run_id ...
Reversible? Yes — retrieval granularity is config, not schema.
```

### docs/PROBLEMS.md

```
## P-004 — Numbers extracted from wrong table
Date: YYYY-MM-DD
Phase: 2
Symptom: BLEU values attributed to the wrong SNR condition in 6/20 sampled papers.
First hypothesis (WRONG): table extraction was dropping rows.
Actual cause: multi-row headers flattened, so column-to-condition mapping was lost.
Fix: preserve header hierarchy; index table description separately from serialized table.
Cost: 3 hours.
Prevention: added 8 table-dependent questions to the eval set.
```

Recording the wrong hypothesis is mandatory. That is the part with value in it.

### docs/CHANGELOG.md

```
## C-002 — Dropped citation-graph expansion from Phase 3 to Phase 5
Date: YYYY-MM-DD
Original plan: graph traversal as part of core retrieval.
Change: deferred; hybrid + reranker already hit the phase exit criteria.
Trigger: Phase 3 ran 2 days long; graph gain estimated small for lookup-type queries.
Impact: lineage questions stay unsupported until Phase 5.
```

### Per-phase report

Each phase closes with `docs/reports/phase-N.md`: what was built, eval numbers before and after, ablation deltas, what surprised me, what carries into the next phase.

---

## §4 — Stack

- **Python 3.11**, uv or poetry.
- **Postgres + pgvector** — chunks, claims, citation edges, and embeddings in one joinable store. Not a hosted vector DB.
- **BM25** via Postgres full-text search, or a local rank_bm25 index if FTS proves inadequate. Decide in Phase 2 with a measurement.
- **Embeddings**: start with a strong open sentence-transformer; benchmark two alternatives in Phase 3 and record the comparison.
- **Reranker**: cross-encoder from sentence-transformers, LoRA adapter per corpus via PEFT.
- **NLI verifier**: small entailment model, local.
- **Generator**: an API model. Config-swappable, never hardcoded.
- **Parsing**: GROBID or equivalent for structure and references; a dedicated table extractor for tables. Compare two on 20 papers in Phase 1, record the winner.
- **MLflow** for experiment tracking.
- **FastAPI** backend, minimal React or plain HTML frontend.
- **Docker Compose**, GitHub Actions for CI eval gating.

Deviations allowed with a DECISIONS.md entry.

---

## §5 — Phases

Day counts assume heavy Claude Code use. Each phase has hard exit criteria; do not proceed without meeting them.

### Phase 0 — Scope lock and skeleton (Day 1)

- Repo, docs skeleton, CLAUDE.md, Docker Compose with Postgres up.
- **Freeze the SemCom corpus**: ~120 papers. Split 2/3 development, 1/3 holdout. The holdout is not opened, read, or tuned against until Phase 6.
- **Freeze the extraction schema** for SemCom: task, architecture, dataset, channel model, SNR range, metrics, reported values, limitations. Written to `schema/semcom.yaml` with a date.
- **Freeze the gold comparison table** from my existing survey as `eval/gold_table_semcom.csv`.
- Write the non-goals list into CLAUDE.md verbatim.

*Exit:* holdout split committed and untouchable; schema and gold table frozen; `docker compose up` works.

### Phase 1 — Ingestion and corpus store (Days 2–4)

- PDF/arXiv source → structured parse: title, abstract, section hierarchy, paragraphs, tables, reference list.
- Citation edges extracted into a graph table.
- Section-aware storage, no chunking decisions baked into the parser.
- Async job pipeline: queue, progress, per-paper failure quarantine, resumable.
- Parser bake-off on 20 papers, winner recorded.

*Exit:* 120 papers ingested, <5% hard parse failures, failures inspectable, tables preserved as tables, re-running ingestion is idempotent.

### Phase 2 — Naive baseline and eval harness (Days 5–7)

This phase produces the number everything else is measured against. Do not skip or shortcut it.

- Naive RAG: fixed 512-token flat chunks, dense-only, top-k=5, single generation call, no citations enforced.
- **Eval set v1: 60 questions, hand-labelled by me**, with supporting spans, across five types — single-paper lookup, cross-paper comparison, numeric/table extraction, contradiction, unanswerable.
- Harness computing: retrieval recall@k and nDCG@10, answer accuracy vs my labels, citation faithfulness, abstention rate. Reported per question type.
- MLflow logging every run with full config.

*Exit:* baseline numbers recorded in `docs/reports/phase-2.md` and committed. Eval runs by one command.

### Phase 3 — Retrieval upgrades, measured one at a time (Days 8–12)

Add in this order. Run the eval after each. Record the delta. Revert anything that does not help.

1. Section-aware structural chunking (no cross-section splits)
2. Contextual chunk augmentation (prepend paper + section + topic header before embedding)
3. Small-to-big / parent-document retrieval (embed paragraphs, return enclosing subsection)
4. Hybrid BM25 + dense with reciprocal rank fusion
5. Hierarchical summary nodes (paper-level and section-level summaries as retrievable units)
6. Table handling: structured extraction, NL description indexed, real table passed to generator
7. Claim-level store for schema fields, queried directly for numeric lookups
8. Cross-encoder reranking (off-the-shelf first, adapter comes in Phase 5)

Eval set grows to 150 questions during this phase.

*Exit:* an ablation table with a row per technique and its delta, including any negative deltas. Overall improvement over baseline on every metric.

### Phase 4 — Groundedness and abstention (Days 13–15)

This is the phase that makes the system trustworthy enough to actually use.

- Query router: lookup / comparison / numeric / lineage / out-of-scope. Out-of-scope refuses without retrieval.
- Query decomposition for multi-hop, with sub-queries logged separately so planning is evaluable apart from retrieval.
- Context sufficiency grading: sufficient → generate; insufficient → one reformulated retry; unanswerable → refuse.
- Constrained generation: mandatory span citation per sentence.
- NLI verification pass: each sentence checked against its cited span. Unentailed sentences dropped; too many drops → refuse the answer.
- Unanswerable question set expanded to 30.

*Exit:* faithfulness ≥ 95% on a human-checked sample, abstention recall ≥ 85%, and a measured false-refusal rate on answerable questions.

### Phase 5 — Per-corpus adaptation (Days 16–20)

Replace the hardcoded SemCom pieces with induced ones, and measure what is lost.

- **Schema induction**: sample the corpus, infer its reporting dimensions. Compare induced schema against my frozen SemCom schema — field overlap is a reportable number.
- **Auto-generated eval set**: synthesize QA pairs with span grounding, filter by verifying the answer is recoverable from the cited span. Measure agreement between auto-eval and my hand labels on SemCom.
- **Reranker LoRA adapter**: mine positives and hard negatives from the corpus using citation edges and section co-occurrence. Train per corpus. Report the delta over the off-the-shelf reranker.
- **Fitted retrieval config**: chunk size, top-k, fusion weights, routing thresholds swept per corpus against the auto-eval.
- Per-corpus isolation: own index, schema, adapter checkpoint, eval set, version pin.

*Exit:* the headline result — induced pipeline recovers ≥ N% of hand-tuned performance on SemCom, stated as a number.

### Phase 6 — Generalization and hardening (Days 21–24)

- Run cold on **three corpora from unrelated fields**, 60–100 papers each. No code changes permitted. Report per-corpus numbers and a failure analysis of where and why it degrades.
- **Open the SemCom holdout** and evaluate on it. This is the honest number.
- Versioned indexes pinned to code + embedding-model version; any past result reproducible.
- Eval suite in CI, regression beyond threshold fails the build.
- Per-query tracing: sub-queries, docs retrieved, scores, tokens, latency, cost. Dashboard with per-corpus ingest time, adapter training time, eval scores, cost.
- Deployed in containers.

*Exit:* three unseen corpora working, holdout numbers recorded, CI gate demonstrated failing on a deliberately introduced regression (screenshot it).

### Phase 7 — Daily-use readiness (Days 25–28)

The phase that makes it a tool instead of a project.

- Functional chat UI with citations rendered as clickable spans opening the source PDF at the right location.
- Comparison table view over selected papers and fields, with abstained cells visibly marked.
- Contradiction view.
- Export: cited answers and tables to markdown for my notes.
- **Three real sessions of survey work**, logged in `docs/USAGE_LOG.md`: what I asked, what it got wrong, what I had to verify by hand.
- Final writeup: architecture, full ablation table, generalization results, error analysis, and what I would do next.

*Exit:* I trust it enough to use it by default, and the failure modes are documented rather than surprising.

---

## §6 — Standing risks

| Risk | Mitigation |
|---|---|
| Scope creep into survey writing | Non-goals in CLAUDE.md; changes require CHANGELOG entry |
| My own expertise papering over wrong answers | Always label against spans, never against memory |
| Building clever retrieval before the baseline | Phase 2 exit criteria are hard-gated |
| Auto-eval quietly diverging from truth | Measure auto-eval vs human agreement explicitly in Phase 5 |
| Generalization half-built when time runs out | Phases 5–6 are cuttable; Phases 0–4 alone are a complete project |

If time runs short, cut Phase 5 and 6 generalization before cutting Phase 4 groundedness. A single-corpus system that never hallucinates beats a general one that does.
