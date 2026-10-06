"""Unit tests for plan_route (deterministic part + vote aggregation; no LLM calls)."""
import asyncio
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arch_tools import routing as R  # noqa: E402
from arch_tools.net import ToolError  # noqa: E402
from arch_tools.tools import call_tool, validate_arguments  # noqa: E402

REPO = Path(__file__).resolve().parents[3]


def sig(**on):
    s = {k: False for k in R.SIGNALS}
    s.update(on)
    return s


def plan(route, agents=(), **on):
    return R.check_plan({"route": route, "agents": list(agents), "signals": sig(**on)})


# ---------------- consistency with src/

def test_agent_vocabulary_matches_src_agents():
    names = {p.stem for p in (REPO / "src/agents").glob("*.md")} - {"orchestrator", "memory-manager"}
    assert set(R.AGENTS) == names


def test_routes_match_orchestrator_table_and_workflows():
    text = (REPO / "src/agents/orchestrator.md").read_text()
    table = set(re.findall(r"^\| ([a-z-]+) \| ", text, re.M)) - {"Route", "Gate"}
    workflows = {p.stem for p in (REPO / "src/workflows").glob("*.md")}
    assert table <= set(R.ROUTES)
    assert workflows <= set(R.ROUTES)


# ---------------- route corrections

def test_quick_fix_with_unknown_cause_becomes_debug():
    p = plan("quick-fix", ["coder"], unknown_cause=True, changes_requested=True)
    assert p["route"] == "debug" and p["agents"][0] == "debugger"


def test_question_judging_code_goes_to_code_review():
    p = plan("explain", ["explain"], judge_code=True, security=True, read_only=True)
    assert p["route"] == "code-review" and p["agents"] == ["reviewer"]
    assert any("unknown agent" in f for f in p["fixes"])


def test_open_decision_turns_implement_into_architecture():
    p = plan("implement", ["coder"], open_decision=True, changes_requested=True, new_dependency=True)
    assert p["route"] == "architecture-change"
    assert p["agents"][:2] == ["architect", "reviewer"] and "coder" in p["agents"]
    assert p["difficulty"] == "L"


def test_settled_architecture_with_changes_becomes_implement():
    p = plan("architecture-change", ["architect", "coder"], changes_requested=True, multi_component=True)
    assert p["route"] == "implement" and "architect" not in p["agents"]


def test_explicit_workflow_keeps_route():
    p = R.check_plan({"route": "quick-fix", "signals": sig(unknown_cause=True)}, explicit_workflow=True)
    assert p["route"] == "quick-fix"


# ---------------- read-only

def test_read_only_never_gets_writers():
    p = plan("debug", ["debugger", "tester", "coder", "planner"], read_only=True, unknown_cause=True)
    assert p["agents"] == ["debugger"] and p["read_only"]


def test_read_only_implement_falls_back_to_explain():
    p = plan("implement", ["explore", "coder"], read_only=True, multi_component=True)
    assert p["route"] == "explain" and p["agents"] == ["explore"]


def test_research_routes_keep_documenter():
    p = plan("paper-analyze", ["paper-analyst"])
    assert p["agents"] == ["paper-analyst", "claim-checker", "documenter"] and not p["read_only"]


# ---------------- difficulty checklist

@pytest.mark.parametrize(
    "route,on,expected",
    [
        ("quick-fix", {}, "S"),
        ("implement", {}, "M"),  # route floor
        ("implement", {"security": True}, "L"),
        ("refactor", {"data_risk": True}, "L"),
        ("architecture-change", {"changes_requested": True, "open_decision": True, "new_dependency": True}, "L"),
        ("architecture-change", {"open_decision": True, "data_risk": True}, "M"),  # recommend only, 2 signals
        ("code-review", {"read_only": True, "judge_code": True, "security": True}, "M"),
        ("verify", {}, "S"),
        ("research-cycle", {}, "L"),
        ("general-technical", {"open_decision": True, "new_dependency": True, "multi_component": True}, "M"),
    ],
)
def test_difficulty(route, on, expected):
    assert R.compute_difficulty(route, sig(**on))[0] == expected


# ---------------- agent templates and gates

def test_implement_m_has_all_gates_in_order():
    p = plan("implement", ["coder"], changes_requested=True, multi_component=True)
    assert p["agents"] == ["planner", "tester", "coder", "reviewer"]


def test_refactor_keeps_explore_first_and_drops_architect():
    p = plan("refactor", ["architect", "coder", "explore"], multi_component=True)
    assert p["agents"] == ["explore", "planner", "tester", "coder", "reviewer"]
    assert any("architect" in f for f in p["fixes"])


def test_review_and_fix_reviews_first_then_fixes():
    p = plan("code-review", ["reviewer", "coder"], changes_requested=True, judge_code=True, security=True)
    a = p["agents"]
    assert a[0] == "reviewer" and a.index("coder") > 0 and a[-1] == "reviewer"


def test_debug_small_skips_review():
    p = plan("debug", ["debugger", "coder"], changes_requested=True)
    assert p["difficulty"] == "M"  # debug floor
    assert p["agents"] == ["debugger", "tester", "coder", "reviewer"]


def test_browser_only_verify():
    p = plan("verify", ["browser-agent"])
    assert p["agents"] == ["browser-agent"]


def test_aliases_and_prefixes_normalized():
    p = R.check_plan({"route": "architecture", "agents": ["arch:architect", "@reviewer"], "signals": sig(open_decision=True)})
    assert p["route"] == "architecture-change" and p["agents"] == ["architect", "reviewer"]


def test_unknown_route_is_an_error():
    with pytest.raises(ToolError):
        R.check_plan({"route": "do-stuff", "signals": sig()})


# ---------------- voting

def test_vote_majority_overrides_draft_route_and_signals():
    draft = {"route": "architecture-change", "signals": sig(open_decision=True)}
    samples = [{"route": "implement", "signals": sig(security=True)}, {"route": "implement", "signals": sig(security=True)}]
    merged, info = R.vote(draft, samples)
    assert merged["route"] == "implement" and merged["signals"]["security"] and not merged["signals"]["open_decision"]
    assert info["route_agreement"] == 0.67 and "route_change" in info


def test_vote_tie_keeps_draft():
    draft = {"route": "debug", "signals": sig(unknown_cause=True)}
    samples = [{"route": "quick-fix", "signals": sig()}]
    merged, _ = R.vote(draft, samples)
    assert merged["route"] == "debug" and merged["signals"]["unknown_cause"]


def test_three_way_disagreement_is_ambiguous(monkeypatch):
    async def fake(request, n, model, cfg):
        return [{"route": "implement", "signals": {}}, {"route": "refactor", "signals": {}}], []

    monkeypatch.setattr(R, "sample_routes", fake)
    out = asyncio.run(R.plan_route({"request": "x", "route": "debug", "signals": sig(), "samples": 2}))
    assert out["ambiguous"] and out["route"] == "debug" and "votes disagreed" in out["instructions"]


def test_no_voting_by_default(monkeypatch):
    monkeypatch.delenv("ARCH_ROUTE_SAMPLES", raising=False)
    out = asyncio.run(call_tool("plan_route", {"request": "fix typo", "route": "quick-fix", "signals": sig(changes_requested=True)}))
    assert out["vote"]["ballots"] == 1 and out["agents"] == ["coder"]
    assert '"route": "quick-fix"' in out["final_json"]


def test_extract_json_object_from_noisy_text():
    text = 'Sure. ```json\n{"route": "debug", "signals": {"unknown_cause": true}, "note": "a } brace"}\n```'
    assert R.extract_json_object(text)["route"] == "debug"
    assert R.extract_json_object("no json here") is None


def test_schema_requires_full_checklist():
    with pytest.raises(ToolError):
        validate_arguments("plan_route", {"request": "x", "route": "debug", "signals": {"unknown_cause": True}})


def test_repeated_calls_reuse_votes_and_say_stop(monkeypatch):
    calls = {"n": 0}

    async def fake(request, n, model, cfg):
        calls["n"] += 1
        return [{"route": "architecture-change", "signals": {"open_decision": True}}] * n, []

    monkeypatch.setattr(R, "sample_routes", fake)
    monkeypatch.setattr(R, "_SEEN", {})
    args = {"request": "Postgres queue or Kafka?", "route": "architecture-change", "signals": sig(open_decision=True),
            "samples": 2}
    first = asyncio.run(R.plan_route(dict(args)))
    second = asyncio.run(R.plan_route(dict(args)))
    third = asyncio.run(R.plan_route(dict(args)))
    assert calls["n"] == 1  # votes sampled once per request
    assert "repeat_call" not in first and second["repeat_call"] == 2
    assert third["instructions"].startswith("STOP calling plan_route")
    assert first["final_json"] == third["final_json"]


@pytest.mark.parametrize("value,expected", [(None, False), ("off", False), ("on", True), ("default", None)])
def test_route_thinking_env(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv("ARCH_ROUTE_THINKING", raising=False)
    else:
        monkeypatch.setenv("ARCH_ROUTE_THINKING", value)
    assert R.route_thinking() is expected
