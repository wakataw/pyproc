"""Local SQLite FTS indexes for MCP procurement search."""

from __future__ import annotations

import json
import logging
import os
import shutil
import sqlite3
import time
from pathlib import Path
from uuid import uuid4

from pyproc import Lpse, JenisPengadaan
import pyproc.mcp.server as mcp_server_cfg  # for mutable SSL_VERIFY
from pyproc.mcp.parallel import (
    ThreadSafeRateLimiter,
    create_worker_lpse_pool,
    fetch_details_parallel,
)

logger = logging.getLogger(__name__)

CHUNK_SIZE = 100

PACKAGE_METHODS = {
    "tender": ("get_paket_tender", "detil_paket_tender"),
    "non_tender": ("get_paket_non_tender", "detil_paket_non_tender"),
    "pencatatan_non_tender": (
        "get_paket_pencatatan_non_tender",
        "detil_paket_pencatatan_non_tender",
    ),
    "swakelola": ("get_paket_swakelola", "detil_paket_swakelola"),
    "darurat": ("get_paket_pengadaan_darurat", "detil_paket_pengadaan_darurat"),
}

INDEX_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS packages (
    id_paket TEXT PRIMARY KEY,
    title TEXT,
    lpse_host TEXT,
    package_type TEXT,
    detail_json TEXT
);

CREATE VIRTUAL TABLE IF NOT EXISTS packages_fts
USING fts5(id_paket UNINDEXED, title, body);
"""


def get_index_root() -> Path:
    """Return the local directory used for disposable MCP search indexes."""
    configured = os.environ.get("PYPROC_MCP_INDEX_DIR")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".cache" / "pyproc" / "mcp-indexes"


def _index_path(index_id: str) -> Path:
    return get_index_root() / index_id / "index.sqlite"


def _safe_index_id(index_id: str) -> str:
    if not index_id or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-" for ch in index_id):
        raise ValueError("Invalid index_id")
    return index_id


def _package_title(row: list | tuple) -> str:
    try:
        return str(row[1])
    except (IndexError, TypeError):
        return ""


def _package_id(row: list | tuple) -> str:
    try:
        return str(row[0])
    except (IndexError, TypeError):
        return ""


def _detail_text(detail: dict) -> str:
    return json.dumps(detail, ensure_ascii=False, sort_keys=True, default=str)


def _init_db(path: Path, metadata: dict) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path))
    db.executescript(INDEX_SCHEMA_SQL)
    for key, value in metadata.items():
        db.execute(
            "INSERT OR REPLACE INTO metadata(key, value) VALUES(?, ?)",
            (key, json.dumps(value, ensure_ascii=False, default=str)),
        )
    db.commit()
    return db


def _create_worker_lpse_pool(host, count, timeout, verify):
    """Thin wrapper that re-exports ``parallel.create_worker_lpse_pool``."""
    return create_worker_lpse_pool(host, count, timeout, verify)


def _make_rate_limiter(rate_limit_callback):
    """Create a ``ThreadSafeRateLimiter`` from the legacy callback's delay.

    If *rate_limit_callback* is the MCP ``_rate_limit`` function, the
    effective delay is ``RATE_LIMIT_DELAY`` (imported from server config).
    """
    from pyproc.mcp.server import RATE_LIMIT_DELAY
    return ThreadSafeRateLimiter(min_delay=RATE_LIMIT_DELAY)


def _batch_position(pid, batch_items):
    """Return the 0-based index of *pid* in *batch_items*."""
    for i, (item_pid, _title) in enumerate(batch_items):
        if item_pid == pid:
            return i
    return 0


def _batch_title(pid, batch_items):
    """Return the title for *pid* from *batch_items*."""
    for item_pid, title in batch_items:
        if item_pid == pid:
            return title
    return str(pid)


def create_procurement_search_index(
    lpse_host: str,
    package_type: str = "tender",
    tahun_anggaran: int | None = None,
    kategori: str | None = None,
    keyword_seed: str | None = None,
    max_packages: int = 0,
    timeout: int = 30,
    rate_limit_callback=None,
    progress_callback=None,
) -> dict:
    """Download a bounded package set and index details into local SQLite FTS.

    Args:
        progress_callback: Optional callable(step, current, total, message)
            called at progress milestones.  step is one of 'scroll',
            'index_start', 'index_package', 'complete'.
    """
    index_id = f"{lpse_host}-{package_type}-{int(time.time())}-{uuid4().hex[:8]}"
    path = _index_path(index_id)
    metadata = {
        "index_id": index_id,
        "lpse_host": lpse_host,
        "package_type": package_type,
        "tahun_anggaran": tahun_anggaran,
        "kategori": kategori,
        "keyword_seed": keyword_seed,
        "max_packages": max_packages,
        "created_at": int(time.time()),
    }
    db = _init_db(path, metadata)

    indexed = 0
    failed = 0
    kategori_enum = JenisPengadaan[kategori] if kategori else None

    try:
        with Lpse(lpse_host, timeout=timeout, verify=mcp_server_cfg.SSL_VERIFY) as lpse:
            if rate_limit_callback:
                rate_limit_callback()
            search_method = getattr(lpse, PACKAGE_METHODS[package_type][0])
            base_kwargs = {
                "data_only": True,
                "search_keyword": keyword_seed,
                "tahun": tahun_anggaran,
            }
            if package_type != "swakelola":
                base_kwargs["kategori"] = kategori_enum

            # Paginate: scroll until max_packages reached or SPSE exhausted
            all_rows = []
            start = 0
            unlimited = max_packages <= 0
            limit = max_packages if not unlimited else float('inf')

            while len(all_rows) < limit:
                if unlimited:
                    req_length = CHUNK_SIZE
                else:
                    req_length = min(CHUNK_SIZE, max(1, max_packages - len(all_rows)))
                chunk_kwargs = {**base_kwargs, "start": start, "length": req_length}
                chunk = search_method(**chunk_kwargs)
                if not chunk:
                    break
                all_rows.extend(chunk)
                logger.info(
                    "Scrolled: %d rows from %s (TA %s)",
                    len(all_rows), lpse_host, tahun_anggaran,
                )
                if progress_callback:
                    progress_callback(
                        "scroll", len(all_rows), None,
                        f"Scrolled {len(all_rows)} packages from {lpse_host}",
                    )
                start += len(chunk)
                if len(chunk) < req_length:
                    break  # partial page -> end of data

            # Respect max_packages cap (only matters if SPSE returned more than requested)
            to_process = len(all_rows) if unlimited else min(len(all_rows), max_packages)
            logger.info(
                "Will index %d packages from %s (%s, %s)",
                to_process, lpse_host, package_type, tahun_anggaran,
            )
            if progress_callback:
                progress_callback(
                    "index_start", 0, to_process,
                    f"Indexing {to_process} packages from {lpse_host}",
                )

        # ── Detail / index phase (parallel batches) ──────────────────────────
        # The scroll Lpse is released; create a fresh pool of workers, each
        # with its own session and browser footprint so the server sees
        # concurrent requests as distinct clients.
        BATCH_SIZE = 16
        from pyproc.mcp.server import MCP_WORKERS
        workers = min(MCP_WORKERS, BATCH_SIZE)
        lpse_pool = _create_worker_lpse_pool(
            lpse_host, workers, timeout, mcp_server_cfg.SSL_VERIFY,
        )
        rate_limiter = _make_rate_limiter(rate_limit_callback)

        detail_method_name = PACKAGE_METHODS[package_type][1]

        for batch_start in range(0, to_process, BATCH_SIZE):
            batch_end = min(batch_start + BATCH_SIZE, to_process)
            batch = all_rows[batch_start:batch_end]
            # Build (id_paket, title) pairs, skipping rows without an ID
            batch_items = []
            for row in batch:
                pid = _package_id(row)
                if pid:
                    batch_items.append((pid, _package_title(row)))

            if not batch_items:
                continue

            pids = [item[0] for item in batch_items]
            results = fetch_details_parallel(
                package_ids=pids,
                lpse_pool=lpse_pool,
                detail_method_name=detail_method_name,
                rate_limiter=rate_limiter,
                continue_on_error=True,
            )

            # Write batch results to SQLite (single-threaded, safe)
            for result in results:
                pid = result["package_id"]
                batch_idx = batch_start + _batch_position(pid, batch_items) + 1
                if result.get("success") and "detail" in result:
                    detail_dict = result["detail"]
                    detail_dict["_index_errors"] = result.get("error_messages", [])
                    body = _detail_text(detail_dict)
                    title = _batch_title(pid, batch_items)
                    db.execute(
                        "INSERT OR REPLACE INTO packages VALUES(?, ?, ?, ?, ?)",
                        (pid, title, lpse_host, package_type, body),
                    )
                    db.execute(
                        "INSERT INTO packages_fts(id_paket, title, body) VALUES(?, ?, ?)",
                        (pid, title, body),
                    )
                    indexed += 1
                else:
                    failed += 1
                    title = _batch_title(pid, batch_items)
                    logger.warning(
                        "Failed to index package %s (%s)", pid, title,
                    )

            # Report progress at batch granularity
            if progress_callback:
                progress_callback(
                    "index_package", batch_end, to_process,
                    f"Indexed batch up to {batch_end}/{to_process}",
                )
            db.commit()  # commit each batch for durability

        # Clean up worker sessions
        for lpse in lpse_pool:
            lpse.session.close()
    finally:
        db.commit()
        db.close()

    logger.info(
        "Index complete: %d indexed, %d failed from %s (%s, %s)",
        indexed, failed, lpse_host, package_type, tahun_anggaran,
    )
    if progress_callback:
        progress_callback(
            "complete", indexed + failed, indexed + failed,
            f"Index complete: {indexed} indexed, {failed} failed",
        )

    return {
        **metadata,
        "path": str(path),
        "indexed_packages": indexed,
        "failed_packages": failed,
        "usage_hint": (
            "Use search_procurement_index with this index_id for local "
            "full-text search. Delete the index when it is no longer needed."
        ),
    }


def search_procurement_index(index_id: str, query: str, limit: int = 20) -> dict:
    """Search an existing local SQLite FTS index."""
    index_id = _safe_index_id(index_id)
    path = _index_path(index_id)
    if not path.exists():
        raise ValueError(f"Search index '{index_id}' was not found")

    db = sqlite3.connect(str(path))
    db.row_factory = sqlite3.Row
    try:
        rows = db.execute(
            """
            SELECT id_paket, title,
                   snippet(packages_fts, 2, '[', ']', '...', 20) AS snippet,
                   bm25(packages_fts) AS rank
            FROM packages_fts
            WHERE packages_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (query, limit),
        ).fetchall()
    except sqlite3.OperationalError as exc:
        raise ValueError(f"Invalid full-text query: {exc}") from exc
    finally:
        db.close()

    matches = [
        {
            "id_paket": row["id_paket"],
            "title": row["title"],
            "snippet": row["snippet"],
            "rank": row["rank"],
        }
        for row in rows
    ]
    return {
        "index_id": index_id,
        "query": query,
        "count": len(matches),
        "matches": matches,
    }


def list_procurement_indexes() -> dict:
    """List local MCP search indexes."""
    root = get_index_root()
    indexes = []
    if root.exists():
        for path in sorted(root.glob("*/index.sqlite")):
            db = sqlite3.connect(str(path))
            try:
                metadata_rows = db.execute("SELECT key, value FROM metadata").fetchall()
            finally:
                db.close()
            metadata = {}
            for key, value in metadata_rows:
                try:
                    metadata[key] = json.loads(value)
                except json.JSONDecodeError:
                    metadata[key] = value
            metadata["path"] = str(path)
            indexes.append(metadata)
    return {"count": len(indexes), "indexes": indexes}


def delete_procurement_index(index_id: str) -> dict:
    """Delete a local MCP search index."""
    index_id = _safe_index_id(index_id)
    index_dir = get_index_root() / index_id
    existed = index_dir.exists()
    if existed:
        shutil.rmtree(index_dir)
    return {
        "index_id": index_id,
        "deleted": existed,
    }


def _load_index_metadata(index_path: Path) -> dict | None:
    """Load metadata from an index.sqlite file. Returns None on error."""
    try:
        db = sqlite3.connect(str(index_path))
        try:
            metadata_rows = db.execute("SELECT key, value FROM metadata").fetchall()
        finally:
            db.close()
        metadata = {}
        for key, value in metadata_rows:
            try:
                metadata[key] = json.loads(value)
            except json.JSONDecodeError:
                metadata[key] = value
        return metadata
    except Exception:
        return None


def find_existing_isb_index(kd_lpse: int, tahun_anggaran: int) -> dict | None:
    """Find an existing ISB index matching the given parameters.

    Returns:
        Metadata dict with index_id, record count, and path if found,
        None otherwise.
    """
    root = get_index_root()
    if not root.exists():
        return None

    for path in sorted(root.glob("*/index.sqlite")):
        metadata = _load_index_metadata(path)
        if not metadata:
            continue
        if (
            metadata.get("source") == "isb_satudata"
            and metadata.get("kd_lpse") == kd_lpse
            and metadata.get("tahun_anggaran") == tahun_anggaran
        ):
            metadata["path"] = str(path)
            return metadata
    return None


def find_existing_spse_index(
    lpse_host: str,
    package_type: str = "tender",
    tahun_anggaran: int | None = None,
    kategori: str | None = None,
    keyword_seed: str | None = None,
) -> dict | None:
    """Find an existing SPSE index matching the given parameters.

    Returns:
        Metadata dict with index_id and path if found, None otherwise.
    """
    root = get_index_root()
    if not root.exists():
        return None

    for path in sorted(root.glob("*/index.sqlite")):
        metadata = _load_index_metadata(path)
        if not metadata:
            continue
        if (
            metadata.get("source") != "isb_satudata"
            and metadata.get("lpse_host") == lpse_host
            and metadata.get("package_type") == package_type
            and metadata.get("tahun_anggaran") == tahun_anggaran
            and metadata.get("kategori") == kategori
            and metadata.get("keyword_seed") == keyword_seed
        ):
            metadata["path"] = str(path)
            return metadata
    return None


# ── ISB Satu Data lightweight indexes ─────────────────────────────────────

ISB_INDEX_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS isb_tenders (
    kode_tender TEXT PRIMARY KEY,
    nama_paket TEXT,
    raw_json TEXT
);

CREATE VIRTUAL TABLE IF NOT EXISTS isb_tenders_fts
USING fts5(kode_tender UNINDEXED, nama_paket, body);
"""


def _isb_init_db(path: Path, metadata: dict) -> sqlite3.Connection:
    """Create an ISB index SQLite database."""
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path))
    db.executescript(ISB_INDEX_SCHEMA_SQL)
    for key, value in metadata.items():
        db.execute(
            "INSERT OR REPLACE INTO metadata(key, value) VALUES(?, ?)",
            (key, json.dumps(value, ensure_ascii=False, default=str)),
        )
    db.commit()
    return db


def _extract_isb_fields(record: dict) -> tuple[str, str]:
    """Extract kode_tender and nama_paket from an ISB record dict.

    ISB field names may contain spaces (e.g., 'Kode Tender', 'Nama Paket').
    """
    kode = str(
        record.get("Kode Tender")
        or record.get("kode_tender")
        or record.get("kode tender")
        or ""
    ).strip()
    nama = str(
        record.get("Nama Paket")
        or record.get("nama_paket")
        or record.get("nama paket")
        or ""
    ).strip()
    return kode, nama


def create_isb_data_index(
    data: list[dict],
    kd_lpse: int,
    tahun_anggaran: int,
) -> dict:
    """Create a lightweight SQLite FTS index from ISB Satu Data records.

    This is a fast, single-pass index — no additional HTTP requests.
    The data list is indexed directly into SQLite FTS.

    Args:
        data: List of tender record dicts from ISB Satu Data API.
        kd_lpse: LPSE code.
        tahun_anggaran: Budget year.

    Returns:
        Dict with index_id, record count, and usage hint.
    """
    index_id = f"isb-{kd_lpse}-{tahun_anggaran}-{uuid4().hex[:8]}"
    path = _index_path(index_id)
    metadata = {
        "index_id": index_id,
        "source": "isb_satudata",
        "kd_lpse": kd_lpse,
        "tahun_anggaran": tahun_anggaran,
        "created_at": int(time.time()),
    }
    db = _isb_init_db(path, metadata)

    indexed = 0
    for record in data:
        kode, nama = _extract_isb_fields(record)
        if not kode:
            continue
        body = json.dumps(record, ensure_ascii=False, sort_keys=True, default=str)
        db.execute(
            "INSERT OR REPLACE INTO isb_tenders VALUES(?, ?, ?)",
            (kode, nama, body),
        )
        db.execute(
            "INSERT INTO isb_tenders_fts(kode_tender, nama_paket, body) VALUES(?, ?, ?)",
            (kode, nama, body),
        )
        indexed += 1

    db.commit()
    db.close()

    logger.info("ISB index created: %s (%d records)", index_id, indexed)

    return {
        **metadata,
        "path": str(path),
        "indexed_records": indexed,
        "usage_hint": (
            f"Use search_isb_index with index_id='{index_id}' to query. "
            "Delete when no longer needed."
        ),
    }


def search_isb_index(
    index_id: str, query: str, limit: int = 20,
) -> dict:
    """Search a local ISB Satu Data SQLite FTS index.

    Args:
        index_id: Index ID returned by create_isb_data_index.
        query: FTS5 search query.
        limit: Maximum matches to return.

    Returns:
        Dict with matches and metadata.
    """
    index_id = _safe_index_id(index_id)
    path = _index_path(index_id)
    if not path.exists():
        raise ValueError(f"ISB index '{index_id}' was not found")

    db = sqlite3.connect(str(path))
    db.row_factory = sqlite3.Row
    try:
        rows = db.execute(
            """
            SELECT kode_tender, nama_paket,
                   snippet(isb_tenders_fts, 2, '[', ']', '...', 20) AS snippet,
                   bm25(isb_tenders_fts) AS rank
            FROM isb_tenders_fts
            WHERE isb_tenders_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (query, limit),
        ).fetchall()
    except sqlite3.OperationalError as exc:
        raise ValueError(f"Invalid full-text query: {exc}") from exc
    finally:
        db.close()

    matches = [
        {
            "kode_tender": row["kode_tender"],
            "nama_paket": row["nama_paket"],
            "snippet": row["snippet"],
            "rank": row["rank"],
        }
        for row in rows
    ]
    return {
        "index_id": index_id,
        "query": query,
        "count": len(matches),
        "matches": matches,
    }


def cleanup_isb_temp_files(max_age_seconds: int = 3600) -> int:
    """Delete orphaned ISB temp files older than max_age_seconds.

    Returns the number of files deleted.
    """
    data_dir = Path.home() / ".cache" / "pyproc" / "api-data"
    if not data_dir.exists():
        return 0

    now = time.time()
    deleted = 0
    for f in data_dir.glob(".isb_temp_*.json"):
        try:
            if now - f.stat().st_mtime > max_age_seconds:
                f.unlink()
                deleted += 1
        except OSError:
            pass
    return deleted


def get_data_dir() -> Path:
    """Return the API data output directory (same as tools._get_api_data_dir)."""
    configured = os.environ.get("PYPROC_MCP_DATA_DIR")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".cache" / "pyproc" / "api-data"


def cleanup_all_data() -> dict:
    """Delete all local MCP indexes and downloaded data files.

    Removes:
    - All index directories under the index root (SPSE + ISB indexes)
    - All files under the API data directory (JSON exports + temp files)

    Returns:
        Summary dict with counts of deleted items.
    """
    # ── Delete all indexes ────────────────────────────────────────────
    index_root = get_index_root()
    indexes_deleted = 0
    if index_root.exists():
        for entry in sorted(index_root.iterdir()):
            if entry.is_dir():
                try:
                    shutil.rmtree(entry)
                    indexes_deleted += 1
                except OSError:
                    pass

    # ── Delete all data files ─────────────────────────────────────────
    data_dir = get_data_dir()
    files_deleted = 0
    if data_dir.exists():
        for entry in sorted(data_dir.iterdir()):
            if entry.is_file():
                try:
                    entry.unlink()
                    files_deleted += 1
                except OSError:
                    pass

    logger.info(
        "Cleanup complete: %d indexes, %d data files deleted",
        indexes_deleted, files_deleted,
    )

    return {
        "indexes_deleted": indexes_deleted,
        "files_deleted": files_deleted,
        "index_dir": str(index_root),
        "data_dir": str(data_dir),
    }
