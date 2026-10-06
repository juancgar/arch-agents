"""Pure text utilities: heading detection, structure-aware chunking, tokenization, snippet windows."""

from __future__ import annotations

import bisect
import re
from dataclasses import dataclass

TARGET_CHARS = 3200  # ~800 tokens
OVERLAP_CHARS = 480  # ~15 %
SNIPPET_CHARS = 1200

STOPWORDS = frozenset(
    """a about above after again against all also am an and any are as at be because been before being below
    between both but by can could did do does doing down during each et al few for from further had has have
    having he her here hers herself him himself his how i if in into is it its itself just me more most my
    myself no nor not now of off on once only or other our ours ourselves out over own same she should so some
    such than that the their theirs them themselves then there these they this those through to too under until
    up use used using very via was we were what when where which while who whom why will with you your yours
    yourself yourselves""".split()
)

_TOKEN = re.compile(r"\w+")
_PARA_START = re.compile(r"\n[ \t]*\n\s*")  # .end() = first char of the next paragraph
_SENT_START = re.compile(r"[.!?][\"'”’)\]]*\s+")  # .end() = first char of the next sentence
_WS = re.compile(r"\s")


def tokenize(text: str) -> list[str]:
    """Lower-cased word tokens for BM25 (stopwords and 1-letter tokens dropped, digits kept)."""
    return [t for t in _TOKEN.findall(text.lower()) if (len(t) > 1 or t.isdigit()) and t not in STOPWORDS]


# ------------------------------------------------------------------------------------------------
# Headings
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Heading:
    offset: int  # character offset of the heading line
    level: int
    title: str


_MD_HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")
_NUMBERED_HEADING = re.compile(
    r"^[ \t]{0,4}(?P<num>\d{1,2}(?:\.\d{1,2}){0,3}|[A-Z](?:\.\d{1,2}){1,3})\.?[ \t]+(?P<title>[A-Z][^\n]{1,80})$"
)
_CANONICAL_HEADING = re.compile(
    r"^[ \t]{0,4}(?P<title>abstract|introduction|related work|background|preliminaries|methods?|methodology|"
    r"approach|experiments?|experimental setup|evaluation|results|discussion|limitations|conclusions?|"
    r"future work|references|bibliography|acknowledge?ments?|appendix(?:[ \t]+[a-z])?)[ \t]*:?[ \t]*$",
    re.IGNORECASE,
)
_LINE = re.compile(r"(?m)^.*$")


def markdown_headings(text: str) -> list[Heading]:
    """ATX headings outside fenced code blocks."""
    headings: list[Heading] = []
    fence: str | None = None
    for m in _LINE.finditer(text):
        line = m.group(0)
        stripped = line.strip()
        if stripped.startswith(("```", "~~~")):
            marker = stripped[:3]
            if fence is None:
                fence = marker
            elif marker == fence:
                fence = None
            continue
        if fence is not None:
            continue
        h = _MD_HEADING.match(line)
        if h:
            title = re.sub(r"[*_`]", "", h.group(2)).strip()
            if title:
                headings.append(Heading(m.start(), len(h.group(1)), title))
    return headings


def plain_headings(text: str) -> list[Heading]:
    """Numbered ("3.2 Training") and canonical ("References") section headings in PDF/plain text."""
    headings: list[Heading] = []
    for m in _LINE.finditer(text):
        line = m.group(0)
        if len(line) > 90:
            continue
        numbered = _NUMBERED_HEADING.match(line)
        if numbered:
            title = numbered.group("title").strip()
            letters = sum(ch.isalpha() for ch in title)
            if title.endswith((".", ",", ";")) or len(title.split()) > 12 or letters < 0.6 * len(title.replace(" ", "")):
                continue
            num = numbered.group("num")
            headings.append(Heading(m.start(), num.count(".") + 1, f"{num} {title}"))
            continue
        canonical = _CANONICAL_HEADING.match(line)
        if canonical:
            headings.append(Heading(m.start(), 1, canonical.group("title").strip().title()))
    return headings


def section_labels(headings: list[Heading], doc_title: str | None = None) -> list[tuple[int, str]]:
    """(offset, label) pairs; markdown-style nesting becomes 'Parent > Child' (document title omitted)."""
    labels: list[tuple[int, str]] = []
    stack: list[Heading] = []
    for h in headings:
        while stack and stack[-1].level >= h.level:
            stack.pop()
        stack.append(h)
        parts = [x.title for x in stack]
        if doc_title and len(parts) > 1 and parts[0].strip().lower() == doc_title.strip().lower():
            parts = parts[1:]
        if parts and parts[0][:1].isdigit():
            parts = parts[-1:]  # numbered headings already carry their hierarchy
        labels.append((h.offset, " > ".join(parts[-3:])))
    return labels


def label_at(labels: list[tuple[int, str]], offset: int) -> str | None:
    i = bisect.bisect_right(labels, (offset, "\U0010ffff")) - 1
    return labels[i][1] if i >= 0 else None


def page_at(page_starts: list[int], offset: int) -> int | None:
    if not page_starts:
        return None
    return max(1, bisect.bisect_right(page_starts, offset))


# ------------------------------------------------------------------------------------------------
# Chunking
# ------------------------------------------------------------------------------------------------


def _last_in(sorted_positions: list[int], lo: int, hi: int) -> int | None:
    """Largest p with lo < p <= hi."""
    i = bisect.bisect_right(sorted_positions, hi) - 1
    return sorted_positions[i] if i >= 0 and sorted_positions[i] > lo else None


def _first_in(sorted_positions: list[int], lo: int, hi: int) -> int | None:
    """Smallest p with lo <= p <= hi."""
    i = bisect.bisect_left(sorted_positions, lo)
    return sorted_positions[i] if i < len(sorted_positions) and sorted_positions[i] <= hi else None


def _skip_ws(text: str, pos: int) -> int:
    n = len(text)
    while pos < n and text[pos].isspace():
        pos += 1
    return pos


def _rstrip_pos(text: str, start: int, end: int) -> int:
    while end > start and text[end - 1].isspace():
        end -= 1
    return end


def chunk_spans(
    text: str,
    cut_points: list[int] | tuple[int, ...] = (),
    target: int = TARGET_CHARS,
    overlap: int = OVERLAP_CHARS,
) -> list[tuple[int, int]]:
    """Split text into (start, end) spans of about `target` chars.

    Preferred cut points, in order: a heading (cut_points) in the last 70 % of the window, a paragraph break,
    a sentence end, whitespace, then a hard cut. Chunks overlap by about `overlap` chars except across
    headings, where a new section starts a clean chunk. text[start:end] never begins or ends with whitespace.
    """
    n = len(text)
    headings = sorted({p for p in cut_points if 0 < p < n})
    paragraphs = [m.end() for m in _PARA_START.finditer(text)]
    sentences = [m.end() for m in _SENT_START.finditer(text)]
    spans: list[tuple[int, int]] = []
    start = _skip_ws(text, 0)
    while start < n:
        if n - start <= target * 1.15:  # the tail fits (allow a little overflow instead of a tiny last chunk)
            end, kind = n, "end"
        else:
            limit = start + target
            end, kind = None, ""
            h = _last_in(headings, start + int(target * 0.3), limit)
            if h is not None:
                end, kind = h, "heading"
            else:
                lo = start + target // 2
                for name, positions in (("paragraph", paragraphs), ("sentence", sentences)):
                    p = _last_in(positions, lo, limit)
                    if p is not None:
                        end, kind = p, name
                        break
                if end is None:
                    ws = max(text.rfind(" ", lo, limit), text.rfind("\n", lo, limit))
                    end, kind = (ws + 1, "space") if ws > lo else (limit, "hard")
        stop = _rstrip_pos(text, start, end)
        if stop > start:
            spans.append((start, stop))
        if end >= n:
            break
        if kind == "heading":
            nxt = end
        else:
            want = max(end - overlap, start + 1)
            nxt = _first_in(paragraphs, want, end - 1)
            if nxt is None:
                nxt = _first_in(sentences, want, end - 1)
            if nxt is None:
                m = _WS.search(text, want, end)
                nxt = m.end() if m else want
        start = _skip_ws(text, max(nxt, start + 1))
    return spans


# ------------------------------------------------------------------------------------------------
# Snippets
# ------------------------------------------------------------------------------------------------


def best_window(text: str, terms: set[str] | frozenset[str], size: int = SNIPPET_CHARS) -> tuple[int, int]:
    """(start, end) of the `size`-char window of `text` with the most query terms (distinct terms first)."""
    n = len(text)
    if n <= size:
        return 0, n
    hits = [(m.start(), m.group(0).lower()) for m in _TOKEN.finditer(text) if m.group(0).lower() in terms]
    start = 0
    if hits:
        positions = [p for p, _ in hits]
        starts = {0}
        starts.update(m.end() for m in _SENT_START.finditer(text, 0, max(1, n - size // 2)))
        starts.update(max(0, p - 120) for p in positions)
        best_key: tuple[int, int, int] | None = None
        for s in sorted(starts)[:2000]:
            lo = bisect.bisect_left(positions, s)
            hi = bisect.bisect_left(positions, s + size - 20)
            window_hits = hits[lo:hi]
            key = (len({t for _, t in window_hits}), len(window_hits), -s)
            if best_key is None or key > best_key:
                best_key, start = key, s
        start = min(start, n - size)  # always return a full-size window
        if start > 0 and text[start - 1].isalnum():  # do not start mid-word
            m = _WS.search(text, start, min(n, start + 40))
            start = m.end() if m else start
    start = _skip_ws(text, start)
    end = min(n, start + size)
    if end < n:
        cut = _last_in([m.end() for m in _SENT_START.finditer(text, start, end)], start + int(size * 0.75), end)
        if cut is None:
            ws = max(text.rfind(" ", start, end), text.rfind("\n", start, end))
            cut = ws if ws > start + int(size * 0.75) else end
        end = cut
    return start, _rstrip_pos(text, start, end)
