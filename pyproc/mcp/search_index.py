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
