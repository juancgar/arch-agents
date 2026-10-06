"""Deterministic citation checks: extract arXiv IDs, DOIs and URLs and verify them.

Statuses
    VALID           identifier exists (and the cited title matches, when one was given)
    NOT_FOUND       identifier does not exist (or a URL answers 404/410-style errors)
    TITLE_MISMATCH  identifier exists but the cited title differs from the registered one
    UNREACHABLE     could not be checked (offline, network error, timeout, blocked); never a failure

Lookups that end in VALID or NOT_FOUND are cached in sqlite for 30 days. UNREACHABLE is never cached.
"""

from __future__ import annotations

import asyncio
import bisect
import fcntl
import html
import ipaddress
import json
import os
import re
import sqlite3
import time
import unicodedata
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote, unquote, urlsplit

import httpx

from .net import USER_AGENT, ToolError

VALID = "VALID"
NOT_FOUND = "NOT_FOUND"
TITLE_MISMATCH = "TITLE_MISMATCH"
UNREACHABLE = "UNREACHABLE"

CACHE_TTL_S = 30 * 24 * 3600
TITLE_THRESHOLD = 0.85
ARXIV_API = "https://export.arxiv.org/api/query"
ARXIV_ABS = "https://arxiv.org/abs/"
CROSSREF_API = "https://api.crossref.org/works/"
DOI_HANDLE_API = "https://doi.org/api/handles/"
ARXIV_MIN_INTERVAL_S = 3.0
ARXIV_BATCH = 50
_DOI_SAFE = "/:;()"

# --------------------------------------------------------------------------------------------
# Identifier grammar
# --------------------------------------------------------------------------------------------

_OLD_ARCHIVES = (
    "acc-phys", "adap-org", "alg-geom", "ao-sci", "astro-ph", "atom-ph", "bayes-an", "chao-dyn",
    "chem-ph", "cmp-lg", "comp-gas", "cond-mat", "cs", "dg-ga", "funct-an", "gr-qc", "hep-ex",
    "hep-lat", "hep-ph", "hep-th", "math", "math-ph", "mtrl-th", "nlin", "nucl-ex", "nucl-th",
    "patt-sol", "physics", "plasm-ph", "q-alg", "q-bio", "q-fin", "quant-ph", "solv-int", "stat",
    "supr-con",
)
_ARCHIVE_ALT = "|".join(re.escape(a) for a in sorted(_OLD_ARCHIVES, key=len, reverse=True))
_ID_BODY = (
    r"(?:(?P<new>(?P<yymm>\d{4})\.(?P<num>\d{4,5}))"
    r"|(?P<old>(?P<arch>" + _ARCHIVE_ALT + r")(?:\.[A-Za-z]{2})?/(?P<oldnum>\d{7})))"
    r"(?:v(?P<ver>\d{1,3}))?"
)
_ARXIV_FULL = re.compile(r"^" + _ID_BODY + r"$")
# Bare identifiers in prose. Not preceded by a word char, '.', '/' or '-' (that would make them part of
# a URL, DOI or longer number) unless the prefix is "abs/" (DBLP style "CoRR abs/2310.01798").
_ARXIV_IN_TEXT = re.compile(r"(?:(?<=abs/)|(?<![\w./-]))" + _ID_BODY + r"(?![\w-]|\.\d)")
_DOI_IN_TEXT = re.compile(
    r"(?:(?<=doi\.org/)|(?<![\w./-]))(?:doi:\s*)?(?P<doi>10\.\d{4,9}/[-._;()/:a-zA-Z0-9+~<>#]+)", re.IGNORECASE
)
_DOI_FULL = re.compile(r"^10\.\d{4,9}/\S+$")
_URL_IN_TEXT = re.compile(r"https?://[^\s<>\"'`\[\]{}|\\^]+", re.IGNORECASE)
_MD_LINK = re.compile(
    r"\[(?P<text>[^\[\]\n]{1,400})\]\((?P<url>https?://[^\s()]+(?:\([^\s()]*\)[^\s()]*)*)(?:\s+\"[^\"\n]*\")?\)"
)
_ARXIV_URL = re.compile(r"^https?://(?:www\.|export\.)?arxiv\.org/(?:abs|pdf|html|format)/(?P<rest>[^?#]+)", re.I)
_DOI_URL = re.compile(r"^https?://(?:dx\.|www\.)?doi\.org/(?P<doi>10\.\d{4,9}/[^?#]+)", re.I)
_PUBLISHER_DOI_URL = re.compile(
    r"^https?://[^/]+/(?:[^?#]*/)?doi/(?:abs/|full/|pdf/|epdf/|pdfdirect/|book/)?(?P<doi>10\.\d{4,9}/[^?#]+)", re.I
)


def _valid_new_style(yymm: str, num: str) -> bool:
    yy, mm = int(yymm[:2]), int(yymm[2:])
    if not 1 <= mm <= 12:
        return False
    if len(num) == 4:  # April 2007 .. December 2014
        return (7, 4) <= (yy, mm) <= (14, 12)
    return (yy, mm) >= (15, 1)


def _valid_old_style(num7: str) -> bool:
    yy, mm = int(num7[:2]), int(num7[2:4])
    return 1 <= mm <= 12 and (yy >= 91 or yy <= 7)


def _from_match(m: re.Match[str]) -> tuple[str, int | None] | None:
    ver = int(m.group("ver")) if m.group("ver") else None
    if m.group("new"):
        if not _valid_new_style(m.group("yymm"), m.group("num")):
            return None
        return m.group("new"), ver
    if not _valid_old_style(m.group("oldnum")):
        return None
    return f"{m.group('arch')}/{m.group('oldnum')}", ver  # canonical form drops the subject class


def parse_arxiv_id(value: str) -> tuple[str, int | None] | None:
    """Return (base_id, version) for 'arXiv:2310.01798v2', 'cs/0101001', arxiv.org URLs, ...; None if invalid."""
    s = value.strip()
    url = _ARXIV_URL.match(s)
    if url:
        s = url.group("rest").rstrip("/")
        if s.lower().endswith(".pdf"):
            s = s[:-4]
    s = re.sub(r"^arxiv\s*:\s*", "", s, flags=re.IGNORECASE)
    m = _ARXIV_FULL.match(s)
    return _from_match(m) if m else None


def _trim_doi(doi: str) -> str:
    while doi:
        last = doi[-1]
        if last in ".,;:":
            doi = doi[:-1]
        elif last == ")" and doi.count(")") > doi.count("("):
            doi = doi[:-1]
        elif last == ">" and doi.count(">") > doi.count("<"):
            doi = doi[:-1]
        else:
            break
    return doi


def _trim_url(url: str) -> str:
    while url:
        last = url[-1]
        if last in ".,;:!?*'\"~":
            url = url[:-1]
        elif last == ")" and url.count(")") > url.count("("):
            url = url[:-1]
        else:
            break
    return url


# --------------------------------------------------------------------------------------------
# Titles
# --------------------------------------------------------------------------------------------


def normalize_title(title: str) -> str:
    t = html.unescape(re.sub(r"<[^>]+>", " ", title))
    t = re.sub(r"\\[a-zA-Z]+\s*", " ", t)  # LaTeX commands (keep their arguments)
    t = unicodedata.normalize("NFKD", t)
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    t = re.sub(r"[^\w\s]|_", " ", t.lower())
    return " ".join(t.split())


def _main_title(title: str) -> str | None:
    for sep in (":", " - ", " – ", " — "):
        if sep in title:
            head = title.split(sep, 1)[0]
            return head if normalize_title(head) else None
    return None


def _ratio(a: str, b: str) -> float:
    a, b = normalize_title(a), normalize_title(b)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b, autojunk=False).ratio()


def title_similarity(cited: str, actual: str) -> float:
    """Fuzzy similarity in [0, 1]. A cited title may omit (or add) the subtitle after a colon/dash."""
    scores = [_ratio(cited, actual)]
    main_actual, main_cited = _main_title(actual), _main_title(cited)
    if main_actual:
        scores.append(_ratio(cited, main_actual))
    if main_cited:
        scores.append(_ratio(main_cited, actual))
    return max(scores)


def titles_match(cited: str, actual: str, threshold: float = TITLE_THRESHOLD) -> bool:
    return title_similarity(cited, actual) >= threshold


_TITLE_DELIMITED = re.compile(
    r"\*\*(?P<b>[^*\n]{3,300}?)\*\*"
    r"|(?<![*\w])\*(?P<i>[^*\n]{3,300}?)\*(?![*\w])"
    r"|(?<![\w])_(?P<u>[^_\n]{3,300}?)_(?![\w])"
    r"|\"(?P<q>[^\"\n]{3,300}?)\""
    r"|“(?P<cq>[^”\n]{3,300}?)”"
)
_GAP_FILLER = {
    "arxiv", "preprint", "eprint", "e", "print", "corr", "abs", "doi", "in", "url", "available", "at",
    "online", "http", "https", "et", "al", "and", "vol", "volume", "no", "pp", "proc", "accessed",
    "retrieved", "from", "see", "pdf", "link", "id",
}
_GENERIC_LINK_TEXT = {
    "arxiv", "pdf", "link", "paper", "here", "doi", "url", "abs", "html", "source", "website", "code",
    "project page", "github", "openreview", "preprint", "full text", "this paper", "the paper",
}


def _clean_title(candidate: str | None) -> str | None:
    if not candidate:
        return None
    t = " ".join(candidate.split()).strip(" .,;:")
    if len(t) < 8 or len(t) > 300 or len(t.split()) < 2:
        return None
    if sum(ch.isalpha() for ch in t) < 4 or re.search(r"https?://|^arxiv:|^doi:|^10\.\d{4,9}/", t, re.I):
        return None
    if parse_arxiv_id(t) or t.lower() in _GENERIC_LINK_TEXT:
        return None
    return t


def _gap_ok(gap: str) -> bool:
    if len(gap) > 80 or any(ch in gap for ch in "*_\"“”\n"):
        return False
    capitalized = 0
    for token in re.findall(r"[^\W\d_]+|\d+", gap):
        if token.isdigit() or token.lower() in _GAP_FILLER:
            continue
        if token[0].isupper():
            capitalized += 1  # author names / venues, e.g. "Huang et al., ICLR 2024"
            continue
        return False  # lower-case prose between the emphasis and the identifier: not a citation title
    return capitalized <= 4


def _title_before(text: str, pos: int) -> str | None:
    """Title written just before an identifier: '*Title*. arXiv:…', '"Title" (arXiv:…)', '**Title**, doi:…'."""
    line_start = text.rfind("\n", 0, pos) + 1
    window = text[max(line_start, pos - 400) : pos]
    best = None
    for m in _TITLE_DELIMITED.finditer(window):
        best = m
    if best is None or not _gap_ok(window[best.end() :]):
        return None
    candidate = next(g for g in best.groups() if g is not None)
    return _clean_title(candidate)


# --------------------------------------------------------------------------------------------
# Extraction
# --------------------------------------------------------------------------------------------


@dataclass
class Citation:
    kind: str  # "arxiv" | "doi" | "url"
    value: str  # arXiv base id, DOI (original case) or URL
    version: int | None = None
    title: str | None = None
    raw: str | None = None
    pos: int = 0
    error: str | None = None  # malformed explicit input -> NOT_FOUND without a lookup

    @property
    def key(self) -> str:
        if self.kind == "doi":
            return f"doi:{self.value.lower()}"
        if self.kind == "url":
            return f"url:{self.value.split('#', 1)[0]}"
        return f"{self.kind}:{self.value}"

    @property
    def display_id(self) -> str:
        return f"{self.value}v{self.version}" if self.kind == "arxiv" and self.version else self.value


class _Spans:
    def __init__(self) -> None:
        self._spans: list[tuple[int, int]] = []

    def add(self, start: int, end: int) -> None:
        bisect.insort(self._spans, (start, end))

    def overlaps(self, start: int, end: int) -> bool:
        i = bisect.bisect_left(self._spans, (start, end))
        for j in (i - 1, i):
            if 0 <= j < len(self._spans):
                s, e = self._spans[j]
                if s < end and start < e:
                    return True
        return False


def _classify_url(url: str) -> tuple[str, str, int | None] | None:
    """Map a URL onto (kind, value, version); arxiv.org and DOI URLs become identifier checks."""
    if _ARXIV_URL.match(url):
        parsed = parse_arxiv_id(url)
        if parsed:
            return "arxiv", parsed[0], parsed[1]
    for rx in (_DOI_URL, _PUBLISHER_DOI_URL):
        m = rx.match(url)
        if m:
            doi = _trim_doi(unquote(m.group("doi")).rstrip("/"))
            if _DOI_FULL.match(doi):
                if doi.lower().startswith("10.48550/arxiv."):
                    parsed = parse_arxiv_id(doi[len("10.48550/arxiv.") :])
                    if parsed:
                        return "arxiv", parsed[0], parsed[1]
                return "doi", doi, None
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if not parts.hostname or "." not in parts.hostname:
        return None
    return "url", url, None


def extract_citations(text: str) -> list[Citation]:
    """Find arXiv IDs (new and old style), DOIs and http(s) URLs, with cited titles when written nearby."""
    found: list[Citation] = []
    consumed = _Spans()
    link_text = {m.start("url"): m.group("text") for m in _MD_LINK.finditer(text)}

    for m in _URL_IN_TEXT.finditer(text):
        url = _trim_url(m.group(0))
        if len(url) <= len("https://x"):
            continue
        start, end = m.start(), m.start() + len(url)
        consumed.add(start, end)
        classified = _classify_url(url)
        if not classified:
            continue
        kind, value, version = classified
        if kind == "url" and not is_public_http_url(value):
            continue  # localhost / LAN links in prose are not citations
        title = _clean_title(link_text.get(start)) if start in link_text else None
        if title is None:
            link_start = text.rfind("[", 0, start) if start in link_text else start
            title = _title_before(text, max(link_start, 0))
        found.append(Citation(kind, value, version, title, raw=url, pos=start))

    for m in _DOI_IN_TEXT.finditer(text):
        doi = _trim_doi(m.group("doi"))
        start, end = m.start(), m.start("doi") + len(doi)
        if consumed.overlaps(start, end) or not _DOI_FULL.match(doi):
            continue
        consumed.add(start, end)
        title = _title_before(text, start)
        if doi.lower().startswith("10.48550/arxiv."):
            parsed = parse_arxiv_id(doi[len("10.48550/arxiv.") :])
            if parsed:
                found.append(Citation("arxiv", parsed[0], parsed[1], title, raw=doi, pos=start))
                continue
        found.append(Citation("doi", doi, None, title, raw=m.group(0)[: end - start], pos=start))

    for m in _ARXIV_IN_TEXT.finditer(text):
        if consumed.overlaps(m.start(), m.end()):
            continue
        parsed = _from_match(m)
        if not parsed:
            continue
        found.append(Citation("arxiv", parsed[0], parsed[1], _title_before(text, m.start()), raw=m.group(0), pos=m.start()))

    found.sort(key=lambda c: c.pos)
    return dedupe(found)


def dedupe(citations: Iterable[Citation]) -> list[Citation]:
    """One entry per identifier (and version); keep distinct cited titles as separate entries."""
    groups: dict[tuple[str, int | None], list[Citation]] = {}
    for c in citations:
        group = groups.setdefault((c.key, c.version), [])
        if c.title is None:
            if not group:
                group.append(c)
            continue
        norm = normalize_title(c.title)
        if any(x.title and normalize_title(x.title) == norm for x in group):
            continue
        untitled = next((x for x in group if x.title is None), None)
        if untitled is not None:
            untitled.title = c.title
        else:
            group.append(c)
    return sorted((c for g in groups.values() for c in g), key=lambda c: c.pos)


def citation_from_input(item: dict[str, Any], index: int = 0) -> Citation:
    """Build a Citation from an explicit {id?, doi?, url?, title?} item (precedence: id > doi > url)."""
    title = str(item.get("title") or "").strip() or None
    arxiv_id = str(item.get("id") or "").strip()
    doi = str(item.get("doi") or "").strip()
    url = str(item.get("url") or "").strip()
    if arxiv_id:
        if re.match(r"^(?:doi:\s*)?10\.\d{4,9}/", arxiv_id, re.I):
            doi, arxiv_id = re.sub(r"^doi:\s*", "", arxiv_id, flags=re.I), ""
        elif re.match(r"^https?://", arxiv_id, re.I) and not _ARXIV_URL.match(arxiv_id):
            url, arxiv_id = arxiv_id, ""
    if arxiv_id:
        parsed = parse_arxiv_id(arxiv_id)
        if not parsed:
            return Citation("arxiv", arxiv_id, None, title, raw=arxiv_id, pos=index, error="malformed arXiv identifier")
        return Citation("arxiv", parsed[0], parsed[1], title, raw=arxiv_id, pos=index)
    if doi:
        doi_clean = re.sub(r"^(?:https?://(?:dx\.|www\.)?doi\.org/|doi:\s*)", "", doi, flags=re.I)
        doi_clean = _trim_doi(unquote(doi_clean))
        if not _DOI_FULL.match(doi_clean):
            return Citation("doi", doi, None, title, raw=doi, pos=index, error="malformed DOI")
        if doi_clean.lower().startswith("10.48550/arxiv."):
            parsed = parse_arxiv_id(doi_clean[len("10.48550/arxiv.") :])
            if parsed:
                return Citation("arxiv", parsed[0], parsed[1], title, raw=doi, pos=index)
        return Citation("doi", doi_clean, None, title, raw=doi, pos=index)
    if url:
        classified = _classify_url(url) if re.match(r"^https?://", url, re.I) else None
        if not classified:
            return Citation("url", url, None, title, raw=url, pos=index, error="malformed URL")
        kind, value, version = classified
        return Citation(kind, value, version, title, raw=url, pos=index)
    raise ToolError(f"citations[{index}] needs at least one of 'id' (arXiv), 'doi' or 'url'")


# --------------------------------------------------------------------------------------------
# Cache and rate limiting
# --------------------------------------------------------------------------------------------


@dataclass
class Lookup:
    status: str  # VALID | NOT_FOUND | UNREACHABLE
    title: str | None = None
    info: dict[str, Any] = field(default_factory=dict)
    cached: bool = False


class VerdictCache:
    """sqlite cache of VALID / NOT_FOUND lookups. Any failure silently disables caching."""

    def __init__(self, path: Path | None, ttl_s: float = CACHE_TTL_S):
        self.ttl_s = ttl_s
        self._conn: sqlite3.Connection | None = None
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(path, timeout=5)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS verdicts (key TEXT PRIMARY KEY, status TEXT NOT NULL,"
                " title TEXT, info TEXT, checked_at REAL NOT NULL)"
            )
            conn.commit()
            self._conn = conn
        except (sqlite3.Error, OSError):
            self._conn = None

    def get(self, key: str, now: float | None = None) -> Lookup | None:
        if self._conn is None:
            return None
        now = time.time() if now is None else now
        try:
            row = self._conn.execute(
                "SELECT status, title, info, checked_at FROM verdicts WHERE key = ?", (key,)
            ).fetchone()
        except sqlite3.Error:
            return None
        if not row or row[0] not in (VALID, NOT_FOUND) or now - row[3] > self.ttl_s:
            return None
        info = json.loads(row[2]) if row[2] else {}
        info["checked_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(row[3]))
        return Lookup(row[0], row[1], info, cached=True)

    def put(self, key: str, lookup: Lookup, now: float | None = None) -> None:
        if self._conn is None or lookup.status not in (VALID, NOT_FOUND):
            return
        try:
            self._conn.execute(
                "INSERT OR REPLACE INTO verdicts (key, status, title, info, checked_at) VALUES (?, ?, ?, ?, ?)",
                (key, lookup.status, lookup.title, json.dumps(lookup.info), time.time() if now is None else now),
            )
            self._conn.commit()
        except sqlite3.Error:
            pass

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None


class ArxivRateLimiter:
    """Keeps arXiv API requests >= min_interval apart, across processes when a state file is usable."""

    def __init__(self, state_file: Path | None, min_interval: float = ARXIV_MIN_INTERVAL_S):
        self.state_file = state_file
        self.min_interval = min_interval
        self._last = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self, deadline: float | None = None) -> None:
        async with self._lock:
            fd = None
            if self.state_file is not None:
                try:
                    self.state_file.parent.mkdir(parents=True, exist_ok=True)
                    fd = os.open(self.state_file, os.O_RDWR | os.O_CREAT, 0o644)
                except OSError:
                    fd = None
            try:
                if fd is not None:
                    while True:
                        try:
                            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                            break
                        except BlockingIOError:
                            if deadline is not None and time.monotonic() > deadline:
                                raise TimeoutError("arXiv rate limiter busy") from None
                            await asyncio.sleep(0.05)
                last = max(self._last, self._read(fd))
                wait = last + self.min_interval - time.time()
                if wait > 0:
                    if deadline is not None and time.monotonic() + wait > deadline:
                        raise TimeoutError("no time left to respect the arXiv rate limit")
                    await asyncio.sleep(wait)
                self._last = time.time()
                self._write(fd, self._last)
            finally:
                if fd is not None:
                    try:
                        fcntl.flock(fd, fcntl.LOCK_UN)
                    finally:
                        os.close(fd)

    @staticmethod
    def _read(fd: int | None) -> float:
        if fd is None:
            return 0.0
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            return float(os.read(fd, 64).decode().strip() or 0)
        except (OSError, ValueError):
            return 0.0

    @staticmethod
    def _write(fd: int | None, value: float) -> None:
        if fd is None:
            return
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            os.ftruncate(fd, 0)
            os.write(fd, f"{value:.3f}".encode())
        except OSError:
            pass


# --------------------------------------------------------------------------------------------
# Network checks
# --------------------------------------------------------------------------------------------


def parse_arxiv_feed(xml_text: str) -> dict[str, tuple[str, int | None]]:
    """Map base id -> (title, latest version) for every entry of an arXiv API Atom feed."""
    ns = {"a": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(xml_text)
    out: dict[str, tuple[str, int | None]] = {}
    for entry in root.findall("a:entry", ns):
        id_url = (entry.findtext("a:id", default="", namespaces=ns) or "").strip()
        m = re.search(r"arxiv\.org/abs/(?P<id>.+?)(?:v(?P<ver>\d+))?$", id_url)
        if not m:
            continue  # error entries look like http://arxiv.org/api/errors#...
        title = " ".join((entry.findtext("a:title", default="", namespaces=ns) or "").split())
        parsed = parse_arxiv_id(m.group("id"))
        base = parsed[0] if parsed else m.group("id")
        out[base] = (title, int(m.group("ver")) if m.group("ver") else None)
    return out


_META_TITLE = re.compile(r'<meta\s+name="citation_title"\s+content="([^"]*)"', re.I)

# HTTP codes that say "the resource may exist but we may not look": never a NOT_FOUND verdict.
_UNVERIFIABLE_HTTP = {401, 402, 403, 407, 408, 418, 425, 429, 451}


def is_public_http_url(url: str) -> bool:
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").rstrip(".").lower()
    except ValueError:
        return False
    if parts.scheme.lower() not in ("http", "https") or not host:
        return False
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal", ".lan", ".home.arpa")):
        return False
    try:
        return ipaddress.ip_address(host).is_global
    except ValueError:
        return "." in host  # single-label hosts are intranet names


class Verifier:
    def __init__(
        self,
        client: httpx.AsyncClient,
        cache: VerdictCache,
        *,
        offline: bool = False,
        deadline: float | None = None,
        limiter: ArxivRateLimiter | None = None,
    ):
        self.client = client
        self.cache = cache
        self.offline = offline
        self.deadline = deadline
        self.limiter = limiter or ArxivRateLimiter(None)
        self._crossref = asyncio.Semaphore(3)
        self._handles = asyncio.Semaphore(3)
        self._urls = asyncio.Semaphore(8)
        self._arxiv_abs = asyncio.Semaphore(2)

    def _timeout(self, seconds: float) -> httpx.Timeout:
        if self.deadline is not None:
            seconds = max(0.5, min(seconds, self.deadline - time.monotonic()))
        return httpx.Timeout(seconds, connect=min(seconds, 5.0))

    async def run(self, citations: list[Citation]) -> list[dict[str, Any]]:
        lookups: dict[str, Lookup] = {}
        todo: dict[str, Citation] = {}
        for c in citations:
            if c.error or c.key in lookups or c.key in todo:
                continue
            hit = self.cache.get(c.key)
            if hit is not None:
                lookups[c.key] = hit
            else:
                todo[c.key] = c

        if todo and self.offline:
            for key in todo:
                lookups[key] = Lookup(UNREACHABLE, info={"reason": "offline mode and no cached verdict"})
        elif todo:
            tasks: list[asyncio.Task[None]] = []
            arxiv_ids = sorted({c.value for c in todo.values() if c.kind == "arxiv"})
            if arxiv_ids:
                tasks.append(asyncio.create_task(self._check_arxiv(arxiv_ids, lookups)))
            for key, c in todo.items():
                if c.kind == "doi":
                    tasks.append(asyncio.create_task(self._store(key, self._check_doi(c.value), lookups)))
                elif c.kind == "url":
                    tasks.append(asyncio.create_task(self._store(key, self._check_url(c.value), lookups)))
            timeout = None if self.deadline is None else max(0.0, self.deadline - time.monotonic())
            pending: set[asyncio.Task[None]] = set()
            if tasks:
                _done, pending = await asyncio.wait(tasks, timeout=timeout)
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            for key in todo:
                if key not in lookups:
                    lookups[key] = Lookup(UNREACHABLE, info={"reason": "not checked within the time budget"})
            for key in todo:
                self.cache.put(key, lookups[key])

        return [self._detail(c, lookups.get(c.key)) for c in citations]

    @staticmethod
    async def _store(key: str, coro: Any, lookups: dict[str, Lookup]) -> None:
        try:
            lookups[key] = await coro
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # defensive: a bug in one check must not hide the others
            lookups[key] = Lookup(UNREACHABLE, info={"reason": f"internal error: {_reason(exc)}"})

    async def _check_arxiv(self, ids: list[str], lookups: dict[str, Lookup]) -> None:
        for i in range(0, len(ids), ARXIV_BATCH):
            batch = ids[i : i + ARXIV_BATCH]
            try:
                await self.limiter.acquire(self.deadline)
                # ids only contain [0-9a-z./-]; keep "," and "/" literal in the query string
                url = f"{ARXIV_API}?id_list={','.join(batch)}&max_results={len(batch)}"
                response = await self.client.get(url, timeout=self._timeout(15))
                if response.status_code != 200:
                    raise ValueError(f"arXiv API HTTP {response.status_code}")
                entries = parse_arxiv_feed(response.text)
            except (httpx.HTTPError, ValueError, ET.ParseError, TimeoutError) as exc:
                for arxiv_id in batch:
                    lookups[f"arxiv:{arxiv_id}"] = Lookup(UNREACHABLE, info={"reason": _reason(exc)})
                continue
            missing = []
            for arxiv_id in batch:
                if arxiv_id in entries:
                    title, version = entries[arxiv_id]
                    lookups[f"arxiv:{arxiv_id}"] = Lookup(
                        VALID, title or None, {"source": "arxiv-api", "latest_version": version}
                    )
                else:
                    missing.append(arxiv_id)
            # The export API silently omits unknown ids (and occasionally returns partial feeds), so every
            # absence is confirmed against the abstract page before it becomes a cached NOT_FOUND.
            await asyncio.gather(*(self._store(f"arxiv:{a}", self._confirm_arxiv(a), lookups) for a in missing))

    async def _confirm_arxiv(self, arxiv_id: str) -> Lookup:
        async with self._arxiv_abs:
            try:
                response = await self.client.get(ARXIV_ABS + arxiv_id, timeout=self._timeout(10))
            except httpx.HTTPError as exc:
                return Lookup(UNREACHABLE, info={"reason": _reason(exc)})
        if response.status_code == 404:
            return Lookup(NOT_FOUND, info={"source": "arxiv", "reason": "arXiv has no paper with this identifier"})
        if response.status_code == 200:
            m = _META_TITLE.search(response.text)
            title = " ".join(html.unescape(m.group(1)).split()) if m else None
            return Lookup(VALID, title, {"source": "arxiv-abs"})
        return Lookup(UNREACHABLE, info={"reason": f"arXiv abstract page HTTP {response.status_code}"})

    async def _check_doi(self, doi: str) -> Lookup:
        quoted = quote(doi, safe=_DOI_SAFE)
        try:
            async with self._crossref:
                response = await self.client.get(CROSSREF_API + quoted, timeout=self._timeout(10))
            if response.status_code == 200:
                message = response.json().get("message") or {}
                titles = message.get("title") or []
                title = " ".join(html.unescape(re.sub(r"<[^>]+>", "", titles[0])).split()) if titles else None
                return Lookup(VALID, title or None, {"source": "crossref"})
            if response.status_code != 404:
                return Lookup(UNREACHABLE, info={"reason": f"Crossref HTTP {response.status_code}"})
            # Not in Crossref: could still be a DataCite/mEDRA/... DOI. The handle API is authoritative.
            async with self._handles:
                handle = await self.client.get(DOI_HANDLE_API + quoted, timeout=self._timeout(10))
            code = None
            try:
                code = handle.json().get("responseCode")
            except ValueError:
                pass
            if handle.status_code == 200 and code == 1:
                return Lookup(VALID, None, {"source": "doi.org", "note": "registered outside Crossref; title not checked"})
            if handle.status_code == 404 or code == 100:
                return Lookup(NOT_FOUND, info={"source": "doi.org", "reason": "DOI is not registered"})
            return Lookup(UNREACHABLE, info={"reason": f"doi.org handle API HTTP {handle.status_code}"})
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            return Lookup(UNREACHABLE, info={"reason": _reason(exc)})

    async def _check_url(self, url: str) -> Lookup:
        if not is_public_http_url(url):
            return Lookup(UNREACHABLE, info={"reason": "local or private address; not checked"})
        async with self._urls:
            try:
                response = await self.client.head(url, timeout=self._timeout(8))
                code = response.status_code
                if code >= 400:  # many servers reject HEAD; retry with GET without reading the body
                    async with self.client.stream("GET", url, timeout=self._timeout(8)) as streamed:
                        code = streamed.status_code
            except (httpx.HTTPError, ValueError) as exc:
                return Lookup(UNREACHABLE, info={"reason": _reason(exc)})
        if code < 400:
            return Lookup(VALID, info={"source": "http", "http_status": code})
        if code in _UNVERIFIABLE_HTTP or code >= 500:
            return Lookup(UNREACHABLE, info={"reason": f"HTTP {code}; cannot verify", "http_status": code})
        return Lookup(NOT_FOUND, info={"source": "http", "reason": f"HTTP {code}", "http_status": code})

    def _detail(self, c: Citation, lookup: Lookup | None) -> dict[str, Any]:
        detail: dict[str, Any] = {"status": UNREACHABLE, "type": c.kind, "id": c.display_id}
        if c.error:
            detail.update(status=NOT_FOUND, reason=f"{c.error}; it cannot resolve")
            if c.title:
                detail["cited_title"] = c.title
            return detail
        lookup = lookup or Lookup(UNREACHABLE, info={"reason": "not checked"})
        status = lookup.status
        if lookup.title:
            detail["title"] = lookup.title
        if c.title:
            detail["cited_title"] = c.title
        latest = lookup.info.get("latest_version")
        if status == VALID and c.kind == "arxiv" and c.version and latest and c.version > latest:
            status = NOT_FOUND
            detail["reason"] = f"version v{c.version} does not exist (latest is v{latest})"
        elif status == VALID and c.title and lookup.title:
            similarity = title_similarity(c.title, lookup.title)
            detail["title_similarity"] = round(similarity, 3)
            if similarity < TITLE_THRESHOLD:
                status = TITLE_MISMATCH
        for k in ("reason", "note", "http_status", "source", "checked_at"):
            if k in lookup.info and k not in detail:
                detail[k] = lookup.info[k]
        if lookup.cached:
            detail["cached"] = True
        detail["status"] = status
        return detail


def _reason(exc: BaseException) -> str:
    if isinstance(exc, (httpx.TimeoutException, TimeoutError)):
        return f"timeout ({type(exc).__name__})"
    text = str(exc).strip()
    return f"{type(exc).__name__}: {text}"[:200] if text else type(exc).__name__


# --------------------------------------------------------------------------------------------
# Entry points
# --------------------------------------------------------------------------------------------


def summarize(details: list[dict[str, Any]], *, not_checked: int = 0, offline: bool = False) -> dict[str, Any]:
    counts = Counter(d["status"] for d in details)
    return {
        "ok": counts[NOT_FOUND] == 0 and counts[TITLE_MISMATCH] == 0,
        "total": len(details),
        "valid": counts[VALID],
        "not_found": counts[NOT_FOUND],
        "title_mismatch": counts[TITLE_MISMATCH],
        "unreachable": counts[UNREACHABLE],
        "not_checked": not_checked,
        "offline": offline,
        "details": details,
    }


def prioritize(citations: list[Citation], limit: int) -> tuple[list[Citation], int]:
    """Keep at most `limit` citations, identifiers (arXiv/DOI) before plain URLs, in text order."""
    if len(citations) <= limit:
        return citations, 0
    ids = [c for c in citations if c.kind != "url"]
    urls = [c for c in citations if c.kind == "url"]
    keep = (ids + urls)[:limit]
    keep_set = {id(c) for c in keep}
    return [c for c in citations if id(c) in keep_set], len(citations) - len(keep)


async def verify_citations(
    text: str | None = None,
    citations: list[dict[str, Any]] | None = None,
    *,
    offline: bool = False,
    cache_dir: Path | None = None,
    max_citations: int = 200,
    timeout_s: float | None = 60.0,
    client: httpx.AsyncClient | None = None,
    limiter: ArxivRateLimiter | None = None,
) -> dict[str, Any]:
    found: list[Citation] = []
    if text:
        found.extend(extract_citations(text))
    offset = len(text or "") + 1
    for i, item in enumerate(citations or []):
        if not isinstance(item, dict):
            raise ToolError(f"citations[{i}] must be an object with id/doi/url/title")
        c = citation_from_input(item, i)
        c.pos = offset + i
        found.append(c)
    found = dedupe(found)
    selected, not_checked = prioritize(found, max_citations)
    deadline = None if timeout_s is None else time.monotonic() + timeout_s
    cache = VerdictCache(cache_dir / "citations.sqlite" if cache_dir else None)
    if limiter is None:
        limiter = ArxivRateLimiter(cache_dir / "arxiv-rate-limit" if cache_dir else None)
    own_client = client is None
    if client is None:
        client = httpx.AsyncClient(
            follow_redirects=True, headers={"User-Agent": USER_AGENT}, timeout=httpx.Timeout(10, connect=5)
        )
    try:
        details = await Verifier(client, cache, offline=offline, deadline=deadline, limiter=limiter).run(selected)
    finally:
        cache.close()
        if own_client:
            await client.aclose()
    return summarize(details, not_checked=not_checked, offline=offline)


def failure_lines(result: dict[str, Any]) -> list[str]:
    """Human-readable lines for blocking statuses (used as the hook's stderr reason)."""
    lines = []
    for d in result.get("details", []):
        if d["status"] == NOT_FOUND:
            lines.append(f"- {d['type']} {d['id']}: NOT_FOUND ({d.get('reason', 'does not exist')})")
        elif d["status"] == TITLE_MISMATCH:
            lines.append(
                f"- {d['type']} {d['id']}: TITLE_MISMATCH: cited \"{d.get('cited_title')}\" but registered title"
                f" is \"{d.get('title')}\" (similarity {d.get('title_similarity')})"
            )
    return lines
