"""MCP stdio server exposing the arch-tools catalogue (mcp SDK v2 low-level Server)."""

from __future__ import annotations

import logging
import sys
import traceback
from typing import Any

from mcp import types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from . import __version__
from .net import ToolError, dumps
from .tools import INSTRUCTIONS, TOOLS, call_tool

log = logging.getLogger("arch-tools")


def _tool_list() -> list[types.Tool]:
    return [
        types.Tool(
            name=spec["name"],
            description=spec["description"],
            input_schema=spec["input_schema"],
            annotations=types.ToolAnnotations(**spec["annotations"]),
        )
        for spec in TOOLS
    ]


def _text_result(payload: Any, *, is_error: bool = False) -> types.CallToolResult:
    return types.CallToolResult(content=[types.TextContent(text=dumps(payload))], is_error=is_error)


async def _on_list_tools(ctx: Any, params: Any) -> types.ListToolsResult:
    return types.ListToolsResult(tools=_tool_list())


async def _on_call_tool(ctx: Any, params: types.CallToolRequestParams) -> types.CallToolResult:
    try:
        result = await call_tool(params.name, params.arguments)
    except ToolError as exc:
        return _text_result(exc.to_dict(), is_error=True)
    except Exception as exc:  # noqa: BLE001 - report, never crash the server
        log.error("tool %s failed:\n%s", params.name, traceback.format_exc())
        return _text_result({"error": f"internal error in {params.name}: {type(exc).__name__}: {exc}"}, is_error=True)
    return _text_result(result)


def build_server() -> Server:
    return Server(
        "arch-tools",
        version=__version__,
        title="arch-agents v2 tools",
        instructions=INSTRUCTIONS,
        on_list_tools=_on_list_tools,
        on_call_tool=_on_call_tool,
    )


async def serve() -> None:
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr, format="arch-tools %(levelname)s %(message)s")
    server = build_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())
