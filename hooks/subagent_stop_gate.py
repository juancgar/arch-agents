#!/usr/bin/env python3
"""SubagentStop gate (Claude Code): deterministic evidence checks before a subagent may finish.

- coder / tester / debugger: the report must contain a non-empty "## Evidence" section that shows
  commands were actually run (or explicitly says what could not be run).
- research agents: cited arXiv IDs / DOIs / URLs must exist (checked by arch-tools `check-text`).

Blocks at most once per stop (if `stop_hook_active` is set we let it through, so we never loop).
Outputs {"decision": "block", "reason": ...} to make the subagent continue with the reason.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

CODE_AGENTS = {"coder", "tester", "debugger"}
RESEARCH_AGENTS = {"researcher", "synthesizer", "novelty-checker", "paper-analyst", "paper-comparator",
                   "literature-reviewer", "proposal-designer", "claim-checker"}
COMMAND_HINTS = re.compile(
    r"(pytest|python -m|npm (test|run)|npx|tsc|cargo (test|build)|go test|make\b|ruff|mypy|eslint|"
    r"uv run|node |bash |git (diff|status|log)|\bpassed\b|\bfailed\b|exit code|could not (run|be run)|not run)",
    re.IGNORECASE)


def block(reason: str) -> int:
    print(json.dumps({"decision": "block", "reason": reason}))
    return 0


def section(text: str, title: str) -> str:
    m = re.search(rf"^##\s*{title}\s*$(.*?)(?=^##\s|\Z)", text, re.MULTILINE | re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else ""


def check_code_report(agent: str, text: str) -> str | None:
    evidence = section(text, "Evidence")
    if not evidence or evidence.lower() in ("none", "n/a", "-"):
        return (f"Your report has no Evidence section with content. As the {agent}, list the commands you ran and "
                "their key results (pass/fail counts, error lines), or state explicitly what could not be run and why.")
    if not COMMAND_HINTS.search(evidence):
        return ("Your Evidence section doesn't show any command that was run or any test result. Add the exact "
                "commands and their outcomes, or say explicitly that nothing could be run and why.")
    return None


def check_citations(text: str) -> str | None:
    cfg_file = Path(__file__).with_name("paths.json")
    if not cfg_file.exists():
        return None
    cfg = json.loads(cfg_file.read_text())
    server = cfg.get("arch_tools_server")
    if not server or not Path(server).exists():
        return None
    try:
        proc = subprocess.run([cfg.get("uv", "uv"), "run", "--script", server, "check-text", "--max", "40"],
                              input=text, capture_output=True, text=True, timeout=45)
    except Exception:
        return None  # checker unavailable: don't block
    if proc.returncode != 2:
        return None
    try:
        result = json.loads(proc.stdout)
    except Exception:
        return None
    bad = [d for d in result.get("details", []) if d.get("status") in ("NOT_FOUND", "TITLE_MISMATCH")]
    if not bad:
        return None
    lines = []
    for d in bad[:10]:
        ref = d.get("id") or d.get("doi") or d.get("url") or d.get("ref") or "?"
        if d.get("status") == "TITLE_MISMATCH":
            claimed = d.get('claimed_title') or d.get('cited_title')
            actual = d.get('actual_title') or d.get('title')
            lines.append(f"- {ref}: title mismatch (you wrote {claimed!r}, the record says {actual!r})")
        else:
            lines.append(f"- {ref}: does not exist")
    return ("These citations failed verification:\n" + "\n".join(lines) +
            "\nCorrect them from the actual source or remove the claims that depend on them. Never invent citations.")


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    if data.get("stop_hook_active"):
        return 0
    agent = str(data.get("agent_type", "")).split(":")[-1]
    text = data.get("last_assistant_message") or ""
    if isinstance(text, list):  # content blocks
        text = "\n".join(b.get("text", "") for b in text if isinstance(b, dict))
    if not text.strip():
        return 0
    if agent in CODE_AGENTS:
        reason = check_code_report(agent, text)
        if reason:
            return block(reason)
    if agent in RESEARCH_AGENTS:
        reason = check_citations(text)
        if reason:
            return block(reason)
    return 0


if __name__ == "__main__":
    sys.exit(main())
