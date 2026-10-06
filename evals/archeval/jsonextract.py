"""Robust extraction of JSON from agent output.

Two jobs:
* unwrap the launcher's stdout (Claude Code `--json` result envelope, or plain text);
* find the ROUTE-ONLY object inside prose, ```json fences, or slightly broken JSON.
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass, field
from typing import Any

from .textutil import strip_ansi

_FENCE_RE = re.compile(r"```[ \t]*([A-Za-z0-9_+.-]*)[^\n]*\n(.*?)(?:```|\Z)", re.S)
_TRAILING_COMMA_RE = re.compile(r",\s*([}\]])")
_SMART_QUOTES = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'"})
_PY_LITERALS_RE = re.compile(r"\b(true|false|null)\b")

# Keys copied from a Claude Code result envelope into the trace's `usage` field.
ENVELOPE_USAGE_KEYS = (
    "total_cost_usd",
    "cost_usd",
    "usage",
    "modelUsage",
    "num_turns",
    "duration_ms",
    "duration_api_ms",
    "is_error",
    "subtype",
    "session_id",
)


def loads_lenient(text: str) -> Any | None:
    """json.loads, then a few repairs (trailing commas, smart quotes, Python literals)."""
    text = text.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except (ValueError, RecursionError):
        pass
    repaired = _TRAILING_COMMA_RE.sub(r"\1", text.translate(_SMART_QUOTES))
    try:
        return json.loads(repaired)
    except (ValueError, RecursionError):
        pass
    py = _PY_LITERALS_RE.sub(lambda m: {"true": "True", "false": "False", "null": "None"}[m.group(1)], repaired)
    try:
        value = ast.literal_eval(py)
    except (ValueError, SyntaxError, TypeError, MemoryError, RecursionError):
        return None
    return value if isinstance(value, (dict, list)) else None


def _match_brace(text: str, start: int) -> int | None:
    """Index one past the brace matching text[start] == '{', honouring quoted strings."""
    depth = 0
    quote: str | None = None
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if quote:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                quote = None
            continue
        if ch in "\"'":
            # An apostrophe directly between letters is prose ("don't"), not a quote.
            if ch == "'" and 0 < i < len(text) - 1 and text[i - 1].isalnum() and text[i + 1].isalnum():
                continue
            quote = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i + 1
    return None


def iter_objects(text: str) -> list[Any]:
    """All parseable `{...}` objects in text, outermost first; nested ones only if the outer fails."""
    found: list[Any] = []
    i = 0
    while True:
        start = text.find("{", i)
        if start < 0:
            break
        end = _match_brace(text, start)
        if end is not None:
            obj = loads_lenient(text[start:end])
            if isinstance(obj, dict):
                found.append(obj)
                i = end
                continue
        i = start + 1
    return found


def _route_objects(obj: Any, depth: int = 0) -> list[dict]:
    """Route objects in a parsed value, looking inside string values (e.g. an envelope's `result`)."""
    if depth > 3:
        return []
    out: list[dict] = []
    if isinstance(obj, dict):
        if "route" in obj:
            return [obj]
        for value in obj.values():
            if isinstance(value, str) and "route" in value:
                found, _ = extract_route_json(value, _depth=depth + 1)
                if found is not None:
                    out.append(found)
            elif isinstance(value, (dict, list)):
                out.extend(_route_objects(value, depth + 1))
    elif isinstance(obj, list):
        for item in obj:
            out.extend(_route_objects(item, depth + 1))
    return out


def extract_route_json(text: str, _depth: int = 0) -> tuple[dict | None, str | None]:
    """Return (route_object, error). Prefers the last fenced block, then the last inline object."""
    if not text or not text.strip():
        return None, "empty output"
    text = strip_ansi(text)
    fenced: list[dict] = []
    for match in _FENCE_RE.finditer(text):
        body = match.group(2)
        parsed = loads_lenient(body)
        candidates = _route_objects(parsed, _depth) if parsed is not None else []
        if not candidates:
            for obj in iter_objects(body):
                candidates.extend(_route_objects(obj, _depth))
        fenced.extend(candidates)
    if fenced:
        return fenced[-1], None
    inline: list[dict] = []
    whole = loads_lenient(text)
    if whole is not None:
        inline.extend(_route_objects(whole, _depth))
    if not inline:
        for obj in iter_objects(text):
            inline.extend(_route_objects(obj, _depth))
    if inline:
        return inline[-1], None
    return None, "no JSON object with a 'route' key found"


@dataclass
class LauncherOutput:
    """The launcher's stdout split into the answer text and run metadata."""

    answer_text: str
    envelope: dict | None = None
    usage: dict = field(default_factory=dict)
    format: str = "text"  # "claude-json" | "text"


def _is_envelope(obj: Any) -> bool:
    return isinstance(obj, dict) and (obj.get("type") == "result" or ("result" in obj and ("num_turns" in obj or "total_cost_usd" in obj or "session_id" in obj or "duration_ms" in obj)))


def parse_launcher_stdout(stdout: str) -> LauncherOutput:
    """Unwrap Claude Code's result JSON when present; otherwise the stdout is the answer.

    Handles a single object, an array of messages (`--verbose`), JSON lines, and
    leading log noise before the JSON.
    """
    text = strip_ansi(stdout or "").strip()
    envelope: dict | None = None
    parsed = None
    try:
        parsed = json.loads(text) if text else None
    except ValueError:
        parsed = None
    if _is_envelope(parsed):
        envelope = parsed
    elif isinstance(parsed, list):
        for item in reversed(parsed):
            if _is_envelope(item):
                envelope = item
                break
    if envelope is None and text:
        for line in reversed(text.splitlines()):
            line = line.strip()
            if not (line.startswith("{") and line.endswith("}")):
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if _is_envelope(obj):
                envelope = obj
                break
    if envelope is None:
        return LauncherOutput(answer_text=text)
    result = envelope.get("result")
    answer = result if isinstance(result, str) else ("" if result is None else json.dumps(result))
    usage = {k: envelope[k] for k in ENVELOPE_USAGE_KEYS if k in envelope}
    slim = {k: v for k, v in envelope.items() if k != "result"}
    return LauncherOutput(answer_text=answer, envelope=slim, usage=usage, format="claude-json")


def cost_of(usage: dict) -> float | None:
    for key in ("total_cost_usd", "cost_usd"):
        value = usage.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    return None
