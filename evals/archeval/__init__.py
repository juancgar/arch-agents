"""Evaluation harness for arch-agents v2 (library behind run.py and compare.py).

Everything here is deterministic and LLM-free. The system under test is only
reached through the `bin/arch` launcher (see agent.py); in --dry-run mode a stub
replaces it.
"""

from __future__ import annotations

from pathlib import Path

EVALS_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = EVALS_DIR.parent

ROUTING_DIR = EVALS_DIR / "routing"
CODING_DIR = EVALS_DIR / "coding"
RESEARCH_DIR = EVALS_DIR / "research"
DEFAULT_RESULTS_DIR = EVALS_DIR / "results"

# Route names accepted in ROUTE-ONLY output (12 v1 coding routes + research workflows).
ROUTES: tuple[str, ...] = (
    "quick-fix",
    "explain",
    "debug",
    "implement",
    "refactor",
    "architecture",
    "code-review",
    "verify",
    "document",
    "repo-map",
    "general-technical",
    "general",
    "research-discovery",
    "paper-analyze",
    "paper-compare",
    "literature-review",
    "novelty-check",
    "research-proposal",
    "research-cycle",
    "full-cycle",
)

AGENTS: tuple[str, ...] = (
    "orchestrator",
    "architect",
    "planner",
    "reviewer",
    "synthesizer",
    "novelty-checker",
    "proposal-designer",
    "paper-comparator",
    "literature-reviewer",
    "coder",
    "debugger",
    "tester",
    "researcher",
    "paper-analyst",
    "claim-checker",
    "explore",
    "documenter",
    "browser-agent",
    "memory-manager",
)

DIFFICULTIES: tuple[str, ...] = ("S", "M", "L")

PLANS: tuple[str, ...] = ("max", "daily", "saver", "local", "offline")
# Plans that run Claude Code and accept `--json` (Claude Code result JSON on stdout).
CLAUDE_PLANS: frozenset[str] = frozenset({"max", "daily", "saver", "local"})

SUITES: tuple[str, ...] = ("routing", "coding", "research")

ROUTE_ONLY_PREFIX = "ROUTE-ONLY: "

# File changes under these prefixes are recorded but never count as project
# changes (v2 keeps per-task notes in .arch/tasks/<id>/).
SCORING_IGNORED_PREFIXES: tuple[str, ...] = (".arch/",)

# Never copied into an agent's work directory, never snapshotted.
CACHE_DIR_NAMES: frozenset[str] = frozenset(
    {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".venv", "node_modules"}
)
