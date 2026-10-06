#!/usr/bin/env python3
"""Stop gate (Claude Code, main session): don't let the final answer claim files were saved/written
unless those files exist. Blocks once with the list of missing files."""
import json
import os
import re
import sys
from pathlib import Path

CLAIM = re.compile(r"(saved|written|wrote|created|stored|guardad[oa]|creado)\b[^\n]{0,80}?((?:~|/)[\w./\-~+@%()]+\.\w{1,8})",
                   re.IGNORECASE)


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    if data.get("stop_hook_active"):
        return 0
    text = data.get("last_assistant_message") or ""
    if isinstance(text, list):
        text = "\n".join(b.get("text", "") for b in text if isinstance(b, dict))
    cwd = data.get("cwd") or os.getcwd()
    missing = []
    for m in CLAIM.finditer(text):
        raw = m.group(2).rstrip(".,;:)`'\"")
        p = Path(os.path.expanduser(raw))
        if not p.is_absolute():
            p = Path(cwd) / p
        if not p.exists():
            missing.append(raw)
    if missing:
        print(json.dumps({"decision": "block", "reason":
            "Your answer says these files were saved, but they don't exist: " + ", ".join(sorted(set(missing))[:10]) +
            ". Have the documenter write them and confirm, or correct the answer."}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
