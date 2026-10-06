"""LLM-free detection of clarifying questions and stated assumptions (EN/ES/JA).

Heuristics, deliberately conservative: a clarifying question is a question
addressed to the user ("could you", "do you want", "should I", ...), not any
sentence that ends with "?". Both detectors return the matching snippets so a
human can audit the decision in the trace.
"""

from __future__ import annotations

import re

_QUESTION_SPLIT_RE = re.compile(r"(?<=[?？])|\n")
_USER_DIRECTED_RE = re.compile(
    r"\b(you|your|should i|shall i|do we|should we|would it|which one|prefer|confirm|clarif)"
    r"|¿|usted|quieres|prefieres|deseas|debo|confirma"
    r"|ますか|でしょうか|ですか|ください|教えて|よろしい",
    re.IGNORECASE,
)
_QUESTION_SECTION_RE = re.compile(
    r"^\s{0,3}(?:#{1,6}\s*|\*\*|__)?\s*(?:clarifying questions?|open questions? for you|questions? for you|questions?"
    r"|preguntas?|質問|確認事項)\s*(?:\*\*|__)?\s*[:：]?\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_ASSUMPTION_RE = re.compile(
    r"\bassum(?:e|ed|es|ing|ption|ptions)\b|\bi(?:'ll| will) take it that\b|\bi interpreted\b|\bmy interpretation\b"
    r"|\bsupuest[oa]s?\b|\basum(?:o|í|imos|iendo|iré|ido)\b|\bsuposici[oó]n(?:es)?\b"
    r"|前提|仮定|想定",
    re.IGNORECASE,
)


def clarifying_questions(text: str) -> list[str]:
    """Question sentences that are addressed to the user."""
    found: list[str] = []
    for chunk in _QUESTION_SPLIT_RE.split(text or ""):
        chunk = chunk.strip()
        if not chunk:
            continue
        is_question = chunk.endswith(("?", "？")) or chunk.startswith("¿")
        if is_question and _USER_DIRECTED_RE.search(chunk):
            found.append(chunk[-300:])
    if not found and _QUESTION_SECTION_RE.search(text or ""):
        found.append("<questions section>")
    return found


def stated_assumptions(text: str) -> list[str]:
    snippets = []
    for match in _ASSUMPTION_RE.finditer(text or ""):
        lo = max(0, match.start() - 60)
        snippets.append(text[lo : match.end() + 80].replace("\n", " "))
    return snippets


def asks_or_states_assumptions(text: str) -> dict:
    questions = clarifying_questions(text)
    assumptions = stated_assumptions(text)
    return {
        "ok": bool(questions or assumptions),
        "asked": bool(questions),
        "stated_assumptions": bool(assumptions),
        "question_snippets": questions[:5],
        "assumption_snippets": assumptions[:5],
    }
