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

## D-005 — Paper ids are filename-derived slugs, not arXiv ids or DOIs
Date: 2026-09-09
Phase: 0
Decision: `external_id` is a slug derived from the paper's filename — lowercased,
leading "12. " numbering stripped, non-alphanumerics collapsed to hyphens, capped
at 80 characters. `corpus/provenance.json` records which source file(s) each id
came from. Ids are fixed from here.
Alternatives considered: (i) arXiv id or DOI, as recommended on 2026-09-09;
(ii) a content hash prefix; (iii) sequential numbering.
Reasoning: (i) was the recommendation and is still the better scheme in the
abstract — externally resolvable, stable, and it would let the Phase 7 UI link
out. It was abandoned on contact with the actual corpus: the files are named by
descriptive title, not identifier, and several are informally named
("semcom principles and challenges", "robust semcom against noise"), so
recovering a DOI for each of 43 papers means opening each PDF. That work belongs
in Phase 1, where the parser extracts title and reference metadata anyway, and
doing it by hand now would duplicate it. (ii) is stable but unreadable, which
matters because the user hand-writes these ids into `eval/holdout_papers.txt` and
into 60 eval labels — an unreadable id makes those tasks error-prone in a way
that is invisible until the labels are wrong. (iii) has the same problem and
additionally renumbers when the corpus grows to ~120, which it will (C-001).
Slugs are readable, stable under corpus growth, and derived deterministically.
Consequence accepted: ids are not externally resolvable. When Phase 1 extracts
DOIs they are stored as a *separate column*, not swapped into `external_id`,
because eval labels will already reference the slug by then (see D-003 on why
re-keying after CHECKPOINT 4 is prohibitively expensive).
Evidence: the 43-paper corpus as received, 2026-09-09.
Reversible? Cheaply now, expensively after the user writes the holdout list and
eval labels against these ids. Effectively fixed once CHECKPOINT 1 is frozen.

## D-006 — Near-duplicate PDFs collapsed by slug as well as by hash
Date: 2026-09-09
Phase: 0
Decision: Dedupe on content hash first, then on derived slug, keeping the largest
file. The 50 source files collapsed to 43 unique papers: 6 byte-identical pairs
plus one same-title pair differing by 156 bytes.
Alternatives considered: (i) hash-only dedupe, keeping both BVCS copies as
separate papers; (ii) ask the user to resolve every near-duplicate by hand.
Reasoning: the two BVCS files share a title, PDF version, and size to within
0.006%, which is the signature of the same PDF downloaded twice with differing
embedded metadata, not two versions of a paper. Under (i) that paper would be
ingested twice, and a duplicate in the corpus is not cosmetic here: it inflates
retrieval recall for its own content, can occupy two slots in a top-k, and would
let one paper appear on both sides of a dev/holdout split — quietly contaminating
the number the split exists to protect. (ii) is the right move for a genuinely
ambiguous case but this one is not ambiguous.
Evidence: sizes 2,507,216 vs 2,507,060 bytes; identical titles; both %PDF-1.5.
Reversible? Yes — `corpus/provenance.json` records every collapsed source file,
so any decision here can be revisited without going back to the source folder.

## D-007 — arXiv preprint removed where the published version is also present
Date: 2026-09-09
Phase: 0
Decision: `semantic-for-future-internet-2022` (arXiv preprint) removed; the
published version, `semantic-communications-for-future-internet-fundamentals-...`
(IEEE COMST vol. 25 no. 1, 2023), is kept. Same paper, Yang et al. Corpus is now
42 unique papers, down from 43.
Alternatives considered: (i) keep both as separate papers; (ii) keep both but
constrain them to the same side of the dev/holdout split.
Reasoning: extracted first-page text confirms identical title and author list;
the files differ because one is the preprint and one the typeset version. Under
(i) the pair could straddle the dev/holdout boundary, which would mean the system
had been tuned on the very content the holdout exists to test — silent
contamination of the one number the split protects, and undetectable after the
fact. (ii) preserves both but requires a constraint the user would have to
remember while hand-picking the split, which is exactly the kind of discipline-
based guard CLAUDE.md rules out. The published version is preferred as the
citable artifact and the one with final section numbering.
Note: the third 38-page file, `semantic-empowered-communications-2023`, was
checked at the same time and is a genuinely different paper (Lu et al.,
"Semantics-Empowered Communications"). Retained.
Evidence: first-page text extraction, 2026-09-09. Preprint header "Semantic
Communications for Future Internet: Fundamentals, Applications, and Challenges,
Wanting Yang, Hongyang Du, ..." matches the published version's header verbatim.
Reversible? Yes — the source folder is untouched and `corpus/provenance.json`
records the preprint filename against the kept paper.

## D-008 — Schema draft ships as `status: draft` and is refused by the loader
Date: 2026-09-09
Phase: 0
Decision: The proposed extraction schema lives at its real path,
`schema/semcom.yaml`, carrying `status: draft` and `frozen_date: null`.
`survey.extraction.schema.load_schema` raises `SchemaNotFrozenError` on anything
not marked `frozen` with a valid ISO date. The user freezes it by editing those
two keys.
Alternatives considered: (i) write the draft to `schema/semcom.draft.yaml` and
have the user rename it; (ii) hand the draft over in conversation and write no
file; (iii) write it to the real path with no status flag and rely on the user
remembering it is provisional.
Reasoning: (iii) is the failure this project keeps designing against — a
plausible file at the expected path that nothing distinguishes from the real
thing. Extraction against provisional field definitions is worse than no
extraction: it fills the claim store with values whose meaning silently changes
when a field is later renamed or re-typed, and every number already recorded
against them becomes wrong without any error surfacing. (i) is safe but leaves
the frozen path empty and makes the freeze a filesystem operation rather than a
statement of intent. (ii) loses the structure entirely. Putting the draft at the
real path with a mechanical gate mirrors the holdout worksheet, which worked:
the file is editable in place, and the thing that unblocks it is a deliberate
edit the user makes.
Same pattern, three checkpoints now: worksheet at the real path, guard that
fails closed, freeze by explicit edit.
Evidence: 23 unit tests pass, including one asserting the shipped draft still
refuses to load.
Reversible? Yes — the schema is the user's to rewrite entirely.

## D-009 — `task` split into `modality` + `contribution_type`; semantic noise split from `channel_model`
Date: 2026-09-09
Phase: 0
Decision: Two changes to the draft schema, both made after reading the 28
development papers (user delegated the taxonomy on 2026-09-09, "you decide from
the corpus"). (1) The single `task` enum becomes two fields, `modality` (text /
image / video / speech / multimodal / modality_agnostic) and `contribution_type`
(jscc_system / semantic_noise_robustness / knowledge_base_driven /
generative_ai_semcom / semantic_similarity_metric / knowledge_extraction /
resource_allocation / architecture_component / survey / background).
(2) `semantic_noise_model` becomes its own field rather than values inside
`channel_model`, and joins the contradiction match key.
Alternatives considered: (i) keep one flat `task` enum and allow multiple values,
as drafted; (ii) a free-text task field with clustering deferred to Phase 5.
Reasoning: the corpus falsifies (i). `robust-semcom-against-noise` is a text
paper *and* a robustness paper; `end-to-end-generative-semantic-communication-
powered-by-shared-semantic-knowledge-base` is text *and* knowledge-base-driven.
A flat enum with cardinality `many` can technically hold both, but it cannot say
which axis each value belongs to, so "papers doing the same thing" is not
expressible — and that grouping is what comparison tables and contradiction
detection are built on. Two orthogonal enums make the join condition explicit.
The second change has the same shape. Several dev papers model adversarial or
semantic noise *on top of* a physical channel (FGSM-generated semantic noise over
AWGN; knowledge-base mismatch). Folding those into `channel_model` would make two
AWGN papers look like they used different channels, suppressing real comparisons,
while leaving genuinely incomparable setups indistinguishable. Splitting the axis
and adding it to `setup_must_match` fixes both directions.
(ii) is the Phase 5 approach and is where induced schemas will land; doing it now
would leave Phase 2 with no stable grouping to evaluate against.
Evidence: first-page text of 22 of the 28 dev papers (6 use embedded font
encodings the throwaway extractor cannot decode — a Phase 1 parser requirement,
not a schema issue). Holdout papers were excluded via assert_no_holdout.
Reversible? Yes — the schema is still `draft` and the user's to rewrite.

## D-010 — Number addressability (metric_variant, channel uses) and per-metric contradiction tolerances
Date: 2026-09-09
Phase: 0
Decision: Two schema questions the user delegated ("decide using your best
judgement"). (1) `reported_values` gains `metric_variant` and
`channel_uses_per_symbol`, both added to the contradiction match key.
(2) The single `disagreement_threshold_relative: 0.10` is replaced by per-metric
absolute tolerances, with a relative default for ratio-scale quantities only.
Alternatives considered: (i) keep (metric, snr, channel, dataset, system) as the
address, as drafted; (ii) keep one relative threshold across all metrics;
(iii) defer both to Phase 4 when contradiction detection is actually built.
Reasoning on (1): "BLEU" is not a number. Text SemCom papers plot BLEU-1 through
BLEU-4 on one figure, and the orders differ by a wide margin on the same system
at the same SNR. Under (i) the contradiction detector would compare a BLEU-1 from
one paper against a BLEU-4 from another, see a large gap, and report a conflict
between two papers that agree — manufacturing exactly the kind of confident error
this project exists to prevent. `channel_uses_per_symbol` is the same problem on
the rate axis: papers trade fidelity against bandwidth, so equal-SNR scores are
not comparable at unequal channel uses.
Reasoning on (2): a flat relative threshold is wrong in both directions. BLEU and
similarity scores are bounded on [0,1] and cluster high, so 10% relative on 0.90
tolerates a 0.09 gap — enormous here, and genuine disagreements would be silently
dropped. PSNR is dB on an unbounded scale where 10% of 30 dB is 3 dB, far past
any real conflict. Relative tolerance is only meaningful for ratio-scale
quantities (latency, throughput, efficiency), so those keep it and the bounded
metrics get absolute figures.
Tolerances are set conservatively — a gap must exceed the tolerance to be called
a contradiction. The asymmetry is deliberate: a false contradiction costs the
user's attention every time the view is opened, while a missed one leaves the
underlying numbers still visible in the comparison table. This matches the
spec's general posture that abstention beats a confident error.
(iii) rejected because the schema is frozen at Phase 0 and the claim store is
built against it; adding condition axes later would invalidate every number
already extracted.
Evidence: none directly — judgement from the structure of the metrics, not from
the corpus text. Flagged as TODO(user) in the schema: the 0.02 BLEU tolerance is
the figure most worth the user's scrutiny, since it sets how often the
contradiction view fires.
Reversible? The tolerances are config and cheap to retune. The two new record
fields are not — they are part of the claim store's primary key, so adding them
after extraction runs would mean re-extracting the corpus.

## D-011 — User's review vocabulary replaces the Claude-induced taxonomy
Date: 2026-09-13
Phase: 0
Decision: `schema/semcom.yaml` is rewritten (schema_version 2) around the
controlled vocabulary from the user's own review notes: type, modality, encoder,
channel, transmission, ch_aware_train, metric_validated, failure_mode. The
taxonomy Claude induced from abstracts on 2026-09-09 (D-009: modality +
contribution_type + semantic_noise_model) is superseded. `verdict` and `status`
are moved OUT of the extraction fields into `human_only_columns`.
Alternatives considered: (i) keep the induced taxonomy and treat the notes as a
second, parallel vocabulary; (ii) merge the two enum-by-enum; (iii) adopt the
notes wholesale and drop the quantitative fields Claude added.
Reasoning: the user has read these papers; the induction had only abstracts, and
six of the 28 dev PDFs were not even text-extractable. On the evidence the user's
vocabulary is simply better, and it carries four axes the induction missed
entirely -- encoder provenance (scratch / frozen-pt / finetuned-pt / LLM),
transmission (analog / scalar-quant / vector-quant), channel-aware training, and
failure mode. Each is a comparability axis: two BLEU curves from a
channel-aware-trained model and a channel-agnostic one are not the same
measurement. (i) is the worst option -- two vocabularies for one concept
guarantees drift between what is extracted and what the gold table records,
and the gold table is the thing being measured against. (ii) was attempted and
abandoned: the user's `type` and the induced `contribution_type` overlap but cut
differently, and a merged enum would have been neither.
(iii) is rejected because the notes table is a *screening matrix* -- one row per
paper, for triage -- and cannot hold per-condition numeric results. Spec §1
requires numeric extraction, comparison tables and contradiction surfacing, so
reported_values / snr_range / metrics / the contradiction rules are retained
alongside the user's columns.
Separating verdict and status is the other substantive change. They are the
user's editorial judgements about their own argument ("we argue with it"), not
properties of the papers. Leaving them among the extraction fields would mean
scoring the system on something no extraction system can produce, which would
depress every accuracy number for no reason and mask real failures.
`metric_validated` is marked priority: critical, with a strict 0.85 abstention
threshold and its own separately reported accuracy. The user states it is the
spine of the survey's Section IV; it is also the hardest field to extract, since
papers rarely state it and it must be inferred from whether a correlation or
human study was run. Averaging it into a headline accuracy over ten easy enums
would hide failure exactly where it matters most. The asymmetry justifies the
strict threshold: a wrong `yes` propagates into the survey's central argument,
while a `not_extracted` only sends the user to read the paper -- which they would
do anyway.
Evidence: the user's controlled-vocabulary table, supplied 2026-09-13.
Reversible? Yes -- still `draft` and the user's to rewrite. But it should be
frozen before extraction runs, since the claim store keys off these fields.

## D-012 — PyMuPDF as the Phase 1 baseline parser; GROBID is the challenger
Date: 2026-09-13
Phase: 1
Decision: PyMuPDF is implemented first as the baseline parser, with GROBID added
as the challenger in task 1.4 and the two compared in 1.5. Both emit the same
`ParsedPaper` dataclasses, so the bake-off compares parsers rather than storage
code and a parser swap cannot change the database shape.
Alternatives considered: (i) start with GROBID, per spec §4 which names it first;
(ii) start with a modern layout parser (Docling/Marker); (iii) compare all three.
Reasoning: CLAUDE.md requires the simplest thing that runs end to end before the
sophisticated one, and GROBID is a Java service in a container whose failure
modes are its own. Standing it up first would mean debugging a service before
knowing what good output looks like on this corpus. PyMuPDF is a library call,
runs in 0.5s per paper, and produced measurable baseline numbers within an hour.
Those numbers are now the thing GROBID has to beat, which is the whole point --
without them the bake-off is two unmeasured options and an argument.
(iii) is deferred, not rejected: a third parser is worth adding only if GROBID
fails to clear the baseline decisively.
Evidence: baseline over all 42 papers, 2026-09-13 --
  hard failures 0/42 (0%)      |  plausible title 42/42 (100%)
  year 42/42 (100%)            |  >=1 reference 42/42 (100%)
  >=3 sections 42/42 (100%)    |  doi 29/42 (69%)
  abstract 7/42 (17%)          |  tables 0/42 (0%)
  median 68 paragraphs, 39,872 chars, 32 references, 0.50s/paper
The two weak numbers are the informative ones. Abstract detection at 17% is a
genuine baseline weakness: this corpus splits between papers with an `Abstract`
heading and IEEE-style papers running it inline as `Abstract--`, and the inline
fallback only catches some. Tables at 0% is not a weakness but an absence --
PyMuPDF sees text runs, not cells, and no table extraction was attempted. Both
are squarely what GROBID plus a dedicated table extractor exist for, so the
bake-off has two clear targets rather than a vague hope of improvement.
Note on the metrics themselves: they are proxies, not correctness. Nobody has
hand-labelled the true title of 42 papers, so "plausible title" checks shape, not
accuracy. They are valid for comparing parsers on one corpus, which is what a
bake-off needs, and no stronger claim is made for them.
Reversible? Yes. If GROBID wins, PyMuPDF stays as the fallback for papers GROBID
cannot parse, since 0% hard failures is worth keeping.

## D-013 — Table extraction tuned for precision, not recall
Date: 2026-09-13
Phase: 1
Decision: `survey.ingest.tables` filters PyMuPDF's detector aggressively: a
candidate is rejected unless it has >=2 rows, >=2 columns, >=50% non-empty cells,
and <=34% wholly empty columns, with a small-and-sparse rule to catch diagram
debris. Header row is stored separately from body rows in the `grid` jsonb.
Result: 18/42 papers (43%) have >=1 table, up from 0%.
Alternatives considered: (i) store every detected candidate and filter later;
(ii) accept only tables with a "TABLE N" caption; (iii) skip tables in the
baseline and wait for a dedicated extractor.
Reasoning: the detector fires on figure legends and boxed diagrams as well as
tables — inspection showed 2-row "tables" holding fragments of a diagram label
('UT', 'Transfo', 'rmer') split across nine mostly-empty columns. The asymmetry
decides the tuning: a missed table is visible as an absence, and the text is
still in the paragraphs, so a question about it can still be answered or abstained
on. A false table is invisible as an error — it enters the claim store looking
exactly like a real one, and numbers read out of a mis-detected grid are
fabricated rather than merely missing. Under (i) that debris reaches the claim
store and every downstream number inherits it.
(ii) was tempting and rejected: caption matching is precise but this corpus has
unlabelled tables, and requiring a caption discards real data for tidiness.
(iii) contradicts baseline-first — 43% measured beats 0% and an intention.
Header hierarchy is kept because flattening it is precisely the spec's own P-004
example: BLEU values attributed to the wrong SNR because a multi-row header was
flattened and the column-to-condition mapping was lost.
Evidence: over 42 papers, 18 with >=1 table, captions resolved on every sampled
table. Spot-check confirmed real tables with correct headers, including BVCS
Table I whose header is `[BLEU1, BLEU2, BLEU3, BLEU4, BERT Score]` — the exact
case D-010 anticipated, where treating "BLEU" as one metric would manufacture
contradictions between papers that agree.
Known limitation, now with evidence: PyMuPDF flattens multi-level headers. The
Attention paper's Table 3 header arrives as a single cell `train N d d h`,
which is the P-004 failure in miniature. This is a concrete target for the
challenger parser rather than a vague hope of improvement.
Cost: parse time rose from 0.50s to 4.36s per paper. Acceptable — 3 minutes for
the corpus, run rarely.
Reversible? Yes; thresholds are constants in one module.

## D-014 — Parser bake-off: no winner, hybrid adopted
Date: 2026-09-13
Phase: 1
Decision: Neither parser wins. The default becomes a hybrid — GROBID for header,
abstract, sections and structured references; PyMuPDF for tables and for the
publication year when GROBID reports none; PyMuPDF alone as a whole-paper
fallback when GROBID is unreachable or fails.
Alternatives considered: (i) declare GROBID the winner and accept no tables;
(ii) declare PyMuPDF the winner and accept 15% abstract coverage; (iii) add a
third parser (Docling/Marker) and try again for an outright winner.
Evidence: both parsers over the same first 20 papers, 2026-09-13 --

  metric              grobid      pymupdf
  hard failures       0/20 (0%)   0/20 (0%)
  plausible title     19/20 (95%) 20/20 (100%)
  abstract            20/20 (100%) 3/20 (15%)
  year                7/20 (35%)  20/20 (100%)
  doi                 15/20 (75%) 15/20 (75%)
  >=1 reference       20/20 (100%) 20/20 (100%)
  structured refs     20/20 (100%) 0/20 (0%)
  >=3 sections        20/20 (100%) 20/20 (100%)
  >=1 table           0/20 (0%)   8/20 (40%)
  median chars        34,513      42,170
  median seconds      2.28        6.53

Reasoning: (i) is disqualified by an exit criterion, not by preference — "tables
preserved as tables" is required to close Phase 1, and the CRF GROBID image has
no table model at all, so its 0% is structural rather than a tuning gap.
(ii) gives up structured references, which matters beyond Phase 1: P-003 showed
title-phrase matching resolves only 101 of 3,391 edges, while GROBID returns each
reference's title and DOI as fields, making resolution identity-based. The
citation graph is what Phase 5 mines for reranker training pairs.
The year difference is a difference in purpose, not quality. GROBID reports a date
only when it can attribute one, which is correct for a bibliographic tool; we
would rather have the year printed on the page than a null, which is what
PyMuPDF's cruder rule gives. So the fallback fills a gap and never overrides.
(iii) is deferred. A third parser would be worth adding if the hybrid still fell
short of the exit criteria; it does not.
Note the two places the comparison is weaker than it looks: `venue` is 0% for both
parsers, which means my extraction is wrong rather than that the data is absent,
and `plausible title` measures shape, not correctness. Neither changes the
decision, and both are recorded so the numbers are not read as stronger than they
are.
Cost: the hybrid parses each paper with both engines when GROBID finds no year,
so it is slower than either. Acceptable for a corpus of this size, run rarely.
Reversible? Yes — three parsers are registered and selectable with `--parser`.

## D-015 — Structured reference fields are stored and resolution is identity-first
Date: 2026-09-13
Phase: 1
Decision: `citation_edges` gains `ref_title`, `ref_doi`, `ref_arxiv_id`, and
`papers` gains `arxiv_id`. Resolution tries identities first — reference DOI,
then arXiv id, then exact normalised title — and falls back to phrase matching
only for parsers that supply no structured fields.
Alternatives considered: (i) keep storing `raw_reference` alone and continue
phrase-matching, as before; (ii) store the structured fields but keep matching on
the raw string.
Reasoning: this was a miss, caught by a regression rather than by design. The
first hybrid ingest dropped resolved edges from 101 to 20, because GROBID's
`raw_reference` is a re-serialisation of TEI fields and reads differently from the
baseline's raw text, so phrase matching found less. The deeper problem was that
the whole justification for depending on a GROBID container (D-014) is that it
returns each reference's title and DOI *as fields* — and `store.py` was throwing
those fields away and then approximately recovering them from a string. A DOI
match is an identity; a phrase match is an inference that P-003 showed can be
wrong one time in three.
(i) is what produced the regression. (ii) keeps the same weakness while paying
the storage cost.
arXiv normalisation strips version suffixes and category tags: GROBID returns
"arXiv:2108.09119v3[cs.CL]" where a reference may carry "arXiv:2108.09119".
v2 and v3 of a paper are the same paper for this purpose.
Evidence: to be recorded after the re-ingest completes. The number to watch is
resolved edges, which should exceed the 101 the phrase matcher managed, with
precision at least as good because identity matches cannot be coincidental.
Reversible? Yes — additive columns and an extra matching stage.

## D-016 — GROBID body extraction widened; ingestion parallelised
Date: 2026-09-13
Phase: 1 (post-close improvements)
Decision: Three changes to the hybrid pipeline.
(1) The TEI walk takes `<div>` children in document order rather than selecting
only `<p>`, so `<formula>` siblings are kept in place; figure/table captions
become a `figure_caption` section; footnotes become a `note` section.
(2) Venue is read from the page-1 running header by pattern, since GROBID
supplies none without `consolidateHeader`.
(3) Parsing runs in a thread pool (`--workers`, default 4); storage stays serial.
Alternatives considered: (i) leave the 15% content gap, since the missing text is
"only" equations and captions; (ii) enable GROBID's `consolidateHeader` for
venue; (iii) parallelise writes as well as parses.
Reasoning on (1): the gap was measured, not assumed — comparing both parsers on
five papers showed GROBID returning 83-88% of PyMuPDF's characters, and sampling
the difference showed real body prose among the junk. The cause was structural:
equations are `<formula>` *siblings* of `<p>`, so a `<p>`-only walk drops every
equation and leaves the prose around it ("The received signal is given by ...
where n is Gaussian noise") referring to nothing. Captions were dropped entirely,
and in this literature a caption routinely carries the result itself ("BLEU score
versus SNR under AWGN"). Recovery: 83-88% to 88-96% of PyMuPDF's characters, and
paragraphs in the database from 3,798 to 4,891.
The residual gap is now mostly PyMuPDF being *worse*: it fails to join ligature
breaks, so "de nition" and "cant performance" count as text GROBID "dropped" when
GROBID has the correct form. The rest is author lists, IEEE footers and diagram
labels, all of which should be dropped.
Captions are marked `figure_caption` rather than merged into body prose. Figure
*understanding* is a non-goal and remains one — the image is never looked at —
but caption text is text. Keeping the distinction means a later phase can exclude
captions from generation context if they turn out to invite claims about images
we cannot see, without re-ingesting.
On (2): `consolidateHeader` calls an external service per paper, which is slow,
network-dependent, and would make ingestion non-reproducible offline. The
heuristic reaches 36% coverage, up from 0%. That is a weak number and is reported
as one; a miss is `not_reported`, which the schema treats as a first-class value.
On (3): parsing is I/O-bound — an HTTP round trip to GROBID plus PyMuPDF, whose C
extension releases the GIL — so threads overlap genuinely. 692s to 252s over 42
papers, a 2.7x speedup, putting 100 papers at roughly 10 minutes against
Definition of Done #7's 20-minute budget. (iii) is rejected: parallel writes would
need a connection pool and would break the per-paper commit that makes an
interrupted run lose at most one paper. The bottleneck was never the writes.
Evidence: 58 tests pass; all Phase 1 exit criteria still met after the changes.
Reversible? Yes. `--workers 1` restores serial ingestion; caption and note
sections are identifiable by `kind` and can be filtered out downstream.

## D-017 — Whitespace table detection tried and REVERTED (negative result)
Date: 2026-09-13
Phase: 1 (post-close improvements)
Decision: Table detection stays on PyMuPDF's line-based strategy at 18/42 papers
(43%). The whitespace-based ("text") strategy, anchored on captions, was
implemented, measured, inspected and reverted.
What was tried: counting "TABLE n" captions across the corpus gave an independent
estimate of ground truth — 35 of 42 papers contain at least one, roughly 126
tables. Against that, the line strategy finds tables in 18 papers and the text
strategy in all 42, but the text strategy reports 677 candidates. Gating it on a
nearby caption cut that to 118 tables across 33 papers, almost exactly the
caption-derived estimate. On those numbers the change looked clearly correct, and
coverage in the full pipeline came out at 34/42 (81%).
Why it was reverted: the contents were unusable. Sampling papers that previously
had no tables showed page-sized grids rather than tables — a 58x2 "Table I" whose
header was `['erase channel an', 'TABLE I']`, a 47x8 whose header was
`['2666', '', '', 'IEEE JOURNAL', 'ON SELECTED', 'AREAS IN COMM']`, rows holding
body prose chopped across columns ('level of commun' | 'ication' | 'problem: the
eff'). The text strategy segments the whole page into a grid; the caption anchor
fired because a real caption happened to fall inside the search band, not because
the detected region was a table.
This is worse than missing the tables. Per D-013, a missed table is visible as an
absence and its text is still in the paragraphs; a false table enters the claim
store looking exactly like a real one. These would have fed running headers and
prose fragments into numeric extraction.
Evidence: 34/42 papers with >=1 table after, 18/42 after reverting. Contents
inspected on four papers that had none before; all four were page grids.
Lesson, and it is the second time this phase: the aggregate looked right and the
content was wrong. 118 detected against ~126 expected is exactly the number a
working implementation would produce. P-003 had the same shape — a plausible
resolution rate hiding a third of links pointing at the wrong paper. Checking a
count is not checking a result.
What would actually work, for whoever revisits this: the caption gives the
table's location to within a caption band, so the region could be bounded by the
caption plus whitespace analysis *within that region only*, rather than
segmenting the page and hoping a caption lands nearby. Alternatively a dedicated
table model — the full GROBID image, or Docling — which is what the spec's
"dedicated table extractor" meant.
Reversible? Already reverted. The rejected approach is described above in enough
detail to avoid re-deriving it.
