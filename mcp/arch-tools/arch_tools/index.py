"""Incremental paper index: walk library dirs, extract, chunk, embed, store.

Layout of ARCH_INDEX_DIR
    index.sqlite          files (manifest: path, mtime_ns, size, title, ...), chunks (text + offsets), meta
    vectors-<gen>.npy     float32 L2-normalized embeddings; chunks.vec_row points into it (-1 = no vector yet)
    manifest.json         human-readable export of the file manifest (sqlite is authoritative)

Only new/changed files are re-processed, removed files are dropped, and chunks that still lack a vector
(e.g. the embedding server was down last time) are embedded on the next run.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import sqlite3
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Sequence

import httpx
import numpy as np

from .chunking import chunk_spans, label_at, page_at, section_labels
from .config import EMBED_MODEL, Config
from .documents import SUPPORTED_SUFFIXES, Document, ExtractionError, extract_document
from .net import ServiceError, ToolError
from .retrieval import embed_texts

MAX_FILE_BYTES = 50 * 1024 * 1024
DB_NAME = "index.sqlite"
MANIFEST_NAME = "manifest.json"
SKIP_DIR_NAMES = {"node_modules", "__pycache__", "venv", "site-packages"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS files (
    path TEXT PRIMARY KEY, mtime_ns INTEGER NOT NULL, size INTEGER NOT NULL, kind TEXT, title TEXT,
    n_chunks INTEGER NOT NULL DEFAULT 0, page_starts TEXT, sections TEXT, error TEXT, indexed_at REAL
);
CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT NOT NULL, chunk_no INTEGER NOT NULL,
    start_char INTEGER NOT NULL, end_char INTEGER NOT NULL, section TEXT, page INTEGER,
    header TEXT NOT NULL, text TEXT NOT NULL, vec_row INTEGER NOT NULL DEFAULT -1
);
CREATE INDEX IF NOT EXISTS chunks_path ON chunks(path);
"""

Log = Callable[[str], None]


def _stderr(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def contextual_header(title: str, section: str | None, page: int | None) -> str:
    parts = [f"Title: {title}"]
    if section:
        parts.append(f"Section: {section}")
    if page:
        parts.append(f"Page: {page}")
    return "; ".join(parts)


def chunk_id(path: str, chunk_no: int) -> str:
    return f"{hashlib.sha1(path.encode()).hexdigest()[:10]}:{chunk_no}"


def scan_library(dirs: Sequence[Path], log: Log = _stderr) -> dict[str, tuple[int, int]]:
    """{absolute path: (mtime_ns, size)} of .md/.txt/.pdf files. Hidden dirs and node_modules are skipped;
    symlinks are followed once (by real path)."""
    files: dict[str, tuple[int, int]] = {}
    seen_files: set[str] = set()
    seen_dirs: set[str] = set()
    for root in dirs:
        if not root.is_dir():
            log(f"[index] warning: library dir not found: {root}")
            continue
        for dirpath, dirnames, filenames in os.walk(root, followlinks=True):
            real = os.path.realpath(dirpath)
            if real in seen_dirs:
                dirnames[:] = []
                continue
            seen_dirs.add(real)
            dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and d not in SKIP_DIR_NAMES)
            for name in sorted(filenames):
                if name.startswith(".") or Path(name).suffix.lower() not in SUPPORTED_SUFFIXES:
                    continue
                path = os.path.abspath(os.path.join(dirpath, name))
                try:
                    st = os.stat(path)
                except OSError:
                    continue
                real_file = os.path.realpath(path)
                if real_file in seen_files:
                    continue
                seen_files.add(real_file)
                files[path] = (st.st_mtime_ns, st.st_size)
    return files


def connect(index_dir: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(index_dir / DB_NAME, timeout=30)
    conn.executescript(SCHEMA)
    return conn


def read_meta(conn: sqlite3.Connection) -> dict[str, str]:
    return {k: v for k, v in conn.execute("SELECT key, value FROM meta")}


def _set_meta(conn: sqlite3.Connection, values: dict[str, Any]) -> None:
    conn.executemany(
        "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
        [(k, v if isinstance(v, str) else json.dumps(v)) for k, v in values.items()],
    )


def load_vectors(index_dir: Path, meta: dict[str, str], mmap: bool = True) -> np.ndarray | None:
    name = meta.get("vectors_file")
    if not name:
        return None
    path = index_dir / name
    try:
        matrix = np.load(path, mmap_mode="r" if mmap else None)
    except (OSError, ValueError):
        return None
    return matrix if matrix.ndim == 2 else None


class _IndexLock:
    def __init__(self, path: Path):
        self.path = path
        self.fd: int | None = None

    def __enter__(self) -> "_IndexLock":
        self.fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(self.fd)
            self.fd = None
            raise ToolError(f"another `index` run is in progress for {self.path.parent}") from None
        return self

    def __exit__(self, *exc: object) -> None:
        if self.fd is not None:
            fcntl.flock(self.fd, fcntl.LOCK_UN)
            os.close(self.fd)
            self.fd = None


def document_rows(doc: Document) -> tuple[list[tuple[Any, ...]], list[tuple[int, str]]]:
    labels = section_labels(doc.headings, doc.title)
    rows = []
    path = str(doc.path)
    for no, (start, end) in enumerate(chunk_spans(doc.text, [h.offset for h in doc.headings])):
        section = label_at(labels, start)
        page = page_at(doc.page_starts, start)
        header = contextual_header(doc.title, section, page)
        rows.append((path, no, start, end, section, page, header, doc.text[start:end]))
    return rows, labels


async def build_index(
    cfg: Config,
    *,
    dirs: Sequence[Path] | None = None,
    rebuild: bool = False,
    embed: bool = True,
    batch_size: int = 16,
    client: httpx.AsyncClient | None = None,
    log: Log = _stderr,
) -> dict[str, Any]:
    index_dir = cfg.index_dir
    index_dir.mkdir(parents=True, exist_ok=True)
    with _IndexLock(index_dir / ".lock"):
        conn = connect(index_dir)
        try:
            return await _build(conn, cfg, list(dirs or cfg.library_dirs), rebuild, embed, batch_size, client, log)
        finally:
            conn.close()


async def _build(
    conn: sqlite3.Connection,
    cfg: Config,
    dirs: list[Path],
    rebuild: bool,
    embed: bool,
    batch_size: int,
    client: httpx.AsyncClient | None,
    log: Log,
) -> dict[str, Any]:
    started = time.monotonic()
    index_dir = cfg.index_dir
    warnings: list[str] = []
    meta = read_meta(conn)

    old_vectors: np.ndarray | None = None
    if rebuild:
        with conn:
            conn.execute("DELETE FROM chunks")
            conn.execute("DELETE FROM files")
        log("[index] --rebuild: cleared existing index")
    else:
        old_vectors = load_vectors(index_dir, meta)
        has_rows = conn.execute("SELECT COUNT(*) FROM chunks WHERE vec_row >= 0").fetchone()[0]
        if has_rows and old_vectors is None:
            warnings.append("vectors file missing or unreadable; all chunks will be re-embedded")
            log(f"[index] warning: {warnings[-1]}")
            with conn:
                conn.execute("UPDATE chunks SET vec_row = -1")

    log(f"[index] scanning: {', '.join(str(d) for d in dirs)}")
    current = scan_library(dirs, log)
    known = {p: (m, s) for p, m, s in conn.execute("SELECT path, mtime_ns, size FROM files")}
    removed = sorted(set(known) - set(current))
    changed = sorted(p for p in current if p in known and known[p] != current[p])
    new = sorted(p for p in current if p not in known)
    unchanged = len(current) - len(changed) - len(new)
    log(f"[index] {len(current)} files: {len(new)} new, {len(changed)} changed, {len(removed)} removed, {unchanged} unchanged")

    with conn:
        for path in removed:
            conn.execute("DELETE FROM chunks WHERE path = ?", (path,))
            conn.execute("DELETE FROM files WHERE path = ?", (path,))

    todo = new + changed
    skipped = 0
    for i, path in enumerate(todo, 1):
        mtime_ns, size = current[path]
        doc: Document | None = None
        error: str | None = None
        if size > MAX_FILE_BYTES:
            error = f"skipped: {size / 1e6:.1f} MB exceeds the 50 MB limit"
        else:
            try:
                doc = extract_document(Path(path))
            except (ExtractionError, OSError) as exc:
                error = f"extraction failed: {exc}"
        rows: list[tuple[Any, ...]] = []
        labels: list[tuple[int, str]] = []
        if doc is not None:
            if doc.text.strip():
                rows, labels = document_rows(doc)
            else:
                error = "no extractable text"
        if error:
            skipped += 1
        with conn:
            conn.execute("DELETE FROM chunks WHERE path = ?", (path,))
            conn.executemany(
                "INSERT INTO chunks (path, chunk_no, start_char, end_char, section, page, header, text)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
            conn.execute(
                "INSERT OR REPLACE INTO files (path, mtime_ns, size, kind, title, n_chunks, page_starts, sections,"
                " error, indexed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    path, mtime_ns, size, doc.kind if doc else None, doc.title if doc else None, len(rows),
                    json.dumps(doc.page_starts) if doc and doc.page_starts else None,
                    json.dumps(labels) if labels else None, error, time.time(),
                ),
            )
        log(f"[index] ({i}/{len(todo)}) {path}: {len(rows)} chunks" + (f" [{error}]" if error else ""))

    pending = conn.execute("SELECT id, header, text FROM chunks WHERE vec_row < 0 ORDER BY id").fetchall()
    new_vectors: dict[int, np.ndarray] = {}
    if pending and not embed:
        log(f"[index] --no-embed: {len(pending)} chunks stored without vectors (BM25 only)")
    elif pending:
        log(f"[index] embedding {len(pending)} chunks via {cfg.retrieval_base} (batch {batch_size})")
        own_client = client is None
        http = client or httpx.AsyncClient()
        last_report = time.monotonic()
        try:
            for b in range(0, len(pending), batch_size):
                batch = pending[b : b + batch_size]
                try:
                    vectors = await embed_texts(http, cfg, [f"{header}\n\n{text}" for _, header, text in batch])
                except ServiceError as exc:
                    warnings.append(
                        f"embedding stopped after {len(new_vectors)}/{len(pending)} chunks: {exc.message}."
                        " Re-run `index` later to embed the rest; search falls back to BM25 for them."
                    )
                    log(f"[index] warning: {warnings[-1]}")
                    break
                for (cid, _, _), vec in zip(batch, vectors):
                    new_vectors[cid] = vec
                done = min(b + batch_size, len(pending))
                if time.monotonic() - last_report > 3 or done == len(pending):
                    log(f"[index] embedded {done}/{len(pending)} chunks")
                    last_report = time.monotonic()
        finally:
            if own_client:
                await http.aclose()

    if not (rebuild or removed or todo or new_vectors) and meta.get("generation"):
        log("[index] no file changes and no new vectors; index left as is")
        return _summary(conn, index_dir, meta, new, changed, removed, skipped, started, warnings)

    # Assemble the vector matrix for the new generation (unchanged rows are carried over).
    dim = int(old_vectors.shape[1]) if old_vectors is not None and old_vectors.shape[0] else None
    if new_vectors:
        new_dim = int(next(iter(new_vectors.values())).shape[0])
        if dim is not None and new_dim != dim:
            raise ToolError(
                f"embedding dimension changed ({dim} -> {new_dim}); the embedding model differs from the one"
                " used to build this index",
                hint="re-run with `index --rebuild`",
            )
        dim = new_dim
    stacked: list[np.ndarray] = []
    assignments: list[tuple[int, int]] = []
    for cid, vec_row in conn.execute("SELECT id, vec_row FROM chunks ORDER BY id").fetchall():
        if cid in new_vectors:
            vec = new_vectors[cid]
        elif vec_row >= 0 and old_vectors is not None and vec_row < old_vectors.shape[0]:
            vec = np.asarray(old_vectors[vec_row])
        else:
            assignments.append((-1, cid))
            continue
        assignments.append((len(stacked), cid))
        stacked.append(vec)
    matrix = np.vstack(stacked).astype(np.float32) if stacked else np.zeros((0, dim or 0), dtype=np.float32)

    generation = f"{time.strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:6]}"
    vectors_name = f"vectors-{generation}.npy"
    tmp = index_dir / f".{vectors_name}.tmp"
    with open(tmp, "wb") as fh:
        np.save(fh, matrix)
    os.replace(tmp, index_dir / vectors_name)
    meta_values = {
        "generation": generation,
        "vectors_file": vectors_name,
        "dim": str(dim or 0),
        "embed_model": EMBED_MODEL,
        "retrieval_base": cfg.retrieval_base,
        "library_dirs": [str(d) for d in dirs],
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    with conn:
        conn.executemany("UPDATE chunks SET vec_row = ? WHERE id = ?", assignments)
        _set_meta(conn, meta_values)
    del old_vectors  # release the memory map before deleting superseded files
    for stale in index_dir.glob("vectors-*.npy"):
        if stale.name != vectors_name:
            try:
                stale.unlink()
            except OSError:
                pass
    meta = read_meta(conn)
    _write_manifest(conn, index_dir, meta)
    return _summary(conn, index_dir, meta, new, changed, removed, skipped, started, warnings)


def _write_manifest(conn: sqlite3.Connection, index_dir: Path, meta: dict[str, str]) -> None:
    files = {
        path: {"mtime_ns": mtime_ns, "size": size, "title": title, "chunks": n_chunks, **({"error": error} if error else {})}
        for path, mtime_ns, size, title, n_chunks, error in conn.execute(
            "SELECT path, mtime_ns, size, title, n_chunks, error FROM files ORDER BY path"
        )
    }
    manifest = {
        "generation": meta.get("generation"),
        "updated_at": meta.get("updated_at"),
        "embed_model": meta.get("embed_model"),
        "dim": int(meta.get("dim") or 0),
        "library_dirs": json.loads(meta.get("library_dirs") or "[]"),
        "files": files,
    }
    tmp = index_dir / f".{MANIFEST_NAME}.tmp"
    tmp.write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, index_dir / MANIFEST_NAME)


def _summary(
    conn: sqlite3.Connection,
    index_dir: Path,
    meta: dict[str, str],
    new: list[str],
    changed: list[str],
    removed: list[str],
    skipped: int,
    started: float,
    warnings: list[str],
) -> dict[str, Any]:
    n_files = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    n_chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    n_vectors = conn.execute("SELECT COUNT(*) FROM chunks WHERE vec_row >= 0").fetchone()[0]
    return {
        "index_dir": str(index_dir),
        "generation": meta.get("generation"),
        "files": n_files,
        "chunks": n_chunks,
        "embedded_chunks": n_vectors,
        "chunks_without_vectors": n_chunks - n_vectors,
        "new": len(new),
        "changed": len(changed),
        "removed": len(removed),
        "skipped_files": skipped,
        "seconds": round(time.monotonic() - started, 2),
        "warnings": warnings,
    }
