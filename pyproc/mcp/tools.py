"""MCP tool handler functions for PyProc.

Each handler wraps a PyProc library method, validates input via schemas,
normalizes output, and returns MCP TextContent responses.

This module auto-registers all tools with the server on import.
"""

import anyio
import json
import logging
import os
import queue
import time
from datetime import datetime
from pathlib import Path

from mcp import types as mcp_types

from pyproc import Lpse, JenisPengadaan
import pyproc.lpse as _lpse_mod  # for _set_ssl_verify
from pyproc.mcp.schemas import (
    validate_search_params,
    validate_detail_params,
    validate_bulk_detail_params,
    validate_lpse_host,
    validate_host_search_params,
    validate_host_detail_params,
    validate_search_index_create_params,
    validate_search_index_query_params,
    validate_search_index_delete_params,
    validate_isb_index_search_params,
    validate_master_klpd_params,
    validate_master_lpse_params,
    validate_tender_umum_publik_params,
    validate_ssl_verify_params,
    normalize_search_results,
    normalize_detail_result,
    normalize_categories,
    normalize_host_validation,
    SEARCH_TOOL_SCHEMA,
    DETAIL_TOOL_SCHEMA,
    BULK_DETAIL_TOOL_SCHEMA,
    VALIDATE_HOST_SCHEMA,
    CATEGORIES_SCHEMA,
    HOST_SEARCH_SCHEMA,
    HOST_DETAIL_SCHEMA,
    SEARCH_OPTIONS_SCHEMA,
    MASTER_KLPD_SCHEMA,
    MASTER_LPSE_SCHEMA,
    TENDER_UMUM_PUBLIK_SCHEMA,
    SSL_VERIFY_SCHEMA,
    CREATE_SEARCH_INDEX_SCHEMA,
    SEARCH_INDEX_SCHEMA,
    LIST_SEARCH_INDEXES_SCHEMA,
    DELETE_SEARCH_INDEX_SCHEMA,
    SEARCH_ISB_INDEX_SCHEMA,
    CLEAR_ALL_DATA_SCHEMA,
)
from pyproc.mcp.server import register_tool, server, TIMEOUT, RATE_LIMIT_DELAY, MCP_WORKERS
import pyproc.mcp.server as mcp_server_cfg  # for mutable SSL_VERIFY
from pyproc.mcp.parallel import (
    ThreadSafeRateLimiter,
    create_worker_lpse_pool,
    fetch_details_parallel,
)

# Sync lpse module's SSL_VERIFY with server config on startup
_lpse_mod._set_ssl_verify(mcp_server_cfg.SSL_VERIFY)

from pyproc.mcp.hosts import (
    HostMetadataError,
    search_lpse_hosts,
    get_lpse_host_detail,
)
from pyproc.mcp.search_index import (
    create_procurement_search_index,
    search_procurement_index,
    list_procurement_indexes,
    delete_procurement_index,
    create_isb_data_index,
    search_isb_index,
    find_existing_isb_index,
    find_existing_spse_index,
    cleanup_isb_temp_files,
    cleanup_all_data,
)

logger = logging.getLogger(__name__)

# Simple rate limiter: track last request time
_last_request_time: float = 0.0


def _rate_limit():
    """Enforce minimum delay between requests."""
    global _last_request_time
    now = time.monotonic()
    elapsed = now - _last_request_time
    if elapsed < RATE_LIMIT_DELAY:
        time.sleep(RATE_LIMIT_DELAY - elapsed)
    _last_request_time = time.monotonic()


def _make_json_response(data: dict | list) -> list[mcp_types.TextContent]:
    """Create a JSON MCP TextContent response from a dict or list."""
    return [mcp_types.TextContent(
        type="text",
        text=json.dumps(data, ensure_ascii=False, indent=2, default=str),
    )]


def _get_api_data_dir() -> Path:
    """Return the directory for API data output files."""
    configured = os.environ.get("PYPROC_MCP_DATA_DIR")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".cache" / "pyproc" / "api-data"


def _save_json_to_file(data: list | dict, prefix: str,
                        tool_name: str = "",
                        extra_params: dict | None = None) -> dict:
    """Save JSON data to a file and return a compact summary.

    Args:
        data: The data to save (list or dict).
        prefix: Filename prefix (e.g. 'tender_umum_kd119_2026').
        tool_name: Name of the tool that produced this data (for the
            confirmation hint).
        extra_params: Additional parameters to include in the
            confirmation hint (e.g. tahun_anggaran, kd_lpse).

    Returns:
        Summary dict with file_path, record_count, preview, and
        processing_hints.
    """
    data_dir = _get_api_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{prefix}_{timestamp}.json"
    file_path = data_dir / filename

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)

    record_count = len(data) if isinstance(data, list) else 1
    preview = data[:3] if isinstance(data, list) else data

    # Build confirmation hint for returning full data inline
    confirmation_hint = ""
    if tool_name:
        params_parts = []
        if extra_params:
            for k, v in extra_params.items():
                params_parts.append(f'"{k}": {json.dumps(v)}')
        params_parts.append('"return_full_data": true')
        params_str = ", ".join(params_parts)
        confirmation_hint = (
            f"If the user explicitly confirms they want the full "
            f"{record_count}-record JSON in context, call "
            f"{tool_name} again with return_full_data=true. "
            f"Example: {{{params_str}}}"
        )

    return {
        "status": "saved_to_file",
        "file_path": str(file_path),
        "record_count": record_count,
        "preview": preview,
        "processing_hints": (
            f"Full data ({record_count} records) saved to: {file_path}\n"
            "Do NOT load the full JSON into your context. "
            "Process the file locally instead:\n"
            f"  - jq: jq '.[] | .NamaPaket' {file_path}\n"
            f"  - Python: import json; data = json.load(open('{file_path}'))\n"
            f"  - Count: jq 'length' {file_path}\n"
            "For full-text search across procurement data, consider "
            "create_procurement_search_index instead."
        ),
        "confirmation_hint": confirmation_hint,
    }


def _merge_keyword_results(
    rows_by_keyword: list[tuple[str | None, list, int]],
    lpse_host: str,
    start: int,
    length: int,
    keyword_match_mode: str,
    package_type: str = "tender",
) -> dict:
    """Normalize and merge package rows returned by one or more keyword searches."""
    merged: dict[str, dict] = {}
    keyword_sets: dict[str, set[str]] = {}
    active_keywords = [keyword for keyword, _rows, _total in rows_by_keyword if keyword]

    for keyword, rows, _total in rows_by_keyword:
        normalized = normalize_search_results(rows, lpse_host, len(rows), start, length, package_type)
        for package in normalized["packages"]:
            package_id = str(package.get("id_paket") or package.get("raw") or "")
            if not package_id:
                continue
            if package_id not in merged:
                merged[package_id] = package
                keyword_sets[package_id] = set()
            if keyword:
                keyword_sets[package_id].add(keyword)

    packages = []
    for package_id, package in merged.items():
        matched_keywords = sorted(keyword_sets.get(package_id, set()))
        if (
            keyword_match_mode == "all"
            and active_keywords
            and len(matched_keywords) != len(active_keywords)
        ):
            continue
        package["matched_keywords"] = matched_keywords
        packages.append(package)

    return {
        "packages": packages,
        "total": rows_by_keyword[0][2] if len(rows_by_keyword) == 1 else len(packages),
        "count": len(packages),
        "start": start,
        "length": length,
        "lpse_host": lpse_host,
        "lpse_url": f"https://spse.inaproc.id/{lpse_host}",
        "package_type": package_type,
        "keywords": active_keywords,
        "keyword_match_mode": keyword_match_mode,
        "search_note": (
            "This is direct SPSE keyword search, not local full-text search. "
            "Multiple keywords are searched separately and merged."
        ),
}


# ── tool handler functions ───────────────────────────────────────────────────

PACKAGE_TOOL_METHODS = {
    "tender": ("get_paket_tender", "detil_paket_tender"),
    "non_tender": ("get_paket_non_tender", "detil_paket_non_tender"),
    "pencatatan_non_tender": (
        "get_paket_pencatatan_non_tender",
        "detil_paket_pencatatan_non_tender",
    ),
    "swakelola": ("get_paket_swakelola", "detil_paket_swakelola"),
    "darurat": ("get_paket_pengadaan_darurat", "detil_paket_pengadaan_darurat"),
}


async def _handle_search_packages(arguments: dict, package_type: str) -> list[mcp_types.TextContent]:
    try:
        params = validate_search_params(arguments)
    except ValueError as exc:
        return [mcp_types.TextContent(type="text",
                     text=f"Error: Invalid parameter: {exc}")]

    if package_type == "swakelola":
        params.pop("kategori", None)
        params.pop("kontrak_status", None)
    elif package_type != "tender":
        params.pop("kontrak_status", None)
        params.pop("tipe_swakelola_id", None)

    logger.info(
        "Search %s: host=%s keywords=%s tahun=%s kategori=%s start=%s length=%s",
        package_type, params['lpse_host'], params.get('keywords'), params.get('tahun_anggaran'),
        params.get('kategori'), params['start'], params['length'],
    )

    _rate_limit()
    with Lpse(params['lpse_host'], timeout=TIMEOUT, verify=mcp_server_cfg.SSL_VERIFY) as lpse:
        kategori = None
        if params.get('kategori'):
            kategori = JenisPengadaan[params['kategori']]

        search_method_name = PACKAGE_TOOL_METHODS[package_type][0]
        search_method = getattr(lpse, search_method_name)
        keywords = params.get('keywords') or [None]
        rows_by_keyword = []
        for keyword in keywords:
            kwargs = {
                "start": params['start'],
                "length": params['length'],
                "search_keyword": keyword,
                "tahun": params.get('tahun_anggaran'),
                "order": params.get('order'),
                "ascending": params.get('ascending'),
                "instansi_id": params.get('instansi_id'),
                "data_only": True,
            }
            if package_type != "swakelola":
                kwargs["kategori"] = kategori
                kwargs["rekanan"] = params.get('rekanan')
            else:
                kwargs["rekanan"] = params.get('rekanan')
                kwargs["tipe_swakelola"] = params.get("tipe_swakelola_id")
            if package_type == "tender":
                kwargs["kontrak_status"] = params.get('kontrak_status')
            result = search_method(**kwargs)
            packages = result if isinstance(result, list) else result.get('data', [])
            total = len(packages) if isinstance(result, list) else result.get('recordsFiltered', len(packages))
            rows_by_keyword.append((keyword, packages, total))

    output = _merge_keyword_results(
        rows_by_keyword, params['lpse_host'],
        params['start'], params['length'],
        params['keyword_match_mode'],
        package_type,
    )
    return _make_json_response(output)


async def handle_search_tender_packages(
    name: str, arguments: dict
) -> list[mcp_types.TextContent]:
    """Search tender procurement packages on an LPSE host."""
    return await _handle_search_packages(arguments, "tender")


async def handle_search_non_tender_packages(
    name: str, arguments: dict
) -> list[mcp_types.TextContent]:
    """Search non-tender (direct procurement) packages on an LPSE host."""
    return await _handle_search_packages(arguments, "non_tender")


async def handle_search_pencatatan_non_tender_packages(
    name: str, arguments: dict
) -> list[mcp_types.TextContent]:
    """Search pencatatan non-tender packages on an LPSE host."""
    return await _handle_search_packages(arguments, "pencatatan_non_tender")


async def handle_search_swakelola_packages(
    name: str, arguments: dict
) -> list[mcp_types.TextContent]:
    """Search swakelola packages on an LPSE host."""
    return await _handle_search_packages(arguments, "swakelola")


async def handle_search_pengadaan_darurat_packages(
    name: str, arguments: dict
) -> list[mcp_types.TextContent]:
    """Search pengadaan darurat packages on an LPSE host."""
    return await _handle_search_packages(arguments, "darurat")


async def handle_get_tender_detail(
    name: str, arguments: dict
) -> list[mcp_types.TextContent]:
    """Get full detail for a tender procurement package."""
    try:
        params = validate_detail_params(arguments)
    except ValueError as exc:
        return [mcp_types.TextContent(type="text",
                     text=f"Error: Invalid parameter: {exc}")]

    logger.info(
        "Get tender detail: host=%s package_id=%s",
        params['lpse_host'], params['package_id'],
    )

    _rate_limit()
    with Lpse(params['lpse_host'], timeout=TIMEOUT, verify=mcp_server_cfg.SSL_VERIFY) as lpse:
        detil = lpse.detil_paket_tender(params['package_id'])
        info = detil.get_all_detil()

        if info.get('error') and not detil.pengumuman and not detil.peserta:
            error_details = '; '.join(info.get('error_message', []))
            return [mcp_types.TextContent(
                type="text",
                text=json.dumps({
                    "error": True,
                    "message": f"Failed to retrieve package detail: {error_details}",
                    "package_id": params['package_id'],
                }, ensure_ascii=False, indent=2),
            )]

        detail_dict = detil.todict()

    output = normalize_detail_result(detail_dict)
    return _make_json_response(output)


async def handle_get_non_tender_detail(
    name: str, arguments: dict
) -> list[mcp_types.TextContent]:
    """Get full detail for a non-tender (direct procurement) package."""
    try:
        params = validate_detail_params(arguments)
    except ValueError as exc:
        return [mcp_types.TextContent(type="text",
                     text=f"Error: Invalid parameter: {exc}")]

    logger.info(
        "Get non-tender detail: host=%s package_id=%s",
        params['lpse_host'], params['package_id'],
    )

    _rate_limit()
    with Lpse(params['lpse_host'], timeout=TIMEOUT, verify=mcp_server_cfg.SSL_VERIFY) as lpse:
        detil = lpse.detil_paket_non_tender(params['package_id'])
        info = detil.get_all_detil()

        if info.get('error') and not detil.pengumuman and not detil.peserta:
            error_details = '; '.join(info.get('error_message', []))
            return [mcp_types.TextContent(
                type="text",
                text=json.dumps({
                    "error": True,
                    "message": f"Failed to retrieve package detail: {error_details}",
                    "package_id": params['package_id'],
                }, ensure_ascii=False, indent=2),
            )]

        detail_dict = detil.todict()

    output = normalize_detail_result(detail_dict)
    return _make_json_response(output)


async def _handle_get_detail(arguments: dict, package_type: str) -> list[mcp_types.TextContent]:
    try:
        params = validate_detail_params(arguments)
    except ValueError as exc:
        return [mcp_types.TextContent(type="text",
                     text=f"Error: Invalid parameter: {exc}")]

    logger.info(
        "Get %s detail: host=%s package_id=%s",
        package_type, params['lpse_host'], params['package_id'],
    )

    _rate_limit()
    with Lpse(params['lpse_host'], timeout=TIMEOUT, verify=mcp_server_cfg.SSL_VERIFY) as lpse:
        detil = getattr(lpse, PACKAGE_TOOL_METHODS[package_type][1])(params['package_id'])
        info = detil.get_all_detil()
        if info.get('error') and not detil.pengumuman:
            error_details = '; '.join(info.get('error_message', []))
            return [mcp_types.TextContent(
                type="text",
                text=json.dumps({
                    "error": True,
                    "message": f"Failed to retrieve package detail: {error_details}",
                    "package_id": params['package_id'],
                }, ensure_ascii=False, indent=2),
            )]
        detail_dict = detil.todict()

    output = normalize_detail_result(detail_dict)
    output["package_type"] = package_type
    return _make_json_response(output)


async def handle_get_pencatatan_non_tender_detail(
    name: str, arguments: dict
) -> list[mcp_types.TextContent]:
    """Get full detail for a pencatatan non-tender package."""
    return await _handle_get_detail(arguments, "pencatatan_non_tender")


async def handle_get_swakelola_detail(
    name: str, arguments: dict
) -> list[mcp_types.TextContent]:
    """Get full detail for a swakelola package."""
    return await _handle_get_detail(arguments, "swakelola")


async def handle_get_pengadaan_darurat_detail(
    name: str, arguments: dict
) -> list[mcp_types.TextContent]:
    """Get full detail for a pengadaan darurat package."""
    return await _handle_get_detail(arguments, "darurat")


async def _handle_bulk_detail(
    arguments: dict,
    package_type: str,
) -> list[mcp_types.TextContent]:
    try:
        params = validate_bulk_detail_params(arguments)
    except ValueError as exc:
        return [mcp_types.TextContent(type="text",
                     text=f"Error: Invalid parameter: {exc}")]

    # Create per-worker Lpse pool with unique browser footprints
    package_ids = params["package_ids"]
    workers = min(len(package_ids), MCP_WORKERS)
    lpse_pool = create_worker_lpse_pool(
        params["lpse_host"], workers, TIMEOUT, mcp_server_cfg.SSL_VERIFY,
    )
    rate_limiter = ThreadSafeRateLimiter(min_delay=RATE_LIMIT_DELAY)

    try:
        # Offload blocking parallel fetch from the anyio event loop
        raw_details = await anyio.to_thread.run_sync(
            fetch_details_parallel,
            package_ids,
            lpse_pool,
            PACKAGE_TOOL_METHODS[package_type][1],
            rate_limiter,
            params["continue_on_error"],
        )
    finally:
        for lpse in lpse_pool:
            lpse.session.close()

    # Normalize and assemble final output
    details = []
    for item in raw_details:
        if item.get("success") and "detail" in item:
            item["detail"] = normalize_detail_result(item["detail"])
        details.append(item)

    success_count = len([item for item in details if item.get("success")])
    output = {
        "lpse_host": params["lpse_host"],
        "package_type": package_type,
        "requested_count": len(package_ids),
        "count": len(details),
        "success_count": success_count,
        "error_count": len(details) - success_count,
        "details": details,
    }
    return _make_json_response(output)


async def handle_get_tender_details_bulk(
    name: str, arguments: dict
) -> list[mcp_types.TextContent]:
    """Get full details for multiple tender packages in one MCP call."""
    return await _handle_bulk_detail(arguments, "tender")


async def handle_get_non_tender_details_bulk(
    name: str, arguments: dict
) -> list[mcp_types.TextContent]:
    """Get full details for multiple non-tender packages in one MCP call."""
    return await _handle_bulk_detail(arguments, "non_tender")


async def handle_get_pencatatan_non_tender_details_bulk(
    name: str, arguments: dict
) -> list[mcp_types.TextContent]:
    """Get full details for multiple pencatatan non-tender packages."""
    return await _handle_bulk_detail(arguments, "pencatatan_non_tender")


async def handle_get_swakelola_details_bulk(
    name: str, arguments: dict
) -> list[mcp_types.TextContent]:
    """Get full details for multiple swakelola packages."""
    return await _handle_bulk_detail(arguments, "swakelola")


async def handle_get_pengadaan_darurat_details_bulk(
    name: str, arguments: dict
) -> list[mcp_types.TextContent]:
    """Get full details for multiple pengadaan darurat packages."""
    return await _handle_bulk_detail(arguments, "darurat")


async def handle_get_procurement_categories(
    name: str, arguments: dict
) -> list[mcp_types.TextContent]:
    """Return the list of supported procurement categories (no network call)."""
    logger.info("Get procurement categories")

    output = normalize_categories()
    return _make_json_response(output)


async def handle_get_master_klpd(
    name: str, arguments: dict
) -> list[mcp_types.TextContent]:
    """Return LKPP master K/L/PD references for instansi_id filtering."""
    try:
        params = validate_master_klpd_params(arguments)
    except ValueError as exc:
        return [mcp_types.TextContent(type="text",
                     text=f"Error: Invalid parameter: {exc}")]

    logger.info(
        "Get master KLPD: query=%s kd=%s jenis=%s limit=%s",
        params["query"], params["kd_klpd"], params["jenis_klpd"], params["limit"],
    )

    _rate_limit()
    rows = Lpse.get_master_klpd(timeout=TIMEOUT)
    query = params["query"].lower()
    if params["kd_klpd"]:
        rows = [
            row for row in rows
            if str(row.get("kd_klpd", "")).lower() == params["kd_klpd"].lower()
        ]
    if params["jenis_klpd"]:
        rows = [
            row for row in rows
            if str(row.get("jenis_klpd", "")).lower() == params["jenis_klpd"].lower()
        ]
    if query:
        rows = [
            row for row in rows
            if query in str(row.get("nama_klpd", "")).lower()
            or query in str(row.get("kd_klpd", "")).lower()
        ]

    output = {
        "count": min(len(rows), params["limit"]),
        "total_matches": len(rows),
        "usage": (
            "Use kd_klpd as instansi_id in search_tender_packages or "
            "search_non_tender_packages."
        ),
    }

    limited_rows = rows[:params["limit"]]

    if params.get("save_to_file") and limited_rows:
        prefix = "master_klpd"
        if params["query"]:
            prefix = f"master_klpd_{params['query'][:30]}"
        summary = _save_json_to_file(limited_rows, prefix, tool_name="get_master_klpd")
        summary.update(output)
        return _make_json_response(summary)

    output["klpd"] = limited_rows
    return _make_json_response(output)


async def handle_get_master_lpse(
    name: str, arguments: dict
) -> list[mcp_types.TextContent]:
    """Return LKPP Satu Data master LPSE references for kd_lpse values."""
    try:
        params = validate_master_lpse_params(arguments)
    except ValueError as exc:
        return [mcp_types.TextContent(type="text",
                     text=f"Error: Invalid parameter: {exc}")]

    logger.info(
        "Get master LPSE: query=%s kd=%s limit=%s",
        params["query"], params["kd_lpse"], params["limit"],
    )

    _rate_limit()
    rows = Lpse.get_master_lpse(timeout=TIMEOUT)
    query = params["query"].lower()
    if params["kd_lpse"]:
        rows = [
            row for row in rows
            if int(row.get("kd_lpse", 0)) == params["kd_lpse"]
        ]
    if query:
        rows = [
            row for row in rows
            if query in str(row.get("nama_lpse", "")).lower()
            or query in str(row.get("kd_lpse", "")).lower()
        ]

    output = {
        "count": min(len(rows), params["limit"]),
        "total_matches": len(rows),
        "usage": (
            "Use kd_lpse from this tool as the kd_lpse parameter in "
            "get_tender_umum_publik."
        ),
    }

    limited_rows = rows[:params["limit"]]

    if params.get("save_to_file") and limited_rows:
        prefix = "master_lpse"
        if params["query"]:
            prefix = f"master_lpse_{params['query'][:30]}"
        summary = _save_json_to_file(limited_rows, prefix, tool_name="get_master_lpse")
        summary.update(output)
        return _make_json_response(summary)

    output["lpse"] = limited_rows
    return _make_json_response(output)


async def handle_get_tender_umum_publik(
    name: str, arguments: dict
) -> list[mcp_types.TextContent]:
    """Return tender data from LKPP ISB Satu Data as alternative source.

    Multi-step interaction:
    1. Call without output_mode → checks for existing index, fetches data,
       returns choice prompt with record count and preview.
    2. If existing index found, asks reuse or refresh.
    3. Call with output_mode='local_index'|'file'|'inline' → processes
       data according to chosen mode.
    """
    try:
        params = validate_tender_umum_publik_params(arguments)
    except ValueError as exc:
        return [mcp_types.TextContent(type="text",
                     text=f"Error: Invalid parameter: {exc}")]

    kd_lpse = params["kd_lpse"]
    tahun = params["tahun_anggaran"]
    output_mode = params.get("output_mode")
    force_refresh = params.get("force_refresh", False)

    logger.info(
        "Get tender umum publik: tahun=%s kd_lpse=%s output_mode=%s force_refresh=%s",
        tahun, kd_lpse, output_mode, force_refresh,
    )

    # ── Step 2: process with chosen output_mode ──────────────────────
    if output_mode:
        return await _handle_isb_output_mode(kd_lpse, tahun, output_mode)

    # ── Check for existing index ─────────────────────────────────────
    if not force_refresh:
        existing = find_existing_isb_index(kd_lpse, tahun)
        if existing:
            output = {
                "status": "existing_index_found",
                "index_id": existing.get("index_id"),
                "indexed_records": existing.get("indexed_records", "unknown"),
                "kd_lpse": kd_lpse,
                "tahun_anggaran": tahun,
                "created_at": existing.get("created_at"),
                "source": "LKPP ISB Satu Data (alternative data source)",
                "choices": {
                    "reuse": (
                        "Use the existing index as-is. Call "
                        f"search_isb_index with index_id='{existing.get('index_id')}' "
                        "to query it."
                    ),
                    "refresh": (
                        "Delete the existing index and fetch fresh data "
                        "from the API. Call get_tender_umum_publik again "
                        "with force_refresh=true."
                    ),
                },
            }
            return _make_json_response(output)

    # ── Fetch fresh data from API ────────────────────────────────────
    _rate_limit()
    rows = Lpse.get_tender_umum_publik(
        tahun_anggaran=tahun,
        kd_lpse=kd_lpse,
        timeout=TIMEOUT,
    )

    if not rows:
        output = {
            "count": 0,
            "source": "LKPP ISB Satu Data (alternative data source)",
            "kd_lpse": kd_lpse,
            "tahun_anggaran": tahun,
            "tenders": [],
            "notes": (
                "No tender data found for the given parameters. "
                "Data from ISB Satu Data. Field names may contain spaces "
                "(e.g., 'Kode Tender', 'Nama Paket'). This is an alternative "
                "data source. Use as fallback when realtime SPSE/Inaproc "
                "search returns no results or errors."
            ),
        }
        return _make_json_response(output)

    # Save to temp file for step 2
    import hashlib
    data_dir = _get_api_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    params_hash = hashlib.md5(f"{kd_lpse}_{tahun}".encode()).hexdigest()[:8]
    temp_filename = f".isb_temp_kd{kd_lpse}_{tahun}_{params_hash}.json"
    temp_path = data_dir / temp_filename
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2, default=str)

    preview = rows[:3]

    output = {
        "status": "choose_output_mode",
        "record_count": len(rows),
        "preview": preview,
        "temp_file": str(temp_path),
        "source": "LKPP ISB Satu Data (alternative data source)",
        "kd_lpse": kd_lpse,
        "tahun_anggaran": tahun,
        "output_options": {
            "local_index": {
                "description": (
                    "Create a local SQLite FTS index for full-text search. "
                    "Recommended — fast, queryable with search_isb_index."
                ),
                "recommended": True,
            },
            "file": {
                "description": (
                    "Save to JSON file. Process with jq, Python, or local tools."
                ),
            },
            "inline": {
                "description": (
                    f"Return all {len(rows)} records as JSON directly into "
                    f"context. WARNING: will consume significant tokens. "
                    f"NOT recommended."
                ),
                "warning": True,
            },
        },
        "next_step": (
            "Call get_tender_umum_publik again with the same tahun_anggaran "
            "and kd_lpse, plus output_mode='local_index', 'file', or 'inline'."
        ),
    }
    return _make_json_response(output)


async def _handle_isb_output_mode(
    kd_lpse: int, tahun: int, output_mode: str,
) -> list[mcp_types.TextContent]:
    """Process ISB data from temp file using the chosen output_mode."""
    import hashlib
    data_dir = _get_api_data_dir()
    params_hash = hashlib.md5(f"{kd_lpse}_{tahun}".encode()).hexdigest()[:8]
    temp_filename = f".isb_temp_kd{kd_lpse}_{tahun}_{params_hash}.json"
    temp_path = data_dir / temp_filename

    if not temp_path.exists():
        return [mcp_types.TextContent(
            type="text",
            text=(
                f"Error: Temp data file not found: {temp_path}. "
                "Call get_tender_umum_publik without output_mode first to "
                "fetch the data."
            ),
        )]

    with open(temp_path, encoding="utf-8") as f:
        rows = json.load(f)

    # ── local_index ──────────────────────────────────────────────────
    if output_mode == "local_index":
        result = create_isb_data_index(
            data=rows, kd_lpse=kd_lpse, tahun_anggaran=tahun,
        )
        # Cleanup temp file after indexing
        try:
            temp_path.unlink()
        except OSError:
            pass
        result["source"] = "LKPP ISB Satu Data (alternative data source)"
        return _make_json_response(result)

    # ── file ─────────────────────────────────────────────────────────
    if output_mode == "file":
        prefix = f"tender_umum_kd{kd_lpse}_{tahun}"
        summary = _save_json_to_file(rows, prefix)
        # Cleanup temp file
        try:
            temp_path.unlink()
        except OSError:
            pass
        summary["source"] = "LKPP ISB Satu Data (alternative data source)"
        summary["kd_lpse"] = kd_lpse
        summary["tahun_anggaran"] = tahun
        return _make_json_response(summary)

    # ── inline ───────────────────────────────────────────────────────
    if output_mode == "inline":
        # Cleanup temp file
        try:
            temp_path.unlink()
        except OSError:
            pass
        output = {
            "status": "inline_with_warning",
            "warning": (
                f"⚠️ {len(rows)} records returned inline. This will consume "
                f"significant context tokens. Consider using "
                f"output_mode='local_index' or 'file' instead."
            ),
            "record_count": len(rows),
            "source": "LKPP ISB Satu Data (alternative data source)",
            "kd_lpse": kd_lpse,
            "tahun_anggaran": tahun,
            "tenders": rows,
        }
        return _make_json_response(output)

    return [mcp_types.TextContent(
        type="text",
        text=f"Error: Unknown output_mode: {output_mode}",
    )]


async def handle_search_isb_index(
    name: str, arguments: dict
) -> list[mcp_types.TextContent]:
    """Search a local ISB Satu Data SQLite FTS index."""
    try:
        params = validate_isb_index_search_params(arguments)
    except ValueError as exc:
        return [mcp_types.TextContent(type="text",
                     text=f"Error: Invalid parameter: {exc}")]

    logger.info(
        "Search ISB index: index_id=%s query=%s limit=%s",
        params["index_id"], params["query"], params["limit"],
    )

    try:
        output = search_isb_index(**params)
    except ValueError as exc:
        return [mcp_types.TextContent(type="text",
                     text=f"Error: {exc}")]
    return _make_json_response(output)


async def handle_clear_all_data(
    name: str, arguments: dict
) -> list[mcp_types.TextContent]:
    """Delete all local MCP indexes and downloaded data files."""
    confirm = arguments.get("confirm", False)
    if isinstance(confirm, str):
        confirm = confirm.strip().lower() in ("1", "true", "yes", "y")

    if not confirm:
        return [mcp_types.TextContent(
            type="text",
            text=(
                "Error: confirm must be true. This will delete all local "
                "indexes and downloaded data files. This action cannot be undone."
            ),
        )]

    logger.info("Clearing all local MCP data")
    result = cleanup_all_data()
    result["message"] = (
        f"Deleted {result['indexes_deleted']} indexes and "
        f"{result['files_deleted']} data files."
    )
    return _make_json_response(result)


async def handle_set_ssl_verify(
    name: str, arguments: dict
) -> list[mcp_types.TextContent]:
    """Enable or disable TLS/SSL certificate verification for SPSE requests."""
    try:
        params = validate_ssl_verify_params(arguments)
    except ValueError as exc:
        return [mcp_types.TextContent(type="text",
                     text=f"Error: Invalid parameter: {exc}")]

    old_value = mcp_server_cfg.SSL_VERIFY
    mcp_server_cfg.SSL_VERIFY = params["enable"]
    _lpse_mod._set_ssl_verify(params["enable"])

    logger.info(
        "SSL verification changed: %s -> %s", old_value, params["enable"]
    )

    output = {
        "ssl_verify": params["enable"],
        "previous": old_value,
        "message": (
            "SSL certificate verification is now "
            + ("ENABLED." if params["enable"] else "DISABLED.")
        ),
    }
    return _make_json_response(output)


async def handle_get_ssl_verify(
    name: str, arguments: dict
) -> list[mcp_types.TextContent]:
    """Return the current TLS/SSL certificate verification setting."""
    output = {
        "ssl_verify": mcp_server_cfg.SSL_VERIFY,
        "message": (
            "SSL certificate verification is currently "
            + ("ENABLED." if mcp_server_cfg.SSL_VERIFY else "DISABLED.")
        ),
    }
    return _make_json_response(output)


async def handle_get_procurement_search_options(
    name: str, arguments: dict
) -> list[mcp_types.TextContent]:
    """Explain available MCP procurement search strategies."""
    output = {
        "default_recommendation": "direct_keyword_search",
        "strategies": [
            {
                "name": "direct_keyword_search",
                "tools": ["search_lpse_hosts", "search_tender_packages", "search_non_tender_packages"],
                "best_for": "Known or guessable procurement terms such as laptop, notebook, komputer.",
                "tradeoffs": [
                    "Fast and lightweight.",
                    "Uses SPSE/Inaproc keyword search directly.",
                    "Not true full-text search across downloaded details.",
                    "Can search several exact keywords and merge results.",
                ],
            },
            {
                "name": "local_full_text_index",
                "tools": [
                    "create_procurement_search_index",
                    "search_procurement_index",
                    "list_procurement_indexes",
                    "delete_procurement_index",
                ],
                "best_for": "Broad discovery when exact SPSE keywords miss relevant package detail text.",
                "tradeoffs": [
                    "Downloads package details first, so it is slower.",
                    "Makes more requests to public SPSE/Inaproc systems.",
                    "Must be bounded by host, year/category/seed keyword, and max_packages.",
                    "Stores disposable local SQLite FTS indexes.",
                ],
            },
        ],
        "llm_guidance": (
            "Start with search_lpse_hosts and direct keyword search. Offer "
            "local_full_text_index only when direct results are weak or the "
            "user explicitly asks for broader full-text search."
        ),
    }
    return _make_json_response(output)


async def handle_search_lpse_hosts(
    name: str, arguments: dict
) -> list[mcp_types.TextContent]:
    """Search known LPSE hosts by institution name or host alias."""
    try:
        params = validate_host_search_params(arguments)
    except ValueError as exc:
        return [mcp_types.TextContent(type="text",
                     text=f"Error: Invalid parameter: {exc}")]

    logger.info(
        "Search LPSE hosts: query=%s limit=%s refresh=%s",
        params["query"], params["limit"], params["refresh"],
    )

    try:
        output = search_lpse_hosts(
            query=params["query"],
            limit=params["limit"],
            refresh=params["refresh"],
        )
    except HostMetadataError as exc:
        return [mcp_types.TextContent(type="text", text=f"Error: {exc}")]
    return _make_json_response(output)


async def handle_get_lpse_host_detail(
    name: str, arguments: dict
) -> list[mcp_types.TextContent]:
    """Return metadata for one known LPSE host slug."""
    try:
        params = validate_host_detail_params(arguments)
    except ValueError as exc:
        return [mcp_types.TextContent(type="text",
                     text=f"Error: Invalid parameter: {exc}")]

    logger.info(
        "Get LPSE host detail: host=%s refresh=%s",
        params["lpse_host"], params["refresh"],
    )

    try:
        output = get_lpse_host_detail(
            lpse_host=params["lpse_host"],
            refresh=params["refresh"],
        )
    except HostMetadataError as exc:
        return [mcp_types.TextContent(type="text", text=f"Error: {exc}")]
    return _make_json_response(output)


async def handle_validate_lpse_host(
    name: str, arguments: dict
) -> list[mcp_types.TextContent]:
    """Validate whether an LPSE host is accessible."""
    try:
        host = validate_lpse_host(arguments.get('lpse_host', ''))
    except ValueError as exc:
        return [mcp_types.TextContent(type="text",
                     text=f"Error: Invalid parameter: {exc}")]

    logger.info("Validate LPSE host: %s", host)

    url = f"https://spse.inaproc.id/{host}"

    try:
        _rate_limit()
        lpse = Lpse(host, timeout=TIMEOUT, verify=mcp_server_cfg.SSL_VERIFY)
        token = lpse.get_auth_token()
        lpse.session.close()

        is_valid = token is not None and len(token) > 0
        message = (
            f"LPSE host '{host}' is accessible." if is_valid
            else f"LPSE host '{host}' responded but auth token could not be retrieved."
        )
    except Exception as exc:
        is_valid = False
        message = f"LPSE host '{host}' is not accessible: {exc}"

    output = normalize_host_validation(is_valid, host, url, message)
    return _make_json_response(output)


async def handle_create_procurement_search_index(
    name: str, arguments: dict
) -> list[mcp_types.TextContent]:
    """Create a bounded local SQLite FTS index from public procurement data.

    Sends MCP progress notifications when the client provides a progressToken.
    """
    try:
        params = validate_search_index_create_params(arguments)
    except ValueError as exc:
        return [mcp_types.TextContent(type="text",
                     text=f"Error: Invalid parameter: {exc}")]

    logger.info(
        "Create search index: host=%s type=%s tahun=%s kategori=%s seed=%s max=%s",
        params["lpse_host"], params["package_type"], params.get("tahun_anggaran"),
        params.get("kategori"), params.get("keyword_seed"), params["max_packages"],
    )
    params = dict(params)
    params.pop("confirm_download", None)
    force_refresh = params.pop("force_refresh", False)

    # ── Check for existing index ─────────────────────────────────────
    if not force_refresh:
        existing = find_existing_spse_index(
            lpse_host=params["lpse_host"],
            package_type=params["package_type"],
            tahun_anggaran=params.get("tahun_anggaran"),
            kategori=params.get("kategori"),
            keyword_seed=params.get("keyword_seed"),
        )
        if existing:
            output = {
                "status": "existing_index_found",
                "index_id": existing.get("index_id"),
                "indexed_packages": existing.get("indexed_packages", "unknown"),
                "lpse_host": params["lpse_host"],
                "package_type": params["package_type"],
                "tahun_anggaran": params.get("tahun_anggaran"),
                "created_at": existing.get("created_at"),
                "choices": {
                    "reuse": (
                        "Use the existing index as-is. Call "
                        f"search_procurement_index with index_id="
                        f"'{existing.get('index_id')}' to query it."
                    ),
                    "refresh": (
                        "Delete the existing index and create a fresh one. "
                        "Call create_procurement_search_index again with "
                        "force_refresh=true."
                    ),
                },
            }
            return _make_json_response(output)

    # ── check for MCP progress token ──────────────────────────────────────
    progress_token = None
    session = None
    try:
        ctx = server.request_context
        if ctx.meta is not None:
            progress_token = ctx.meta.progressToken
            session = ctx.session
    except LookupError:
        pass  # Not inside an MCP request (e.g., direct test call)

    if progress_token is None or session is None:
        # No progress support — call directly (preserves existing behaviour)
        output = create_procurement_search_index(
            timeout=TIMEOUT,
            rate_limit_callback=_rate_limit,
            **params,
        )
        return _make_json_response(output)

    # ── progress requested — run indexing in worker thread, send notifications ──
    progress_queue: queue.Queue = queue.Queue(maxsize=100)
    _SENTINEL = object()

    def _progress_callback(step: str, current: int, total: int | None,
                           message: str) -> None:
        """Thread-safe: push progress data to queue (non-blocking)."""
        try:
            progress_queue.put_nowait((step, current, total, message))
        except queue.Full:
            pass  # Non-critical; discard if queue is overwhelmed

    result_container: list[dict] = []

    async def _run_index() -> None:
        """Run the synchronous indexing function in a worker thread."""
        def _sync_index():
            return create_procurement_search_index(
                timeout=TIMEOUT,
                rate_limit_callback=_rate_limit,
                progress_callback=_progress_callback,
                **params,
            )
        result = await anyio.to_thread.run_sync(_sync_index)
        result_container.append(result)
        progress_queue.put(_SENTINEL)

    async def _drain_progress() -> None:
        """Drain progress events from the queue and send MCP notifications."""
        sentinel_seen = False
        while not sentinel_seen:
            # Drain all currently queued items without blocking
            while True:
                try:
                    item = progress_queue.get_nowait()
                except queue.Empty:
                    break
                if item is _SENTINEL:
                    sentinel_seen = True
                    break
                _step, current, total, message = item
                try:
                    await session.send_progress_notification(
                        progress_token=progress_token,
                        progress=float(current),
                        total=float(total) if total is not None else None,
                        message=message,
                    )
                except Exception:
                    logger.debug(
                        "Failed to send progress notification", exc_info=True,
                    )
            if not sentinel_seen:
                await anyio.sleep(0.5)

    async with anyio.create_task_group() as tg:
        tg.start_soon(_drain_progress)
        tg.start_soon(_run_index)

    return _make_json_response(result_container[0])


async def handle_search_procurement_index(
    name: str, arguments: dict
) -> list[mcp_types.TextContent]:
    """Search a local SQLite FTS procurement index."""
    try:
        params = validate_search_index_query_params(arguments)
    except ValueError as exc:
        return [mcp_types.TextContent(type="text",
                     text=f"Error: Invalid parameter: {exc}")]

    output = search_procurement_index(**params)
    return _make_json_response(output)


async def handle_list_procurement_indexes(
    name: str, arguments: dict
) -> list[mcp_types.TextContent]:
    """List local SQLite FTS procurement indexes."""
    output = list_procurement_indexes()
    return _make_json_response(output)


async def handle_delete_procurement_index(
    name: str, arguments: dict
) -> list[mcp_types.TextContent]:
    """Delete a local SQLite FTS procurement index."""
    try:
        params = validate_search_index_delete_params(arguments)
    except ValueError as exc:
        return [mcp_types.TextContent(type="text",
                     text=f"Error: Invalid parameter: {exc}")]

    output = delete_procurement_index(**params)
    return _make_json_response(output)


# ── tool descriptions for registration ───────────────────────────────────────

TOOL_DESCRIPTIONS = {
    "search_tender_packages": (
        "Search for tender procurement packages on an LPSE host. "
        "Searches the SPSE/Inaproc DataTables endpoint for tender (lelang) "
        "packages matching the given criteria. Supports a single keyword or "
        "up to 5 exact keywords searched separately and merged. This is not "
        "full-text search over downloaded details. Returns a list of matching "
        "packages with basic metadata and matched_keywords. "
        "Data sourced from public SPSE/Inaproc system. "
        "Not affiliated with LKPP or any government institution."
    ),
    "search_non_tender_packages": (
        "Search for non-tender (direct procurement / penunjukan langsung) "
        "packages on an LPSE host. Supports a single keyword or up to 5 "
        "exact keywords searched separately and merged. This is not full-text "
        "search over downloaded details. Returns a list of matching packages "
        "with basic metadata and matched_keywords. "
        "Data sourced from public SPSE/Inaproc system. "
        "Not affiliated with LKPP or any government institution."
    ),
    "get_tender_detail": (
        "Get full detail for a tender procurement package. Retrieves all "
        "available detail sections: announcement (pengumuman), participants "
        "(peserta), evaluation results (hasil evaluasi), winner (pemenang), "
        "contracted winner (pemenang berkontrak), and schedule (jadwal). "
        "This is the most data-rich tool. Expect 5-15 seconds per call due "
        "to multiple page scrapes. Rate limited to minimum 2 seconds between "
        "calls. Data sourced from public SPSE/Inaproc system. "
        "Not affiliated with LKPP or any government institution."
    ),
    "get_non_tender_detail": (
        "Get full detail for a non-tender (direct procurement) package. "
        "Retrieves all available detail sections: announcement, participants, "
        "evaluation results, winner, contracted winner, and schedule. "
        "Rate limited to minimum 2 seconds between calls. "
        "Data sourced from public SPSE/Inaproc system. "
        "Not affiliated with LKPP or any government institution."
    ),
    "get_tender_details_bulk": (
        "Get full details for multiple tender packages from one LPSE host in "
        "one MCP call. Use this instead of repeatedly calling get_tender_detail "
        "from chat. Maximum 20 package IDs per call."
    ),
    "get_non_tender_details_bulk": (
        "Get full details for multiple non-tender packages from one LPSE host "
        "in one MCP call. Use this instead of repeatedly calling "
        "get_non_tender_detail from chat. Maximum 20 package IDs per call."
    ),
    "search_pencatatan_non_tender_packages": (
        "Search pencatatan non-tender packages on an LPSE host. This is a "
        "separate SPSE entity from ordinary non_tender packages and uses the "
        "/dt/nonspk endpoint."
    ),
    "get_pencatatan_non_tender_detail": (
        "Get detail for a pencatatan non-tender package: announcement and "
        "contracted realization/winner information."
    ),
    "get_pencatatan_non_tender_details_bulk": (
        "Get details for multiple pencatatan non-tender packages in one call."
    ),
    "search_swakelola_packages": (
        "Search swakelola packages on an LPSE host. Supports tipe_swakelola_id "
        "for filtering swakelola executor type."
    ),
    "get_swakelola_detail": (
        "Get detail for a swakelola package: announcement and pelaksana swakelola."
    ),
    "get_swakelola_details_bulk": (
        "Get details for multiple swakelola packages in one call."
    ),
    "search_pengadaan_darurat_packages": (
        "Search pencatatan pengadaan darurat packages on an LPSE host."
    ),
    "get_pengadaan_darurat_detail": (
        "Get detail for a pengadaan darurat package: announcement and contracted realization."
    ),
    "get_pengadaan_darurat_details_bulk": (
        "Get details for multiple pengadaan darurat packages in one call."
    ),
    "get_procurement_categories": (
        "Get the list of supported procurement categories (Jenis Pengadaan). "
        "Returns all 6 standard SPSE procurement categories with their names, "
        "enum values, and descriptions. No network call required. "
        "Use this to discover valid values for the 'kategori' parameter "
        "in search tools."
    ),
    "get_master_klpd": (
        "Get LKPP Satu Data master K/L/PD references. Use kd_klpd from this "
        "tool as instansi_id when filtering search_tender_packages or "
        "search_non_tender_packages by institution. "
        "By default, results are saved to a JSON file to avoid overwhelming "
        "the LLM context. Set save_to_file=false only when the filtered "
        "result is small enough for inline consumption."
    ),
    "get_master_lpse": (
        "Get LKPP Satu Data master LPSE references. Use kd_lpse from this "
        "tool as the kd_lpse parameter in get_tender_umum_publik. This is "
        "reference data for valid LPSE codes. "
        "By default, results are saved to a JSON file to avoid overwhelming "
        "the LLM context. Set save_to_file=false only when the filtered "
        "result is small enough for inline consumption."
    ),
    "get_tender_umum_publik": (
        "Get tender procurement data from LKPP ISB Satu Data (alternative "
        "data source). Use this as a fallback when the realtime SPSE/Inaproc "
        "search tools (search_tender_packages) return no results or errors. "
        "Also use when the user explicitly asks for ISB Satu Data. Requires "
        "kd_lpse from get_master_lpse and tahun_anggaran. Field names in "
        "results may contain spaces (e.g., 'Kode Tender', 'Nama Paket'). "
        "TWO-STEP INTERACTION: On first call (without output_mode), the tool "
        "fetches data and returns a choice prompt with record count, preview, "
        "and 3 output options. Call again with output_mode to process: "
        "'local_index' creates a SQLite FTS index (recommended), "
        "'file' saves to JSON file, "
        "'inline' returns full JSON (NOT recommended, will warn)."
    ),
    "search_isb_index": (
        "Search a local ISB Satu Data SQLite FTS index created by "
        "get_tender_umum_publik with output_mode='local_index'. "
        "Searches tender names and details locally without network requests. "
        "Use this to find specific tenders within a large ISB dataset."
    ),
    "set_ssl_verify": (
        "Enable or disable TLS/SSL certificate verification for all SPSE/Inaproc "
        "requests made by this MCP server. When disabled (enable=false), "
        "certificate errors such as self-signed or expired certificates are "
        "ignored. This is useful when connecting through corporate proxies or "
        "VPNs that intercept TLS traffic. The setting takes effect immediately "
        "and persists for the lifetime of the MCP session. The initial value "
        "can be set via the PYPROC_SSL_VERIFY environment variable "
        "(set to '1', 'true', or 'yes' to enable)."
    ),
    "get_ssl_verify": (
        "Return the current TLS/SSL certificate verification setting. "
        "Returns whether SSL verification is currently enabled or disabled."
    ),
    "get_procurement_search_options": (
        "Explain the two MCP search strategies: direct SPSE keyword search "
        "and optional local full-text indexing. Use this when a user asks "
        "whether they should provide multiple exact keywords or download data "
        "first for full-text search."
    ),
    "search_lpse_hosts": (
        "Search known LPSE/SPSE host identifiers by institution name, alias, "
        "or free-text query. There are two procurement executor scopes: "
        "agency-specific hosts, such as 'kemenkeu', 'jakarta', or 'pu', and "
        "a nationwide host, exactly 'nasional'. Use 'nasional' directly when "
        "the user asks for national, nationwide, all-Indonesia, lintas "
        "instansi, or pencatatan nasional data. Use this tool before package "
        "search when the user mentions an institution such as 'kementerian "
        "keuangan' instead of a concrete lpse_host value. For example, "
        "resolve 'kementerian keuangan' to host 'kemenkeu', then call "
        "search_tender_packages with lpse_host='kemenkeu' and the user's "
        "procurement keyword. "
        "Returns ranked host candidates and canonical SPSE URLs. This tool "
        "reads cached Gist host metadata using newUrlPath plus the built-in "
        "'nasional' host, and does not search procurement packages."
    ),
    "get_lpse_host_detail": (
        "Get metadata for one known LPSE host slug returned by "
        "search_lpse_hosts. Use this to confirm the canonical SPSE URL and "
        "institution name before calling procurement search or detail tools."
    ),
    "validate_lpse_host": (
        "Validate whether an LPSE host identifier is accessible. "
        "Attempts to connect to the SPSE/Inaproc server and retrieve an "
        "authentication token. Returns whether the host is valid and "
        "accessible. Useful before using a host with search or detail tools."
    ),
    "create_procurement_search_index": (
        "Create a local SQLite full-text search index by downloading "
        "public package details for one LPSE host. By default downloads all "
        "available packages (max_packages=0). Set a positive max_packages to "
        "limit scope. Prefer year/category/seed filters to narrow results. "
        "This can make many SPSE requests. "
        "Progress notifications are sent during index creation when the "
        "client supports the notifications/progress protocol. "
        "Does not call the CLI."
    ),
    "search_procurement_index": (
        "Search a previously created local SQLite full-text procurement index. "
        "This searches downloaded package details locally and does not make "
        "network requests."
    ),
    "list_procurement_indexes": (
        "List local disposable SQLite full-text procurement indexes created "
        "by the MCP server."
    ),
    "delete_procurement_index": (
        "Delete a local disposable SQLite full-text procurement index. This "
        "only removes local MCP cache data."
    ),
    "clear_all_data": (
        "Delete ALL local MCP indexes (SPSE and ISB) and downloaded data "
        "files. Requires confirm=true. This frees disk space but cannot "
        "be undone — all indexes must be recreated after clearing."
    ),
}

# ── register all tools ───────────────────────────────────────────────────────

# (description is stored alongside schema; the server reads it during
# handle_list_tools by pulling from _tool_handlers)

register_tool(
    "search_tender_packages",
    handle_search_tender_packages,
    {**SEARCH_TOOL_SCHEMA, "_description": TOOL_DESCRIPTIONS["search_tender_packages"]},
)
register_tool(
    "search_non_tender_packages",
    handle_search_non_tender_packages,
    {**SEARCH_TOOL_SCHEMA, "_description": TOOL_DESCRIPTIONS["search_non_tender_packages"]},
)
register_tool(
    "get_tender_detail",
    handle_get_tender_detail,
    {**DETAIL_TOOL_SCHEMA, "_description": TOOL_DESCRIPTIONS["get_tender_detail"]},
)
register_tool(
    "get_non_tender_detail",
    handle_get_non_tender_detail,
    {**DETAIL_TOOL_SCHEMA, "_description": TOOL_DESCRIPTIONS["get_non_tender_detail"]},
)
register_tool(
    "get_tender_details_bulk",
    handle_get_tender_details_bulk,
    {**BULK_DETAIL_TOOL_SCHEMA, "_description": TOOL_DESCRIPTIONS["get_tender_details_bulk"]},
)
register_tool(
    "get_non_tender_details_bulk",
    handle_get_non_tender_details_bulk,
    {**BULK_DETAIL_TOOL_SCHEMA, "_description": TOOL_DESCRIPTIONS["get_non_tender_details_bulk"]},
)
register_tool(
    "search_pencatatan_non_tender_packages",
    handle_search_pencatatan_non_tender_packages,
    {**SEARCH_TOOL_SCHEMA, "_description": TOOL_DESCRIPTIONS["search_pencatatan_non_tender_packages"]},
)
register_tool(
    "get_pencatatan_non_tender_detail",
    handle_get_pencatatan_non_tender_detail,
    {**DETAIL_TOOL_SCHEMA, "_description": TOOL_DESCRIPTIONS["get_pencatatan_non_tender_detail"]},
)
register_tool(
    "get_pencatatan_non_tender_details_bulk",
    handle_get_pencatatan_non_tender_details_bulk,
    {**BULK_DETAIL_TOOL_SCHEMA, "_description": TOOL_DESCRIPTIONS["get_pencatatan_non_tender_details_bulk"]},
)
register_tool(
    "search_swakelola_packages",
    handle_search_swakelola_packages,
    {**SEARCH_TOOL_SCHEMA, "_description": TOOL_DESCRIPTIONS["search_swakelola_packages"]},
)
register_tool(
    "get_swakelola_detail",
    handle_get_swakelola_detail,
    {**DETAIL_TOOL_SCHEMA, "_description": TOOL_DESCRIPTIONS["get_swakelola_detail"]},
)
register_tool(
    "get_swakelola_details_bulk",
    handle_get_swakelola_details_bulk,
    {**BULK_DETAIL_TOOL_SCHEMA, "_description": TOOL_DESCRIPTIONS["get_swakelola_details_bulk"]},
)
register_tool(
    "search_pengadaan_darurat_packages",
    handle_search_pengadaan_darurat_packages,
    {**SEARCH_TOOL_SCHEMA, "_description": TOOL_DESCRIPTIONS["search_pengadaan_darurat_packages"]},
)
register_tool(
    "get_pengadaan_darurat_detail",
    handle_get_pengadaan_darurat_detail,
    {**DETAIL_TOOL_SCHEMA, "_description": TOOL_DESCRIPTIONS["get_pengadaan_darurat_detail"]},
)
register_tool(
    "get_pengadaan_darurat_details_bulk",
    handle_get_pengadaan_darurat_details_bulk,
    {**BULK_DETAIL_TOOL_SCHEMA, "_description": TOOL_DESCRIPTIONS["get_pengadaan_darurat_details_bulk"]},
)
register_tool(
    "get_procurement_categories",
    handle_get_procurement_categories,
    {**CATEGORIES_SCHEMA, "_description": TOOL_DESCRIPTIONS["get_procurement_categories"]},
)
register_tool(
    "get_master_klpd",
    handle_get_master_klpd,
    {**MASTER_KLPD_SCHEMA, "_description": TOOL_DESCRIPTIONS["get_master_klpd"]},
)
register_tool(
    "get_master_lpse",
    handle_get_master_lpse,
    {**MASTER_LPSE_SCHEMA, "_description": TOOL_DESCRIPTIONS["get_master_lpse"]},
)
register_tool(
    "get_tender_umum_publik",
    handle_get_tender_umum_publik,
    {**TENDER_UMUM_PUBLIK_SCHEMA, "_description": TOOL_DESCRIPTIONS["get_tender_umum_publik"]},
)
register_tool(
    "set_ssl_verify",
    handle_set_ssl_verify,
    {**SSL_VERIFY_SCHEMA, "_description": TOOL_DESCRIPTIONS["set_ssl_verify"]},
)
register_tool(
    "get_ssl_verify",
    handle_get_ssl_verify,
    {"type": "object", "properties": {}, "_description": TOOL_DESCRIPTIONS["get_ssl_verify"]},
)
register_tool(
    "get_procurement_search_options",
    handle_get_procurement_search_options,
    {**SEARCH_OPTIONS_SCHEMA, "_description": TOOL_DESCRIPTIONS["get_procurement_search_options"]},
)
register_tool(
    "search_lpse_hosts",
    handle_search_lpse_hosts,
    {**HOST_SEARCH_SCHEMA, "_description": TOOL_DESCRIPTIONS["search_lpse_hosts"]},
)
register_tool(
    "get_lpse_host_detail",
    handle_get_lpse_host_detail,
    {**HOST_DETAIL_SCHEMA, "_description": TOOL_DESCRIPTIONS["get_lpse_host_detail"]},
)
register_tool(
    "validate_lpse_host",
    handle_validate_lpse_host,
    {**VALIDATE_HOST_SCHEMA, "_description": TOOL_DESCRIPTIONS["validate_lpse_host"]},
)
register_tool(
    "create_procurement_search_index",
    handle_create_procurement_search_index,
    {**CREATE_SEARCH_INDEX_SCHEMA, "_description": TOOL_DESCRIPTIONS["create_procurement_search_index"]},
)
register_tool(
    "search_procurement_index",
    handle_search_procurement_index,
    {**SEARCH_INDEX_SCHEMA, "_description": TOOL_DESCRIPTIONS["search_procurement_index"]},
)
register_tool(
    "list_procurement_indexes",
    handle_list_procurement_indexes,
    {**LIST_SEARCH_INDEXES_SCHEMA, "_description": TOOL_DESCRIPTIONS["list_procurement_indexes"]},
)
register_tool(
    "delete_procurement_index",
    handle_delete_procurement_index,
    {**DELETE_SEARCH_INDEX_SCHEMA, "_description": TOOL_DESCRIPTIONS["delete_procurement_index"]},
)
register_tool(
    "search_isb_index",
    handle_search_isb_index,
    {**SEARCH_ISB_INDEX_SCHEMA, "_description": TOOL_DESCRIPTIONS["search_isb_index"]},
)
register_tool(
    "clear_all_data",
    handle_clear_all_data,
    {**CLEAR_ALL_DATA_SCHEMA, "_description": TOOL_DESCRIPTIONS["clear_all_data"]},
)

logger.info("Registered %d MCP tools", len(TOOL_DESCRIPTIONS))
