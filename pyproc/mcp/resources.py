"""MCP resource definitions for PyProc.

Resources provide read-only reference data to LLM clients.
These are loaded by importing this module (they auto-register).
"""

import json
import logging

from pyproc.mcp.server import register_resource
from pyproc.mcp.schemas import normalize_categories
from pyproc.mcp.tools import TOOL_DESCRIPTIONS

logger = logging.getLogger(__name__)


# ── resource handlers ────────────────────────────────────────────────────────


async def _get_categories() -> str:
    """Return procurement categories as JSON."""
    data = normalize_categories()
    return json.dumps(data, ensure_ascii=False, indent=2)


async def _get_tool_docs() -> str:
    """Return tool documentation as markdown."""
    lines = [
        "# PyProc MCP Tools",
        "",
        "PyProc MCP provides the following tools for accessing Indonesian "
        "public procurement data from SPSE/Inaproc.",
        "",
        "**Important:** This project is not affiliated with LKPP, LPSE, "
        "SPSE, Inaproc, or any Indonesian government institution. "
        "Data is sourced from publicly available SPSE/Inaproc pages.",
        "",
        "## Available Tools",
        "",
    ]

    for name, description in TOOL_DESCRIPTIONS.items():
        lines.append(f"### `{name}`")
        lines.append("")
        lines.append(description)
        lines.append("")

    lines.extend([
        "## Search Modes",
        "",
        "SPSE/Inaproc search is keyword-based. Start with direct keyword "
        "tools and provide several exact terms when useful, such as "
        "`laptop`, `notebook`, and `komputer`. If direct keyword search is "
        "too narrow, ask the user before creating a local full-text index "
        "because indexing downloads package details and makes more requests.",
        "",
        "## Rate Limiting",
        "",
        "All tools that make network requests enforce a minimum delay "
        "between calls to avoid overloading SPSE servers. The default "
        "is 1 second between requests (configurable via `PYPROC_RATE_LIMIT_DELAY` "
        "environment variable).",
        "",
        "## Data Accuracy",
        "",
        "Data is retrieved from public SPSE/Inaproc systems in real-time or "
        "near real-time. Data may be incomplete, delayed, or changed by "
        "source systems. Always verify against official sources at "
        "https://spse.inaproc.id.",
    ])

    return "\n".join(lines)


async def _get_responsible_use() -> str:
    """Return responsible-use policy as markdown."""
    return (
        "# Responsible Use Policy\n\n"
        "## Disclaimer\n\n"
        "**This project is not affiliated with LKPP, LPSE, SPSE, Inaproc, "
        "or any Indonesian government institution.**\n\n"
        "PyProc MCP accesses publicly available procurement data from "
        "SPSE/Inaproc systems. Users are responsible for:\n\n"
        "- **Respectful usage** — Do not overwhelm SPSE servers with excessive "
        "requests. The tool includes built-in rate limiting.\n"
        "- **Data accuracy** — Procurement data may be incomplete, delayed, or "
        "changed by source systems. LLM-generated analysis should be verified "
        "against official sources at https://spse.inaproc.id.\n"
        "- **Compliance** — Ensure your use complies with applicable laws and "
        "regulations in Indonesia.\n"
        "- **No disruption** — Do not use this tool to disrupt public "
        "e-procurement services.\n\n"
        "## Indonesian (Bahasa Indonesia)\n\n"
        "Penulis tidak terafiliasi dengan pengembang SPSE atau pemilik "
        "aplikasi SPSE. Software ini dikembangkan dengan tujuan akademis, "
        "bentuk pengawasan oleh masyarakat, dan membantu pengusaha untuk "
        "mempermudah otomasi perolehan informasi pengadaan dari pemerintah.\n\n"
        "Penggunaan yang tidak wajar dan mengganggu sebagian atau seluruh "
        "fungsi aplikasi SPSE pada satuan kerja menjadi tanggung jawab "
        "masing-masing pengguna.\n\n"
        "PyProc ada karena SPSE ada, jadi gunakanlah dengan bijak dan "
        "secukupnya.\n"
    )


async def _get_lpse_host_guide() -> str:
    """Return LPSE host discovery guidance as markdown."""
    return (
        "# LPSE Host Discovery Guide\n\n"
        "Most procurement tools require an `lpse_host` value such as "
        "`kemenkeu`, `jakarta`, `pu`, or `nasional`. There are two "
        "procurement executor scopes:\n\n"
        "- Agency-specific hosts for one K/L/PD or local government, such as "
        "`kemenkeu`, `jakarta`, or `pu`.\n"
        "- The nationwide host `nasional`, used for national-wide/lintas "
        "instansi data and pencatatan nasional sources.\n\n"
        "End users often ask by institution name instead, for example: "
        "`cari data lelang pengadaan laptop pada kementerian keuangan`. If "
        "the user asks for national, nationwide, all Indonesia, lintas "
        "instansi, or pencatatan nasional data, use `lpse_host=\"nasional\"` "
        "directly.\n\n"
        "Recommended MCP flow:\n\n"
        "1. Call `search_lpse_hosts` with the institution text, for example "
        "`query=\"kementerian keuangan\"`. For national-wide searches, use "
        "`lpse_host=\"nasional\"` directly or call `search_lpse_hosts` with "
        "`query=\"nasional\"`.\n"
        "2. Pick the best returned `host` candidate, such as `kemenkeu`.\n"
        "3. Call the relevant package search tool, such as "
        "`search_tender_packages`, `search_non_tender_packages`, "
        "`search_pencatatan_non_tender_packages`, `search_swakelola_packages`, "
        "or `search_pengadaan_darurat_packages`, "
        "with that `lpse_host` and the procurement keyword, such as "
        "`keyword=\"laptop\"`.\n"
        "4. If candidates are ambiguous, ask the user to choose the intended "
        "LPSE/institution before searching package data.\n\n"
        "`search_lpse_hosts` uses maintained Gist host metadata and reads "
        "the `newUrlPath` field for agency hosts. The `nasional` host is "
        "built in and does not depend on the Gist metadata. Legacy `oldUrl` "
        "values are ignored. "
        "Canonical host URLs are always built as "
        "`https://spse.inaproc.id/{newUrlPath}`. The tool keeps an "
        "in-memory cache to avoid repeated metadata requests. It does not "
        "search procurement packages and does not validate every returned "
        "host by default.\n"
    )


# ── register resources ───────────────────────────────────────────────────────

register_resource(
    "pyproc://categories",
    "Procurement Categories",
    "List of all supported SPSE procurement categories (Jenis Pengadaan) "
    "with names, enum values, and descriptions.",
    "application/json",
    _get_categories,
)

register_resource(
    "pyproc://docs/tools",
    "Tool Usage Guide",
    "Documentation for all available MCP tools including descriptions, "
    "parameters, rate limits, and data source notes.",
    "text/markdown",
    _get_tool_docs,
)

register_resource(
    "pyproc://docs/responsible-use",
    "Responsible Use Policy",
    "Usage guidelines, disclaimers, and responsible-use policy for PyProc MCP. "
    "Includes non-affiliation statement in English and Indonesian.",
    "text/markdown",
    _get_responsible_use,
)

register_resource(
    "pyproc://docs/lpse-hosts",
    "LPSE Host Discovery Guide",
    "How to resolve institution names into LPSE host slugs before calling "
    "procurement search or detail tools.",
    "text/markdown",
    _get_lpse_host_guide,
)

logger.info("Registered %d MCP resources", 4)
