"""Unit tests for arch-tools (no network). Run:
    uv run --no-project --python 3.12 --with pytest --with "mcp>=2.3,<3" --with httpx --with rank-bm25 --with numpy \
        --with pypdf --with jsonschema pytest mcp/arch-tools/tests -q
"""
import asyncio
import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arch_tools import citations as C  # noqa: E402
from arch_tools.chunking import chunk_spans  # noqa: E402
from arch_tools.config import Config  # noqa: E402
from arch_tools.llm import local_llm, strip_think  # noqa: E402
from arch_tools.memory import build_search_argv  # noqa: E402
from arch_tools.search import rrf_fuse  # noqa: E402


# ---------------- citations: extraction ----------------

def kinds(text):
    return [(c.kind, c.value) for c in C.dedupe(C.extract_citations(text))]


def test_extracts_new_style_arxiv_with_and_without_prefix():
    got = kinds("See arXiv:2310.01798 and also 2402.05120v2 for details.")
    assert ("arxiv", "2310.01798") in got
    assert ("arxiv", "2402.05120") in got


def test_extracts_old_style_arxiv():
    assert ("arxiv", "cs/0101001") in kinds("Classic result in arXiv:cs/0101001.")


def test_extracts_doi_without_trailing_punctuation():
    got = kinds("Published as doi:10.1038/s41586-025-10072-4.")
    assert ("doi", "10.1038/s41586-025-10072-4") in got


def test_arxiv_url_becomes_arxiv_id_and_plain_url_stays_url():
    got = kinds("Paper: https://arxiv.org/abs/2305.14251 and blog https://www.anthropic.com/engineering/building-effective-agents")
    assert ("arxiv", "2305.14251") in got
    assert any(k == "url" and "anthropic.com" in v for k, v in got)


def test_markdown_link_and_dedupe():
    got = kinds("[FActScore](https://arxiv.org/abs/2305.14251) ... again arXiv:2305.14251")
    assert got.count(("arxiv", "2305.14251")) == 1


def test_captures_title_next_to_id():
    cits = C.extract_citations("Huang et al. *Large Language Models Cannot Self-Correct Reasoning Yet*. arXiv:2310.01798")
    arx = [c for c in cits if c.kind == "arxiv"][0]
    assert arx.title and "Self-Correct" in arx.title


def test_parse_arxiv_id_versions():
    assert C.parse_arxiv_id("2310.01798v3") == ("2310.01798", 3)
    assert C.parse_arxiv_id("2310.01798") == ("2310.01798", None)
    assert C.parse_arxiv_id("not-an-id") is None


# ---------------- citations: titles and summary ----------------

def test_title_matching_is_robust_to_case_and_punctuation():
    assert C.titles_match("large language models cannot self-correct reasoning yet",
                          "Large Language Models Cannot Self-Correct Reasoning Yet")
    assert not C.titles_match("Attention Is All You Need", "Large Language Models Cannot Self-Correct Reasoning Yet")


def test_summary_ok_flag_ignores_unreachable():
    details = [{"status": C.VALID}, {"status": C.UNREACHABLE}]
    assert C.summarize(details)["ok"] is True
    details.append({"status": C.NOT_FOUND})
    s = C.summarize(details)
    assert s["ok"] is False and s["not_found"] == 1 and s["unreachable"] == 1


# ---------------- chunking ----------------

def test_chunks_cover_text_and_respect_size():
    text = ("Paragraph about memory. " * 40 + "\n\n") * 12
    spans = chunk_spans(text, target=800, overlap=120)
    assert spans[0][0] == 0
    assert spans[-1][1] >= len(text.rstrip())
    for s, e in spans:
        assert e > s
        assert e - s <= 800 * 1.3
        assert not text[s].isspace() and not text[e - 1].isspace()
    # consecutive chunks overlap or touch (nothing skipped)
    for (s1, e1), (s2, e2) in zip(spans, spans[1:]):
        assert s2 <= e1 + 2


def test_short_text_is_one_chunk():
    assert chunk_spans("Short note.", target=800, overlap=100) == [(0, len("Short note."))]


# ---------------- fusion ----------------

def test_rrf_prefers_documents_ranked_high_in_both_lists():
    fused = rrf_fuse([[1, 2, 3], [2, 1, 4]])
    top = [doc for doc, _ in fused[:2]]
    assert set(top) == {1, 2}
    assert fused[-1][0] in (3, 4)


def test_rrf_single_ranking_keeps_order():
    assert [d for d, _ in rrf_fuse([[5, 3, 9]])] == [5, 3, 9]


# ---------------- local_llm ----------------

def test_strip_think_removes_reasoning_blocks():
    assert strip_think("<think>secret plan</think>\nAnswer: 42") == "Answer: 42"


def _mock_client(message, finish="stop"):
    def handler(request: httpx.Request):
        if request.url.path.endswith("/v1/models"):
            return httpx.Response(200, json={"data": [{"id": "laguna-xs"}, {"id": "qwen3.6-35b"}]})
        assert request.headers["authorization"].startswith("Bearer ")
        body = json.loads(request.content)
        assert body["model"] == "laguna-xs"
        return httpx.Response(200, json={"model": "laguna-xs", "choices": [{"message": message, "finish_reason": finish}],
                                         "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8}})
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    key = tmp_path / "key"
    key.write_text("test-key\n")
    monkeypatch.setenv("ARCH_LLM_BASE", "http://router.test")
    monkeypatch.setenv("ARCH_LLM_KEY_FILE", str(key))
    return Config.from_env()


def test_local_llm_returns_content(cfg):
    async def run():
        async with _mock_client({"content": "<think>hmm</think>pong"}) as client:
            return await local_llm("ping", model="laguna-xs", cfg=cfg, client=client)
    out = asyncio.run(run())
    assert out["text"] == "pong" and out["source"] == "content"


def test_local_llm_truncated_reasoning_is_not_an_answer(cfg):
    async def run():
        async with _mock_client({"content": "", "reasoning_content": "Okay, the user wants"}, finish="length") as client:
            return await local_llm("ping", model="laguna-xs", cfg=cfg, client=client)
    out = asyncio.run(run())
    assert out["text"] == "" and out["source"] == "empty" and "max_tokens" in out.get("warning", "")


def test_local_llm_thinking_flag_reaches_template(cfg):
    seen = []

    def handler(request: httpx.Request):
        if request.url.path.endswith("/v1/models"):
            return httpx.Response(200, json={"data": [{"id": "laguna-xs"}]})
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]})

    async def run(**kw):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await local_llm("ping", model="laguna-xs", cfg=cfg, client=client, **kw)

    asyncio.run(run(thinking=False))
    asyncio.run(run())
    assert seen[0]["chat_template_kwargs"] == {"enable_thinking": False}
    assert "chat_template_kwargs" not in seen[1]  # default: the model's own setting


def test_local_llm_unknown_model_lists_choices(cfg):
    async def run():
        async with _mock_client({"content": "x"}) as client:
            return await local_llm("ping", model="nope", cfg=cfg, client=client)
    with pytest.raises(Exception) as err:
        asyncio.run(run())
    assert "nope" in str(err.value)


# ---------------- memory_search argv ----------------

def test_memory_argv_maps_filters_and_guards_query():
    argv = build_search_argv("/bin/memory", "-rf looks like a flag", "project_memory", project="arch-agents",
                             memory_types=["bug_pattern", "repo_constraint"], status="active", limit=3)
    assert argv[0] == "/bin/memory" and "search" in argv
    joined = " ".join(argv)
    assert "--project=arch-agents" in joined and "--status=active" in joined and "--limit=3" in joined
    assert "bug_pattern,repo_constraint" in joined
    # the query comes after `--`, so it can never be parsed as an option
    assert argv.index("--") < argv.index("-rf looks like a flag")


@pytest.mark.parametrize("kwargs", [
    {"collection": "nope"},
    {"collection": "project_memory", "status": "deleted"},
    {"collection": "project_memory", "memory_types": ["not_a_type"]},
])
def test_memory_argv_rejects_bad_values(kwargs):
    with pytest.raises(Exception):
        build_search_argv("/bin/memory", "q", **kwargs)


def test_memory_argv_rejects_empty_query():
    with pytest.raises(Exception):
        build_search_argv("/bin/memory", "   ", "project_memory")
