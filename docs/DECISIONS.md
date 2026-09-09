# Decision log

Every non-obvious decision, written **at the time of the decision**, not retroactively.

Format (from spec §3):

```
## D-NNN — Short title
Date: YYYY-MM-DD
Phase: N
Decision: what was chosen.
Alternatives considered: what was rejected.
Reasoning: why, with evidence where evidence exists.
Evidence: eval run date, MLflow run_id, or "none — judgement call".
Reversible? Yes/No — and what it would cost.
```

Number sequentially. Never edit a past entry to make it look better; supersede it
with a new entry that references the old one.

---

## D-000 — Spec file name kept as `SURVEY_ASSISTANT_SPEC.md`
Date: 2026-09-09
Phase: 0
Decision: Left the spec at its existing filename rather than renaming it to
`PROJECT_SPEC.md` as §0 of the spec assumes.
Alternatives considered: rename the file to match the instructions.
Reasoning: The file is the user's, was already open in their editor, and renaming
it is an unrequested change to their repo. All project docs reference the actual
name instead. Flagged to the user as open question B7.
Evidence: none — judgement call.
Reversible? Yes — a rename plus three reference updates.

---

<!-- Append new entries below. -->
## D-002 — Six checkpoints are human-gated and cannot be model-generated
Date: 2026-09-09
Phase: 0
Decision: Six artifacts are produced by the user alone and hard-block work that
depends on them: (1) the holdout split `eval/holdout_papers.txt`, (2) the frozen
extraction schema `schema/semcom.yaml`, (3) the gold comparison table
`eval/gold_table_semcom.csv`, (4) the 60 hand-labelled eval questions with spans,
(5) the Phase 4 faithfulness sample, (6) the three real usage sessions in
`docs/USAGE_LOG.md`. Claude may propose a draft only for (2). For the rest,
generating a substitute is prohibited outright. Enforcement lives in CLAUDE.md
under "Human-gated checkpoints" and as a `BLOCKED ON HUMAN` status in PHASES.md.
Alternatives considered: (i) let Claude generate provisional versions and have the
user correct them; (ii) treat these as soft preferences and proceed if the user is
slow; (iii) synthesize eval questions now and swap in human labels later.
Reasoning: each of these six is a *ground-truth* artifact — the thing every other
number is measured against. A model-generated version does not merely risk being
wrong, it is circular: the system would be graded against output from the same
family of model that produces the answers, so errors are correlated and invisible.
Two specific failure modes this prevents. First, contamination: the user knows the
SemCom literature well, so without a slice they have never opened, every final
number is unfalsifiable — and the damage is irreversible, since reading the holdout
to check it destroys it. Second, decorative ablations: every Phase 3 delta is
measured on the Phase 2 question set, so a thin or synthetic set makes the entire
ablation table a measurement of nothing, while still looking like a result.
The pull toward violating this is predictable and worth naming: building the
hierarchical index is more interesting than waiting for a human to label questions,
and a plausible-looking placeholder removes the block immediately. That is exactly
why the rule is mechanical rather than a matter of judgement in the moment. Stubs
for plumbing tests are permitted only as `*_STUB` files with a check that fails any
eval run touching them.
Alternative (iii) is not rejected in general, only rescheduled: auto-generated eval
questions are a Phase 5 deliverable, where their agreement with the user's hand
labels is itself one of the reported numbers rather than an assumption.
Evidence: none — judgement call, and a direct instruction from the user
(2026-09-09). Consistent with spec §6, which lists "my own expertise papering over
wrong answers" and "auto-eval quietly diverging from truth" as standing risks.
Reversible? No, in the direction that matters. The gates can be relaxed at any
time, but a holdout that has been read cannot be un-read and an ablation table
built on synthetic labels cannot be retroactively validated. Treat as permanent.

---

## D-001 — uv as package manager; dependencies added per phase
Date: 2026-09-09
Phase: 0
Decision: uv, with `requires-python = ">=3.11,<3.12"` per spec §4. Phase 0 pins only
what Phase 0 uses (pydantic, psycopg, pyyaml, dotenv); each later phase adds its own
dependencies when first imported, not speculatively.
Alternatives considered: poetry (spec allows either); pip + requirements.txt.
Reasoning: spec offers uv or poetry and expresses no preference. uv resolves and
locks fast enough that the install step never discourages a clean rebuild, which
matters for the Phase 6 reproducibility requirement. The per-phase dependency rule
is the more consequential half: a torch/sentence-transformers/mlflow block installed
now would sit unused for a week and make the Phase 3 embedding-model comparison
harder to attribute, since the lockfile would not say when each thing arrived.
Evidence: none — judgement call.
Reversible? Yes — pyproject is compatible; switching to poetry costs a lockfile regen.

## D-003 — Spans are character offsets into a paragraph, not sentence ids
Date: 2026-09-09
Phase: 0
Decision: A citable span is `(paragraph_id, char_start, char_end)` over
`paragraphs.text`. Table cells cite `(table_id, grid coordinates)` instead.
Alternatives considered: (i) sentence-id references into a pre-segmented sentence
table; (ii) chunk-id references, where a citation points at whatever retrieval unit
was used.
Reasoning: the spec requires span-level citation on every sentence, NLI verification
of each sentence against its cited span, and a Phase 7 UI that opens the PDF at the
right location — all three need a range that is finer than a retrieval unit and
stable across pipeline changes. (ii) is rejected outright: chunking changes eight
times in Phase 3, so citations anchored to chunks would silently repoint whenever
chunk size changed, and no Phase 2 result would remain comparable to a Phase 3 one.
(i) is rejected because sentence segmentation is itself an error source on academic
text (citations, abbreviations, inline math), and baking it into the citation key
makes a segmenter bug retroactively corrupt stored citations. Character offsets are
the invariant the parser produces directly.
Evidence: none — judgement call, made before any code depends on it.
Reversible? Expensive. Every stored claim, eval label, and verification result keys
off this. Changing it after the user hand-labels 60 questions with spans
(CHECKPOINT 4) would invalidate those labels, which is precisely the artifact that
cannot be regenerated. Treat as fixed from here.

## D-004 — Holdout enforced by a view plus a CI check, not by discipline
Date: 2026-09-09
Phase: 0
Decision: Two mechanical guards. (1) `v_dev_papers` in the schema: every retrieval
and eval path before Phase 6 selects from that view, never from `papers` directly,
so a holdout row cannot enter a result set through a forgotten WHERE clause.
(2) A CI check (task 0.6b) that fails any eval run whose retrieved paper ids
intersect `eval/holdout_papers.txt`.
Alternatives considered: (i) a `WHERE split = 'dev'` convention applied by hand in
each query; (ii) two physically separate databases; (iii) trusting the rule as
written in CLAUDE.md.
Reasoning: CLAUDE.md already says this is "enforced mechanically, not by
discipline", and (iii) is the thing that phrase rules out. (i) fails in the way
conventions fail — the omission that leaks the holdout looks exactly like every
correct query, and nothing surfaces it. The view makes the safe path the default
path and the unsafe one require naming `papers` explicitly, which is greppable in
review. (ii) is stronger still and was tempting, but it doubles ingestion and
config surface for the whole project to buy safety on one Phase 6 transition, and
it makes the Phase 6 holdout evaluation a migration rather than a flag flip.
Belt-and-braces via the CI check covers the residual risk that someone bypasses
the view. Note the asymmetry that justifies paying for two guards: the cost of
over-enforcing is mild inconvenience, the cost of under-enforcing is an
unfalsifiable headline number discovered too late to fix.
Evidence: none — judgement call. Implements spec §5 Phase 0 and §6's contamination risk.
Reversible? Yes as machinery; the property it protects is not. A holdout that has
been read cannot be un-read.

---
