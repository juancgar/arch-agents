"""MCP tool catalogue (names, descriptions, JSON schemas) and argument dispatch.

Kept free of `mcp` imports so it can be unit-tested and reused by the CLI.
"""

from __future__ import annotations

import copy
from typing import Any

from .config import DEFAULT_CHAT_MODEL, Config
from .memory import COLLECTIONS, MEMORY_TYPES, STATUSES
from .net import ToolError
from .routing import ROUTES, SIGNALS

INSTRUCTIONS = (
    "arch-tools gives deterministic and local helpers to arch-agents. "
    "verify_citations: run on any research output before finalizing; NOT_FOUND / TITLE_MISMATCH must be fixed "
    "or removed, UNREACHABLE is not a failure. paper_search: search the local paper library first and cite "
    "results by path + start_char/end_char (or page). local_llm: free local model for bulk text work "
    "(summaries, extraction, reformatting), not for final judgments. memory_search: read-only memory lookup; "
    "repository evidence overrides memory. plan_route: the orchestrator's routing check; call it once per request "
    "before delegating and follow the plan it returns."
)

TOOLS: list[dict[str, Any]] = [
    {
        "name": "verify_citations",
        "description": (
            "Deterministically check citations. Extracts arXiv IDs (2310.01798, arXiv:2310.01798v2, old-style "
            "cs/0101001), DOIs (10.xxxx/...) and http(s) URLs from `text`, and/or checks an explicit `citations` "
            "list. arXiv IDs are checked with the arXiv API, DOIs with Crossref (doi.org fallback), URLs with "
            "HEAD/GET. A title written next to an identifier (*Title*. arXiv:..., \"Title\" (arXiv:...), "
            "[Title](url)) or given in `citations` is fuzzy-matched against the registered title. Per-citation "
            "status: VALID, NOT_FOUND, TITLE_MISMATCH (both titles returned) or UNREACHABLE (offline, network "
            "error, blocked or timed out; never counts as a failure). `ok` is false if any citation is "
            "NOT_FOUND or TITLE_MISMATCH. Verdicts are cached for 30 days."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Text to scan (markdown report, reference list, answer draft).",
                    "maxLength": 2_000_000,
                },
                "citations": {
                    "type": "array",
                    "description": "Explicit citations. Each needs at least one of id, doi, url (precedence id > doi > url).",
                    "maxItems": 200,
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "description": "arXiv identifier, e.g. 2310.01798, arXiv:2310.01798v2, cs/0101001"},
                            "doi": {"type": "string", "description": "DOI, e.g. 10.1038/nature14539 (doi: and https://doi.org/ prefixes accepted)"},
                            "url": {"type": "string", "description": "http(s) URL that must be live"},
                            "title": {"type": "string", "description": "Title as cited; compared with the registered title"},
                        },
                        "additionalProperties": False,
                    },
                },
                "offline": {
                    "type": "boolean",
                    "default": False,
                    "description": "Never touch the network; report cached verdicts only (the rest is UNREACHABLE).",
                },
            },
            "additionalProperties": False,
        },
        "annotations": {"title": "Verify citations", "read_only_hint": True, "open_world_hint": True, "idempotent_hint": True},
    },
    {
        "name": "paper_search",
        "description": (
            "Search the local research library (ResearchHub notes and local PDFs) with hybrid retrieval: BM25 + "
            "dense embeddings fused by reciprocal-rank fusion, then cross-encoder reranking of the top 50. "
            "Returns the k best passages: path, title, chunk_id, section and/or page when known, start_char/"
            "end_char of the passage in the extracted document text, text (<= 1,200 chars) and score. `mode` "
            "reports degradation, e.g. \"bm25-only\" when the retrieval server is down."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1, "maxLength": 2000, "description": "Natural-language query or keywords."},
                "k": {"type": "integer", "minimum": 1, "maximum": 20, "default": 8, "description": "Number of passages to return."},
                "path_filter": {
                    "type": "string",
                    "description": "Only search files whose absolute path contains this substring (case-insensitive).",
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        "annotations": {"title": "Search local papers", "read_only_hint": True, "open_world_hint": False, "idempotent_hint": True},
    },
    {
        "name": "local_llm",
        "description": (
            "Run one prompt on a free local model (llama.cpp router; no API cost, no internet). Use it for bulk "
            "text work such as summarizing, extracting, classifying or reformatting, not for final judgments. "
            "Returns the answer text with <think> blocks removed. The first call after a model swap can take "
            "10-60 s. An unknown model name returns the list of available models."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "minLength": 1, "description": "User message."},
                "system": {"type": "string", "description": "Optional system message."},
                "model": {"type": "string", "default": DEFAULT_CHAT_MODEL, "description": f"Router model id (default {DEFAULT_CHAT_MODEL})."},
                "max_tokens": {"type": "integer", "minimum": 1, "maximum": 32768, "default": 2048},
                "temperature": {"type": "number", "minimum": 0, "maximum": 2},
            },
            "required": ["prompt"],
            "additionalProperties": False,
        },
        "annotations": {"title": "Local LLM", "read_only_hint": True, "open_world_hint": False},
    },
    {
        "name": "memory_search",
        "description": (
            "Read-only search of the local semantic memory service (runs `memory search --json`). Returns stored "
            "memories with relevance scores. Memory can be stale: repository evidence overrides it. Collections: project_memory (repo facts, decisions, constraints), research_memory, "
            "task_memory, knowledge_memory."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1, "maxLength": 2000},
                "collection": {"type": "string", "enum": list(COLLECTIONS)},
                "project": {"type": "string", "description": "Canonical project id to restrict to."},
                "memory_types": {
                    "type": "array",
                    "items": {"type": "string", "enum": list(MEMORY_TYPES)},
                    "description": "Match any of these memory types.",
                },
                "status": {"type": "string", "enum": list(STATUSES)},
                "limit": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "Match any of these tags."},
                "scope_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Match memories scoped to any of these repository paths.",
                },
            },
            "required": ["query", "collection"],
            "additionalProperties": False,
        },
        "annotations": {"title": "Search memory (read-only)", "read_only_hint": True, "open_world_hint": False, "idempotent_hint": True},
    },
]

TOOLS.append(
    {
        "name": "plan_route",
        "description": (
            "Check and complete the orchestrator's routing decision before any delegation. Give the request, your "
            "draft route and agents, and a true/false answer for every checklist signal. Returns the corrected "
            "plan: route (hard precedence rules applied), difficulty S/M/L computed from the checklist, the agent "
            "sequence with required gates (tests before code, review after code, no writers on read-only requests), "
            "the list of fixes applied, and `final_json`. On local plans it also samples the routing decision a few "
            "more times and takes a majority vote; `ambiguous: true` means the votes disagreed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "request": {
                    "type": "string", "minLength": 1, "maxLength": 8000,
                    "description": "The user's request, rewritten to be self-contained if it depends on earlier turns.",
                },
                "route": {"type": "string", "enum": list(ROUTES), "description": "Your draft route."},
                "signals": {
                    "type": "object",
                    "description": "Checklist: answer every item true or false about the request.",
                    "properties": {k: {"type": "boolean", "description": q} for k, q in SIGNALS.items()},
                    "required": list(SIGNALS),
                    "additionalProperties": False,
                },
                "agents": {"type": "array", "items": {"type": "string"}, "description": "Draft agent sequence."},
                "difficulty": {"type": "string", "enum": ["S", "M", "L"], "description": "Your own estimate (compared, not used)."},
                "clarify": {"type": ["string", "null"], "description": "The one batched question to ask, or null."},
                "assumptions": {"type": "array", "items": {"type": "string"}},
                "explicit_workflow": {
                    "type": "boolean", "default": False,
                    "description": "True when the user invoked the workflow by name: the route is kept as given.",
                },
            },
            "required": ["request", "route", "signals"],
            "additionalProperties": False,
        },
        "annotations": {"title": "Plan route", "read_only_hint": True, "open_world_hint": False},
    }
)

TOOLS_BY_NAME = {tool["name"]: tool for tool in TOOLS}


def validate_arguments(name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
    """Validate against the tool's JSON schema and fill top-level defaults."""
    tool = TOOLS_BY_NAME.get(name)
    if tool is None:
        raise ToolError(f"unknown tool {name!r}", data={"tools": sorted(TOOLS_BY_NAME)})
    args = copy.deepcopy(arguments or {})
    if not isinstance(args, dict):
        raise ToolError("arguments must be a JSON object")
    import jsonschema  # dependency of mcp; imported lazily for fast CLI start-up

    validator = jsonschema.Draft202012Validator(tool["input_schema"])
    errors = sorted(validator.iter_errors(args), key=lambda e: list(e.absolute_path))
    if errors:
        problems = []
        for err in errors[:5]:
            where = "/".join(str(p) for p in err.absolute_path) or "(root)"
            problems.append(f"{where}: {err.message}")
        raise ToolError(f"invalid arguments for {name}: " + "; ".join(problems))
    for key, prop in tool["input_schema"]["properties"].items():
        if key not in args and "default" in prop:
            args[key] = copy.deepcopy(prop["default"])
    return args


async def call_tool(name: str, arguments: dict[str, Any] | None, cfg: Config | None = None) -> Any:
    args = validate_arguments(name, arguments)
    cfg = cfg or Config.from_env()
    if name == "verify_citations":
        from .citations import verify_citations

        if not args.get("text") and not args.get("citations"):
            raise ToolError("provide `text` and/or a non-empty `citations` list")
        return await verify_citations(
            args.get("text"), args.get("citations"), offline=bool(args.get("offline")), cache_dir=cfg.cache_dir,
            timeout_s=60.0,
        )
    if name == "paper_search":
        from .search import paper_search

        return await paper_search(args["query"], args["k"], args.get("path_filter"), cfg=cfg)
    if name == "local_llm":
        from .llm import local_llm

        return await local_llm(
            args["prompt"], system=args.get("system"), model=args.get("model"), max_tokens=args["max_tokens"],
            temperature=args.get("temperature"), cfg=cfg,
        )
    if name == "memory_search":
        from .memory import memory_search

        return await memory_search(
            args["query"], args["collection"], project=args.get("project"), memory_types=args.get("memory_types"),
            status=args.get("status"), limit=args.get("limit"), tags=args.get("tags"),
            scope_paths=args.get("scope_paths"), cfg=cfg,
        )
    if name == "plan_route":
        from .routing import plan_route

        return await plan_route(args, cfg=cfg)
    raise ToolError(f"unknown tool {name!r}")  # pragma: no cover - validate_arguments already rejects it
