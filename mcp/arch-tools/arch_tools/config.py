"""Environment-driven configuration (read fresh on every call so tests can patch env)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

DEFAULTS = {
    "ARCH_LLM_BASE": "http://omen:8080",
    "ARCH_RETRIEVAL_BASE": "http://omen:8081",
    "ARCH_LLM_KEY_FILE": "~/.config/llama-server/api-key",
    "ARCH_INDEX_DIR": "~/Storage/AI-Workspace/research-index",
    "ARCH_LIBRARY_DIRS": "~/ResearchHub:~/AI-Workspace/research/papers",
    "ARCH_CACHE_DIR": "~/.cache/arch-tools",
    "ARCH_MEMORY_CLI": "~/.local/bin/memory",
}

EMBED_MODEL = "embed"
RERANK_MODEL = "rerank"
DEFAULT_CHAT_MODEL = "laguna-xs"


def _expand(value: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(value.strip())))


def _base_url(value: str) -> str:
    url = value.strip().rstrip("/")
    if url.endswith("/v1"):  # tolerate ".../v1" in the env var
        url = url[: -len("/v1")]
    return url


@dataclass(frozen=True)
class Config:
    llm_base: str
    retrieval_base: str
    key_file: Path
    index_dir: Path
    library_dirs: tuple[Path, ...]
    cache_dir: Path
    memory_cli: Path

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Config":
        env = os.environ if env is None else env

        def get(name: str) -> str:
            value = env.get(name, "")
            return value if value.strip() else DEFAULTS[name]

        dirs = tuple(_expand(p) for p in get("ARCH_LIBRARY_DIRS").split(":") if p.strip())
        return cls(
            llm_base=_base_url(get("ARCH_LLM_BASE")),
            retrieval_base=_base_url(get("ARCH_RETRIEVAL_BASE")),
            key_file=_expand(get("ARCH_LLM_KEY_FILE")),
            index_dir=_expand(get("ARCH_INDEX_DIR")),
            library_dirs=dirs,
            cache_dir=_expand(get("ARCH_CACHE_DIR")),
            memory_cli=_expand(get("ARCH_MEMORY_CLI")),
        )

    def api_key(self) -> str | None:
        try:
            key = self.key_file.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        return key or None

    def auth_headers(self) -> dict[str, str]:
        key = self.api_key()
        return {"Authorization": f"Bearer {key}"} if key else {}
