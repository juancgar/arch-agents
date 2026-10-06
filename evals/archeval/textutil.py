"""Small text helpers shared by the scorers."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Sequence

_ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[@-Z\\-_]")
_DASHES_RE = re.compile(r"[-_‐‑‒–—−]+")
_SPACES_RE = re.compile(r"\s+")


def strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def truncate(text: str | None, limit: int) -> str | None:
    """Cap very long strings in traces, keeping the head and a marker."""
    if text is None or len(text) <= limit:
        return text
    return text[:limit] + f"\n...[truncated {len(text) - limit} chars]"


def normalize(text: str) -> str:
    """Normalize text for keyword matching.

    NFKC + casefold, hyphens/underscores/dashes become spaces, whitespace is
    collapsed. Applied identically to answers and to keyword synonyms, so
    "trade-off", "trade_off" and "trade off" all match each other.
    """
    text = unicodedata.normalize("NFKC", text).casefold()
    text = _DASHES_RE.sub(" ", text)
    return _SPACES_RE.sub(" ", text).strip()


def _pattern_for(synonym: str) -> re.Pattern[str]:
    if synonym.startswith("re:"):
        return re.compile(synonym[3:], re.IGNORECASE)
    norm = normalize(synonym)
    # Left word boundary only, so stems match ("forget" matches "forgetting")
    # but "rl" does not match inside "world". CJK text has no ASCII letters
    # around it, so the lookbehind never blocks it.
    return re.compile(r"(?<![a-z0-9])" + re.escape(norm))


def group_positions(norm_text: str, synonyms: Sequence[str]) -> tuple[list[int], str | None]:
    """All match offsets of any synonym in already-normalized text, plus the first synonym that hit."""
    positions: list[int] = []
    first_hit: str | None = None
    for syn in synonyms:
        hits = [m.start() for m in _pattern_for(syn).finditer(norm_text)]
        if hits and first_hit is None:
            first_hit = syn
        positions.extend(hits)
    return sorted(set(positions)), first_hit


def groups_within_window(positions_per_group: Sequence[Sequence[int]], window: int | None) -> bool:
    """True if every group has a match and one match per group fits in `window` chars.

    `window=None` only requires each group to match somewhere. Uses the classic
    minimum-window-covering-all-categories sweep.
    """
    if any(not pos for pos in positions_per_group):
        return False
    if window is None or len(positions_per_group) <= 1:
        return True
    events = sorted((p, g) for g, plist in enumerate(positions_per_group) for p in plist)
    need = len(positions_per_group)
    counts = [0] * need
    covered = 0
    left = 0
    for right, (pos_r, g_r) in enumerate(events):
        if counts[g_r] == 0:
            covered += 1
        counts[g_r] += 1
        while covered == need:
            pos_l, g_l = events[left]
            if pos_r - pos_l <= window:
                return True
            counts[g_l] -= 1
            if counts[g_l] == 0:
                covered -= 1
            left += 1
    return False


def match_groups(text: str, groups: Sequence[Sequence[str]], window: int | None = None) -> dict:
    """Check a list of keyword groups (AND across groups, OR within a group)."""
    norm = normalize(text)
    positions: list[list[int]] = []
    hits: list[str | None] = []
    for group in groups:
        pos, first = group_positions(norm, group)
        positions.append(pos)
        hits.append(first)
    all_found = all(h is not None for h in hits)
    ok = groups_within_window(positions, window) if all_found else False
    return {
        "ok": ok,
        "matched": hits,
        "missing_groups": [i for i, h in enumerate(hits) if h is None],
        "window_failed": all_found and not ok,
    }


def first_plain_synonym(group: Iterable[str]) -> str | None:
    for syn in group:
        if not syn.startswith("re:"):
            return syn
    return None
