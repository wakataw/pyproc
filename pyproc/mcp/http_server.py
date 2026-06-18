"""HTTP transport entry point for the PyProc MCP server.

Provides a Streamable HTTP MCP server using Starlette and uvicorn.
This is an alternative to the default stdio transport.

Usage:
    pyproc mcp --interface http                     # via unified CLI
    PYPROC_MCP_PORT=9090 pyproc mcp --interface http  # custom port
"""

import contextlib
import logging
import os

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

from pyproc import __version__
from pyproc.mcp.server import server

logger = logging.getLogger(__name__)

# ── HTTP configuration from environment ─────────────────────────────────────

HTTP_HOST = os.environ.get("PYPROC_MCP_HOST", "0.0.0.0")
HTTP_PORT = int(os.environ.get("PYPROC_MCP_PORT", "8080"))
HTTP_STATELESS = (
    os.environ.get("PYPROC_MCP_STATELESS", "0").strip().lower()
    in ("1", "true", "yes", "on")
)
HTTP_JSON_RESPONSE = (
    os.environ.get("PYPROC_MCP_JSON_RESPONSE", "1").strip().lower()
    in ("1", "true", "yes", "on")
)
HTTP_SESSION_IDLE_TIMEOUT = int(
    os.environ.get("PYPROC_MCP_SESSION_IDLE_TIMEOUT", "1800")
)


# ── Starlette application ───────────────────────────────────────────────────


def create_app(host=None, port=None):
    """Create and return a Starlette ASGI app for the MCP server.

    The app wraps the shared ``mcp.server.Server`` instance in a
    ``StreamableHTTPSessionManager`` that handles session lifecycle
    and exposes an ASGI3 request handler.

    Every call creates a fresh app and session manager (required because
    ``StreamableHTTPSessionManager.run()`` can only be used once).

    Args:
        host: Bind address for log display (defaults to ``HTTP_HOST``).
        port: Listen port for log display (defaults to ``HTTP_PORT``).
    """
    bind_host = host if host is not None else HTTP_HOST
    bind_port = port if port is not None else HTTP_PORT

    session_manager = StreamableHTTPSessionManager(
        app=server,
        json_response=HTTP_JSON_RESPONSE,
        stateless=HTTP_STATELESS,
        session_idle_timeout=(
            HTTP_SESSION_IDLE_TIMEOUT if not HTTP_STATELESS else None
        ),
    )

    @contextlib.asynccontextmanager
    async def lifespan(app):
        async with session_manager.run():
            logger.info(
                "PyProc MCP HTTP server v%s ready on http://%s:%d",
                __version__, bind_host, bind_port,
            )
            logger.info(
                "Configuration: stateless=%s json_response=%s timeout=%s",
                HTTP_STATELESS, HTTP_JSON_RESPONSE,
                HTTP_SESSION_IDLE_TIMEOUT,
            )
            app.state.session_manager = session_manager
            yield
        logger.info("Streamable HTTP session manager shut down")

    async def healthcheck(request):
        """Liveness check — does not touch MCP session state."""
        return JSONResponse({"status": "ok", "version": __version__})

    async def mcp_asgi(scope, receive, send):
        """Raw ASGI3 handler — forwards to the session manager."""
        await session_manager.handle_request(scope, receive, send)

    routes = [
        Route("/health", endpoint=healthcheck, methods=["GET"]),
        Mount("/", app=mcp_asgi),
    ]

    return Starlette(routes=routes, lifespan=lifespan)


# ── entry point ──────────────────────────────────────────────────────────────


def run_http_server(host=None, port=None):
    """Start the MCP server on HTTP transport (Streamable HTTP).

    Args:
        host: Optional bind address override for ``PYPROC_MCP_HOST``.
        port: Optional listen port override for ``PYPROC_MCP_PORT``.
    """
    import uvicorn

    # Import tools and resources to trigger registration on the shared server
    import pyproc.mcp.tools       # noqa: F401 — registers tools
    import pyproc.mcp.resources   # noqa: F401 — registers resources

    bind_host = host if host is not None else HTTP_HOST
    bind_port = port if port is not None else HTTP_PORT

    logger.info("PyProc MCP HTTP server v%s starting", __version__)
    logger.info(
        "Configuration: host=%s port=%s stateless=%s json_response=%s",
        bind_host, bind_port, HTTP_STATELESS, HTTP_JSON_RESPONSE,
    )

    app = create_app(host=bind_host, port=bind_port)
    uvicorn.run(app, host=bind_host, port=bind_port)
