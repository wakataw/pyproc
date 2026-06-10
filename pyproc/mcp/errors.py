"""MCP-specific error mapping.

Maps Python exceptions from the PyProc library layer to user-friendly
MCP error messages suitable for LLM consumption.
"""

import logging
import requests

from pyproc.exceptions import LpseServerExceptions, LpseHostExceptions

logger = logging.getLogger(__name__)


def map_exception_to_mcp_error(exc: Exception) -> str:
    """Map a Python exception to an MCP error message string.

    Args:
        exc: The exception raised during tool execution.

    Returns:
        A user-friendly error message string for the MCP client.
    """
    if isinstance(exc, LpseServerExceptions):
        return f"SPSE server error: {exc}"

    if isinstance(exc, LpseHostExceptions):
        return f"Invalid LPSE host: {exc}"

    if isinstance(exc, requests.exceptions.Timeout):
        return "Request to SPSE server timed out. The server may be slow or unreachable. Try again later or increase the timeout."

    if isinstance(exc, requests.exceptions.ConnectionError):
        return f"Could not connect to SPSE server: {exc}"

    if isinstance(exc, requests.exceptions.RequestException):
        return f"HTTP request failed: {exc}"

    if isinstance(exc, (ValueError, TypeError)):
        return f"Invalid parameter: {exc}"

    # Generic fallback
    logger.error("Unexpected error in MCP tool", exc_info=True)
    return f"An unexpected error occurred: {exc}"
