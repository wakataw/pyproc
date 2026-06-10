"""MCP server entry point for PyProc.

Provides a stdio-based MCP server that exposes SPSE/Inaproc procurement
data as MCP tools for LLM agents.

Usage:
    pyproc-mcp           # Start via console script
    python -m pyproc.mcp.server
"""

import logging
import os
import sys

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types as mcp_types

from pyproc import __version__
from pyproc.mcp.errors import map_exception_to_mcp_error

# ── server instance ──────────────────────────────────────────────────────────

server = Server("pyproc")

# ── configuration from environment ────────────────────────────────────────────

TIMEOUT = int(os.environ.get("PYPROC_TIMEOUT", "30"))
RATE_LIMIT_DELAY = float(os.environ.get("PYPROC_RATE_LIMIT_DELAY", "1.0"))
LOG_LEVEL = os.environ.get("PYPROC_LOG_LEVEL", "INFO").upper()

# ── logging (to stderr, never stdout — stdio transport uses stdout) ─────────

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="[%(asctime)s %(levelname)s] %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

# ── tool registry ────────────────────────────────────────────────────────────

# Tool handlers are registered as dict name → handler function.
# Handlers are populated by tools.py during import (see register_tools).
_tool_handlers: dict = {}


def register_tool(name: str, handler, schema: dict):
    """Register a tool handler with its input schema.

    Args:
        name: Tool name (snake_case, verb_noun convention).
        handler: Async callable that receives (name, arguments) and returns
                 a list of mcp_types.Content items.
        schema: JSON Schema dict for the tool's input.
    """
    _tool_handlers[name] = {"handler": handler, "schema": schema}
    logger.debug("Registered MCP tool: %s", name)


# ── resource registry ────────────────────────────────────────────────────────

_resource_handlers: dict = {}


def register_resource(uri: str, name: str, description: str,
                      mime_type: str, handler):
    """Register an MCP resource handler.

    Args:
        uri: Resource URI (e.g., 'pyproc://categories').
        name: Human-readable resource name.
        description: Resource description.
        mime_type: MIME type for the resource content.
        handler: Async callable that returns the resource content as a string.
    """
    _resource_handlers[uri] = {
        "name": name,
        "description": description,
        "mime_type": mime_type,
        "handler": handler,
    }
    logger.debug("Registered MCP resource: %s (%s)", name, uri)


# ── MCP protocol handlers ────────────────────────────────────────────────────


def _clean_schema(schema: dict) -> dict:
    """Remove internal fields from a JSON Schema dict before sending to client."""
    return {k: v for k, v in schema.items() if not k.startswith("_")}


@server.list_tools()
async def handle_list_tools() -> list[mcp_types.Tool]:
    """Return the list of registered MCP tools."""
    tools = []
    for name, info in _tool_handlers.items():
        description = info["schema"].get("_description", "")
        clean_schema = _clean_schema(info["schema"])
        tools.append(mcp_types.Tool(
            name=name,
            description=description,
            inputSchema=clean_schema,
        ))
    logger.debug("Listing %d tools", len(tools))
    return tools


@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict
) -> list[mcp_types.TextContent]:
    """Handle a tool invocation by dispatching to the registered handler."""
    logger.info("Tool called: %s", name)
    logger.debug("Arguments: %s", arguments)

    if name not in _tool_handlers:
        error_msg = f"Unknown tool: {name}"
        logger.error(error_msg)
        return [mcp_types.TextContent(
            type="text",
            text=f"Error: {error_msg}. Available tools: "
                 f"{', '.join(_tool_handlers.keys())}",
        )]

    handler = _tool_handlers[name]["handler"]
    try:
        result = await handler(name, arguments)
        return result
    except Exception as exc:
        error_msg = map_exception_to_mcp_error(exc)
        logger.error("Tool %s failed: %s", name, exc)
        return [mcp_types.TextContent(type="text", text=f"Error: {error_msg}")]


@server.list_resources()
async def handle_list_resources() -> list[mcp_types.Resource]:
    """Return the list of registered MCP resources."""
    resources = []
    for uri, info in _resource_handlers.items():
        resources.append(mcp_types.Resource(
            uri=uri,
            name=info["name"],
            description=info["description"],
            mimeType=info["mime_type"],
        ))
    logger.debug("Listing %d resources", len(resources))
    return resources


@server.read_resource()
async def handle_read_resource(uri: str) -> str:
    """Read a registered MCP resource by URI."""
    logger.info("Resource read: %s", uri)

    if uri not in _resource_handlers:
        error_msg = f"Unknown resource: {uri}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    handler = _resource_handlers[uri]["handler"]
    try:
        content = await handler()
        return content
    except Exception as exc:
        error_msg = map_exception_to_mcp_error(exc)
        logger.error("Resource %s failed: %s", uri, exc)
        raise ValueError(error_msg) from exc


# ── entry point ──────────────────────────────────────────────────────────────


async def run_server():
    """Start the MCP server on stdio transport."""
    logger.info("PyProc MCP server v%s starting", __version__)
    logger.info("Configuration: timeout=%ds, rate_limit_delay=%.1fs, log=%s",
                TIMEOUT, RATE_LIMIT_DELAY, LOG_LEVEL)

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def main():
    """Console script entry point: pyproc-mcp."""
    import anyio

    # Import tools and resources to trigger registration
    import pyproc.mcp.tools       # noqa: F401 — registers tools
    import pyproc.mcp.resources   # noqa: F401 — registers resources

    try:
        anyio.run(run_server)
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
        sys.exit(0)
    except Exception:
        logger.critical("Fatal error starting MCP server", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
