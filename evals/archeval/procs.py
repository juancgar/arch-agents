"""Subprocess execution with hard timeouts.

Output goes to temporary files rather than pipes, so a grandchild that keeps a
pipe open (MCP servers, language servers, ...) can never block the harness.
The child gets its own session; on timeout the whole process group is killed.
"""

from __future__ import annotations

import os
import signal
import subprocess
import tempfile
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ProcResult:
    argv: list[str]
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool
    wall_time_s: float
    error: str | None = None  # the process could not be started at all


def _kill_group(proc: subprocess.Popen, grace_s: float = 5.0) -> None:
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(proc.pid, sig)
        except (ProcessLookupError, PermissionError):
            return
        try:
            proc.wait(timeout=grace_s)
            return
        except subprocess.TimeoutExpired:
            continue


def run_process(
    argv: Sequence[str],
    cwd: str | Path,
    timeout: float | None,
    env: Mapping[str, str] | None = None,
    stdin_text: str | None = None,
) -> ProcResult:
    argv = [str(a) for a in argv]
    start = time.monotonic()
    with tempfile.TemporaryFile() as out_f, tempfile.TemporaryFile() as err_f, tempfile.TemporaryFile() as in_f:
        if stdin_text is not None:
            in_f.write(stdin_text.encode("utf-8"))
            in_f.seek(0)
        try:
            proc = subprocess.Popen(
                argv,
                cwd=str(cwd),
                env=dict(env) if env is not None else None,
                stdin=in_f if stdin_text is not None else subprocess.DEVNULL,
                stdout=out_f,
                stderr=err_f,
                start_new_session=True,
            )
        except OSError as exc:
            return ProcResult(argv, None, "", "", False, time.monotonic() - start, f"{type(exc).__name__}: {exc}")
        timed_out = False
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            _kill_group(proc)
        except BaseException:
            _kill_group(proc, grace_s=1.0)
            raise
        wall = time.monotonic() - start
        out_f.seek(0)
        err_f.seek(0)
        stdout = out_f.read().decode("utf-8", errors="replace")
        stderr = err_f.read().decode("utf-8", errors="replace")
    return ProcResult(argv, proc.returncode if not timed_out else None, stdout, stderr, timed_out, wall)
