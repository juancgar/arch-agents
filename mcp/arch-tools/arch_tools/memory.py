"""memory_search: read-only wrapper around `memory search --json` (the Phase 2A memory CLI).

`search` is always available. `remember` is exposed only when ARCH_MEMORY_WRITE=1 (opt-in, e.g. for plain
Claude Code sessions); forget/propose/decide are deliberately not exposed.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
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


def write_enabled() -> bool:
    return os.environ.get("ARCH_MEMORY_WRITE") == "1"


# Common credential formats; memory text is embedded and searchable, so these must never be stored.
SECRET_RE = re.compile(
    r"(sk-[A-Za-z0-9_-]{20,}|sk-ant-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}"
    r"|AKIA[0-9A-Z]{16}|xox[abpr]-[A-Za-z0-9-]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY-----"
    r"|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})"
)


def build_remember_argv(
    cli: Path | str,
    text: str,
    collection: str,
    *,
    project: str | None = None,
    memory_type: str | None = None,
    tags: Sequence[str] | None = None,
    scope_paths: Sequence[str] | None = None,
    source_path: str | None = None,
    source: str | None = "claude-code",
) -> list[str]:
    """argv for `memory remember`, with the same flag/positional guards as build_search_argv."""
    text = (text or "").strip()
    if not text:
        raise ToolError("text must not be empty")
    if SECRET_RE.search(text):
        raise ToolError("text looks like it contains a credential; remove it before storing")
    if collection not in COLLECTIONS:
        raise ToolError(f"collection must be one of {', '.join(COLLECTIONS)}")
    if memory_type is not None and memory_type not in MEMORY_TYPES:
        raise ToolError(f"memory_type must be one of {', '.join(MEMORY_TYPES)}")
    argv = [str(cli), "remember", "--json", "--status=active"]
    if project and project.strip():
        argv.append(f"--project={project.strip()}")
    if memory_type:
        argv.append(f"--memory-type={memory_type}")
    tag_csv = _csv(tags, "tags")
    if tag_csv:
        argv.append(f"--tags={tag_csv}")
    scope_csv = _csv(scope_paths, "scope_paths")
    if scope_csv:
        argv.append(f"--scope-paths={scope_csv}")
    if source_path and source_path.strip():
        argv.append(f"--source-path={source_path.strip()}")
    if source:
        argv.append(f"--source={source}")
    argv += ["--", collection, text]
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
        raise ServiceUnavailable(f"memory {argv[1]} timed out after {timeout_s:.0f}s") from None
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
        raise ServiceError(f"memory search failed (exit {code})", data={"cli_error": _cli_error(stderr)})
    return _parse_json_output(stdout)


def _cli_error(stderr: str) -> Any:
    for line in reversed(stderr.strip().splitlines()):
        try:
            return json.loads(line)
        except ValueError:
            continue
    return stderr.strip()[-800:]


async def memory_remember(
    text: str,
    collection: str,
    *,
    project: str | None = None,
    memory_type: str | None = None,
    tags: Sequence[str] | None = None,
    scope_paths: Sequence[str] | None = None,
    source_path: str | None = None,
    cfg: Config | None = None,
    timeout_s: float = TIMEOUT_S,
) -> Any:
    if not write_enabled():
        raise ToolError("memory writes are disabled (set ARCH_MEMORY_WRITE=1)")
    cfg = cfg or Config.from_env()
    argv = build_remember_argv(
        cfg.memory_cli, text, collection, project=project, memory_type=memory_type, tags=tags,
        scope_paths=scope_paths, source_path=source_path,
    )
    code, stdout, stderr = await run_cli(argv, timeout_s)
    if code != 0:
        raise ServiceError(f"memory remember failed (exit {code})", data={"cli_error": _cli_error(stderr)})
    result = _parse_json_output(stdout)
    if "Duplicate skipped" in stderr:
        result["duplicate"] = True
    return result
