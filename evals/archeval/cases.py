"""Loading and validation of the three case files.

Validation is strict on purpose: a typo in a case file (unknown key, unknown
agent, a YAML `no` that silently became `False`) would otherwise turn into a
silently wrong eval.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from . import AGENTS, CODING_DIR, DIFFICULTIES, RESEARCH_DIR, ROUTES, ROUTING_DIR

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class CaseError(ValueError):
    pass


def _load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict) or not isinstance(data.get("cases"), list):
        raise CaseError(f"{path}: expected a mapping with a 'cases' list")
    return data


def _as_list(value: Any, field: str, cid: str) -> list:
    if value is None:
        return []
    if isinstance(value, (str, int, float, bool)):
        value = [value]
    if not isinstance(value, list):
        raise CaseError(f"{cid}: '{field}' must be a string or a list")
    return value


def _check_keys(case: dict, allowed: set[str], cid: str) -> None:
    unknown = set(case) - allowed
    if unknown:
        raise CaseError(f"{cid}: unknown keys {sorted(unknown)} (allowed: {sorted(allowed)})")


def _check_id(case: dict, seen: set[str]) -> str:
    cid = case.get("id")
    if not isinstance(cid, str) or not _ID_RE.match(cid):
        raise CaseError(f"invalid case id {cid!r} (lowercase letters, digits and hyphens)")
    if cid in seen:
        raise CaseError(f"duplicate case id {cid!r}")
    seen.add(cid)
    return cid


def _keyword_groups(value: Any, where: str) -> list[list[str]]:
    if not isinstance(value, list) or not value:
        raise CaseError(f"{where}: expected a non-empty list of keyword groups")
    groups = []
    for group in value:
        if isinstance(group, str):
            group = [group]
        if not isinstance(group, list) or not group:
            raise CaseError(f"{where}: each group must be a non-empty list of strings")
        for syn in group:
            if not isinstance(syn, str) or not syn.strip():
                raise CaseError(
                    f"{where}: synonym {syn!r} is not a non-empty string "
                    "(quote YAML words like yes/no/on/off/null)"
                )
        groups.append(list(group))
    return groups


# --------------------------------------------------------------------------- routing

ROUTING_KEYS = {
    "id", "prompt", "route", "difficulty", "must_include", "must_not_include", "order",
    "expect_clarify", "min_assumptions", "tags", "notes",
}


def validate_routing_case(case: dict, seen: set[str]) -> dict:
    if not isinstance(case, dict):
        raise CaseError(f"routing case must be a mapping, got {case!r}")
    cid = _check_id(case, seen)
    _check_keys(case, ROUTING_KEYS, cid)
    prompt = case.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise CaseError(f"{cid}: 'prompt' is required")
    routes = _as_list(case.get("route"), "route", cid)
    if not routes:
        raise CaseError(f"{cid}: 'route' is required")
    for r in routes:
        if r not in ROUTES:
            raise CaseError(f"{cid}: unknown route {r!r}")
    diffs = [str(d) for d in _as_list(case.get("difficulty"), "difficulty", cid)]
    for d in diffs:
        if d not in DIFFICULTIES:
            raise CaseError(f"{cid}: unknown difficulty {d!r}")
    must = _as_list(case.get("must_include"), "must_include", cid)
    must_not = _as_list(case.get("must_not_include"), "must_not_include", cid)
    for a in must + must_not:
        if a not in AGENTS:
            raise CaseError(f"{cid}: unknown agent {a!r}")
    if set(must) & set(must_not):
        raise CaseError(f"{cid}: agents both required and forbidden: {sorted(set(must) & set(must_not))}")
    order = case.get("order") or []
    if not isinstance(order, list):
        raise CaseError(f"{cid}: 'order' must be a list of [before, after] pairs")
    for pair in order:
        if not (isinstance(pair, list) and len(pair) == 2 and all(a in AGENTS for a in pair)):
            raise CaseError(f"{cid}: bad order pair {pair!r}")
        if pair[1] in must and pair[0] in must_not:
            raise CaseError(f"{cid}: order {pair} requires a forbidden agent")
    clarify = case.get("expect_clarify")
    if clarify not in (None, True, False):
        raise CaseError(f"{cid}: expect_clarify must be true, false or omitted")
    min_assumptions = case.get("min_assumptions")
    if min_assumptions is not None and (not isinstance(min_assumptions, int) or min_assumptions < 0):
        raise CaseError(f"{cid}: min_assumptions must be a non-negative integer")
    return {
        "id": cid,
        "prompt": prompt.strip(),
        "route": routes,
        "difficulty": diffs,
        "must_include": must,
        "must_not_include": must_not,
        "order": [list(p) for p in order],
        "expect_clarify": clarify,
        "min_assumptions": min_assumptions,
        "tags": [str(t) for t in _as_list(case.get("tags"), "tags", cid)],
        "notes": case.get("notes") or "",
    }


def load_routing_cases(path: Path | None = None) -> list[dict]:
    path = path or ROUTING_DIR / "cases.yaml"
    data = _load_yaml(path)
    seen: set[str] = set()
    return [validate_routing_case(c, seen) for c in data["cases"]]


# --------------------------------------------------------------------------- coding

CODING_KINDS = ("bugfix", "feature", "refactor", "analyze-only", "underspecified")
CODING_REQUIREMENTS = ("hidden_tests", "visible_tests", "no_changes", "answer_mentions", "clarify_or_assumptions")
CODING_KEYS = {
    "id", "dir", "kind", "difficulty", "visible_before", "hidden_before", "require",
    "answer_must_mention", "answer_should_mention", "timeout", "tags", "notes",
}


def validate_coding_case(case: dict, seen: set[str], base_dir: Path) -> dict:
    if not isinstance(case, dict):
        raise CaseError(f"coding case must be a mapping, got {case!r}")
    cid = _check_id(case, seen)
    _check_keys(case, CODING_KEYS, cid)
    fixture = base_dir / str(case.get("dir") or cid)
    if not fixture.is_dir():
        raise CaseError(f"{cid}: fixture directory {fixture} not found")
    for required in ("TASK.md", "hidden_tests", "_reference"):
        if not (fixture / required).exists():
            raise CaseError(f"{cid}: fixture is missing {required}")
    if not list((fixture / "hidden_tests").glob("test_*.py")):
        raise CaseError(f"{cid}: hidden_tests/ has no test_*.py files")
    kind = case.get("kind")
    if kind not in CODING_KINDS:
        raise CaseError(f"{cid}: kind must be one of {CODING_KINDS}")
    for key in ("visible_before", "hidden_before"):
        if case.get(key) not in ("pass", "fail"):
            raise CaseError(f"{cid}: {key} must be 'pass' or 'fail'")
    require = _as_list(case.get("require"), "require", cid)
    if not require:
        raise CaseError(f"{cid}: 'require' must list at least one check")
    for r in require:
        if r not in CODING_REQUIREMENTS:
            raise CaseError(f"{cid}: unknown requirement {r!r}")
    must_mention = case.get("answer_must_mention")
    if "answer_mentions" in require:
        must_mention = _keyword_groups(must_mention, f"{cid}.answer_must_mention")
    elif must_mention:
        raise CaseError(f"{cid}: answer_must_mention given but 'answer_mentions' not required")
    should = case.get("answer_should_mention")
    timeout = case.get("timeout")
    if timeout is not None and (not isinstance(timeout, (int, float)) or timeout <= 0):
        raise CaseError(f"{cid}: timeout must be a positive number of seconds")
    return {
        "id": cid,
        "path": str(fixture),
        "kind": kind,
        "difficulty": case.get("difficulty"),
        "visible_before": case["visible_before"],
        "hidden_before": case["hidden_before"],
        "require": require,
        "answer_must_mention": must_mention or [],
        "answer_should_mention": _keyword_groups(should, f"{cid}.answer_should_mention") if should else [],
        "timeout": timeout,
        "tags": [str(t) for t in _as_list(case.get("tags"), "tags", cid)],
        "notes": case.get("notes") or "",
    }


def load_coding_cases(path: Path | None = None) -> list[dict]:
    path = path or CODING_DIR / "cases.yaml"
    data = _load_yaml(path)
    seen: set[str] = set()
    return [validate_coding_case(c, seen, path.parent) for c in data["cases"]]


# --------------------------------------------------------------------------- research

RESEARCH_KEYS = {
    "id", "area", "question", "key_points", "min_citations", "min_coverage", "window",
    "reference_sources", "tags", "notes",
}
KEY_POINT_KEYS = {"id", "description", "all_of", "window"}
_ARXIV_ID_RE = re.compile(r"^\d{4}\.\d{4,5}$")


def validate_research_case(case: dict, seen: set[str], defaults: dict) -> dict:
    if not isinstance(case, dict):
        raise CaseError(f"research case must be a mapping, got {case!r}")
    cid = _check_id(case, seen)
    _check_keys(case, RESEARCH_KEYS, cid)
    question = case.get("question")
    if not isinstance(question, str) or not question.strip():
        raise CaseError(f"{cid}: 'question' is required")
    window = case.get("window", defaults.get("window", 600))
    kps = case.get("key_points")
    if not isinstance(kps, list) or not 1 <= len(kps) <= 10:
        raise CaseError(f"{cid}: key_points must be a list of 1-10 items")
    kp_ids: set[str] = set()
    key_points = []
    for kp in kps:
        if not isinstance(kp, dict):
            raise CaseError(f"{cid}: key point must be a mapping")
        unknown = set(kp) - KEY_POINT_KEYS
        if unknown:
            raise CaseError(f"{cid}: key point has unknown keys {sorted(unknown)}")
        kid = kp.get("id")
        if not isinstance(kid, str) or not _ID_RE.match(kid) or kid in kp_ids:
            raise CaseError(f"{cid}: key point id {kid!r} missing, invalid or duplicated")
        kp_ids.add(kid)
        if not isinstance(kp.get("description"), str) or not kp["description"].strip():
            raise CaseError(f"{cid}.{kid}: description is required")
        kp_window = kp.get("window", window)
        if kp_window is not None and (not isinstance(kp_window, int) or kp_window <= 0):
            raise CaseError(f"{cid}.{kid}: window must be a positive integer or null")
        key_points.append({
            "id": kid,
            "description": " ".join(kp["description"].split()),
            "all_of": _keyword_groups(kp.get("all_of"), f"{cid}.{kid}.all_of"),
            "window": kp_window,
        })
    min_citations = case.get("min_citations", defaults.get("min_citations", 0))
    if not isinstance(min_citations, int) or min_citations < 0:
        raise CaseError(f"{cid}: min_citations must be a non-negative integer")
    min_coverage = case.get("min_coverage", defaults.get("min_coverage", 0.6))
    if not isinstance(min_coverage, (int, float)) or not 0 < min_coverage <= 1:
        raise CaseError(f"{cid}: min_coverage must be in (0, 1]")
    refs = case.get("reference_sources") or []
    for ref in refs:
        if not isinstance(ref, dict) or not _ARXIV_ID_RE.match(str(ref.get("arxiv", ""))) or not ref.get("title"):
            raise CaseError(f"{cid}: reference_sources entries need 'arxiv' (new-style ID) and 'title'")
    return {
        "id": cid,
        "area": case.get("area") or "",
        "question": " ".join(question.split()),
        "key_points": key_points,
        "min_citations": min_citations,
        "min_coverage": float(min_coverage),
        "reference_sources": [{"arxiv": str(r["arxiv"]), "title": str(r["title"])} for r in refs],
        "tags": [str(t) for t in _as_list(case.get("tags"), "tags", cid)],
        "notes": case.get("notes") or "",
    }


def load_research_cases(path: Path | None = None) -> tuple[list[dict], dict]:
    """Returns (cases, defaults). Defaults carry suite-level settings such as prompt_suffix."""
    path = path or RESEARCH_DIR / "cases.yaml"
    data = _load_yaml(path)
    defaults = data.get("defaults") or {}
    if not isinstance(defaults, dict):
        raise CaseError(f"{path}: 'defaults' must be a mapping")
    seen: set[str] = set()
    return [validate_research_case(c, seen, defaults) for c in data["cases"]], defaults


def select(cases: list[dict], ids: list[str] | None) -> list[dict]:
    if not ids:
        return cases
    known = {c["id"]: c for c in cases}
    return [known[i] for i in ids if i in known]
