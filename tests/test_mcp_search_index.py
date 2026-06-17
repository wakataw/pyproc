"""Tests for pyproc.mcp.search_index — local SQLite FTS indexes."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


class TestSearchIndex(unittest.TestCase):

    def test_create_search_and_delete_index(self):
        from pyproc.mcp import search_index

        with tempfile.TemporaryDirectory() as tmpdir:
            mock_detail = {
                "id_paket": "100",
                "pengumuman": {
                    "nama_tender": "Pengadaan Laptop",
                    "spesifikasi": "Laptop untuk pekerjaan kantor",
                },
            }

            mock_lpse = MagicMock()
            mock_lpse.get_paket_tender.return_value = [
                ["100", "Pengadaan Laptop", "KEMENTERIAN KEUANGAN"],
            ]
            mock_lpse.__enter__ = MagicMock(return_value=mock_lpse)
            mock_lpse.__exit__ = MagicMock(return_value=False)

            # fetch_details_parallel returns the detail phase results
            mock_pool = [MagicMock() for _ in range(4)]

            def _fetch_side_effect(package_ids, **kwargs):
                return [{
                    "package_id": pid,
                    "success": True,
                    "detail": mock_detail,
                } for pid in package_ids]

            with patch.dict(os.environ, {"PYPROC_MCP_INDEX_DIR": tmpdir}):
                with patch("pyproc.mcp.search_index.Lpse", return_value=mock_lpse), \
                     patch("pyproc.mcp.search_index.create_worker_lpse_pool", return_value=mock_pool), \
                     patch("pyproc.mcp.search_index.fetch_details_parallel",
                           side_effect=_fetch_side_effect):
                    created = search_index.create_procurement_search_index(
                        lpse_host="kemenkeu",
                        package_type="tender",
                        tahun_anggaran=2025,
                        keyword_seed="laptop",
                        max_packages=1,
                        timeout=1,
                    )

                self.assertEqual(created["indexed_packages"], 1)

                result = search_index.search_procurement_index(
                    created["index_id"],
                    "laptop",
                )
                self.assertEqual(result["count"], 1)
                self.assertEqual(result["matches"][0]["id_paket"], "100")

                listed = search_index.list_procurement_indexes()
                self.assertEqual(listed["count"], 1)

                deleted = search_index.delete_procurement_index(created["index_id"])
                self.assertTrue(deleted["deleted"])

    def test_search_missing_index(self):
        from pyproc.mcp import search_index

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"PYPROC_MCP_INDEX_DIR": tmpdir}):
                with self.assertRaises(ValueError):
                    search_index.search_procurement_index("missing", "laptop")

    def _make_mock_lpse(self, chunks):
        """Build a mock Lpse that returns paginated chunks from get_paket_tender.

        Detail fetching is now handled by ``fetch_details_parallel`` in the
        parallel module — this mock only covers the scroll/index phase.
        """
        mock_lpse = MagicMock()
        mock_lpse.get_paket_tender.side_effect = list(chunks)
        mock_lpse.__enter__ = MagicMock(return_value=mock_lpse)
        mock_lpse.__exit__ = MagicMock(return_value=False)
        return mock_lpse

    def _make_row(self, pkg_id, title="Test Package"):
        return [str(pkg_id), title, "TEST INSTANSI"]

    def _make_fetch_results(self, pkg_ids, success=True):
        """Build mock results from ``fetch_details_parallel``."""
        return [{
            "package_id": str(pid),
            "success": success,
            "detail": {"id_paket": str(pid)},
        } for pid in pkg_ids]

    def _mock_parallel_patches(self, success=True):
        """Return patches for the parallel detail fetch in search_index.

        Uses ``side_effect`` so each batch call returns results only for
        the package IDs actually passed to it.
        """
        pool = [MagicMock() for _ in range(4)]

        def _fetch_side_effect(package_ids, **kwargs):
            return [{
                "package_id": str(pid),
                "success": success,
                "detail": {"id_paket": str(pid)},
            } for pid in package_ids]

        return (
            patch("pyproc.mcp.search_index.create_worker_lpse_pool", return_value=pool),
            patch("pyproc.mcp.search_index.fetch_details_parallel",
                  side_effect=_fetch_side_effect),
        )

    def test_pagination_multiple_chunks(self):
        """All rows from multiple chunks are collected."""
        from pyproc.mcp import search_index

        chunk1 = [self._make_row(i) for i in range(1, 101)]   # 100 rows
        chunk2 = [self._make_row(i) for i in range(101, 201)]  # 100 rows
        chunk3 = [self._make_row(i) for i in range(201, 251)]  # 50 rows (partial)
        mock_lpse = self._make_mock_lpse([chunk1, chunk2, chunk3])

        p1, p2 = self._mock_parallel_patches()

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"PYPROC_MCP_INDEX_DIR": tmpdir}):
                with patch("pyproc.mcp.search_index.Lpse", return_value=mock_lpse), p1, p2:
                    created = search_index.create_procurement_search_index(
                        lpse_host="kemenkeu",
                        max_packages=0,
                        timeout=1,
                    )

                self.assertEqual(created["indexed_packages"], 250)
                self.assertEqual(created["failed_packages"], 0)
                # Should have made exactly 3 scroll requests
                self.assertEqual(mock_lpse.get_paket_tender.call_count, 3)

    def test_pagination_stops_on_empty(self):
        """Pagination stops when SPSE returns an empty chunk after a full page."""
        from pyproc.mcp import search_index

        chunk1 = [self._make_row(i) for i in range(1, 101)]  # 100 rows (full page)
        chunk2 = []  # empty -> stop
        mock_lpse = self._make_mock_lpse([chunk1, chunk2])

        p1, p2 = self._mock_parallel_patches()

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"PYPROC_MCP_INDEX_DIR": tmpdir}):
                with patch("pyproc.mcp.search_index.Lpse", return_value=mock_lpse), p1, p2:
                    created = search_index.create_procurement_search_index(
                        lpse_host="kemenkeu",
                        max_packages=0,
                        timeout=1,
                    )

                self.assertEqual(created["indexed_packages"], 100)
                self.assertEqual(mock_lpse.get_paket_tender.call_count, 2)

    def test_pagination_respects_max_packages(self):
        """max_packages > 0 caps total rows collected."""
        from pyproc.mcp import search_index

        chunk1 = [self._make_row(i) for i in range(1, 101)]  # 100 rows
        mock_lpse = self._make_mock_lpse([chunk1])

        p1, p2 = self._mock_parallel_patches()

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"PYPROC_MCP_INDEX_DIR": tmpdir}):
                with patch("pyproc.mcp.search_index.Lpse", return_value=mock_lpse), p1, p2:
                    created = search_index.create_procurement_search_index(
                        lpse_host="kemenkeu",
                        max_packages=30,
                        timeout=1,
                    )

                # Should only index 30 (limited by max_packages)
                self.assertEqual(created["indexed_packages"], 30)

    def test_pagination_small_max_packages_single_request(self):
        """max_packages <= CHUNK_SIZE makes a single request of that size."""
        from pyproc.mcp import search_index

        chunk = [self._make_row(i) for i in range(1, 51)]
        mock_lpse = self._make_mock_lpse([chunk])

        p1, p2 = self._mock_parallel_patches()

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"PYPROC_MCP_INDEX_DIR": tmpdir}):
                with patch("pyproc.mcp.search_index.Lpse", return_value=mock_lpse), p1, p2:
                    created = search_index.create_procurement_search_index(
                        lpse_host="kemenkeu",
                        max_packages=50,
                        timeout=1,
                    )

                self.assertEqual(created["indexed_packages"], 50)
                # Single request with length=50
                call_kwargs = mock_lpse.get_paket_tender.call_args[1]
                self.assertEqual(call_kwargs["length"], 50)


class TestIsbIndex(unittest.TestCase):

    def test_create_search_and_delete(self):
        from pyproc.mcp import search_index

        test_data = [
            {"Kode Tender": "100", "Nama Paket": "Pengadaan Laptop", "Pagu": 5000000000},
            {"Kode Tender": "101", "Nama Paket": "Pengadaan Notebook", "Pagu": 3000000000},
            {"Kode Tender": "102", "Nama Paket": "Jasa Konsultansi IT", "Pagu": 1000000000},
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"PYPROC_MCP_INDEX_DIR": tmpdir}):
                # Create
                created = search_index.create_isb_data_index(
                    data=test_data, kd_lpse=119, tahun_anggaran=2026,
                )
                self.assertEqual(created["indexed_records"], 3)
                self.assertIn("isb-119-2026-", created["index_id"])
                self.assertEqual(created["source"], "isb_satudata")

                # Search
                result = search_index.search_isb_index(
                    created["index_id"], "laptop",
                )
                self.assertEqual(result["count"], 1)
                self.assertEqual(result["matches"][0]["kode_tender"], "100")

                # Search broader
                result2 = search_index.search_isb_index(
                    created["index_id"], "pengadaan",
                )
                self.assertEqual(result2["count"], 2)

                # List (should include ISB index)
                listed = search_index.list_procurement_indexes()
                self.assertEqual(listed["count"], 1)

                # Delete
                deleted = search_index.delete_procurement_index(created["index_id"])
                self.assertTrue(deleted["deleted"])

                # Verify gone
                listed2 = search_index.list_procurement_indexes()
                self.assertEqual(listed2["count"], 0)

    def test_search_missing_index(self):
        from pyproc.mcp import search_index

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"PYPROC_MCP_INDEX_DIR": tmpdir}):
                with self.assertRaises(ValueError):
                    search_index.search_isb_index("nonexistent", "laptop")

    def test_create_empty_data(self):
        from pyproc.mcp import search_index

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"PYPROC_MCP_INDEX_DIR": tmpdir}):
                created = search_index.create_isb_data_index(
                    data=[], kd_lpse=999, tahun_anggaran=2026,
                )
                self.assertEqual(created["indexed_records"], 0)

    def test_create_with_malformed_records(self):
        from pyproc.mcp import search_index

        test_data = [
            {"Kode Tender": "100", "Nama Paket": "Valid Record"},
            {"some_field": "no kode_tender"},  # no kode_tender -> skipped
            {"Kode Tender": "", "Nama Paket": "Empty Kode"},  # empty kode -> skipped
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"PYPROC_MCP_INDEX_DIR": tmpdir}):
                created = search_index.create_isb_data_index(
                    data=test_data, kd_lpse=119, tahun_anggaran=2026,
                )
                # Only 1 valid record (the one with non-empty kode_tender)
                self.assertEqual(created["indexed_records"], 1)


class TestFindExistingIndex(unittest.TestCase):

    def test_find_existing_isb_index(self):
        from pyproc.mcp import search_index

        test_data = [
            {"Kode Tender": "100", "Nama Paket": "Test"},
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"PYPROC_MCP_INDEX_DIR": tmpdir}):
                created = search_index.create_isb_data_index(
                    data=test_data, kd_lpse=119, tahun_anggaran=2026,
                )

                found = search_index.find_existing_isb_index(
                    kd_lpse=119, tahun_anggaran=2026,
                )
                self.assertIsNotNone(found)
                self.assertEqual(found["index_id"], created["index_id"])
                self.assertEqual(found["source"], "isb_satudata")

                # Different params should not match
                not_found = search_index.find_existing_isb_index(
                    kd_lpse=999, tahun_anggaran=2026,
                )
                self.assertIsNone(not_found)

    def test_find_existing_spse_index(self):
        from pyproc.mcp import search_index

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"PYPROC_MCP_INDEX_DIR": tmpdir}):
                # Create a mock SPSE index by inserting metadata directly
                index_id = "kemenkeu-tender-9999-test1234"
                path = search_index.get_index_root() / index_id / "index.sqlite"
                db = search_index._isb_init_db(path, {
                    "index_id": index_id,
                    "lpse_host": "kemenkeu",
                    "package_type": "tender",
                    "tahun_anggaran": 2025,
                    "kategori": None,
                    "keyword_seed": "laptop",
                    "indexed_packages": 50,
                })
                db.close()

                found = search_index.find_existing_spse_index(
                    lpse_host="kemenkeu",
                    package_type="tender",
                    tahun_anggaran=2025,
                    kategori=None,
                    keyword_seed="laptop",
                )
                self.assertIsNotNone(found)
                self.assertEqual(found["index_id"], index_id)

                # Different host should not match
                not_found = search_index.find_existing_spse_index(
                    lpse_host="jakarta",
                    package_type="tender",
                    tahun_anggaran=2025,
                )
                self.assertIsNone(not_found)

    def test_find_existing_returns_none_when_empty(self):
        from pyproc.mcp import search_index

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"PYPROC_MCP_INDEX_DIR": tmpdir}):
                self.assertIsNone(
                    search_index.find_existing_isb_index(119, 2026)
                )
                self.assertIsNone(
                    search_index.find_existing_spse_index("kemenkeu")
                )


class TestCleanupAllData(unittest.TestCase):

    def test_cleanup_deletes_everything(self):
        from pyproc.mcp import search_index

        with tempfile.TemporaryDirectory() as index_tmpdir, \
             tempfile.TemporaryDirectory() as data_tmpdir:

            # Create some index dirs
            (Path(index_tmpdir) / "idx1").mkdir()
            (Path(index_tmpdir) / "idx1" / "index.sqlite").touch()
            (Path(index_tmpdir) / "idx2").mkdir()
            (Path(index_tmpdir) / "idx2" / "index.sqlite").touch()

            # Create some data files
            (Path(data_tmpdir) / "file1.json").touch()
            (Path(data_tmpdir) / ".isb_temp_file.json").touch()

            with patch.dict(os.environ, {
                "PYPROC_MCP_INDEX_DIR": index_tmpdir,
                "PYPROC_MCP_DATA_DIR": data_tmpdir,
            }):
                result = search_index.cleanup_all_data()

            self.assertEqual(result["indexes_deleted"], 2)
            self.assertEqual(result["files_deleted"], 2)
            # Directories should be empty
            self.assertEqual(len(list(Path(index_tmpdir).iterdir())), 0)
            self.assertEqual(len(list(Path(data_tmpdir).iterdir())), 0)

    def test_cleanup_empty_dirs(self):
        from pyproc.mcp import search_index

        with tempfile.TemporaryDirectory() as index_tmpdir, \
             tempfile.TemporaryDirectory() as data_tmpdir:
            with patch.dict(os.environ, {
                "PYPROC_MCP_INDEX_DIR": index_tmpdir,
                "PYPROC_MCP_DATA_DIR": data_tmpdir,
            }):
                result = search_index.cleanup_all_data()

            self.assertEqual(result["indexes_deleted"], 0)
            self.assertEqual(result["files_deleted"], 0)


if __name__ == "__main__":
    unittest.main()
