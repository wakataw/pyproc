"""Tests for pyproc.cache.CacheStore."""
import json
import tempfile
import unittest
from pathlib import Path

from pyproc.cache import CacheStore


class TestCacheStore(unittest.TestCase):

    def _make_store(self):
        f = tempfile.NamedTemporaryFile(suffix='.idx', delete=False)
        f.close()
        return Path(f.name)

    def test_create_schema(self):
        db_path = self._make_store()
        try:
            with CacheStore(db_path) as store:
                store.create_schema()
                # Verify table exists
                result = store.db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='INDEX_PAKET'"
                ).fetchone()
                self.assertIsNotNone(result)

                # Verify indexes
                indexes = store.db.execute(
                    "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='INDEX_PAKET'"
                ).fetchall()
                index_names = [i[0] for i in indexes]
                self.assertIn('INDEX_PAKET_KATEGORI_TAHUN_ANGGARAN_IDX', index_names)
                self.assertIn('INDEX_PAKET_STATUS_IDX', index_names)
        finally:
            db_path.unlink(missing_ok=True)

    def test_drop_schema(self):
        db_path = self._make_store()
        try:
            with CacheStore(db_path) as store:
                store.create_schema()
                store.drop_schema()
                result = store.db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='INDEX_PAKET'"
                ).fetchone()
                self.assertIsNone(result)
        finally:
            db_path.unlink(missing_ok=True)

    def test_reset(self):
        db_path = self._make_store()
        try:
            with CacheStore(db_path) as store:
                store.create_schema()
                store.insert_rows([('tender-1', '1', 'tender', '2025', 0, None)])
                self.assertTrue(store.has_rows())

                store.reset()
                self.assertFalse(store.has_rows())
        finally:
            db_path.unlink(missing_ok=True)

    def test_has_rows_empty(self):
        db_path = self._make_store()
        try:
            with CacheStore(db_path) as store:
                store.create_schema()
                self.assertFalse(store.has_rows())
        finally:
            db_path.unlink(missing_ok=True)

    def test_has_rows_with_data(self):
        db_path = self._make_store()
        try:
            with CacheStore(db_path) as store:
                store.create_schema()
                store.insert_rows([('tender-1', '1', 'tender', '2025', 0, None)])
                self.assertTrue(store.has_rows())
        finally:
            db_path.unlink(missing_ok=True)

    def test_insert_and_get_pending(self):
        db_path = self._make_store()
        try:
            with CacheStore(db_path) as store:
                store.create_schema()
                store.insert_rows([
                    ('tender-1', '1', 'tender', '2025', 0, None),
                    ('tender-2', '2', 'tender', '2025', 0, None),
                    ('tender-3', '3', 'tender', '2025', 1, '{}'),
                ])

                pending = list(store.get_pending())
                self.assertEqual(len(pending), 2)
                ids = [r['id_paket'] for r in pending]
                self.assertIn('1', ids)
                self.assertIn('2', ids)
                self.assertNotIn('3', ids)
        finally:
            db_path.unlink(missing_ok=True)

    def test_insert_or_ignore(self):
        db_path = self._make_store()
        try:
            with CacheStore(db_path) as store:
                store.create_schema()
                store.insert_rows([('tender-1', '1', 'tender', '2025', 0, None)])
                store.insert_rows([('tender-1', '1', 'tender', '2025', 0, None)])

                count = store.db.execute("SELECT COUNT(1) FROM INDEX_PAKET").fetchone()[0]
                self.assertEqual(count, 1)
        finally:
            db_path.unlink(missing_ok=True)

    def test_update_detail(self):
        db_path = self._make_store()
        try:
            with CacheStore(db_path) as store:
                store.create_schema()
                store.insert_rows([('tender-1', '1', 'tender', '2025', 0, None)])

                store.update_detail('tender-1', '{"pengumuman": {"kode": "123"}}')

                completed = list(store.get_completed())
                self.assertEqual(len(completed), 1)
                self.assertEqual(completed[0]['status'], 1)
                self.assertIn('pengumuman', json.loads(completed[0]['detail']))
        finally:
            db_path.unlink(missing_ok=True)

    def test_get_completed(self):
        db_path = self._make_store()
        try:
            with CacheStore(db_path) as store:
                store.create_schema()
                store.insert_rows([
                    ('tender-1', '1', 'tender', '2025', 1, '{"a": 1}'),
                    ('tender-2', '2', 'tender', '2025', 0, None),
                ])

                completed = list(store.get_completed())
                self.assertEqual(len(completed), 1)
                self.assertEqual(completed[0]['id_paket'], '1')
        finally:
            db_path.unlink(missing_ok=True)

    def test_count_by_status(self):
        db_path = self._make_store()
        try:
            with CacheStore(db_path) as store:
                store.create_schema()
                store.insert_rows([
                    ('tender-1', '1', 'tender', '2025', 0, None),
                    ('tender-2', '2', 'tender', '2025', 0, None),
                    ('tender-3', '3', 'tender', '2025', 1, '{}'),
                    ('tender-4', '4', 'tender', '2025', 1, '{}'),
                    ('tender-5', '5', 'tender', '2025', 1, '{}'),
                ])

                counts = store.count_by_status()
                self.assertEqual(counts[0], 2)
                self.assertEqual(counts[1], 3)
        finally:
            db_path.unlink(missing_ok=True)

    def test_context_manager_closes_connection(self):
        db_path = self._make_store()
        try:
            store = CacheStore(db_path)
            store.__enter__()
            store.create_schema()
            self.assertIsNotNone(store.db)
            store.__exit__(None, None, None)
            self.assertIsNone(store.db)
        finally:
            db_path.unlink(missing_ok=True)

    def test_close_idempotent(self):
        db_path = self._make_store()
        try:
            with CacheStore(db_path) as store:
                store.create_schema()
                store.close()
                store.close()  # Should not raise
        finally:
            db_path.unlink(missing_ok=True)

    def test_has_rows_no_table(self):
        """has_rows should return False when table doesn't exist."""
        db_path = self._make_store()
        try:
            with CacheStore(db_path) as store:
                # Don't create schema
                self.assertFalse(store.has_rows())
        finally:
            db_path.unlink(missing_ok=True)


if __name__ == '__main__':
    unittest.main()
