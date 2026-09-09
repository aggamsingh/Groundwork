# CLAUDE.md — Working agreement

Corpus-adaptive research QA system over academic papers. Single-user, self-hosted.
Built for real literature surveys, not as a demo.

The spec is `SURVEY_ASSISTANT_SPEC.md`. It is the source of truth. This file
distills §2 of it into the rules that govern day-to-day work.

---

## Non-goals — binding, verbatim from §1

- Writing survey prose. The system produces answers, tables, and citations. I write the paper.
- Figure or diagram understanding.
- Multi-user, auth, billing, sharing.
- Multilingual corpora.
- Fine-tuning a generator model.
- A polished frontend. Functional UI only.

Anything on this list is not built. Not "built minimally", not "stubbed for later".
If it seems necessary, that is a conversation, not a commit.

---

## Rules

**Scope discipline.** The non-goals list is binding. Propose, never assume.
Ask before expanding scope. Never silently add a feature.

**Measure before and after.** No retrieval, chunking, prompt, or generation change
ships without an eval run on both sides and the delta written down. If a change
does not help, it is reverted and the negative result is recorded.
Negative results are project output, not failures.

**Baseline first, always.** Within any phase, the simplest version that runs end
to end comes before the sophisticated one.

**Explain before implementing.** For any non-trivial component, state the approach
and the alternative rejected, in two or three sentences, then implement.
That goes in `docs/DECISIONS.md`.

**No hidden frameworks.** Every retrieval hop must be explainable in an interview.
No abstraction that buries the pipeline. Explicit code over framework magic.
Concretely: one module per retrieval hop, one serialized config object per run.

**Small commits, real messages.** One logical change per commit. The message states
what changed and the eval delta if any.

**Ask when the spec is silent.** Do not invent requirements.

**Speed.** Move fast on: plumbing, parsing, harness, CI, dashboards, UI.
Slow down and involve the user on: the extraction schema, eval question labelling,
reranker training-pair construction, routing logic, and any debugging where
retrieval returns something wrong.

---

## Documentation protocol — non-optional

Three logs, appended to continuously. As important as the code. Formats in §3 of the spec.

| Log | Trigger | Timing |
|---|---|---|
| `docs/DECISIONS.md` | Every non-obvious decision | At the time of the decision, never retroactively |
| `docs/PROBLEMS.md` | Every bug costing more than 15 minutes | Includes the **wrong** first hypothesis — mandatory, that is the part with value in it |
| `docs/CHANGELOG.md` | Any deviation from the spec | **Before** it is implemented, not after |

Each phase closes with `docs/reports/phase-N.md`: what was built, eval numbers before
and after, ablation deltas, what surprised us, what carries into the next phase.

`docs/PHASES.md` tracks phase status. `docs/USAGE_LOG.md` starts in Phase 7.

---

## Hard gates

- **The SemCom holdout (1/3 of the corpus) is not opened, read, or tuned against until Phase 6.**
  Enforced mechanically, not by discipline. Breaking this invalidates the headline number.
- Phase 2 baseline numbers must exist and be committed before any Phase 3 retrieval work.
- No phase proceeds without meeting its stated exit criteria.
- Frozen artifacts (`schema/semcom.yaml`, `eval/gold_table_semcom.csv`, `eval/holdout_papers.txt`)
  change only via a CHANGELOG entry.

## Priority under time pressure

Cut Phase 5 and 6 generalization before cutting Phase 4 groundedness.
A single-corpus system that never hallucinates beats a general one that does.

---

## Human-gated checkpoints

There are tasks in this project that **only the user can do**. They are not optional
and cannot be substituted with anything Claude generates. Claude's job is to stop and
say when each one is due, then wait.

**Never quietly generate a placeholder for a human artifact.** If a stub is needed to
test plumbing, name it `*_STUB` and add a failing check that prevents any eval run from
consuming it.

| # | Checkpoint | Phase | Artifact | Blocks |
|---|---|---|---|---|
| 1 | Holdout split | 0 | `eval/holdout_papers.txt` | all of Phase 1 |
| 2 | Extraction schema | 0 | `schema/semcom.yaml` (dated) | Phase 0 exit |
| 3 | Gold comparison table | 0 | `eval/gold_table_semcom.csv` | Phase 0 exit |
| 4 | Hand-labelled eval questions | 2 | 60 questions w/ spans → 150 | **all of Phase 3** |
| 5 | Faithfulness sample | 4 | hand-checked answers vs cited spans | Phase 4 exit |
| 6 | Real usage sessions | 7 | `docs/USAGE_LOG.md`, 3 sessions | Phase 7 exit |

### CHECKPOINT 1 — Holdout split (Phase 0, before any ingestion code)

The user splits the SemCom reference list into 2/3 development and 1/3 holdout. The
holdout list is committed as `eval/holdout_papers.txt` and is not read, ingested into
the dev index, or tuned against until Phase 6. Reason: the user knows this literature
well, so without an untouched slice every final number is contaminated and indefensible.

**Obligation:** refuse to begin Phase 1 until `eval/holdout_papers.txt` exists and the
user has confirmed the split is frozen. **Do not generate the split** — the user chooses
which papers are held out.

### CHECKPOINT 2 — Extraction schema (Phase 0)

The user writes and freezes `schema/semcom.yaml` themselves, dated. Claude may propose a
draft for the user to edit; the frozen version is theirs.

### CHECKPOINT 3 — Gold comparison table (Phase 0)

The user exports `eval/gold_table_semcom.csv` from their own survey. Claude does **not**
synthesize this file under any circumstance. It is the only human ground truth in the project.

### CHECKPOINT 4 — Hand-labelled eval questions (Phase 2, blocks Phase 3 entirely)

The user writes 60 questions with supporting spans across five types: single-paper lookup,
cross-paper comparison, numeric/table extraction, contradiction, unanswerable. Grows to 150
during Phase 3.

This is the highest-risk checkpoint. Building the hierarchical index will feel more
interesting than waiting for questions to be labelled. Every Phase 3 result is a delta
against the Phase 2 baseline measured on this set — if the set is thin or machine-generated,
the whole ablation table is decorative.

**Obligation:** implement no Phase 3 technique until at least 60 human-labelled questions
exist and the baseline has been evaluated on them. If the user tries to skip ahead, quote
this line and make them override it explicitly. Auto-generated questions are a **Phase 5
artifact only**, and their agreement with the user's labels is itself a measured result —
they never replace the user's labels.

### CHECKPOINT 5 — Faithfulness sample (Phase 4)

The user hand-checks a sample of generated answers against cited spans.
The NLI verifier does not certify itself.

### CHECKPOINT 6 — Real usage sessions (Phase 7)

The user uses the system for three actual survey sessions and logs failures in
`docs/USAGE_LOG.md`. This cannot be simulated.

### Enforcement

- `docs/PHASES.md` carries a **`BLOCKED ON HUMAN`** status. Use it.
- **At the start of any session**, check whether a checkpoint is due and say so *first*,
  before proposing any work.
- **When a checkpoint comes due mid-session**, stop. State which one, state exactly what
  the user must produce and where it goes, and give the smallest useful version of the
  task — e.g. "label 10 questions now so we can smoke-test the harness, 50 more before Phase 3".
- **While the user is blocked**, offer only work that does not depend on the blocked
  artifact, and say plainly which phase that work belongs to.
