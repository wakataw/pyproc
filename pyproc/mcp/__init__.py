"""PyProc MCP server package.

Provides MCP tools for LLM agents to access real-time or near real-time
Indonesian public procurement data from SPSE/Inaproc.

Usage:
    pyproc-mcp           # Start MCP server on stdio
    python -m pyproc.mcp.server
"""

from pyproc import __version__

__all__ = [
    'server',
    'tools',
    'schemas',
    'resources',
    'prompts',
    'errors',
    'hosts',
    'search_index',
]
