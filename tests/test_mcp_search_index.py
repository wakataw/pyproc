"""Tests for pyproc.mcp.search_index — local SQLite FTS indexes."""

import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch


class TestSearchIndex(unittest.TestCase):

    def test_create_search_and_delete_index(self):
        from pyproc.mcp import search_index

        with tempfile.TemporaryDirectory() as tmpdir:
            mock_detail = MagicMock()
            mock_detail.get_all_detil.return_value = {"error": False, "error_message": []}
            mock_detail.todict.return_value = {
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
            mock_lpse.detil_paket_tender.return_value = mock_detail
            mock_lpse.__enter__ = MagicMock(return_value=mock_lpse)
            mock_lpse.__exit__ = MagicMock(return_value=False)

            with patch.dict(os.environ, {"PYPROC_MCP_INDEX_DIR": tmpdir}):
                with patch("pyproc.mcp.search_index.Lpse", return_value=mock_lpse):
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

    def _make_mock_lpse(self, chunks, detail=None):
        """Build a mock Lpse that returns paginated chunks from get_paket_tender."""
        if detail is None:
            detail = MagicMock()
            detail.get_all_detil.return_value = {"error": False, "error_message": []}
            detail.todict.return_value = {"id_paket": "100"}

        mock_lpse = MagicMock()
        mock_lpse.get_paket_tender.side_effect = list(chunks)
        mock_lpse.detil_paket_tender.return_value = detail
        mock_lpse.__enter__ = MagicMock(return_value=mock_lpse)
        mock_lpse.__exit__ = MagicMock(return_value=False)
        return mock_lpse

    def _make_row(self, pkg_id, title="Test Package"):
        return [str(pkg_id), title, "TEST INSTANSI"]

    def test_pagination_multiple_chunks(self):
        """All rows from multiple chunks are collected."""
        from pyproc.mcp import search_index

        chunk1 = [self._make_row(i) for i in range(1, 101)]   # 100 rows
        chunk2 = [self._make_row(i) for i in range(101, 201)]  # 100 rows
        chunk3 = [self._make_row(i) for i in range(201, 251)]  # 50 rows (partial)
        mock_lpse = self._make_mock_lpse([chunk1, chunk2, chunk3])

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"PYPROC_MCP_INDEX_DIR": tmpdir}):
                with patch("pyproc.mcp.search_index.Lpse", return_value=mock_lpse):
                    created = search_index.create_procurement_search_index(
                        lpse_host="kemenkeu",
                        max_packages=0,
                        timeout=1,
                    )

                self.assertEqual(created["indexed_packages"], 250)
                self.assertEqual(created["failed_packages"], 0)
                # Should have made exactly 3 requests
                self.assertEqual(mock_lpse.get_paket_tender.call_count, 3)

    def test_pagination_stops_on_empty(self):
        """Pagination stops when SPSE returns an empty chunk after a full page."""
        from pyproc.mcp import search_index

        chunk1 = [self._make_row(i) for i in range(1, 101)]  # 100 rows (full page)
        chunk2 = []  # empty -> stop
        mock_lpse = self._make_mock_lpse([chunk1, chunk2])

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"PYPROC_MCP_INDEX_DIR": tmpdir}):
                with patch("pyproc.mcp.search_index.Lpse", return_value=mock_lpse):
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

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"PYPROC_MCP_INDEX_DIR": tmpdir}):
                with patch("pyproc.mcp.search_index.Lpse", return_value=mock_lpse):
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

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"PYPROC_MCP_INDEX_DIR": tmpdir}):
                with patch("pyproc.mcp.search_index.Lpse", return_value=mock_lpse):
                    created = search_index.create_procurement_search_index(
                        lpse_host="kemenkeu",
                        max_packages=50,
                        timeout=1,
                    )

                self.assertEqual(created["indexed_packages"], 50)
                # Single request with length=50
                call_kwargs = mock_lpse.get_paket_tender.call_args[1]
                self.assertEqual(call_kwargs["length"], 50)


if __name__ == "__main__":
    unittest.main()
