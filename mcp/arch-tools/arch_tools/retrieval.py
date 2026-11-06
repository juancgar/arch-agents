"""Clients for the llama.cpp retrieval server: /v1/embeddings and /v1/rerank."""

from __future__ import annotations

from typing import Sequence

import httpx
import numpy as np

from .config import EMBED_MODEL, RERANK_MODEL, Config
from .net import ServiceError, request_json

# Qwen3-Embedding expects an instruction on the query side only.
QUERY_INSTRUCTION = (
    "Instruct: Given a search query, retrieve relevant passages from research papers and notes that answer it\n"
    "Query: "
)


def normalize_rows(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (matrix / norms).astype(np.float32, copy=False)


async def embed_texts(
    client: httpx.AsyncClient,
    cfg: Config,
    texts: Sequence[str],
    *,
    timeout: httpx.Timeout | float = httpx.Timeout(120.0, connect=5.0),
) -> np.ndarray:
    """L2-normalized float32 embeddings, one row per input text."""
    if not texts:
        return np.zeros((0, 0), dtype=np.float32)
    payload = await request_json(
        client,
        "POST",
        f"{cfg.retrieval_base}/v1/embeddings",
        json_body={"model": EMBED_MODEL, "input": list(texts)},
        headers=cfg.auth_headers(),
        timeout=timeout,
        service="embedding server",
    )
    try:
        items = sorted(payload["data"], key=lambda d: d.get("index", 0))
        matrix = np.asarray([item["embedding"] for item in items], dtype=np.float32)
    except (KeyError, TypeError, ValueError) as exc:
        raise ServiceError(f"unexpected embedding response: {exc}") from exc
    if matrix.ndim != 2 or matrix.shape[0] != len(texts):
        raise ServiceError(f"embedding server returned {matrix.shape[0]} vectors for {len(texts)} inputs")
    return normalize_rows(matrix)


async def embed_query(
    client: httpx.AsyncClient,
    cfg: Config,
    query: str,
    *,
    timeout: httpx.Timeout | float = httpx.Timeout(30.0, connect=3.0),
) -> np.ndarray:
    vectors = await embed_texts(client, cfg, [QUERY_INSTRUCTION + query], timeout=timeout)
    return vectors[0]


async def rerank(
    client: httpx.AsyncClient,
    cfg: Config,
    query: str,
    documents: Sequence[str],
    *,
    timeout: httpx.Timeout | float = httpx.Timeout(90.0, connect=3.0),
) -> list[float]:
    """Relevance score per document (same order as `documents`)."""
    if not documents:
        return []
    payload = await request_json(
        client,
        "POST",
        f"{cfg.retrieval_base}/v1/rerank",
        json_body={"model": RERANK_MODEL, "query": query, "documents": list(documents)},
        headers=cfg.auth_headers(),
        timeout=timeout,
        service="reranker",
    )
    scores = [float("-inf")] * len(documents)
    try:
        for item in payload["results"]:
            index = int(item["index"])
            if 0 <= index < len(scores):
                scores[index] = float(item["relevance_score"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ServiceError(f"unexpected rerank response: {exc}") from exc
    if all(s == float("-inf") for s in scores):
        raise ServiceError("reranker returned no scores")
    return scores
