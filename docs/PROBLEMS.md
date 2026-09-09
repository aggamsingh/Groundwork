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
