"""Routing scorer: compares a ROUTE-ONLY JSON object with a case's expectations."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from . import AGENTS, DIFFICULTIES, ROUTES
from .jsonextract import extract_route_json

# Only unambiguous spellings. "general question" is deliberately absent: it could
# mean general-technical (route 11) or general (route 12).
ROUTE_ALIASES = {
    "architecture-change": "architecture",
    "architecture-environment": "architecture",
    "quickfix": "quick-fix",
    "explain-code": "explain",
    "code-explanation": "explain",
    "explanation": "explain",
    "debugging": "debug",
    "big-implementation": "implement",
    "implementation": "implement",
    "review": "code-review",
    "codereview": "code-review",
    "verify-test": "verify",
    "verify-test-only": "verify",
    "test-only": "verify",
    "verification": "verify",
    "documentation": "document",
    "docs": "document",
    "repository-map": "repo-map",
    "repomap": "repo-map",
    "general-technical-question": "general-technical",
    "general-coding-question": "general-technical",
    "general-non-coding": "general",
    "general-non-coding-question": "general",
    "researchdiscovery": "research-discovery",
    "paper-analysis": "paper-analyze",
    "paper-comparison": "paper-compare",
    "lit-review": "literature-review",
    "novelty": "novelty-check",
    "proposal": "research-proposal",
}

AGENT_ALIASES = {
    "explorer": "explore",
    "test": "tester",
    "tests": "tester",
    "debug": "debugger",
    "doc": "documenter",
    "docs": "documenter",
    "documentation": "documenter",
    "review": "reviewer",
    "code-reviewer": "reviewer",
    "plan": "planner",
    "code": "coder",
    "browser": "browser-agent",
    "memory": "memory-manager",
    "novelty": "novelty-checker",
    "claim-check": "claim-checker",
    "claims-checker": "claim-checker",
    "paper-analyzer": "paper-analyst",
    "lit-reviewer": "literature-reviewer",
}

DIFFICULTY_ALIASES = {"s": "S", "m": "M", "l": "L", "small": "S", "medium": "M", "large": "L"}

_ARROW_SPLIT_RE = re.compile(r"\s*(?:->|→|=>|,|;|\n|\|)\s*")


def norm_route(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    r = value.strip().lower().lstrip("/").rstrip(".:")
    r = re.sub(r"[\s_]+", "-", r)
    r = re.sub(r"^route-\d+-", "", r)
    return ROUTE_ALIASES.get(r, r)


def norm_agent(value: Any) -> str | None:
    """Normalize one agent name: strip plugin prefixes ("arch:coder"), "@", case, separators."""
    if isinstance(value, dict):
        value = value.get("agent") or value.get("name") or value.get("subagent") or value.get("role")
    if not isinstance(value, str):
        return None
    a = value.strip().strip("`'\"").lstrip("@")
    if ":" in a:
        a = a.rsplit(":", 1)[1]  # "<plugin>:<agent>" (e.g. "arch:coder") -> "<agent>"
    a = re.sub(r"\s*\(.*\)\s*$", "", a)  # "tester (blind)" -> "tester"
    a = re.sub(r"[\s_]+", "-", a.strip().lower()).strip("-")
    return AGENT_ALIASES.get(a, a) or None


def norm_agents(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [v for v in _ARROW_SPLIT_RE.split(value) if v.strip()]
    if not isinstance(value, list):
        return []
    out = []
    for item in value:
        name = norm_agent(item)
        if name:
            out.append(name)
    return out


def norm_difficulty(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    d = value.strip()
    return d if d in DIFFICULTIES else DIFFICULTY_ALIASES.get(d.lower())


def _clarify_text(value: Any) -> str | None:
    if value is None or value is False:
        return None
    if isinstance(value, list):
        value = " ".join(str(v) for v in value if v)
    text = str(value).strip()
    if not text or text.lower() in {"null", "none", "n/a", "no", "false", "-"}:
        return None
    return text


def _order_violations(agents: list[str], order: list[list[str]]) -> list[str]:
    """Pair [a, b]: whenever b is used, a must appear before b's first use."""
    violations = []
    for a, b in order:
        if b not in agents:
            continue
        if a not in agents:
            violations.append(f"{b} used without {a} before it")
        elif agents.index(a) > agents.index(b):
            violations.append(f"{b} before {a}")
    return violations


def score_routing(case: dict, output_text: str, project_changes: list[dict] | None = None) -> dict:
    """Score one ROUTE-ONLY answer. `project_changes` (if given) adds a no-side-effects check."""
    parsed, error = extract_route_json(output_text)
    checks: dict[str, dict] = {}
    got: dict[str, Any] = {}

    checks["parse"] = {"ok": parsed is not None, "detail": error}
    if parsed is not None:
        got["route"] = norm_route(parsed.get("route"))
        got["difficulty"] = norm_difficulty(parsed.get("difficulty"))
        got["agents"] = norm_agents(parsed.get("agents"))
        got["clarify"] = _clarify_text(parsed.get("clarify"))
        assumptions = parsed.get("assumptions")
        got["assumptions"] = [str(a) for a in assumptions] if isinstance(assumptions, list) else (
            [assumptions] if isinstance(assumptions, str) and assumptions.strip() else []
        )
        got["unknown_agents"] = sorted({a for a in got["agents"] if a not in AGENTS})
        got["unknown_route"] = got["route"] not in ROUTES

    agents: list[str] = got.get("agents", [])
    checks["route"] = {
        "ok": parsed is not None and got.get("route") in case["route"],
        "expected": case["route"],
        "got": got.get("route"),
    }
    if case["difficulty"]:
        checks["difficulty"] = {
            "ok": parsed is not None and got.get("difficulty") in case["difficulty"],
            "expected": case["difficulty"],
            "got": got.get("difficulty"),
        }
    if case["must_include"]:
        missing = [a for a in case["must_include"] if a not in agents]
        checks["must_include"] = {"ok": parsed is not None and not missing, "missing": missing}
    if case["must_not_include"]:
        present = [a for a in case["must_not_include"] if a in agents]
        checks["must_not_include"] = {"ok": parsed is not None and not present, "forbidden_present": present}
    if case["order"]:
        violations = _order_violations(agents, case["order"]) if parsed is not None else ["unparsed"]
        checks["order"] = {"ok": not violations, "violations": violations}
    if case["expect_clarify"] is not None:
        asked = got.get("clarify") is not None
        checks["clarify"] = {
            "ok": parsed is not None and asked == case["expect_clarify"],
            "expected": case["expect_clarify"],
            "got": got.get("clarify"),
        }
    if case.get("min_assumptions"):
        n = len(got.get("assumptions", []))
        checks["assumptions"] = {"ok": n >= case["min_assumptions"], "expected_min": case["min_assumptions"], "got": n}
    if project_changes is not None:
        checks["no_side_effects"] = {"ok": not project_changes, "changed": [c["path"] for c in project_changes]}

    passed = sum(1 for c in checks.values() if c["ok"])
    return {
        "pass": all(c["ok"] for c in checks.values()),
        "score": round(passed / len(checks), 4),
        "checks": checks,
        "parsed": parsed,
        "normalized": got,
    }


# --------------------------------------------------------------------------- dry-run stub


def _stable_index(text: str, n: int) -> int:
    return int(hashlib.sha256(text.encode()).hexdigest(), 16) % n


def reference_route_object(case: dict) -> dict:
    """The JSON a perfect orchestrator would emit for this case (used by --dry-run)."""
    agents: list[str] = []
    needed = list(case["must_include"])
    # Pull in "before" agents required by order constraints on included agents.
    for a, b in case["order"]:
        if b in needed and a not in needed:
            needed.insert(0, a)
    # Respect order constraints with a simple stable topological pass.
    pending = list(dict.fromkeys(needed))
    while pending:
        for cand in pending:
            blockers = [a for a, b in case["order"] if b == cand and a in pending]
            if not blockers:
                agents.append(cand)
                pending.remove(cand)
                break
        else:  # cycle (should not happen with validated cases)
            agents.extend(pending)
            break
    return {
        "route": case["route"][0],
        "difficulty": (case["difficulty"] or ["M"])[0],
        "agents": [f"arch:{a}" if _stable_index(case["id"], 2) else a for a in agents],
        "clarify": "Which part should I focus on, and what would count as done?" if case["expect_clarify"] else None,
        "assumptions": [f"assumption {i + 1}" for i in range(case.get("min_assumptions") or 0)],
    }


def stub_output(case: dict, mode: str = "reference") -> str:
    """Canned launcher output; rotates through the wrappings real models produce."""
    if mode == "noop":
        return "I'm not sure which workflow fits; could you tell me more?"
    obj = json.dumps(reference_route_object(case), ensure_ascii=False)
    style = _stable_index(case["id"] + "style", 4)
    if style == 0:
        return obj
    if style == 1:
        return f"Routing decision:\n\n```json\n{obj}\n```\n"
    if style == 2:
        return f"Here is the route: {obj} (no work executed)."
    pretty = json.dumps(reference_route_object(case), ensure_ascii=False, indent=2)
    return f"```\n{pretty}\n```\nNothing was executed because of ROUTE-ONLY."
