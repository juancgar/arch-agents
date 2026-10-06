#!/usr/bin/env python3
"""PreToolUse guard (Claude Code): block dangerous shell commands and writes outside allowed places.

Exit 2 with a reason on stderr blocks the tool call and tells the model why.
"""
import json
import os
import re
import sys
from pathlib import Path

DANGEROUS = [
    (r"(^|[;&|]\s*|\s)sudo\s", "sudo is not allowed for agents"),
    (r"\brm\s+(-[a-zA-Z]*r[a-zA-Z]*f|-[a-zA-Z]*f[a-zA-Z]*r|-r\s+-f|-f\s+-r|--recursive\s+--force|--force\s+--recursive)\b", "recursive force deletion is not allowed"),
    (r"\bgit\s+push\b", "pushing is left to the user"),
    (r"\bgit\s+reset\s+--hard\b", "git reset --hard can destroy work; ask the user"),
    (r"\bgit\s+clean\s+-[a-zA-Z]*f", "git clean -f deletes untracked files; ask the user"),
    (r"(curl|wget)[^|]*\|\s*(ba|z)?sh\b", "piping downloads into a shell is not allowed"),
    (r"\bmkfs(\.|\s)|\bdd\s+if=.*\bof=/dev/", "disk-level commands are not allowed"),
    (r">\s*/dev/sd[a-z]", "writing to block devices is not allowed"),
    (r"\bchmod\s+-R\s+777\b", "chmod -R 777 is not allowed"),
]


def allowed_roots(cwd: str) -> list[Path]:
    roots = [Path(cwd).resolve(), Path("/tmp").resolve()]
    cfg = Path(__file__).with_name("paths.json")
    if cfg.exists():
        for p in json.loads(cfg.read_text()).get("writable", []):
            roots.append(Path(os.path.expanduser(p)).resolve())
    return roots


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0  # never break the session on malformed input
    tool = data.get("tool_name", "")
    tin = data.get("tool_input", {}) or {}
    cwd = data.get("cwd") or os.getcwd()

    if tool == "Bash":
        cmd = tin.get("command", "")
        for pattern, why in DANGEROUS:
            if re.search(pattern, cmd):
                print(f"Blocked by arch-agents guard: {why}. Command: {cmd[:200]}", file=sys.stderr)
                return 2
        return 0

    if tool in ("Edit", "Write", "NotebookEdit", "MultiEdit"):
        target = tin.get("file_path") or tin.get("notebook_path") or ""
        if not target:
            return 0
        path = Path(os.path.expanduser(target))
        if not path.is_absolute():
            path = Path(cwd) / path
        path = path.resolve()
        if not any(path == r or r in path.parents for r in allowed_roots(cwd)):
            print(f"Blocked by arch-agents guard: {path} is outside the project and the research folders. "
                  "Ask the user if this write is really needed.", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
