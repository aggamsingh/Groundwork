# Problem log

Every bug that costs more than 15 minutes. **Recording the wrong hypothesis is
mandatory — that is the part with value in it.**

Format (from spec §3):

```
## P-NNN — Short title
Date: YYYY-MM-DD
Phase: N
Symptom: what was observed, with numbers where there are numbers.
First hypothesis (WRONG): what we believed first and acted on.
Actual cause: what it really was.
Fix: what was changed.
Cost: hours.
Prevention: the test, eval question, or check added so it cannot recur silently.
```

If the first hypothesis happened to be right, the entry still gets written, and
says so — but that is the uncommon case and worth noticing when it happens.

The `Prevention:` line is not optional. A problem that leaves nothing behind in
the eval set or the test suite has been forgotten, not fixed.

---

<!-- No problems logged yet. Append entries below. -->
