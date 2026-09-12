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
## P-001 — Docker engine never starts after a successful install
Date: 2026-09-09
Phase: 0
Symptom: `winget install Docker.DockerDesktop` reported success and the binaries
were present at `C:\Program Files\Docker\Docker\resources\bin\docker.exe`, but
every `docker info` failed with "failed to connect to the docker API at
npipe:////./pipe/docker_engine ... The system cannot find the file specified".
Docker Desktop was launched and eight of its processes were running. Waited four
minutes; the engine never came up.
First hypothesis (WRONG): a stale PATH in the agent's shell. Refreshing PATH from
the machine and user environment did locate docker.exe, which made the hypothesis
look confirmed — but the binary was never the problem, the daemon was.
Second hypothesis (ALSO WRONG): Docker Desktop was blocking on a first-run
licence or onboarding dialog that nobody had dismissed. Plausible, since the
processes were alive and idle, but wrong.
Actual cause: WSL is not installed on this machine. `wsl --status` reports "The
Windows Subsystem for Linux is not installed". Docker Desktop on Windows 11 Home
has no Hyper-V backend option and requires WSL2, so the engine cannot start.
The running processes are the GUI and backend supervisor waiting on a VM that
can never boot, which is why the failure presents as a silent timeout rather
than an error.
Fix: `wsl --install` from an elevated prompt, then reboot, then relaunch Docker
Desktop. Requires the user — admin rights and a restart.
Cost: ~10 minutes, mostly the 4-minute wait.
Prevention: added an environment precondition check to the Phase 0 exit
checklist (task 0.3) — verify `wsl --status` succeeds *before* waiting on the
Docker engine, so this fails in seconds with a clear message instead of timing
out. The general lesson: when a service will not start, check its platform
prerequisites before theorising about the service itself.

## P-002 — A quarantined paper could never be retried
Date: 2026-09-13
Phase: 1
Symptom: after fixing the NUL-byte crash that quarantined
`a-contemporary-survey-on-semantic-communications-...`, a full re-ingest reported
"39 inserted, 3 unchanged" and zero quarantined — yet the database still showed
`ingest_status = 'quarantined'` for that paper, with the original failure reason.
The fix had shipped and the paper never picked it up.
First hypothesis (WRONG): the paragraph counts looked wrong too (456 rows for a
57-paragraph paper, 4117 for 179), so the first theory was that
`_write_structure` was inserting paragraphs once per section — a nested-loop bug
writing the cross product. That was a false alarm caused by my own inspection
query: `count(pg.id)` across a join of sections and paragraphs counts the cross
product. 8 sections x 57 paragraphs = 456 exactly. The stored data was correct
all along, and ten minutes went into a bug that did not exist.
Second hypothesis (WRONG): the quarantine row would have `parser IS NULL`, so the
idempotency check `row[2] == paper.parser` would fail and force a re-parse. True
of the code path I had in mind, false for the one that ran.
Actual cause: the NUL failure happened inside `_write_structure` — that is, *after*
`store()` had already inserted the `papers` row with `parser='pymupdf'`,
`sha256=<correct>` and `ingest_status='ok'`. `quarantine()` then flipped only the
status, leaving sha256 and parser intact. The idempotency check compared content
and parser but never looked at `ingest_status`, so every subsequent run matched
both, returned "unchanged", and skipped the paper. The quarantine was permanent
and silent: a paper could be lost from the corpus forever while every run
reported success.
Fix: `_existing` now selects `ingest_status`, and the unchanged shortcut requires
`ingest_status = 'ok'`. Quarantined papers are always retried. Separately,
`scripts/ingest.py` now rolls back before quarantining, since a storage failure
aborts the transaction and the quarantine write would otherwise land in a
poisoned one.
Cost: ~45 minutes, over half of it on the phantom cross-product bug.
Prevention: `tests/test_store.py::TestQuarantineRetry` reproduces the exact
shape — store successfully, quarantine afterwards, re-store with identical sha
and parser — and asserts the paper returns to `ok`. Two further tests cover
quarantine clearing stale structure and recording its reason. The wider lesson,
worth more than the fix: verify the measurement before debugging the thing it
measures. Both wrong hypotheses came from trusting an ad-hoc SQL query I had
written thirty seconds earlier.
