"""memory_search: read-only wrapper around `memory search --json` (the Phase 2A memory CLI).

Only the `search` subcommand is ever invoked. remember/forget/propose/decide are deliberately not exposed.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Sequence

from .config import Config
from .net import ServiceError, ServiceUnavailable, ToolError

TIMEOUT_S = 60.0
COLLECTIONS = ("project_memory", "research_memory", "task_memory", "knowledge_memory")
MEMORY_TYPES = (
    "architecture_decision", "repo_constraint", "interface_contract", "environment_constraint",
    "bug_pattern", "command_recipe", "task_state",
)
STATUSES = ("active", "closed", "stale", "superseded")


def _csv(values: Sequence[str] | str | None, name: str) -> str | None:
    if values is None:
        return None
    items = [values] if isinstance(values, str) else list(values)
    cleaned = [str(v).strip() for v in items if str(v).strip()]
    for v in cleaned:
        if "," in v:
            raise ToolError(f"{name} entries must not contain commas: {v!r}")
    return ",".join(cleaned) or None


def build_search_argv(
    cli: Path | str,
    query: str,
    collection: str,
    *,
    project: str | None = None,
    memory_types: Sequence[str] | None = None,
    status: str | None = None,
    limit: int | None = None,
    tags: Sequence[str] | None = None,
    scope_paths: Sequence[str] | None = None,
) -> list[str]:
    """argv for `memory search`. Options use --name=value and positionals follow `--`, so values that start
    with '-' can never be parsed as flags."""
    query = (query or "").strip()
    if not query:
        raise ToolError("query must not be empty")
    if collection not in COLLECTIONS:
        raise ToolError(f"collection must be one of {', '.join(COLLECTIONS)}")
    if status is not None and status not in STATUSES:
        raise ToolError(f"status must be one of {', '.join(STATUSES)}")
    types = _csv(memory_types, "memory_types")
    if types:
        unknown = sorted(set(types.split(",")) - set(MEMORY_TYPES))
        if unknown:
            raise ToolError(f"unknown memory_types {unknown}; valid: {', '.join(MEMORY_TYPES)}")
    argv = [str(cli), "search", "--json"]
    if project and project.strip():
        argv.append(f"--project={project.strip()}")
    if types:
        argv.append(f"--memory-types={types}")
    tag_csv = _csv(tags, "tags")
    if tag_csv:
        argv.append(f"--tags={tag_csv}")
    scope_csv = _csv(scope_paths, "scope_paths")
    if scope_csv:
        argv.append(f"--scope-paths={scope_csv}")
    if status:
        argv.append(f"--status={status}")
    if limit is not None:
        argv.append(f"--limit={int(limit)}")
    argv += ["--", collection, query]
    return argv


async def run_cli(argv: list[str], timeout_s: float = TIMEOUT_S) -> tuple[int, str, str]:
    """Run without a shell; kill the process group-less child on timeout. Returns (code, stdout, stderr)."""
    env = {k: v for k, v in os.environ.items() if k not in ("VIRTUAL_ENV", "PYTHONPATH", "PYTHONHOME")}
    # The memory service puts its embedding model on the GPU when one is visible; that runs out of memory while
    # llm-server holds the VRAM. Use the CPU unless ARCH_MEMORY_USE_GPU=1.
    if os.environ.get("ARCH_MEMORY_USE_GPU") != "1":
        env["CUDA_VISIBLE_DEVICES"] = ""
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            start_new_session=True,
        )
    except FileNotFoundError as exc:
        raise ServiceUnavailable(f"memory CLI not found at {argv[0]} (set ARCH_MEMORY_CLI)") from exc
    except PermissionError as exc:
        raise ServiceUnavailable(f"memory CLI at {argv[0]} is not executable") from exc
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except asyncio.TimeoutError:
        try:
            os.killpg(proc.pid, 9)
        except (ProcessLookupError, PermissionError):
            proc.kill()
        await proc.wait()
        raise ServiceUnavailable(f"memory search timed out after {timeout_s:.0f}s") from None
    return proc.returncode or 0, stdout.decode("utf-8", "replace"), stderr.decode("utf-8", "replace")


def _parse_json_output(stdout: str) -> Any:
    text = stdout.strip()
    try:
        return json.loads(text)
    except ValueError:
        pass
    for line in reversed(text.splitlines()):  # tolerate log lines printed before the JSON document
        line = line.strip()
        if line.startswith(("[", "{")):
            try:
                return json.loads(line)
            except ValueError:
                continue
    raise ServiceError("memory CLI did not return JSON", data={"stdout_tail": text[-500:]})


async def memory_search(
    query: str,
    collection: str,
    *,
    project: str | None = None,
    memory_types: Sequence[str] | None = None,
    status: str | None = None,
    limit: int | None = 5,
    tags: Sequence[str] | None = None,
    scope_paths: Sequence[str] | None = None,
    cfg: Config | None = None,
    timeout_s: float = TIMEOUT_S,
) -> Any:
    cfg = cfg or Config.from_env()
    argv = build_search_argv(
        cfg.memory_cli, query, collection, project=project, memory_types=memory_types, status=status,
        limit=limit, tags=tags, scope_paths=scope_paths,
    )
    code, stdout, stderr = await run_cli(argv, timeout_s)
    if code != 0:
        detail: Any = stderr.strip()[-800:]
        for line in reversed(stderr.strip().splitlines()):
            try:
                detail = json.loads(line)
                break
            except ValueError:
                continue
        raise ServiceError(f"memory search failed (exit {code})", data={"cli_error": detail})
    return _parse_json_output(stdout)
