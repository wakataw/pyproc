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


if __name__ == "__main__":
    unittest.main()
