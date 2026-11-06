"""paper_search: hybrid retrieval (BM25 + dense, reciprocal-rank fusion) with cross-encoder reranking."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import httpx
import numpy as np
from rank_bm25 import BM25Okapi

from .chunking import best_window, label_at, page_at, tokenize
from .config import Config
from .index import DB_NAME, chunk_id, load_vectors
from .net import ServiceError, ServiceUnavailable, ToolError
from .retrieval import embed_query, rerank

RRF_K = 60
FIRST_STAGE = 100  # candidates kept from each retriever
RERANK_TOP = 50  # fused candidates sent to the reranker
SERVER_SCRIPT = Path(__file__).resolve().parent.parent / "server.py"


@dataclass(frozen=True)
class Chunk:
    path: str
    chunk_no: int
    start: int
    end: int
    section: str | None
    page: int | None
    header: str
    text: str
    vec_row: int


@dataclass(frozen=True)
class FileInfo:
    title: str
    page_starts: list[int]
    sections: list[tuple[int, str]]


@dataclass
class LoadedIndex:
    generation: str
    updated_at: str | None
    chunks: list[Chunk]
    files: dict[str, FileInfo]
    vectors: np.ndarray | None
    vec_rows: np.ndarray
    bm25: BM25Okapi | None
    doc_terms: list[frozenset[str]]


_cache: dict[str, LoadedIndex] = {}
_cache_lock = threading.Lock()


def _missing_index(index_dir: Path, why: str) -> ToolError:
    return ToolError(
        f"{why} (ARCH_INDEX_DIR={index_dir})",
        hint=f"Build it with: uv run --script {SERVER_SCRIPT} index   (reads ARCH_LIBRARY_DIRS)",
    )


def load_index(index_dir: Path) -> LoadedIndex:
    """Load (or reuse) the index snapshot; reloads automatically when `index` publishes a new generation."""
    db = index_dir / DB_NAME
    if not db.is_file():
        raise _missing_index(index_dir, "No paper index found")
    with _cache_lock:
        conn = sqlite3.connect(db, timeout=30)
        try:
            conn.execute("BEGIN")  # one read snapshot: meta, rows and the vectors file stay consistent
            try:
                meta = {k: v for k, v in conn.execute("SELECT key, value FROM meta")}
            except sqlite3.OperationalError:
                meta = {}
            generation = meta.get("generation")
            if not generation:
                raise _missing_index(index_dir, "The paper index has never been built completely")
            cached = _cache.get(str(index_dir))
            if cached is not None and cached.generation == generation:
                return cached
            files = {}
            for path, title, page_starts, sections in conn.execute(
                "SELECT path, title, page_starts, sections FROM files"
            ):
                files[path] = FileInfo(
                    title or Path(path).stem,
                    json.loads(page_starts) if page_starts else [],
                    [tuple(x) for x in json.loads(sections)] if sections else [],
                )
            chunks = [
                Chunk(*row)
                for row in conn.execute(
                    "SELECT path, chunk_no, start_char, end_char, section, page, header, text, vec_row"
                    " FROM chunks ORDER BY id"
                )
            ]
            vectors = load_vectors(index_dir, meta)
        finally:
            conn.rollback()
            conn.close()
        corpus = [tokenize(f"{c.header}\n{c.text}") for c in chunks]
        loaded = LoadedIndex(
            generation=generation,
            updated_at=meta.get("updated_at"),
            chunks=chunks,
            files=files,
            vectors=vectors if vectors is not None and vectors.shape[0] else None,
            vec_rows=np.asarray([c.vec_row for c in chunks], dtype=np.int64),
            bm25=BM25Okapi(corpus) if chunks else None,
            doc_terms=[frozenset(doc) for doc in corpus],
        )
        _cache[str(index_dir)] = loaded
        return loaded


def rrf_fuse(rankings: Sequence[Sequence[int]], k: int = RRF_K) -> list[tuple[int, float]]:
    """Reciprocal-rank fusion: score(d) = sum over rankings of 1 / (k + rank). Sorted best first."""
    scores: dict[int, float] = defaultdict(float)
    best_rank: dict[int, int] = {}
    for ranking in rankings:
        for rank, doc in enumerate(ranking, start=1):
            scores[doc] += 1.0 / (k + rank)
            best_rank[doc] = min(best_rank.get(doc, rank), rank)
    return sorted(scores.items(), key=lambda item: (-item[1], best_rank[item[0]], item[0]))


def _bm25_ranking(index: LoadedIndex, q_tokens: list[str], mask: np.ndarray) -> tuple[list[int], np.ndarray]:
    n = len(index.chunks)
    if not q_tokens or index.bm25 is None:
        return [], np.zeros(n)
    scores = np.asarray(index.bm25.get_scores(q_tokens), dtype=np.float64)
    terms = set(q_tokens)
    order = np.argsort(-scores, kind="stable")
    ranking = [int(i) for i in order if mask[i] and not terms.isdisjoint(index.doc_terms[i])]
    return ranking[:FIRST_STAGE], scores


def _dense_ranking(index: LoadedIndex, query_vec: np.ndarray, mask: np.ndarray) -> list[int]:
    assert index.vectors is not None
    has_vec = (index.vec_rows >= 0) & mask
    if not has_vec.any():
        return []
    sims = np.full(len(index.chunks), -np.inf, dtype=np.float32)
    rows = index.vec_rows[has_vec]
    sims[has_vec] = np.asarray(index.vectors[rows] @ query_vec.astype(np.float32), dtype=np.float32)
    candidates = np.flatnonzero(has_vec)
    order = candidates[np.argsort(-sims[candidates], kind="stable")]
    return [int(i) for i in order[:FIRST_STAGE]]


async def paper_search(
    query: str,
    k: int = 8,
    path_filter: str | None = None,
    *,
    cfg: Config | None = None,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    cfg = cfg or Config.from_env()
    query = (query or "").strip()
    if not query:
        raise ToolError("query must not be empty")
    k = max(1, min(int(k), 20))
    index = await asyncio.to_thread(load_index, cfg.index_dir)
    info = {"chunks": len(index.chunks), "files": len(index.files), "updated_at": index.updated_at}
    if not index.chunks:
        raise ToolError(
            f"The paper index at {cfg.index_dir} is empty",
            hint=f"Check ARCH_LIBRARY_DIRS and re-run: uv run --script {SERVER_SCRIPT} index",
        )

    n = len(index.chunks)
    if path_filter:
        needle = path_filter.lower()
        mask = np.fromiter((needle in c.path.lower() for c in index.chunks), dtype=bool, count=n)
    else:
        mask = np.ones(n, dtype=bool)
    warnings: list[str] = []
    if not mask.any():
        return {"mode": "none", "query": query, "index": info, "results": [],
                "warnings": [f"no indexed file path contains {path_filter!r}"]}

    q_tokens = tokenize(query)
    bm25_ranking, bm25_scores = _bm25_ranking(index, q_tokens, mask)

    own_client = client is None
    http = client or httpx.AsyncClient()
    try:
        dense_ranking: list[int] = []
        dense_ok = False
        server_down = False
        if index.vectors is None or not (index.vec_rows >= 0).any():
            warnings.append("index has no embeddings (built while the retrieval server was down or with --no-embed)")
        else:
            try:
                query_vec = await embed_query(http, cfg, query)
                if query_vec.shape[0] != index.vectors.shape[1]:
                    raise ServiceError(
                        f"query embedding has {query_vec.shape[0]} dims but the index has {index.vectors.shape[1]};"
                        " rebuild the index with `index --rebuild`"
                    )
                dense_ranking = _dense_ranking(index, query_vec, mask)
                dense_ok = True
            except ServiceError as exc:
                server_down = isinstance(exc, ServiceUnavailable)
                warnings.append(f"dense retrieval unavailable: {exc.message}")

        if dense_ok:
            fused = rrf_fuse([bm25_ranking, dense_ranking])
            score_type = "rrf"
        else:
            fused = [(i, float(bm25_scores[i])) for i in bm25_ranking]
            score_type = "bm25"
        candidates = fused[:RERANK_TOP]
        terms = frozenset(q_tokens)
        windows = {i: best_window(index.chunks[i].text, terms) for i, _ in candidates}

        reranked = False
        if candidates and not server_down:
            documents = [
                f"{index.chunks[i].header}\n{index.chunks[i].text[windows[i][0]:windows[i][1]]}" for i, _ in candidates
            ]
            try:
                scores = await rerank(http, cfg, query, documents)
                candidates = sorted(
                    ((i, s) for (i, _), s in zip(candidates, scores)), key=lambda item: -item[1]
                )
                reranked = True
                score_type = "rerank"
            except ServiceError as exc:
                warnings.append(f"reranker unavailable: {exc.message}")
    finally:
        if own_client:
            await http.aclose()

    mode = {
        (True, True): "hybrid+rerank",
        (True, False): "hybrid",
        (False, True): "bm25+rerank",
        (False, False): "bm25-only",
    }[(dense_ok, reranked)]
    results = []
    for i, score in candidates[:k]:
        c = index.chunks[i]
        ws, we = windows[i]
        start = c.start + ws
        file_info = index.files.get(c.path)
        item: dict[str, Any] = {
            "path": c.path,
            "title": file_info.title if file_info else Path(c.path).stem,
            "chunk_id": chunk_id(c.path, c.chunk_no),
        }
        section = label_at(file_info.sections, start) if file_info and file_info.sections else c.section
        page = page_at(file_info.page_starts, start) if file_info and file_info.page_starts else c.page
        if section:
            item["section"] = section
        if page:
            item["page"] = page
        item.update(
            start_char=start,
            end_char=c.start + we,
            text=c.text[ws:we],
            score=round(float(score), 4) if np.isfinite(score) else None,
        )
        results.append(item)
    out: dict[str, Any] = {"mode": mode, "score_type": score_type, "query": query, "index": info, "results": results}
    if warnings:
        out["warnings"] = warnings
    return out
