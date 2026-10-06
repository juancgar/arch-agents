"""arch-tools: shared tools for the arch-agents v2 multi-agent system.

Modules are imported lazily by ``server.py`` so that latency-sensitive entry
points (``check-text`` in Claude Code hooks) never pay for numpy, pypdf or mcp.
"""

__version__ = "1.0.0"
