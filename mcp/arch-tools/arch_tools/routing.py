"""plan_route: deterministic checks on the orchestrator's routing decision, plus optional self-consistency voting.

The orchestrator drafts a route and answers a yes/no checklist about the request (signals). This module:
  1. (optional) samples the same decision a few more times from the local model and takes a majority vote
     per field (self-consistency, arXiv:2203.11171); disagreement is reported as ambiguity;
  2. corrects the route with hard precedence rules (e.g. a "quick fix" whose cause is unknown is a debug);
  3. computes the difficulty from the checklist instead of a holistic guess (checklists, arXiv:2410.03608);
  4. builds the agent sequence from the route's template, so required gates (tests before code, review after
     code, planner before coder) can't be skipped and read-only requests never get a writer.
Everything except the voting is pure and deterministic.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from collections import Counter
from typing import Any

from .config import Config
from .net import ToolError

# ---------------------------------------------------------------- vocabulary

AGENTS = (
    "architect", "planner", "reviewer", "synthesizer", "novelty-checker", "proposal-designer", "paper-comparator",
    "literature-reviewer", "coder", "tester", "debugger", "researcher", "paper-analyst", "claim-checker", "explore",
    "documenter", "browser-agent",
)
WRITERS = ("coder", "tester", "planner", "documenter")  # agents that change files or only make sense before changes

# writes: "always" = the route itself changes files; "signal" = only if the user asked for changes;
#         "never" = read-only route; "research" = saves research notes, never touches code
ROUTES: dict[str, dict[str, Any]] = {
    "quick-fix": {"floor": "S", "writes": "always", "use": "tiny, localized change whose cause and fix are obvious"},
    "explain": {"floor": "S", "writes": "never", "use": "understand code or behaviour; nothing to change or judge"},
    "debug": {"floor": "M", "writes": "signal", "use": "something fails or misbehaves and the root cause is unknown"},
    "implement": {"floor": "M", "writes": "always", "use": "substantial new behaviour"},
    "refactor": {"floor": "M", "writes": "always", "use": "change structure while behaviour stays the same"},
    "architecture-change": {"floor": "M", "writes": "signal", "use": "decide whether/which option: platforms, components, boundaries"},
    "code-review": {"floor": "S", "writes": "signal", "use": "judge existing code or a diff: safe? correct? bugs? races? good enough?"},
    "verify": {"floor": "S", "writes": "never", "use": "only run tests / checks / a browser check and report"},
    "document": {"floor": "S", "writes": "always", "use": "write or update persistent docs to match the code"},
    "repo-map": {"floor": "M", "writes": "always", "use": "map the whole repository structure into a document"},
    "research-discovery": {"floor": "M", "writes": "research", "use": "find papers on a topic"},
    "paper-analyze": {"floor": "M", "writes": "research", "use": "deep read of one paper"},
    "paper-compare": {"floor": "M", "writes": "research", "use": "compare 2-5 already analysed papers"},
    "literature-review": {"floor": "M", "writes": "research", "use": "thematic review of analysed papers"},
    "novelty-check": {"floor": "M", "writes": "research", "use": "is an idea already done? closest prior work"},
    "research-proposal": {"floor": "L", "writes": "research", "use": "research proposal from verified gaps"},
    "research-cycle": {"floor": "L", "writes": "research", "use": "full investigation of a research question, saved as a report"},
    "full-cycle": {"floor": "L", "writes": "always", "use": "research, then build a tested prototype"},
    "general-technical": {"floor": "S", "writes": "never", "use": "general technical question about no specific codebase"},
    "general": {"floor": "S", "writes": "never", "use": "non-technical question"},
}
CHANGE_ROUTES = ("quick-fix", "implement", "refactor", "document", "repo-map", "full-cycle")
DIRECT_ROUTES = ("general-technical", "general")

ROUTE_ALIASES = {
    "architecture": "architecture-change", "architecture-environment": "architecture-change", "arch": "architecture-change",
    "quickfix": "quick-fix", "fix": "quick-fix", "explanation": "explain", "explain-code": "explain",
    "debugging": "debug", "implementation": "implement", "feature": "implement", "review": "code-review",
    "codereview": "code-review", "security-review": "code-review", "verification": "verify", "test": "verify",
    "tests": "verify", "documentation": "document", "docs": "document", "repository-map": "repo-map",
    "repomap": "repo-map", "general-question": "general-technical", "paper-analysis": "paper-analyze",
    "paper-comparison": "paper-compare", "lit-review": "literature-review", "novelty": "novelty-check",
    "proposal": "research-proposal", "research": "research-discovery",
}
AGENT_ALIASES = {
    "explorer": "explore", "test": "tester", "tests": "tester", "debug": "debugger", "docs": "documenter",
    "doc": "documenter", "review": "reviewer", "code-reviewer": "reviewer", "plan": "planner", "code": "coder",
    "browser": "browser-agent", "novelty": "novelty-checker", "claims-checker": "claim-checker",
    "paper-analyzer": "paper-analyst", "lit-reviewer": "literature-reviewer",
}

SIGNALS: dict[str, str] = {
    "read_only": "The user explicitly forbids changes (analyze/explain/recommend only, read-only, don't touch anything).",
    "changes_requested": "The user asks to change code or files (fix, add, implement, refactor, migrate, write, update).",
    "judge_code": "The user asks for a verdict on existing code: is it safe, correct, vulnerable, racy, buggy, good enough?",
    "unknown_cause": "Something fails or misbehaves (even intermittently) and the cause is not known yet.",
    "open_decision": "A choice between options/platforms/approaches is still open (should we…? X or Y? is it worth it?).",
    "security": "The work changes or judges authentication, authorization, secrets, credentials, crypto or payments.",
    "data_risk": "The work changes stored data or schemas: migrations, deleting/rewriting data, irreversible operations.",
    "multi_component": "It likely spans more than 3 files or several modules/services.",
    "public_interface": "It changes an API, CLI, file format or schema that other code or clients depend on.",
    "new_dependency": "It adds or replaces a library, framework, service or platform.",
}
SIZE = {"S": 0, "M": 1, "L": 2}
SIZE_NAME = {v: k for k, v in SIZE.items()}


# ---------------------------------------------------------------- normalization

def norm_route(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    r = re.sub(r"[\s_]+", "-", value.strip().lower().lstrip("/").rstrip(".:"))
    if ":" in r:
        r = r.rsplit(":", 1)[1]  # "arch:debug" -> "debug"
    r = ROUTE_ALIASES.get(r, r)
    return r if r in ROUTES else None


def norm_agent(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    a = value.strip().strip("`'\"").lstrip("@")
    if ":" in a:
        a = a.rsplit(":", 1)[1]
    a = re.sub(r"\s*\(.*\)\s*$", "", a)
    a = re.sub(r"[\s_]+", "-", a.strip().lower()).strip("-")
    return AGENT_ALIASES.get(a, a) or None


def norm_signals(raw: Any) -> tuple[dict[str, bool], list[str]]:
    """Booleans for every checklist item (missing = False); also returns unknown keys."""
    raw = raw if isinstance(raw, dict) else {}
    out = {}
    for key in SIGNALS:
        v = raw.get(key, False)
        if isinstance(v, str):
            v = v.strip().lower() in {"true", "yes", "y", "1"}
        out[key] = bool(v)
    return out, sorted(k for k in raw if k not in SIGNALS)


# ---------------------------------------------------------------- deterministic plan

def _writes(route: str, s: dict[str, bool]) -> bool:
    mode = ROUTES[route]["writes"]
    if s["read_only"]:
        return False
    return mode == "always" or (mode == "signal" and s["changes_requested"])


def correct_route(route: str, s: dict[str, bool]) -> tuple[str, list[str]]:
    """Hard precedence rules that a checklist answer makes unambiguous."""
    fixes = []
    if route == "quick-fix" and s["unknown_cause"]:
        fixes.append("route quick-fix → debug: the cause is unknown, so it must be diagnosed before fixing")
        route = "debug"
    if route == "explain" and s["judge_code"]:
        fixes.append("route explain → code-review: the user asks for a verdict on the code, not an explanation")
        route = "code-review"
    if route in ("quick-fix", "implement", "refactor") and s["open_decision"]:
        fixes.append(f"route {route} → architecture-change: an option is still open; decide before building")
        route = "architecture-change"
    if route == "architecture-change" and not s["open_decision"] and s["changes_requested"] and not s["read_only"]:
        fixes.append("route architecture-change → implement: no option is open and the user asks for the change")
        route = "implement"
    if s["read_only"] and route in CHANGE_ROUTES and route != "full-cycle":
        new = "code-review" if s["judge_code"] else "explain"
        fixes.append(f"route {route} → {new}: the request is read-only, so nothing may be changed")
        route = new
    return route, fixes


def compute_difficulty(route: str, s: dict[str, bool]) -> tuple[str, str]:
    """S/M/L from the checklist. Returns (difficulty, reason)."""
    risky = [k for k in ("security", "data_risk", "multi_component", "unknown_cause", "public_interface",
                         "new_dependency", "open_decision") if s[k]]
    if _writes(route, s):
        if s["security"] or s["data_risk"]:
            level, why = 2, "changes touch security or stored data"
        elif s["open_decision"] and s["new_dependency"]:
            level, why = 2, "a platform/dependency decision that will then be implemented (costly to reverse)"
        elif len(risky) >= 3:
            level, why = 2, f"{len(risky)} risk signals"
        elif risky:
            level, why = 1, f"risk signals: {', '.join(risky)}"
        else:
            level, why = 0, "no risk signals"
    else:
        level = 2 if len(risky) >= 3 else 1 if risky else 0
        why = f"read-only work with {len(risky)} risk signal(s)" + (f": {', '.join(risky)}" if risky else "")
    floor = SIZE[ROUTES[route]["floor"]]
    if floor > level:
        level, why = floor, f"{why}; raised to the {route} minimum {SIZE_NAME[floor]}"
    if route in DIRECT_ROUTES:
        level = min(level, 1)  # answered directly: size only affects effort
    return SIZE_NAME[level], why


def core_agents(route: str, size: str, s: dict[str, bool]) -> list[str]:
    """The agents a route needs, in order (mirrors src/workflows/*.md and the gates G2–G5)."""
    big = SIZE[size] >= 1
    writes = _writes(route, s)
    build = (["planner"] if big else []) + ["tester", "coder"] + (["reviewer"] if big else [])
    if route == "quick-fix":
        return ["coder"] + (["tester"] if big else [])
    if route == "debug":
        if not writes:
            return ["debugger"]
        return ["debugger"] + (["tester"] if big else []) + ["coder"] + (["reviewer"] if big else [])
    if route in ("implement", "refactor"):
        return build
    if route == "architecture-change":
        return ["architect", "reviewer"] + (build if writes else [])
    if route == "code-review":
        return ["reviewer"] + (["coder", "tester"] + (["reviewer"] if big else []) if writes else [])
    if route == "verify":
        return ["tester"]
    if route == "document":
        return ["documenter"] + (["reviewer"] if big else [])
    if route == "repo-map":
        return ["explore", "documenter"]
    research = {
        "research-discovery": ["researcher", "claim-checker"],
        "paper-analyze": ["paper-analyst", "claim-checker", "documenter"],
        "paper-compare": ["paper-comparator", "claim-checker", "documenter"],
        "literature-review": ["literature-reviewer", "claim-checker", "documenter"],
        "novelty-check": ["novelty-checker", "claim-checker"],
        "research-proposal": ["proposal-designer", "novelty-checker", "reviewer", "claim-checker", "documenter"],
        "research-cycle": ["researcher", "synthesizer", "novelty-checker", "claim-checker", "documenter"],
    }
    if route in research:
        return research[route]
    if route == "full-cycle":
        return (["researcher", "synthesizer", "novelty-checker", "claim-checker"]
                + (["architect"] if s["open_decision"] else []) + ["planner", "tester", "coder", "reviewer", "documenter"])
    return []  # explain, general-technical, general: explore at most, or answer directly


# optional agents the orchestrator may add on top of the template, and where they go
_OPTIONAL_BY_ROUTE = {
    "verify": {"browser-agent"}, "debug": {"browser-agent"}, "implement": {"browser-agent", "documenter"},
    "refactor": {"documenter"}, "quick-fix": {"browser-agent"}, "architecture-change": {"documenter"},
    "code-review": {"explore"}, "novelty-check": {"researcher"}, "research-proposal": {"researcher"},
    "literature-review": set(), "research-discovery": {"researcher"}, "full-cycle": {"browser-agent"},
}


def build_agents(route: str, size: str, s: dict[str, bool], proposed: list[str]) -> tuple[list[str], list[str]]:
    fixes: list[str] = []
    core = core_agents(route, size, s)
    writes = _writes(route, s)
    seen: list[str] = []
    for raw in proposed:
        a = norm_agent(raw)
        if a is None:
            continue
        if a not in AGENTS:
            fixes.append(f"dropped unknown agent '{raw}'")
            continue
        if a not in seen:
            seen.append(a)
    front = ["explore"] if "explore" in seen and route not in DIRECT_ROUTES and "explore" not in core else []
    allowed_extra = _OPTIONAL_BY_ROUTE.get(route, set())
    back = [a for a in seen if a in allowed_extra and a not in core and a not in front]
    if not writes:
        back = [a for a in back if a not in WRITERS or ROUTES[route]["writes"] == "research"]
    final = front + core + back
    if route == "verify" and "browser-agent" in back and "tester" not in seen:
        final = front + ["browser-agent"]  # a pure browser check needs no test runner
    dropped = [a for a in seen if a not in final]
    added = [a for a in core if a not in seen]
    if dropped:
        reason = "read-only request" if not writes and any(a in WRITERS for a in dropped) else f"not part of {route}"
        fixes.append(f"removed {', '.join(dropped)} ({reason})")
    if added:
        fixes.append(f"added required {', '.join(added)} for {route} {size}")
    if seen and [a for a in final if a in seen] != [a for a in seen if a in final]:
        fixes.append("reordered agents to the workflow order (tests before code, review after code)")
    return final, fixes


def check_plan(draft: dict[str, Any], explicit_workflow: bool = False) -> dict[str, Any]:
    """Pure function: normalize, correct and complete a routing draft."""
    fixes: list[str] = []
    route = norm_route(draft.get("route"))
    if route is None:
        raise ToolError(f"unknown route {draft.get('route')!r}", data={"routes": sorted(ROUTES)})
    if draft.get("route") != route:
        fixes.append(f"route name '{draft.get('route')}' normalized to '{route}'")
    signals, unknown = norm_signals(draft.get("signals"))
    if unknown:
        fixes.append(f"ignored unknown signals: {', '.join(unknown)}")
    if not explicit_workflow:
        route, rf = correct_route(route, signals)
        fixes += rf
    size, why = compute_difficulty(route, signals)
    agents, af = build_agents(route, size, signals, list(draft.get("agents") or []))
    fixes += af
    claimed = str(draft.get("difficulty") or "").strip().upper()[:1]
    if claimed in SIZE and claimed != size:
        fixes.append(f"difficulty {claimed} → {size} ({why})")
    clarify = draft.get("clarify")
    clarify = clarify.strip() if isinstance(clarify, str) and clarify.strip().lower() not in {"", "null", "none"} else None
    assumptions = [str(a) for a in draft.get("assumptions") or [] if str(a).strip()]
    return {
        "route": route,
        "difficulty": size,
        "difficulty_reason": why,
        "agents": agents,
        "clarify": clarify,
        "assumptions": assumptions,
        "read_only": not _writes(route, signals) and ROUTES[route]["writes"] != "research",
        "signals": signals,
        "fixes": fixes,
    }


# ---------------------------------------------------------------- self-consistency voting

def router_prompt() -> str:
    routes = "\n".join(f"- {name}: {r['use']}" for name, r in ROUTES.items())
    checks = "\n".join(f"- {k}: {q}" for k, q in SIGNALS.items())
    return (
        "You classify one request for a team of software-engineering and research agents.\n\n"
        f"Routes:\n{routes}\n\n"
        "Precedence when several fit: a verdict on existing code → code-review; failing behaviour with unknown cause → "
        "debug; an open choice between options → architecture-change; same behaviour, new structure → refactor; new "
        "behaviour → implement; tiny obvious change → quick-fix; questions not about a specific codebase → "
        "general-technical / general.\n\n"
        f"Checklist (answer each true/false about the request):\n{checks}\n\n"
        'Reply with only JSON: {"route": "<route>", "signals": {<every checklist key>: true|false}}'
    )


def extract_json_object(text: str) -> dict[str, Any] | None:
    """First balanced {...} that parses as a JSON object."""
    if not text:
        return None
    for start in [m.start() for m in re.finditer(r"\{", text)]:
        depth, in_str, esc = 0, False, False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                esc = (ch == "\\") and not esc
                if ch == '"' and not esc:
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break
                    if isinstance(obj, dict):
                        return obj
                    break
    return None


def vote(draft: dict[str, Any], samples: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Majority vote of route and of each signal over draft + samples; ties keep the draft (it saw the whole
    conversation, the samples only the request)."""
    ballots = [draft] + samples
    routes = [norm_route(b.get("route")) for b in ballots]
    counts = Counter(r for r in routes if r)
    draft_route = routes[0]
    best_n = max(counts.values()) if counts else 0
    leaders = [r for r, n in counts.items() if n == best_n]
    route = draft_route if (draft_route in leaders or not leaders) else leaders[0]
    sig_ballots = [norm_signals(b.get("signals"))[0] for b in ballots]
    signals, changed = {}, []
    for key in SIGNALS:
        yes = sum(sb[key] for sb in sig_ballots)
        no = len(sig_ballots) - yes
        value = sig_ballots[0][key] if yes == no else yes > no
        if value != sig_ballots[0][key]:
            changed.append(f"{key} → {str(value).lower()} ({yes}/{len(sig_ballots)} said true)")
        signals[key] = value
    merged = dict(draft, route=route or draft.get("route"), signals=signals)
    agreement = round(counts.get(route, 0) / len(ballots), 2) if route else 0.0
    info = {
        "ballots": len(ballots),
        "route_votes": dict(counts),
        "route_agreement": agreement,
        "signal_changes": changed,
    }
    if route and route != draft_route:
        info["route_change"] = f"{draft_route} → {route} (majority of {len(ballots)})"
    return merged, info


async def sample_routes(request: str, n: int, model: str, cfg: Config) -> tuple[list[dict[str, Any]], list[str]]:
    from .llm import local_llm

    async def one() -> dict[str, Any] | None:
        res = await local_llm(request, system=router_prompt(), model=model, max_tokens=4096, temperature=0.7, cfg=cfg)
        return extract_json_object(res.get("text") or "")

    results = await asyncio.gather(*(one() for _ in range(n)), return_exceptions=True)
    samples, errors = [], []
    for r in results:
        if isinstance(r, BaseException):
            errors.append(f"{type(r).__name__}: {getattr(r, 'message', r)}")
        elif r is None or norm_route(r.get("route")) is None:
            errors.append("a sample returned no usable route")
        else:
            samples.append(r)
    return samples, errors


def default_samples() -> int:
    try:
        return max(0, min(6, int(os.environ.get("ARCH_ROUTE_SAMPLES", "0"))))
    except ValueError:
        return 0


async def plan_route(args: dict[str, Any], cfg: Config | None = None) -> dict[str, Any]:
    cfg = cfg or Config.from_env()
    draft = {k: args.get(k) for k in ("route", "difficulty", "agents", "clarify", "assumptions", "signals")}
    explicit = bool(args.get("explicit_workflow"))
    n = args.get("samples")
    n = default_samples() if n is None else int(n)
    vote_info: dict[str, Any] = {"ballots": 1, "note": "no voting on this plan"}
    if n > 0 and not explicit and norm_route(draft.get("route")) not in DIRECT_ROUTES:
        model = os.environ.get("ARCH_ROUTE_MODEL", "").strip() or "qwen3.6-35b"
        samples, errors = await sample_routes(args["request"], n, model, cfg)
        draft, vote_info = vote(draft, samples)
        if errors:
            vote_info["sample_errors"] = errors
    plan = check_plan(draft, explicit_workflow=explicit)
    voted = ([f"vote: route {vote_info['route_change']}"] if vote_info.get("route_change") else []) + [
        f"vote: {c}" for c in vote_info.get("signal_changes", [])]
    plan["fixes"] = voted + plan["fixes"]
    plan["vote"] = vote_info
    plan["ambiguous"] = vote_info.get("ballots", 1) >= 3 and vote_info.get("route_agreement", 1) < 0.5
    final = {k: plan[k] for k in ("route", "difficulty", "agents", "clarify", "assumptions")}
    plan["final_json"] = json.dumps(final, ensure_ascii=False)
    plan["instructions"] = (
        "Follow this plan: run the agents in this order and apply the gates for this difficulty. "
        + ("Corrections were applied; accept them unless you have concrete evidence against one (then say why). "
           if plan["fixes"] else "")
        + ("The votes disagreed on the route: if the candidate routes would lead to materially different work, ask "
           "the user one batched question before starting. " if plan["ambiguous"] else "")
        + ("Read-only: no agent may edit files." if plan["read_only"] else "")
    ).strip()
    return plan
