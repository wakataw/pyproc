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


def create_procurement_search_index(
    lpse_host: str,
    package_type: str = "tender",
    tahun_anggaran: int | None = None,
    kategori: str | None = None,
    keyword_seed: str | None = None,
    max_packages: int = 0,
    timeout: int = 30,
    rate_limit_callback=None,
) -> dict:
    """Download a bounded package set and index details into local SQLite FTS."""
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
        with Lpse(lpse_host, timeout=timeout) as lpse:
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
                start += len(chunk)
                if len(chunk) < req_length:
                    break  # partial page -> end of data

            # Respect max_packages cap (only matters if SPSE returned more than requested)
            to_process = len(all_rows) if unlimited else min(len(all_rows), max_packages)
            logger.info(
                "Will index %d packages from %s (%s, %s)",
                to_process, lpse_host, package_type, tahun_anggaran,
            )

            for idx, row in enumerate(all_rows[:to_process], start=1):
                id_paket = _package_id(row)
                if not id_paket:
                    continue
                title = _package_title(row)
                logger.info("[%d/%d] Indexing: %s", idx, to_process, title)
                try:
                    if rate_limit_callback:
                        rate_limit_callback()
                    detail = getattr(lpse, PACKAGE_METHODS[package_type][1])(id_paket)
                    info = detail.get_all_detil()
                    detail_dict = detail.todict()
                    detail_dict["_index_errors"] = info.get("error_message", [])
                    body = _detail_text(detail_dict)
                    db.execute(
                        "INSERT OR REPLACE INTO packages VALUES(?, ?, ?, ?, ?)",
                        (id_paket, title, lpse_host, package_type, body),
                    )
                    db.execute(
                        "INSERT INTO packages_fts(id_paket, title, body) VALUES(?, ?, ?)",
                        (id_paket, title, body),
                    )
                    indexed += 1
                except Exception:
                    failed += 1
                    logger.warning(
                        "Failed to index package %s (%s)", id_paket, title,
                    )
                    continue
    finally:
        db.commit()
        db.close()

    logger.info(
        "Index complete: %d indexed, %d failed from %s (%s, %s)",
        indexed, failed, lpse_host, package_type, tahun_anggaran,
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
