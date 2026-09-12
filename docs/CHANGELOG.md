# Plan-change log

Any deviation from `SURVEY_ASSISTANT_SPEC.md` — dropped work, deferred work,
reordered phases, stack substitutions, changed exit criteria — gets an entry here
**before it is implemented, not after.**

Format (from spec §3):

```
## C-NNN — Short title
Date: YYYY-MM-DD
Original plan: what the spec said.
Change: what is being done instead.
Trigger: what forced or motivated the change.
Impact: what is no longer supported, or deferred, and until when.
```

A deviation that improves things still needs an entry. The log exists so the
finished system can be honestly compared against what was originally promised.

Frozen artifacts — `schema/semcom.yaml`, `eval/gold_table_semcom.csv`,
`eval/holdout_papers.txt` — change **only** through an entry here.

---

<!-- No deviations yet. Append entries below. -->
## C-001 — Corpus starts at 42 papers, grows to ~120 before Phase 2
Date: 2026-09-09
Original plan: spec §5 Phase 0 freezes ~120 papers, split 2/3 development and
1/3 holdout, before any ingestion work begins.
Change: the corpus is seeded with the unique papers the user has on hand and
grows to ~120 before the Phase 2 baseline is measured. New papers are added to
the **development** side only; the holdout, once frozen, is never added to.
Trigger: the user has 42 unique papers today (50 files, 6 byte-identical
duplicate pairs) and did not want to block on assembling the rest. Option 1 of
three offered on 2026-09-09.
Impact:
  - Phase 1 ingestion, the parser bake-off, and pipeline debugging run on 42
    papers, which is sufficient for all of them.
  - Phase 0's "freeze" is therefore partial: the *holdout* is frozen at Phase 0,
    the *dev set* is not frozen until the corpus reaches ~120.
  - If the corpus were left at 42, a 1/3 holdout is ~15 papers and the Phase 6
    headline number would carry a confidence interval wide enough that several
    points of difference are indistinguishable from sampling noise. That is the
    reason for the growth commitment, not tidiness.
  - Risk accepted: papers added later are chosen with knowledge of how the
    system already performs, which can bias the dev set. Mitigated by the
    holdout being frozen first and never extended.
Reminder owed: the user asked to be reminded after Phase 1 to reach ~120 papers.
Tracked as task 1.x in docs/PHASES.md and as a Phase 2 entry gate.

## C-002 — Gold table is a 10-paper hand-built subset, not a survey export
Date: 2026-09-13
Original plan: spec §5 Phase 0 freezes `eval/gold_table_semcom.csv` exported from
the user's existing survey, treating it as an artifact that already exists.
Change: the survey has not been written yet. The gold table instead comes from
the user's paper-review notes, which currently cover ~10 of the 42 papers, and is
frozen at that size for now rather than waiting for all 42.
Trigger: user confirmed on 2026-09-13 that the survey is not yet started but that
a review matrix with a controlled vocabulary exists for ~10 papers.
Impact:
  - Phase 0 can close on a 10-row gold table instead of blocking indefinitely.
  - Numeric extraction accuracy (Definition of Done #5) is measured on ~10 papers
    and MUST be reported with that sample size attached. It is a weaker claim
    than the spec assumed and should not be quoted as a flat percentage.
  - The gold table grows as the user reviews more papers. Rows added later are
    appended; existing rows are not revised to match system output -- that would
    destroy the artifact's independence.
  - Constraint: gold table rows must come from the DEVELOPMENT set only. A gold
    row for a holdout paper would mean tuning against the holdout, which is the
    contamination the split exists to prevent. To be checked when the rows land.
  - The schema (CHECKPOINT 2) is now derived from the same notes, so schema and
    gold table share a vocabulary by construction rather than by coincidence.

## C-003 — Gold table deferred from Phase 0 exit to a Phase 2 entry gate
Date: 2026-09-13
Original plan: spec §5 lists the frozen gold comparison table as a Phase 0 exit
criterion, blocking Phase 1.
Change: `eval/gold_table_semcom.csv` is deferred. Phase 0 may close without it.
It becomes a **hard Phase 2 entry gate**, alongside CHECKPOINT 4 (the 60
hand-labelled questions) and the corpus growth to ~120 papers (C-001).
Trigger: user asked to postpone on 2026-09-13.
Impact:
  - Phase 1 is unblocked by this artifact. Nothing in ingestion, storage, or the
    parser bake-off consumes the gold table.
  - The deferral is also a genuine improvement in sequencing: after Phase 1 the
    user fills these rows from clean parsed text with tables preserved, rather
    than from raw PDFs. Same work, materially easier.
  - Risk, and the reason for the gate rather than a plain deferral: a postponed
    ground-truth artifact with no gate attached becomes a dropped one, and
    Definition of Done #5 (numeric extraction accuracy, reported separately)
    would then have nothing behind it. The gate is what makes this a deferral.
  - CHECKPOINT 3 status changes from "Phase 0, blocking" to "Phase 2 entry,
    blocking". It is NOT downgraded in importance and is still human-only.
  - Phase 0's exit criteria are amended to: holdout frozen, schema frozen,
    `docker compose up` verified. Gold table removed from that list.
