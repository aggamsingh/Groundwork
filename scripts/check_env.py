"""Environment preconditions for `docker compose up` — task 0.3.

Written after P-001: Docker Desktop was installed and running, but the engine
never started because WSL was absent, and the failure presented as a four-minute
silent timeout rather than an error. Each check below fails fast with the actual
remedy, and prerequisites are checked before the service that depends on them.

Usage:
    uv run python scripts/check_env.py
"""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys

OK = "ok  "
BAD = "FAIL"


def _run(cmd: list[str], timeout: int = 20) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=timeout, text=False)
    except FileNotFoundError:
        return 127, "not found"
    except subprocess.TimeoutExpired:
        return 124, "timed out"
    # wsl.exe emits UTF-16; everything else is ASCII-ish. Decode leniently.
    raw = (p.stdout or b"") + (p.stderr or b"")
    text = raw.decode("utf-16-le", "ignore") if b"\x00" in raw[:40] else raw.decode(
        "utf-8", "ignore"
    )
    return p.returncode, " ".join(text.split())


def check_binary(name: str) -> tuple[bool, str]:
    path = shutil.which(name)
    if path:
        return True, path
    return False, f"{name} is not on PATH (restart your shell after installing)"


def check_wsl() -> tuple[bool, str]:
    """Docker Desktop on Windows Home requires the WSL2 backend. See P-001."""
    if platform.system() != "Windows":
        return True, "not Windows, WSL not required"
    code, out = _run(["wsl", "--status"])
    if code == 0:
        return True, "WSL present"
    if "not installed" in out.lower():
        return False, (
            "WSL is not installed. Docker Desktop on Windows Home has no Hyper-V "
            "backend and cannot start without it. Fix: run 'wsl --install' from an "
            "elevated PowerShell, then reboot. (P-001)"
        )
    return False, f"wsl --status failed: {out[:160]}"


def check_docker_engine() -> tuple[bool, str]:
    code, out = _run(["docker", "info", "--format", "{{.ServerVersion}}"], timeout=30)
    if code == 0 and out.strip():
        return True, f"engine {out.strip()}"
    if "docker_engine" in out or "cannot find the file" in out.lower():
        return False, (
            "Docker binaries are present but the engine is not running. Launch "
            "Docker Desktop and wait for it to report Running."
        )
    return False, f"docker info failed: {out[:160]}"


def main() -> int:
    checks: list[tuple[str, tuple[bool, str]]] = [
        ("docker binary", check_binary("docker")),
        ("wsl backend", check_wsl()),
        ("docker engine", check_docker_engine()),
    ]

    failed = 0
    for name, (passed, detail) in checks:
        print(f"[{OK if passed else BAD}] {name:<15} {detail}")
        if not passed:
            failed += 1
            # Prerequisites come first; a later failure is usually a consequence
            # of an earlier one, so stop rather than emit misleading advice.
            break

    if failed:
        print("\nPreconditions not met. Fix the failure above, then re-run.")
        return 1
    print("\nAll preconditions met - 'docker compose up -d' should work.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
