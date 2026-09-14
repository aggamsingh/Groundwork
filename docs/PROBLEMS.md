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

## P-003 — A third of resolved citation edges pointed at the wrong paper
Date: 2026-09-13
Phase: 1
Symptom: citation resolution reported 216/3391 references linked to corpus
papers, which looked reasonable. Sampling twelve of them showed four were wrong —
a 33% false-positive rate. Examples: "Covert communication over noisy channels: A
resolvability perspective" linked to "Engineering Semantic Communication: A
Survey"; "Secure semantic communications: Fundamentals and challenges" linked to
"Semantic Communications: Principles and Challenges"; "Cognitive semantic
communication systems driven by knowledge graph" linked to "Robust Semantic
Communication Driven by Knowledge Graph".
First hypothesis (WRONG): the 0.75 overlap threshold was simply too low, and
raising it to 0.9 would fix it. It would not have. The matcher compared *sets of
tokens*, and in a corpus where every paper is about semantic communication, a
short title like "Engineering Semantic Communication: A Survey" has all four of
its content words present in references to unrelated work. Its score against
those references was 1.0, not 0.75 — no threshold rejects it.
Actual cause: bag-of-words overlap discards word order, which is the only signal
distinguishing near-identical titles in a single-topic corpus. The measure was
also asymmetric (share of the *title's* tokens found in the reference), so short
titles were systematically easier to match — the generic ones, exactly the ones
most likely to collide.
Fix: replaced overlap with ordered-phrase containment — the paper's title must
appear in the reference as a contiguous phrase. Three refinements followed, each
from a false positive that survived the previous one:
  1. A reference matching two corpus titles resolves to neither.
  2. The phrase must end at a title boundary (quote, comma, period). Without this
     "Deep Learning Enabled Semantic Communication Systems" (Xie) matched
     references to "Deep learning-enabled semantic communication systems with
     task-unaware transmitter" (Zhang) — a different paper whose title merely
     starts the same way.
  3. Line-break hyphenation ("Commu- nication") is joined, real hyphens
     ("learning-enabled") become spaces — opposite treatments, distinguished by
     the following whitespace.
Resolution also now clears existing links before recomputing. Without that a
precision fix cannot remove the bad edges it was written to prevent.
Result: 216 links -> 101, all twelve re-sampled correct. Fewer edges, and the
ones remaining are trustworthy.
Cost: ~1 hour.
Prevention: `tests/test_citations.py` pins every false positive above and every
true positive as a test, using the real reference strings. The broader lesson:
the first number looked fine, and only sampling the *content* of the output
exposed the problem. A resolution rate is not a correctness measure — had this
shipped, Phase 5 would have mined reranker training pairs from a graph where one
edge in three was fabricated, and the damage would have surfaced as unexplained
reranker underperformance weeks later.

## P-004 — GROBID container exited immediately on startup
Date: 2026-09-13
Phase: 1
Symptom: `docker compose up -d grobid` reported the container started, but it
exited with code 1 within a minute and `/api/isalive` never answered. The image
pulled and started cleanly; nothing in compose output suggested a problem.
First hypothesis (WRONG): the service was simply slow to load its CRF models —
GROBID is known to take 30-60s on first start, and the healthcheck has a 60s
start period. Waiting longer was the obvious move and would have achieved
nothing, because the process was already dead.
Actual cause: `java.lang.NullPointerException: Cannot invoke
"jdk.internal.platform.CgroupInfo.getMountPoint()" because "anyController" is
null`. The JDK in GROBID 0.8.0 probes cgroups at startup to size its heap against
the container's limits, and that probe NPEs against Docker Desktop's WSL2 cgroup
v2 layout. The failure is in `Bootstrap.registerMetrics`, before any GROBID code
runs, so nothing GROBID-specific appears in the logs.
Fix: `JAVA_OPTS: "-XX:-UseContainerSupport -Xmx2g"`. Disabling container-awareness
skips the cgroup probe entirely. `-Xmx` then has to be explicit, since the JVM can
no longer read the container's memory limit to infer a default.
Cost: ~20 minutes.
Prevention: the workaround is recorded as a comment in `docker-compose.yml`
explaining *why* the flag is there, so nobody removes it later as apparent
tuning. Also: `docker compose ps` hides exited containers, which is what made
this look like a slow start rather than a crash — `docker ps -a` and
`docker logs` were what actually diagnosed it, within seconds of being run.
The pattern repeats P-001 exactly: a service that will not answer was assumed to
be starting slowly, when it had already died. Check whether the process is alive
before waiting on it.

## P-005 — corpus/provenance.json was never committed, despite a commit saying so
Date: 2026-09-13
Phase: 1 (post-close)
Symptom: found while writing `scripts/add_papers.py`. `git ls-files corpus/`
returned only `.gitkeep` and `manifest.csv`. The Phase 0 commit message states
"corpus/provenance.json: which source file(s) each id came from", and D-006 and
D-007 both cite that file as the reason their dedupe decisions are reversible.
The file existed on disk and had never entered the repository.
First hypothesis (WRONG): the file was committed and later removed by some
cleanup. There was no such commit; it was never added in the first place.
Actual cause: `.gitignore` carries `corpus/**` with explicit re-includes for
`manifest.csv` and `.gitkeep` only. `git add -A` therefore skipped
`provenance.json` silently — as designed, since the rule exists to keep PDFs out.
Nothing failed, nothing warned, and the commit message asserted otherwise.
Consequence had it gone unnoticed: two decisions describe themselves as
reversible on the strength of a file stored on exactly one machine, with no
backup and no history. Losing it would not have been noticed either, because
nothing reads it during normal operation — it would have been discovered only at
the moment someone needed to reverse a dedupe decision, which is the moment it is
least recoverable.
Fix: `.gitignore` re-includes `corpus/provenance.json` and the new
`corpus/excluded.csv`. Both are now tracked. The distinction the rule should
encode is data versus decisions: the PDFs are data and stay out; the records of
what was done to them are decisions and belong in history.
Cost: ~10 minutes, all of it after the fact.
Prevention: `scripts/check_artifacts.py` runs in CI over the frozen artifacts,
and this class of error — a file the project depends on that no check reads —
is exactly what it is for. A broader lesson for the commit log: a commit message
naming a file is not evidence the file was committed. `git ls-files` is.

## P-006 — Windows Smart App Control blocked uv.exe mid-project
Date: 2026-09-14
Phase: 2 (machinery)
Symptom: `uv add docling` failed with "Program 'uv.exe' failed to run: An
Application Control policy has blocked this file". Every `uv` invocation now
fails the same way — `uv --version` included — though uv had been used
successfully all through Phases 0 and 1, including minutes earlier.
First hypothesis (WRONG): a transient failure in the background task runner,
since the first failure happened in a backgrounded command and an earlier
`pytest.exe` invocation had failed oddly in the same context. Retrying in the
foreground failed identically, which ruled it out.
Actual cause: Windows Smart App Control is enabled and enforcing
(`HKLM:\SYSTEM\CurrentControlSet\Control\CI\Policy\VerifiedAndReputablePolicyState`
= 1). SAC blocks binaries it does not consider reputable, and its verdicts change
over time as its reputation data updates — which is why uv worked for two phases
and then stopped. The earlier `pytest.exe` block was the same mechanism showing
an early symptom that I worked around (`python -m pytest`) without diagnosing.
Fix: `python -m ensurepip --upgrade` bootstrapped pip into the existing venv, and
packages install with `.venv\Scripts\python.exe -m pip` instead. The venv's
`python.exe` is not blocked, so tests, scripts and ingestion all still run —
`python -m pytest` in place of `uv run pytest`.
Consequence to watch: dependencies added via pip do NOT update `uv.lock`, so the
lockfile is now stale relative to the environment. `pyproject.toml` is kept
current by hand. This matters for spec Definition of Done #7 and for Phase 6
reproducibility, both of which assume a lockfile that describes the environment.
It needs resolving before either is claimed.
What was NOT done, deliberately: Smart App Control cannot be configured with
exclusions, and turning it off is irreversible without reinstalling Windows.
Recommending the user disable a security feature to unblock a package manager
would be a poor trade, and the pip workaround costs nothing by comparison.
Cost: ~25 minutes.
Prevention: `scripts/check_env.py` should gain a check that the package manager
actually runs, since "the tool that installs things has been blocked" presents as
unrelated failures scattered across whatever was being installed at the time.
The wider pattern, now three times over (P-001 Docker, P-004 GROBID, this):
an environment failure impersonating a code failure. Check whether the tool
itself can run before debugging what it was asked to do.

## P-007 — C: drive reached 0 bytes free; Docker Desktop died
Date: 2026-09-14
Phase: 2 (machinery)
Symptom: a container running `pip install torch` failed with
`OSError(30, 'Read-only file system')` and `error waiting for container:
unexpected EOF`. Then `docker system df` returned HTTP 500, and every docker
command returned "Docker Desktop is unable to start".
First hypothesis (WRONG): the container had exhausted its own writable layer, so
the fix was a larger layer or a slimmer install. Plausible from the error alone,
and wrong.
Actual cause: the host disk was completely full — `Get-PSDrive C` reported
**0 GB free** of 191.5 GB. Docker Desktop's VM cannot write to a full disk, so
the daemon failed and took every container with it, including Postgres and the
whole corpus store.
My own contribution, which is the part worth owning: installing docling pulled
torch and transformers (1.41 GB into the venv) and left 3.78 GB in the pip cache
— about 5.2 GB, on a disk that evidently had little headroom to start with. The
install was for a table extractor that Smart App Control then blocked from
loading anyway (P-006), so the space bought nothing.
Fix: purged the pip cache (1,565 files) and uninstalled the torch stack, which is
unusable natively regardless. Free space went 0 -> 9.01 GB. Docker needed a full
restart (kill processes, `wsl --shutdown`, relaunch) before it would start again.
Verified afterwards: 92 tests pass, Postgres back up, pgvector 0.8.6, all 42
papers present, every Phase 1 exit criterion still met. Nothing was lost, which
was luck as much as design — the pgdata volume survived a hard daemon kill.
Cost: ~30 minutes.
Prevention: `scripts/check_env.py` should check free disk space and fail loudly
below a threshold; a full disk presents as unrelated errors in whatever happens
to be writing at the time, which is exactly how this appeared. More directly:
check available space BEFORE installing anything large, and purge the package
cache afterwards rather than leaving a multi-gigabyte cache behind on a machine
that was already nearly full.
Standing note for the project: the disk is the binding constraint on this
machine, not just VRAM. A local model stack (torch plus model weights) is several
gigabytes before any corpus growth, and the corpus is about to roughly triple.

## P-008 — A held-out paper's content was in the dev set from Phase 0
Date: 2026-09-15
Phase: 2
Symptom: a stress test comparing *parsed titles* across the corpus found two
papers with identical normalised titles:
  - `a-robust-deep-learning-enabled-semantic-communication-system-for-text` (dev)
  - `r-deepsc-paper-literal-text-noise-vs-adversarial-physical-noise` (HOLDOUT)
Confirmed the same paper: identical title, identical opening paragraph word for
word, both 6 pages. Different sha256 (separate downloads — one carried a DOI in
its metadata, the other did not) and completely unrelated filenames.
First hypothesis (WRONG): a false positive from title normalisation being too
aggressive — stripping punctuation and case could plausibly collapse two
distinct papers with similar names. Checking the first paragraph of each ruled
it out immediately; they are the same text.
Actual cause: the user held out `r-deepsc-paper-...`, and the same paper was also
present as `a-robust-deep-learning-...` in dev. Three dedupe passes had run over
this corpus and none could see it:
  - content hashing (D-006): bytes differ, so no match
  - slug/filename similarity (D-007, D-019): the filenames share no words at all
  - the "looks like an existing paper" check in add_papers.py: same weakness
Nothing compared the *parsed titles*, because at Phase 0 the papers had not been
parsed yet — the dedupe ran on filenames, which was all that existed then, and
was never revisited once real titles were available.
Consequence: from Phase 0 until now, holdout content sat on the dev side. Nothing
had been tuned yet, so no result is retroactively invalid — the machinery built
so far makes no tuning decisions (C-006), which is the only reason this is a near
miss rather than an invalidated project. Had it survived to Phase 3, every
ablation delta would have been measured on a dev set containing a holdout paper,
and the Phase 6 "honest number" would have been quietly inflated.
Fix: removed the dev copy, keeping the user's holdout choice untouched — their
frozen file is not edited to resolve a mistake of mine. Recorded in
`corpus/excluded.csv` by hash so no future import restores it (D-019). Corpus is
now 41 papers, 27 dev / 14 holdout.
Cost: ~40 minutes, most of it confirming the duplicate was real.
Prevention: `scripts/check_artifacts.py` now compares parsed titles across the
corpus on every CI run and reports whether a collision straddles the split.
`scripts/stress_decisions.py` checks the same thing against the live database.
The general lesson, and it is the fourth time this project has shown it: a check
written against the evidence available at the time must be re-run when better
evidence arrives. Filenames were all Phase 0 had; titles existed from Phase 1
onward and nobody looked again.
