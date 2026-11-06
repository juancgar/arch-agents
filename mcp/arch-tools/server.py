#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#     "mcp>=2.3,<3",
#     "httpx>=0.28,<1",
#     "rank-bm25>=0.2.2",
#     "numpy>=2.0",
#     "pypdf>=6.0",
#     "jsonschema>=4.20",
# ]
# ///
"""arch-tools: MCP server + CLI for arch-agents v2.

    uv run --script server.py [serve]                     MCP stdio server (default)
    uv run --script server.py check-text [--offline] [--max N] [--timeout S] < text
    uv run --script server.py index [--rebuild] [--no-embed] [--dirs A:B] [--batch-size N]
    uv run --script server.py search "query" [-k 8] [--path-filter SUBSTR]
    uv run --script server.py plan-route [--samples N] < draft.json   (same as the plan_route tool)

check-text exit codes: 0 = no NOT_FOUND/TITLE_MISMATCH, 2 = at least one (reasons on stderr), 1 = internal error.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))  # `uv run --script` does not add the script's directory for imports

MAX_STDIN_BYTES = 4 * 1024 * 1024


def _print_json(obj: object, pretty: bool = False) -> None:
    text = json.dumps(obj, ensure_ascii=False, indent=2 if pretty else None, separators=None if pretty else (",", ":"))
    sys.stdout.write(text + "\n")
    sys.stdout.flush()


def cmd_serve(_args: argparse.Namespace) -> int:
    from arch_tools.mcp_server import serve

    try:
        asyncio.run(serve())
    except KeyboardInterrupt:
        pass
    return 0


def cmd_check_text(args: argparse.Namespace) -> int:
    try:
        from arch_tools.citations import failure_lines, verify_citations
        from arch_tools.config import Config

        raw = sys.stdin.buffer.read(MAX_STDIN_BYTES + 1)
        text = raw[:MAX_STDIN_BYTES].decode("utf-8", "replace")
        cfg = Config.from_env()
        result = asyncio.run(
            verify_citations(
                text,
                offline=args.offline,
                cache_dir=cfg.cache_dir,
                max_citations=max(0, args.max),
                timeout_s=max(1.0, args.timeout),
            )
        )
        if len(raw) > MAX_STDIN_BYTES:
            result["input_truncated"] = True
    except Exception as exc:  # noqa: BLE001 - hooks must get a non-blocking exit code, never a traceback
        _print_json({"error": f"{type(exc).__name__}: {exc}"})
        return 1
    _print_json(result)
    if not result["ok"]:
        sys.stderr.write("Citation check failed; fix or remove these citations:\n" + "\n".join(failure_lines(result)) + "\n")
        return 2
    return 0


def cmd_index(args: argparse.Namespace) -> int:
    from arch_tools.config import Config
    from arch_tools.index import build_index
    from arch_tools.net import ToolError

    cfg = Config.from_env()
    dirs = [Path(os.path.expanduser(d)) for d in args.dirs.split(":") if d.strip()] if args.dirs else None
    try:
        summary = asyncio.run(
            build_index(cfg, dirs=dirs, rebuild=args.rebuild, embed=not args.no_embed, batch_size=max(1, args.batch_size))
        )
    except ToolError as exc:
        _print_json(exc.to_dict(), pretty=True)
        return 1
    except KeyboardInterrupt:
        sys.stderr.write("[index] interrupted; finished files are kept, re-run to continue\n")
        return 130
    _print_json(summary, pretty=True)
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    from arch_tools.config import Config
    from arch_tools.net import ToolError
    from arch_tools.search import paper_search

    try:
        result = asyncio.run(paper_search(args.query, args.k, args.path_filter, cfg=Config.from_env()))
    except ToolError as exc:
        _print_json(exc.to_dict(), pretty=True)
        return 1
    _print_json(result, pretty=True)
    return 0


def cmd_plan_route(args: argparse.Namespace) -> int:
    from arch_tools.net import ToolError
    from arch_tools.tools import call_tool

    try:
        draft = json.loads(sys.stdin.read())
        if args.samples is not None:
            draft["samples"] = args.samples
        samples = draft.pop("samples", None)
        if samples is not None:
            os.environ["ARCH_ROUTE_SAMPLES"] = str(samples)
        result = asyncio.run(call_tool("plan_route", draft))
    except (ToolError, json.JSONDecodeError) as exc:
        _print_json(exc.to_dict() if isinstance(exc, ToolError) else {"error": str(exc)}, pretty=True)
        return 1
    _print_json(result, pretty=True)
    return 0


def build_parser() -> argparse.ArgumentParser:
    from arch_tools import __version__

    parser = argparse.ArgumentParser(prog="server.py", description="arch-tools MCP server and CLI")
    parser.add_argument("--version", action="version", version=f"arch-tools {__version__}")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("serve", help="run the MCP stdio server (default)").set_defaults(func=cmd_serve)

    p = sub.add_parser("check-text", help="verify citations in text read from stdin (for hooks)")
    p.add_argument("--offline", action="store_true", help="no network; report cached verdicts only")
    p.add_argument("--max", type=int, default=40, help="check at most N citations (default 40)")
    p.add_argument("--timeout", type=float, default=17.0, help="network time budget in seconds (default 17)")
    p.set_defaults(func=cmd_check_text)

    p = sub.add_parser("index", help="build or refresh the paper index (incremental)")
    p.add_argument("--rebuild", action="store_true", help="drop the index and rebuild from scratch")
    p.add_argument("--no-embed", action="store_true", help="store chunks without embeddings (BM25 only)")
    p.add_argument("--dirs", help="colon-separated library dirs (default: $ARCH_LIBRARY_DIRS)")
    p.add_argument("--batch-size", type=int, default=16, help="chunks per embedding request (default 16)")
    p.set_defaults(func=cmd_index)

    p = sub.add_parser("search", help="query the paper index (same as the paper_search tool)")
    p.add_argument("query")
    p.add_argument("-k", type=int, default=8)
    p.add_argument("--path-filter")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("plan-route", help="check a routing draft read from stdin as JSON (same as the plan_route tool)")
    p.add_argument("--samples", type=int, help="self-consistency samples (default: $ARCH_ROUTE_SAMPLES or 0)")
    p.set_defaults(func=cmd_plan_route)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command is None:
        return cmd_serve(args)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
