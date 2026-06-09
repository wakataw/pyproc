"""SQLite cache store for procurement index and detail data."""
import json
import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS INDEX_PAKET (
    ROW_ID varchar(100) unique primary key,
    ID_PAKET VARCHAR(50),
    JENIS_PAKET VARCHAR(32),
    KATEGORI_TAHUN_ANGGARAN varchar(100),
    STATUS int default 0,
    DETAIL text
);
"""

INDEXES_SQL = [
    "CREATE INDEX IF NOT EXISTS INDEX_PAKET_KATEGORI_TAHUN_ANGGARAN_IDX ON INDEX_PAKET(KATEGORI_TAHUN_ANGGARAN);",
    "CREATE INDEX IF NOT EXISTS INDEX_PAKET_ID_PAKET_IDX ON INDEX_PAKET(ID_PAKET);",
    "CREATE INDEX IF NOT EXISTS INDEX_PAKET_JENIS_PAKET ON INDEX_PAKET(JENIS_PAKET);",
    "CREATE INDEX IF NOT EXISTS INDEX_PAKET_STATUS_IDX ON INDEX_PAKET(STATUS);",
]

DROP_SQL = "DROP TABLE IF EXISTS INDEX_PAKET;"


class CacheStore:
    """Manages a SQLite database for procurement index and detail caching.

    Usage::

        with CacheStore(db_path) as store:
            store.create_schema()
            store.insert_rows(rows)
            for item in store.get_pending():
                ...
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db = None

    def __enter__(self):
        self.db = sqlite3.connect(str(self.db_path), check_same_thread=False)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def close(self):
        if self.db:
            self.db.close()
            self.db = None

    def create_schema(self):
        """Create the INDEX_PAKET table and indexes if they don't exist."""
        self.db.executescript(SCHEMA_SQL)
        for idx_sql in INDEXES_SQL:
            self.db.execute(idx_sql)
        self.db.commit()

    def drop_schema(self):
        """Drop the INDEX_PAKET table if it exists."""
        self.db.execute(DROP_SQL)
        self.db.commit()

    def reset(self):
        """Drop and recreate the schema (full reset)."""
        self.drop_schema()
        self.create_schema()

    def has_rows(self):
        """Return True if the INDEX_PAKET table has any rows."""
        try:
            total = self.db.execute("SELECT COUNT(1) FROM INDEX_PAKET").fetchone()[0]
            return total > 0
        except sqlite3.OperationalError:
            return False

    def insert_rows(self, rows):
        """Insert multiple rows using INSERT OR IGNORE for deduplication.

        Args:
            rows: iterable of tuples matching INDEX_PAKET columns
                  (ROW_ID, ID_PAKET, JENIS_PAKET, KATEGORI_TAHUN_ANGGARAN, STATUS, DETAIL)
        """
        self.db.executemany(
            "INSERT OR IGNORE INTO INDEX_PAKET VALUES(?, ?, ?, ?, ?, ?)",
            rows
        )
        self.db.commit()

    def get_pending(self):
        """Yield rows where STATUS=0 (pending detail download).

        Each row is returned as a dict with lowercase column names.
        """
        cursor = self.db.execute("SELECT * FROM INDEX_PAKET WHERE STATUS = 0")
        for row in cursor.fetchall():
            yield self._row_to_dict(cursor, row)

    def get_completed(self):
        """Yield rows where STATUS=1 (detail downloaded).

        Each row is returned as a dict with lowercase column names.
        """
        cursor = self.db.execute("SELECT * FROM INDEX_PAKET WHERE STATUS = 1")
        for row in cursor.fetchall():
            yield self._row_to_dict(cursor, row)

    def update_detail(self, row_id, detail_json):
        """Update a row's DETAIL and set STATUS=1.

        Args:
            row_id: the ROW_ID primary key
            detail_json: JSON string of the detail data
        """
        self.db.execute(
            "UPDATE INDEX_PAKET SET DETAIL = ?, STATUS = 1 WHERE ROW_ID = ?",
            (detail_json, row_id)
        )
        self.db.commit()

    def count_by_status(self):
        """Return a dict mapping status code to count.

        Returns:
            dict: {0: pending_count, 1: completed_count}
        """
        rows = self.db.execute(
            "SELECT STATUS, COUNT(1) FROM INDEX_PAKET GROUP BY STATUS"
        ).fetchall()
        return dict(rows)

    @staticmethod
    def _row_to_dict(cursor, row):
        """Convert a sqlite3 row to a dict with lowercase column names."""
        d = {}
        for idx, col in enumerate(cursor.description):
            d[col[0].lower()] = row[idx]
        return d
