"""Input validation and output normalization schemas for MCP tools.

All validation functions raise ValueError with descriptive messages on
invalid input. All normalization functions transform raw PyProc library
output into clean, LLM-friendly JSON-serializable structures.
"""

import re

from pyproc.lpse import By, JenisPengadaan

# ── constants ────────────────────────────────────────────────────────────────

MAX_SEARCH_LENGTH = 100
DEFAULT_SEARCH_LENGTH = 20
MAX_TEXT_FIELD_LENGTH = 1000
MAX_HOST_SEARCH_LIMIT = 20
DEFAULT_HOST_SEARCH_LIMIT = 5
MAX_DIRECT_SEARCH_KEYWORDS = 5
VALID_KEYWORD_MATCH_MODES = {"any", "all"}
VALID_PACKAGE_TYPES = {"tender", "non_tender", "pencatatan_non_tender", "swakelola", "darurat"}
VALID_TIPE_SWAKELA = {1, 2, 3, 4}
VALID_ORDER_BY = {
    "kode": By.KODE,
    "id_paket": By.KODE,
    "nama_paket": By.NAMA_PAKET,
    "instansi": By.INSTANSI,
    "hps": By.HPS,
}
VALID_ORDER_DIR = {"asc", "desc"}
VALID_KONTRAK_STATUS = {0, 1, 2}
DEFAULT_INDEX_MAX_PACKAGES = 0
DEFAULT_INDEX_SEARCH_LIMIT = 20
MAX_INDEX_SEARCH_LIMIT = 100
MAX_BULK_DETAIL_PACKAGE_IDS = 20

VALID_CATEGORIES = {e.name for e in JenisPengadaan}

CATEGORY_DESCRIPTIONS = {
    "PENGADAAN_BARANG": "Pengadaan Barang (Goods Procurement)",
    "JASA_KONSULTANSI_BADAN_USAHA_NON_KONSTRUKSI":
        "Jasa Konsultansi Badan Usaha Non Konstruksi (Non-Construction Business Entity Consulting Services)",
    "PEKERJAAN_KONSTRUKSI": "Pekerjaan Konstruksi (Construction Works)",
    "JASA_LAINNYA": "Jasa Lainnya (Other Services)",
    "JASA_KONSULTANSI_PERORANGAN":
        "Jasa Konsultansi Perorangan (Individual Consulting Services)",
    "JASA_KONSULTANSI_BADAN_USAHA_KONSTRUKSI":
        "Jasa Konsultansi Badan Usaha Konstruksi (Construction Business Entity Consulting Services)",
}

# ── sanitization ─────────────────────────────────────────────────────────────

def sanitize_text(value):
    """Sanitize a text value for LLM consumption.

    - Strips control characters
    - Truncates long fields to MAX_TEXT_FIELD_LENGTH
    - Converts non-string values to string
    """
    if value is None:
        return None
    if not isinstance(value, str):
        return str(value)
    # Strip null bytes and other control characters
    cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', value)
    if len(cleaned) > MAX_TEXT_FIELD_LENGTH:
        cleaned = cleaned[:MAX_TEXT_FIELD_LENGTH] + "..."
    return cleaned


def sanitize_dict_keys(d, max_length=MAX_TEXT_FIELD_LENGTH):
    """Recursively sanitize all string values in a dict or list."""
    if isinstance(d, dict):
        return {k: sanitize_dict_keys(v, max_length) for k, v in d.items()}
    if isinstance(d, list):
        return [sanitize_dict_keys(i, max_length) for i in d]
    if isinstance(d, str):
        return sanitize_text(d)
    return d


# ── validation ───────────────────────────────────────────────────────────────

def validate_lpse_host(host: str) -> str:
    """Validate an LPSE host identifier.

    Args:
        host: LPSE host string (e.g., 'kemenkeu', 'jakarta').

    Returns:
        The validated host string.

    Raises:
        ValueError: If host is empty or contains invalid characters.
    """
    if not host or not host.strip():
        raise ValueError("LPSE host must not be empty")
    host = host.strip().lower()
    # Host should be alphanumeric with possible hyphens
    if not re.match(r'^[a-z0-9][a-z0-9\-]*$', host):
        raise ValueError(
            f"Invalid LPSE host format: '{host}'. "
            "Use a simple identifier like 'kemenkeu' or 'jakarta'."
        )
    return host


def validate_package_id(package_id) -> str:
    """Validate a procurement package ID.

    Args:
        package_id: Package ID (int or string of digits).

    Returns:
        The validated package ID as a string.

    Raises:
        ValueError: If package_id is not a valid numeric ID.
    """
    try:
        pid = str(int(package_id))
    except (ValueError, TypeError):
        raise ValueError(
            f"Invalid package ID: {package_id}. Must be a numeric ID."
        )
    return pid


def validate_kategori(kategori: str | None) -> str | None:
    """Validate a procurement category name.

    Args:
        kategori: Category name matching JenisPengadaan enum member.

    Returns:
        The validated category name or None.

    Raises:
        ValueError: If category is invalid.
    """
    if kategori is None:
        return None
    if kategori not in VALID_CATEGORIES:
        raise ValueError(
            f"Invalid category: '{kategori}'. "
            f"Valid categories: {', '.join(sorted(VALID_CATEGORIES))}"
        )
    return kategori


def validate_tahun_anggaran(tahun) -> int | None:
    """Validate a budget year value.

    Args:
        tahun: Budget year (int or string of digits).

    Returns:
        The validated year as int, or None.

    Raises:
        ValueError: If year is out of reasonable range.
    """
    if tahun is None:
        return None
    try:
        year = int(tahun)
    except (ValueError, TypeError):
        raise ValueError(f"Invalid budget year: {tahun}. Must be a number.")
    if year < 2000 or year > 2100:
        raise ValueError(
            f"Budget year {year} is out of range (2000-2100)."
        )
    return year


def validate_search_params(params: dict) -> dict:
    """Validate all search tool parameters.

    Args:
        params: Raw parameters dict from MCP tool call.

    Returns:
        Cleaned and validated parameters dict.

    Raises:
        ValueError: If any parameter is invalid.
    """
    cleaned = {}

    # lpse_host (required)
    cleaned['lpse_host'] = validate_lpse_host(params.get('lpse_host', ''))

    # keyword (optional)
    keyword = params.get('keyword')
    cleaned['keyword'] = str(keyword).strip() if keyword else ''

    keywords = params.get('keywords') or []
    if isinstance(keywords, str):
        keywords = [keywords]
    if not isinstance(keywords, list):
        raise ValueError("keywords must be a list of strings")
    cleaned_keywords = []
    for item in keywords:
        value = str(item).strip()
        if value and value not in cleaned_keywords:
            cleaned_keywords.append(value)
    if cleaned['keyword'] and cleaned['keyword'] not in cleaned_keywords:
        cleaned_keywords.insert(0, cleaned['keyword'])
    if len(cleaned_keywords) > MAX_DIRECT_SEARCH_KEYWORDS:
        raise ValueError(
            f"keywords supports at most {MAX_DIRECT_SEARCH_KEYWORDS} values"
        )
    cleaned['keywords'] = cleaned_keywords

    match_mode = str(params.get('keyword_match_mode') or 'any').strip().lower()
    if match_mode not in VALID_KEYWORD_MATCH_MODES:
        raise ValueError(
            "keyword_match_mode must be one of: "
            f"{', '.join(sorted(VALID_KEYWORD_MATCH_MODES))}"
        )
    cleaned['keyword_match_mode'] = match_mode

    # rekanan (optional). nama_penyedia is accepted as a backward-compatible alias.
    rekanan = params.get('rekanan') or params.get('nama_penyedia')
    cleaned['rekanan'] = str(rekanan).strip() if rekanan else None

    instansi_id = params.get('instansi_id')
    if instansi_id:
        instansi_id = str(instansi_id).strip()
        if not re.match(r'^[A-Za-z0-9_.-]+$', instansi_id):
            raise ValueError("instansi_id contains invalid characters")
    cleaned['instansi_id'] = instansi_id or None

    order_by = str(params.get('order_by') or 'kode').strip().lower()
    if order_by not in VALID_ORDER_BY:
        raise ValueError(
            "order_by must be one of: "
            f"{', '.join(sorted(VALID_ORDER_BY))}"
        )
    cleaned['order_by'] = order_by
    cleaned['order'] = VALID_ORDER_BY[order_by]

    order_dir = str(params.get('order_dir') or params.get('sort_dir') or 'desc').strip().lower()
    if order_dir not in VALID_ORDER_DIR:
        raise ValueError(
            "order_dir must be one of: "
            f"{', '.join(sorted(VALID_ORDER_DIR))}"
        )
    cleaned['order_dir'] = order_dir
    cleaned['ascending'] = order_dir == 'asc'

    kontrak_status = params.get('kontrak_status')
    if kontrak_status == "":
        kontrak_status = None
    if kontrak_status is not None:
        try:
            kontrak_status = int(kontrak_status)
        except (ValueError, TypeError):
            raise ValueError("kontrak_status must be 0, 1, 2, or null")
        if kontrak_status not in VALID_KONTRAK_STATUS:
            raise ValueError("kontrak_status must be 0, 1, 2, or null")
    cleaned['kontrak_status'] = kontrak_status

    # tahun_anggaran (optional)
    cleaned['tahun_anggaran'] = validate_tahun_anggaran(
        params.get('tahun_anggaran')
    )

    # kategori (optional)
    cleaned['kategori'] = validate_kategori(params.get('kategori'))

    tipe_swakelola_id = params.get('tipe_swakelola_id')
    if tipe_swakelola_id == "":
        tipe_swakelola_id = None
    if tipe_swakelola_id is not None:
        try:
            tipe_swakelola_id = int(tipe_swakelola_id)
        except (ValueError, TypeError):
            raise ValueError("tipe_swakelola_id must be 1, 2, 3, 4, or null")
        if tipe_swakelola_id not in VALID_TIPE_SWAKELA:
            raise ValueError("tipe_swakelola_id must be 1, 2, 3, 4, or null")
    cleaned['tipe_swakelola_id'] = tipe_swakelola_id

    # start (optional, default 0)
    start = params.get('start', 0)
    try:
        cleaned['start'] = max(0, int(start))
    except (ValueError, TypeError):
        raise ValueError(f"Invalid start value: {start}")

    # length (optional, default 20, max 100)
    length = params.get('length', DEFAULT_SEARCH_LENGTH)
    try:
        length = int(length)
    except (ValueError, TypeError):
        raise ValueError(f"Invalid length value: {length}")
    cleaned['length'] = max(1, min(length, MAX_SEARCH_LENGTH))

    return cleaned


def validate_detail_params(params: dict) -> dict:
    """Validate detail tool parameters.

    Args:
        params: Raw parameters dict from MCP tool call.

    Returns:
        Cleaned and validated parameters dict.

    Raises:
        ValueError: If any parameter is invalid.
    """
    cleaned = {}

    # lpse_host (required)
    cleaned['lpse_host'] = validate_lpse_host(params.get('lpse_host', ''))

    # package_id (required)
    cleaned['package_id'] = validate_package_id(params.get('package_id'))

    return cleaned


def validate_bulk_detail_params(params: dict) -> dict:
    """Validate bulk detail tool parameters."""
    package_ids = params.get("package_ids")
    if not isinstance(package_ids, list) or not package_ids:
        raise ValueError("package_ids must be a non-empty list")
    if len(package_ids) > MAX_BULK_DETAIL_PACKAGE_IDS:
        raise ValueError(
            f"package_ids supports at most {MAX_BULK_DETAIL_PACKAGE_IDS} values"
        )

    continue_on_error = params.get("continue_on_error", True)
    if isinstance(continue_on_error, str):
        continue_on_error = continue_on_error.strip().lower() in ("1", "true", "yes", "y")

    return {
        "lpse_host": validate_lpse_host(params.get("lpse_host", "")),
        "package_ids": [validate_package_id(package_id) for package_id in package_ids],
        "continue_on_error": bool(continue_on_error),
    }


def validate_host_search_params(params: dict) -> dict:
    """Validate LPSE host search parameters."""
    query = str(params.get("query") or "").strip()
    if not query:
        raise ValueError("Host search query must not be empty")

    try:
        limit = int(params.get("limit", DEFAULT_HOST_SEARCH_LIMIT))
    except (ValueError, TypeError):
        raise ValueError(f"Invalid limit value: {params.get('limit')}")

    refresh = params.get("refresh", False)
    if isinstance(refresh, str):
        refresh = refresh.strip().lower() in ("1", "true", "yes", "y")

    return {
        "query": query,
        "limit": max(1, min(limit, MAX_HOST_SEARCH_LIMIT)),
        "refresh": bool(refresh),
    }


def validate_host_detail_params(params: dict) -> dict:
    """Validate known LPSE host detail parameters."""
    refresh = params.get("refresh", False)
    if isinstance(refresh, str):
        refresh = refresh.strip().lower() in ("1", "true", "yes", "y")

    return {
        "lpse_host": validate_lpse_host(params.get("lpse_host", "")),
        "refresh": bool(refresh),
    }


def validate_search_index_create_params(params: dict) -> dict:
    """Validate local full-text index creation parameters."""
    confirm_download = params.get("confirm_download", False)
    if isinstance(confirm_download, str):
        confirm_download = confirm_download.strip().lower() in ("1", "true", "yes", "y")
    if not confirm_download:
        raise ValueError(
            "confirm_download must be true because local full-text indexing "
            "downloads package details and may make many SPSE requests"
        )

    package_type = str(params.get("package_type") or "tender").strip().lower()
    if package_type not in VALID_PACKAGE_TYPES:
        raise ValueError(
            "package_type must be one of: "
            f"{', '.join(sorted(VALID_PACKAGE_TYPES))}"
        )

    try:
        max_packages = int(params.get("max_packages", DEFAULT_INDEX_MAX_PACKAGES))
    except (ValueError, TypeError):
        raise ValueError(f"Invalid max_packages value: {params.get('max_packages')}")

    return {
        "lpse_host": validate_lpse_host(params.get("lpse_host", "")),
        "package_type": package_type,
        "tahun_anggaran": validate_tahun_anggaran(params.get("tahun_anggaran")),
        "kategori": validate_kategori(params.get("kategori")),
        "keyword_seed": str(params.get("keyword_seed") or "").strip() or None,
        "max_packages": max(0, max_packages),
        "confirm_download": True,
    }


def validate_search_index_query_params(params: dict) -> dict:
    """Validate local full-text index search parameters."""
    index_id = str(params.get("index_id") or "").strip()
    query = str(params.get("query") or "").strip()
    if not index_id:
        raise ValueError("index_id must not be empty")
    if not re.match(r"^[a-zA-Z0-9_.-]+$", index_id):
        raise ValueError("index_id contains invalid characters")
    if not query:
        raise ValueError("query must not be empty")

    try:
        limit = int(params.get("limit", DEFAULT_INDEX_SEARCH_LIMIT))
    except (ValueError, TypeError):
        raise ValueError(f"Invalid limit value: {params.get('limit')}")

    return {
        "index_id": index_id,
        "query": query,
        "limit": max(1, min(limit, MAX_INDEX_SEARCH_LIMIT)),
    }


def validate_search_index_delete_params(params: dict) -> dict:
    """Validate local full-text index deletion parameters."""
    index_id = str(params.get("index_id") or "").strip()
    if not index_id:
        raise ValueError("index_id must not be empty")
    if not re.match(r"^[a-zA-Z0-9_.-]+$", index_id):
        raise ValueError("index_id contains invalid characters")
    return {"index_id": index_id}


def validate_master_klpd_params(params: dict) -> dict:
    """Validate master KLPD lookup parameters."""
    query = str(params.get("query") or "").strip()
    kd_klpd = str(params.get("kd_klpd") or "").strip()
    jenis_klpd = str(params.get("jenis_klpd") or "").strip()
    if kd_klpd and not re.match(r'^[A-Za-z0-9_.-]+$', kd_klpd):
        raise ValueError("kd_klpd contains invalid characters")

    try:
        limit = int(params.get("limit", 50))
    except (ValueError, TypeError):
        raise ValueError(f"Invalid limit value: {params.get('limit')}")

    return {
        "query": query,
        "kd_klpd": kd_klpd or None,
        "jenis_klpd": jenis_klpd or None,
        "limit": max(1, min(limit, 500)),
    }


# ── output normalization ─────────────────────────────────────────────────────

def normalize_search_results(
    raw_data: list, lpse_host: str, total: int,
    start: int, length: int, package_type: str = "tender"
) -> dict:
    """Normalize raw DataTables search results into structured output.

    Args:
        raw_data: List of lists from SPSE DataTables 'data' field.
        lpse_host: LPSE host identifier.
        total: Total record count.
        start: Pagination start offset.
        length: Page size.

    Returns:
        Structured dict with packages list and metadata.
    """
    packages = []
    for row in raw_data:
        try:
            raw_row = sanitize_dict_keys(row)
            pkg = _normalize_package_row(row, raw_row, package_type)
        except (IndexError, TypeError):
            pkg = {"raw": sanitize_dict_keys(row)}

        packages.append(pkg)

    return {
        "packages": packages,
        "total": total,
        "count": len(packages),
        "start": start,
        "length": length,
        "lpse_host": lpse_host,
        "lpse_url": f"https://spse.inaproc.id/{lpse_host}",
        "package_type": package_type,
    }


def _normalize_package_row(row: list, raw_row: list, package_type: str) -> dict:
    base = {
        "id_paket": row[0],
        "nama_paket": sanitize_text(row[1]) if len(row) > 1 else None,
        "instansi": sanitize_text(row[2]) if len(row) > 2 else None,
        "raw": raw_row,
    }
    if package_type == "pencatatan_non_tender":
        base.update({
            "pagu": sanitize_text(row[3]) if len(row) > 3 else None,
            "metode_pengadaan": sanitize_text(row[4]) if len(row) > 4 else None,
            "jenis_pengadaan": sanitize_text(row[5]) if len(row) > 5 else None,
            "tahun_anggaran": sanitize_text(row[6]) if len(row) > 6 else None,
            "versi_spse": sanitize_text(row[7]) if len(row) > 7 else None,
            "status": sanitize_text(row[8]) if len(row) > 8 else None,
        })
    elif package_type == "swakelola":
        base.update({
            "pagu": sanitize_text(row[3]) if len(row) > 3 else None,
            "tahun_anggaran": sanitize_text(row[5]) if len(row) > 5 else None,
            "versi_spse": sanitize_text(row[6]) if len(row) > 6 else None,
            "status": sanitize_text(row[7]) if len(row) > 7 else None,
        })
    elif package_type == "darurat":
        base.update({
            "pagu": sanitize_text(row[3]) if len(row) > 3 else None,
            "tahun_anggaran": sanitize_text(row[4]) if len(row) > 4 else None,
            "versi_spse": sanitize_text(row[5]) if len(row) > 5 else None,
            "jenis_pengadaan": sanitize_text(row[6]) if len(row) > 6 else None,
            "status": sanitize_text(row[7]) if len(row) > 7 else None,
        })
    else:
        base.update({
            "tahap": sanitize_text(row[3]) if len(row) > 3 else None,
            "hps": _parse_hps(row),
            "tahun_anggaran": sanitize_text(row[-1]) if len(row) > 5 else None,
        })
    return base


def _parse_hps(row: list) -> float | None:
    """Extract HPS value from a DataTables row.

    The HPS column position varies between SPSE versions.
    Common patterns: row[4] or row[5] with 'Rp' prefix.
    """
    for idx in (4, 5):
        if idx < len(row) and row[idx]:
            try:
                val = str(row[idx]).replace('Rp', '').replace('.', '').replace(',', '.').strip()
                return float(val)
            except (ValueError, TypeError):
                pass
    return None


def normalize_detail_result(detail_dict: dict) -> dict:
    """Normalize a BaseLpseDetil.todict() result for MCP output.

    Args:
        detail_dict: Raw dict from detail.todict().

    Returns:
        Sanitized dict with consistent structure.
    """
    if not detail_dict:
        return {"error": "No detail data available"}

    result = {
        "package_id": detail_dict.get("id_paket"),
    }

    # Pengumuman (announcement)
    pengumuman = detail_dict.get("pengumuman")
    if pengumuman:
        result["pengumuman"] = sanitize_dict_keys(pengumuman)

    # Peserta (participants)
    peserta = detail_dict.get("peserta")
    if peserta is not None:
        result["peserta"] = sanitize_dict_keys(peserta)
        result["peserta_count"] = len(peserta) if isinstance(peserta, list) else 0

    # Hasil evaluasi (evaluation results)
    hasil = detail_dict.get("hasil")
    if hasil is not None:
        result["hasil_evaluasi"] = sanitize_dict_keys(hasil)
        result["hasil_count"] = len(hasil) if isinstance(hasil, list) else 0

    # Pemenang (winner)
    pemenang = detail_dict.get("pemenang")
    if pemenang is not None:
        result["pemenang"] = _sanitize_pemenang(pemenang)

    # Pemenang berkontrak (contracted winner)
    pemenang_berkontrak = detail_dict.get("pemenang_berkontrak")
    if pemenang_berkontrak is not None:
        result["pemenang_berkontrak"] = _sanitize_pemenang(pemenang_berkontrak)

    # Jadwal (schedule)
    jadwal = detail_dict.get("jadwal")
    if jadwal is not None:
        result["jadwal"] = sanitize_dict_keys(jadwal)

    pelaksana = detail_dict.get("pelaksana")
    if pelaksana is not None:
        result["pelaksana"] = sanitize_dict_keys(pelaksana)

    return result


def _sanitize_pemenang(pemenang: list) -> list:
    """Sanitize winner data, redacting NPWP values."""
    if not isinstance(pemenang, list):
        return []
    sanitized = []
    for p in pemenang:
        if not isinstance(p, dict):
            continue
        item = dict(p)
        # Redact NPWP if present
        if "npwp" in item and item["npwp"]:
            npwp = str(item["npwp"])
            if len(npwp) > 8:
                item["npwp"] = npwp[:3] + "*" * (len(npwp) - 6) + npwp[-3:]
        sanitized.append(item)
    return sanitized


def normalize_categories() -> dict:
    """Return all procurement categories as a structured list."""
    categories = []
    for cat in JenisPengadaan:
        categories.append({
            "name": cat.name,
            "value": cat.value,
            "description": CATEGORY_DESCRIPTIONS.get(
                cat.name, cat.name.replace("_", " ").title()
            ),
        })
    return {"categories": categories, "count": len(categories)}


def normalize_host_validation(is_valid: bool, host: str, url: str,
                              message: str = "") -> dict:
    """Normalize LPSE host validation result."""
    return {
        "valid": is_valid,
        "host": host,
        "url": url,
        "message": message,
    }


# ── tool input schemas (JSON Schema) ─────────────────────────────────────────

SEARCH_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "lpse_host": {
            "type": "string",
            "description": (
                "LPSE host identifier. Examples: agency hosts like "
                "'kemenkeu', 'jakarta', 'sumbarprov', 'pu', or the "
                "nationwide host 'nasional'. This is the path under "
                "spse.inaproc.id."
            ),
        },
        "keyword": {
            "type": "string",
            "description": (
                "Single SPSE keyword. For broader searches, prefer keywords "
                "with several exact terms."
            ),
        },
        "keywords": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Multiple exact SPSE keywords to search separately and merge. "
                f"Maximum {MAX_DIRECT_SEARCH_KEYWORDS} values. Examples: "
                "['laptop', 'notebook', 'komputer']."
            ),
            "maxItems": MAX_DIRECT_SEARCH_KEYWORDS,
        },
        "keyword_match_mode": {
            "type": "string",
            "enum": sorted(VALID_KEYWORD_MATCH_MODES),
            "description": (
                "'any' returns packages found by any keyword. 'all' only "
                "keeps packages found by every keyword. This is not SPSE "
                "full-text search; it merges exact keyword searches."
            ),
            "default": "any",
        },
        "tahun_anggaran": {
            "type": "integer",
            "description": "Budget year filter (e.g., 2025).",
        },
        "kategori": {
            "type": "string",
            "enum": sorted(VALID_CATEGORIES),
            "description": "Procurement category filter.",
        },
        "tipe_swakelola_id": {
            "type": ["integer", "null"],
            "enum": [1, 2, 3, 4, None],
            "description": "Swakelola-only filter: 1 K/L/PD PJA, 2 K/L/PD lain, 3 ormas, 4 pokmas.",
        },
        "nama_penyedia": {
            "type": "string",
            "description": "Deprecated alias for rekanan.",
        },
        "rekanan": {
            "type": "string",
            "description": "Filter by provider/vendor/rekanan name.",
        },
        "instansi_id": {
            "type": "string",
            "description": (
                "K/L/PD code from get_master_klpd kd_klpd, used as the "
                "instansiId package search filter. Example: K66."
            ),
        },
        "order_by": {
            "type": "string",
            "enum": sorted(VALID_ORDER_BY),
            "description": "Column to sort by. Use 'hps' for highest/lowest HPS sorting.",
            "default": "kode",
        },
        "order_dir": {
            "type": "string",
            "enum": sorted(VALID_ORDER_DIR),
            "description": "Sort direction.",
            "default": "desc",
        },
        "kontrak_status": {
            "type": ["integer", "null"],
            "enum": [0, 1, 2, None],
            "description": (
                "Tender-only contract status filter: 0 selesai, "
                "1 pemutusan kontrak, 2 penghentian kontrak, null all."
            ),
        },
        "start": {
            "type": "integer",
            "description": "Pagination offset (default 0).",
            "default": 0,
        },
        "length": {
            "type": "integer",
            "description": (
                "Number of results to return (default 20, maximum 100)."
            ),
            "default": DEFAULT_SEARCH_LENGTH,
            "maximum": MAX_SEARCH_LENGTH,
        },
    },
    "required": ["lpse_host"],
}

MASTER_KLPD_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "Filter by KLPD name or kd_klpd.",
        },
        "kd_klpd": {
            "type": "string",
            "description": "Exact KLPD code, e.g. K66.",
        },
        "jenis_klpd": {
            "type": "string",
            "description": "Exact KLPD type, e.g. KEMENTERIAN.",
        },
        "limit": {
            "type": "integer",
            "description": "Maximum rows to return.",
            "default": 50,
            "minimum": 1,
            "maximum": 500,
        },
    },
}

DETAIL_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "lpse_host": {
            "type": "string",
            "description": (
                "LPSE host identifier. Examples: agency hosts like "
                "'kemenkeu', 'jakarta', 'sumbarprov', or the nationwide "
                "host 'nasional'."
            ),
        },
        "package_id": {
            "type": "string",
            "description": "Numeric package ID (e.g., '10080116000').",
        },
    },
    "required": ["lpse_host", "package_id"],
}

BULK_DETAIL_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "lpse_host": {
            "type": "string",
            "description": (
                "LPSE host identifier. Examples: agency hosts like "
                "'kemenkeu', 'jakarta', 'sumbarprov', or the nationwide "
                "host 'nasional'."
            ),
        },
        "package_ids": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Numeric package IDs to fetch in one call. Maximum "
                f"{MAX_BULK_DETAIL_PACKAGE_IDS} values."
            ),
            "minItems": 1,
            "maxItems": MAX_BULK_DETAIL_PACKAGE_IDS,
        },
        "continue_on_error": {
            "type": "boolean",
            "description": (
                "If true, continue fetching remaining package IDs after one "
                "package fails."
            ),
            "default": True,
        },
    },
    "required": ["lpse_host", "package_ids"],
}

VALIDATE_HOST_SCHEMA = {
    "type": "object",
    "properties": {
        "lpse_host": {
            "type": "string",
            "description": "LPSE host identifier to validate.",
        },
    },
    "required": ["lpse_host"],
}

CATEGORIES_SCHEMA = {
    "type": "object",
    "properties": {},
}

SEARCH_OPTIONS_SCHEMA = {
    "type": "object",
    "properties": {},
}

HOST_SEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": (
                "Free-text LPSE/institution name or procurement executor "
                "scope to resolve into an LPSE host slug. There are two "
                "executor scopes: agency-specific hosts such as 'kemenkeu', "
                "'pemprov dki', 'pu', and the nationwide host 'nasional'. "
                "If the user asks for national, nationwide, all Indonesia, "
                "or pencatatan nasional data, use lpse_host='nasional'."
            ),
        },
        "limit": {
            "type": "integer",
            "description": "Maximum number of host candidates to return.",
            "default": DEFAULT_HOST_SEARCH_LIMIT,
            "minimum": 1,
            "maximum": MAX_HOST_SEARCH_LIMIT,
        },
        "refresh": {
            "type": "boolean",
            "description": (
                "Bypass the in-memory host cache and refresh the known host "
                "list from the maintained Gist metadata."
            ),
            "default": False,
        },
    },
    "required": ["query"],
}

HOST_DETAIL_SCHEMA = {
    "type": "object",
    "properties": {
        "lpse_host": {
            "type": "string",
            "description": (
                "LPSE host slug returned by search_lpse_hosts, e.g. "
                "'kemenkeu' for an agency host or 'nasional' for nationwide data."
            ),
        },
        "refresh": {
            "type": "boolean",
            "description": (
                "Bypass the in-memory host cache and refresh the known host "
                "list from the maintained Gist metadata."
            ),
            "default": False,
        },
    },
    "required": ["lpse_host"],
}

CREATE_SEARCH_INDEX_SCHEMA = {
    "type": "object",
    "properties": {
        "lpse_host": {
            "type": "string",
            "description": "LPSE host slug, e.g. 'kemenkeu' or 'nasional'.",
        },
        "package_type": {
            "type": "string",
            "enum": sorted(VALID_PACKAGE_TYPES),
            "description": "Package type to index.",
            "default": "tender",
        },
        "tahun_anggaran": {
            "type": "integer",
            "description": "Budget year to index. Strongly recommended.",
        },
        "kategori": {
            "type": "string",
            "enum": sorted(VALID_CATEGORIES),
            "description": "Optional procurement category filter.",
        },
        "keyword_seed": {
            "type": "string",
            "description": (
                "Optional SPSE keyword used to bound which packages are "
                "downloaded before local full-text indexing."
            ),
        },
        "max_packages": {
            "type": "integer",
            "description": (
                "Maximum packages to download and index. 0 = all available. "
                f"Default {DEFAULT_INDEX_MAX_PACKAGES}."
            ),
            "default": DEFAULT_INDEX_MAX_PACKAGES,
        },
        "confirm_download": {
            "type": "boolean",
            "description": (
                "Must be true. Confirms user consent to download package details "
                "into a local disposable full-text index. May involve many "
                "SPSE requests when max_packages is 0 or large."
            ),
        },
    },
    "required": ["lpse_host", "confirm_download"],
}

SEARCH_INDEX_SCHEMA = {
    "type": "object",
    "properties": {
        "index_id": {
            "type": "string",
            "description": "Local index ID returned by create_procurement_search_index.",
        },
        "query": {
            "type": "string",
            "description": "SQLite FTS query to run against indexed package details.",
        },
        "limit": {
            "type": "integer",
            "description": "Maximum local matches to return.",
            "default": DEFAULT_INDEX_SEARCH_LIMIT,
            "maximum": MAX_INDEX_SEARCH_LIMIT,
        },
    },
    "required": ["index_id", "query"],
}

LIST_SEARCH_INDEXES_SCHEMA = {
    "type": "object",
    "properties": {},
}

DELETE_SEARCH_INDEX_SCHEMA = {
    "type": "object",
    "properties": {
        "index_id": {
            "type": "string",
            "description": "Local index ID to delete.",
        },
    },
    "required": ["index_id"],
}
