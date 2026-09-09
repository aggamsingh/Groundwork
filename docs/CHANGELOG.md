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
## C-001 — Corpus starts at 44 papers, grows to ~120 before Phase 2
Date: 2026-09-09
Original plan: spec §5 Phase 0 freezes ~120 papers, split 2/3 development and
1/3 holdout, before any ingestion work begins.
Change: the corpus is seeded with the 44 unique papers the user has on hand and
grows to ~120 before the Phase 2 baseline is measured. New papers are added to
the **development** side only; the holdout, once frozen, is never added to.
Trigger: the user has 44 unique papers today (50 files, 6 byte-identical
duplicate pairs) and did not want to block on assembling the rest. Option 1 of
three offered on 2026-09-09.
Impact:
  - Phase 1 ingestion, the parser bake-off, and pipeline debugging run on 44
    papers, which is sufficient for all of them.
  - Phase 0's "freeze" is therefore partial: the *holdout* is frozen at Phase 0,
    the *dev set* is not frozen until the corpus reaches ~120.
  - If the corpus were left at 44, a 1/3 holdout is ~15 papers and the Phase 6
    headline number would carry a confidence interval wide enough that several
    points of difference are indistinguishable from sampling noise. That is the
    reason for the growth commitment, not tidiness.
  - Risk accepted: papers added later are chosen with knowledge of how the
    system already performs, which can bias the dev set. Mitigated by the
    holdout being frozen first and never extended.
Reminder owed: the user asked to be reminded after Phase 1 to reach ~120 papers.
Tracked as task 1.x in docs/PHASES.md and as a Phase 2 entry gate.
