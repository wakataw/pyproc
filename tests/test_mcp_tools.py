"""Tests for pyproc.mcp.tools — tool handlers with mocked Lpse."""
import asyncio
import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from mcp import types as mcp_types


def async_test(coro):
    """Decorator to run async test methods."""
    def wrapper(*args, **kwargs):
        return asyncio.run(coro(*args, **kwargs))
    return wrapper


class TestToolHelpers(unittest.TestCase):

    def test_make_json_response(self):
        from pyproc.mcp.tools import _make_json_response
        result = _make_json_response({"key": "value"})
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], mcp_types.TextContent)
        self.assertEqual(result[0].type, "text")
        parsed = json.loads(result[0].text)
        self.assertEqual(parsed["key"], "value")

    def test_rate_limit(self):
        from pyproc.mcp.tools import _rate_limit, _last_request_time
        import time
        # Reset last request time
        from pyproc.mcp import tools
        tools._last_request_time = 0.0
        start = time.monotonic()
        _rate_limit()
        elapsed = time.monotonic() - start
        # Should complete quickly since no prior request
        self.assertLess(elapsed, 0.1)

        # Second call should wait
        tools._last_request_time = time.monotonic()
        start = time.monotonic()
        _rate_limit()
        elapsed = time.monotonic() - start
        self.assertAlmostEqual(elapsed, 1.0, delta=0.2)

    def test_save_json_to_file(self):
        import tempfile
        from pyproc.mcp.tools import _save_json_to_file

        test_data = [{"id": i, "name": f"item_{i}"} for i in range(10)]

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('pyproc.mcp.tools._get_api_data_dir', return_value=Path(tmpdir)):
                summary = _save_json_to_file(
                    test_data, "test_prefix",
                    tool_name="test_tool",
                    extra_params={"tahun": 2026, "kd": 119},
                )

            self.assertEqual(summary["status"], "saved_to_file")
            self.assertEqual(summary["record_count"], 10)
            self.assertEqual(len(summary["preview"]), 3)
            self.assertIn("file_path", summary)
            self.assertIn("processing_hints", summary)
            self.assertIn("confirmation_hint", summary)
            self.assertIn("test_tool", summary["confirmation_hint"])
            self.assertIn("return_full_data", summary["confirmation_hint"])

            # Verify file was created and contains valid JSON
            file_path = Path(summary["file_path"])
            self.assertTrue(file_path.exists())
            with open(file_path) as f:
                loaded = json.load(f)
            self.assertEqual(len(loaded), 10)

    def test_save_json_to_file_empty_data(self):
        import tempfile
        from pyproc.mcp.tools import _save_json_to_file

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('pyproc.mcp.tools._get_api_data_dir', return_value=Path(tmpdir)):
                summary = _save_json_to_file([], "empty_test")

        self.assertEqual(summary["status"], "saved_to_file")
        self.assertEqual(summary["record_count"], 0)
        self.assertEqual(summary["preview"], [])


class TestHandleGetProcurementCategories(unittest.TestCase):

    @async_test
    async def test_returns_categories(self):
        from pyproc.mcp.tools import handle_get_procurement_categories
        result = await handle_get_procurement_categories(
            "get_procurement_categories", {}
        )
        self.assertIsInstance(result, list)
        data = json.loads(result[0].text)
        self.assertIn("categories", data)
        self.assertEqual(data["count"], 6)


class TestHandleGetProcurementSearchOptions(unittest.TestCase):

    @async_test
    async def test_returns_search_options(self):
        from pyproc.mcp.tools import handle_get_procurement_search_options
        result = await handle_get_procurement_search_options(
            "get_procurement_search_options", {}
        )
        data = json.loads(result[0].text)
        strategy_names = [item["name"] for item in data["strategies"]]
        self.assertIn("direct_keyword_search", strategy_names)
        self.assertIn("local_full_text_index", strategy_names)


class TestHandleLpseHostDiscovery(unittest.TestCase):

    @async_test
    async def test_search_lpse_hosts(self):
        from pyproc.mcp.tools import handle_search_lpse_hosts

        mock_result = {
            "query": "kementerian keuangan",
            "count": 1,
            "hosts": [
                {
                    "host": "kemenkeu",
                    "name": "Kementerian Keuangan",
                    "url": "https://spse.inaproc.id/kemenkeu",
                    "match_score": 1.0,
                }
            ],
        }

        with patch("pyproc.mcp.tools.search_lpse_hosts", return_value=mock_result):
            result = await handle_search_lpse_hosts(
                "search_lpse_hosts",
                {"query": "kementerian keuangan", "limit": 5},
            )

        data = json.loads(result[0].text)
        self.assertEqual(data["hosts"][0]["host"], "kemenkeu")
        self.assertEqual(data["query"], "kementerian keuangan")

    @async_test
    async def test_search_lpse_hosts_validation_error(self):
        from pyproc.mcp.tools import handle_search_lpse_hosts

        result = await handle_search_lpse_hosts("search_lpse_hosts", {})

        self.assertIn("Error", result[0].text)

    @async_test
    async def test_get_lpse_host_detail(self):
        from pyproc.mcp.tools import handle_get_lpse_host_detail

        mock_result = {
            "host": "kemenkeu",
            "name": "Kementerian Keuangan",
            "url": "https://spse.inaproc.id/kemenkeu",
        }

        with patch("pyproc.mcp.tools.get_lpse_host_detail", return_value=mock_result):
            result = await handle_get_lpse_host_detail(
                "get_lpse_host_detail",
                {"lpse_host": "kemenkeu"},
            )

        data = json.loads(result[0].text)
        self.assertEqual(data["host"], "kemenkeu")
        self.assertEqual(data["name"], "Kementerian Keuangan")


class TestHandleSearchTenderPackages(unittest.TestCase):

    @async_test
    async def test_search_mocked(self):
        from pyproc.mcp.tools import handle_search_tender_packages

        mock_lpse = MagicMock()
        mock_lpse.get_paket_tender.return_value = [
            ["10080116000", "Pengadaan Barang A", "KEMENKEU",
             "Tender Sudah Selesai", "Rp 950.000.000,00", "", "Barang", "", "2025"],
        ]
        mock_lpse.__enter__ = MagicMock(return_value=mock_lpse)
        mock_lpse.__exit__ = MagicMock(return_value=False)

        with patch('pyproc.mcp.tools.Lpse', return_value=mock_lpse):
            result = await handle_search_tender_packages(
                "search_tender_packages",
                {"lpse_host": "kemenkeu", "keyword": "barang", "length": "10"}
            )

        data = json.loads(result[0].text)
        self.assertEqual(data["lpse_host"], "kemenkeu")
        self.assertEqual(len(data["packages"]), 1)
        pkg = data["packages"][0]
        self.assertEqual(pkg["id_paket"], "10080116000")
        self.assertEqual(pkg["nama_paket"], "Pengadaan Barang A")
        self.assertEqual(pkg["hps"], 950000000.0)
        self.assertEqual(pkg["matched_keywords"], ["barang"])

    @async_test
    async def test_search_multiple_keywords_dedupes(self):
        from pyproc.mcp.tools import handle_search_tender_packages

        mock_lpse = MagicMock()
        mock_lpse.get_paket_tender.side_effect = [
            [
                ["100", "Pengadaan Laptop", "KEMENKEU", "Selesai",
                 "Rp 10.000.000,00", "", "Barang", "", "2025"],
            ],
            [
                ["100", "Pengadaan Laptop", "KEMENKEU", "Selesai",
                 "Rp 10.000.000,00", "", "Barang", "", "2025"],
                ["101", "Pengadaan Notebook", "KEMENKEU", "Selesai",
                 "Rp 20.000.000,00", "", "Barang", "", "2025"],
            ],
        ]
        mock_lpse.__enter__ = MagicMock(return_value=mock_lpse)
        mock_lpse.__exit__ = MagicMock(return_value=False)

        with patch('pyproc.mcp.tools.Lpse', return_value=mock_lpse):
            result = await handle_search_tender_packages(
                "search_tender_packages",
                {
                    "lpse_host": "kemenkeu",
                    "keywords": ["laptop", "notebook"],
                    "length": 10,
                }
            )

        data = json.loads(result[0].text)
        self.assertEqual(data["count"], 2)
        packages = {item["id_paket"]: item for item in data["packages"]}
        self.assertEqual(packages["100"]["matched_keywords"], ["laptop", "notebook"])
        self.assertEqual(packages["101"]["matched_keywords"], ["notebook"])
        self.assertEqual(mock_lpse.get_paket_tender.call_count, 2)

    @async_test
    async def test_search_multiple_keywords_all_mode(self):
        from pyproc.mcp.tools import handle_search_tender_packages

        mock_lpse = MagicMock()
        mock_lpse.get_paket_tender.side_effect = [
            [["100", "Pengadaan Laptop", "KEMENKEU"]],
            [["100", "Pengadaan Laptop", "KEMENKEU"], ["101", "Notebook", "KEMENKEU"]],
        ]
        mock_lpse.__enter__ = MagicMock(return_value=mock_lpse)
        mock_lpse.__exit__ = MagicMock(return_value=False)

        with patch('pyproc.mcp.tools.Lpse', return_value=mock_lpse):
            result = await handle_search_tender_packages(
                "search_tender_packages",
                {
                    "lpse_host": "kemenkeu",
                    "keywords": ["laptop", "notebook"],
                    "keyword_match_mode": "all",
                }
            )

        data = json.loads(result[0].text)
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["packages"][0]["id_paket"], "100")

    @async_test
    async def test_search_with_kategori(self):
        from pyproc.mcp.tools import handle_search_tender_packages

        mock_lpse = MagicMock()
        mock_lpse.get_paket_tender.return_value = []
        mock_lpse.__enter__ = MagicMock(return_value=mock_lpse)
        mock_lpse.__exit__ = MagicMock(return_value=False)

        with patch('pyproc.mcp.tools.Lpse', return_value=mock_lpse):
            result = await handle_search_tender_packages(
                "search_tender_packages",
                {
                    "lpse_host": "jakarta",
                    "kategori": "PEKERJAAN_KONSTRUKSI",
                    "tahun_anggaran": "2025",
                }
            )

        data = json.loads(result[0].text)
        self.assertEqual(data["packages"], [])

        # Verify Lpse was called with correct args
        call_kwargs = mock_lpse.get_paket_tender.call_args
        self.assertEqual(call_kwargs[1]['tahun'], 2025)
        self.assertIsNotNone(call_kwargs[1]['kategori'])

    @async_test
    async def test_search_dict_response(self):
        """Test search when Lpse returns dict (non-data_only mode fallback)."""
        from pyproc.mcp.tools import handle_search_tender_packages

        mock_lpse = MagicMock()
        mock_lpse.get_paket_tender.return_value = {
            "data": [
                ["1", "Paket A", "INSTANSI", "Selesai",
                 "Rp 100.000.000,00", "", "Barang", "", "2025"],
            ],
            "recordsFiltered": 100,
        }
        mock_lpse.__enter__ = MagicMock(return_value=mock_lpse)
        mock_lpse.__exit__ = MagicMock(return_value=False)

        with patch('pyproc.mcp.tools.Lpse', return_value=mock_lpse):
            result = await handle_search_tender_packages(
                "search_tender_packages",
                {"lpse_host": "kemenkeu"}
            )

        data = json.loads(result[0].text)
        self.assertEqual(data["total"], 100)
        self.assertEqual(len(data["packages"]), 1)

    @async_test
    async def test_validation_error(self):
        from pyproc.mcp.tools import handle_search_tender_packages

        result = await handle_search_tender_packages(
            "search_tender_packages",
            {}  # Missing required lpse_host
        )
        self.assertIn("Error", result[0].text)


class TestHandleGetTenderDetail(unittest.TestCase):

    @async_test
    async def test_detail_mocked(self):
        from pyproc.mcp.tools import handle_get_tender_detail

        mock_detil = MagicMock()
        mock_detil.get_all_detil.return_value = {"error": False, "error_message": []}
        mock_detil.todict.return_value = {
            "id_paket": "10080116000",
            "pengumuman": {
                "kode_tender": "10080116000",
                "nama_tender": "Test Tender",
                "nilai_pagu_paket": 1000000000.0,
            },
            "peserta": [
                {"nama_peserta": "PT. A", "npwp": "01.234.567.8-012.000"}
            ],
            "hasil": None,
            "pemenang": [
                {"nama_pemenang": "PT. A", "npwp": "01.234.567.8-012.000",
                 "harga_penawaran": 900000000.0}
            ],
            "pemenang_berkontrak": None,
            "jadwal": None,
        }

        mock_lpse = MagicMock()
        mock_lpse.detil_paket_tender.return_value = mock_detil
        mock_lpse.__enter__ = MagicMock(return_value=mock_lpse)
        mock_lpse.__exit__ = MagicMock(return_value=False)

        with patch('pyproc.mcp.tools.Lpse', return_value=mock_lpse):
            result = await handle_get_tender_detail(
                "get_tender_detail",
                {"lpse_host": "kemenkeu", "package_id": "10080116000"}
            )

        data = json.loads(result[0].text)
        self.assertEqual(data["package_id"], "10080116000")
        self.assertIn("pengumuman", data)
        self.assertEqual(data["peserta_count"], 1)
        # NPWP in pemenang should be redacted
        npwp = data["pemenang"][0]["npwp"]
        self.assertIn("*", npwp)

    @async_test
    async def test_detail_all_errors(self):
        from pyproc.mcp.tools import handle_get_tender_detail

        mock_detil = MagicMock()
        mock_detil.get_all_detil.return_value = {
            "error": True,
            "error_message": ["SPSE error - 48658064 - get_pengumuman"]
        }
        mock_detil.pengumuman = None
        mock_detil.peserta = None

        mock_lpse = MagicMock()
        mock_lpse.detil_paket_tender.return_value = mock_detil
        mock_lpse.__enter__ = MagicMock(return_value=mock_lpse)
        mock_lpse.__exit__ = MagicMock(return_value=False)

        with patch('pyproc.mcp.tools.Lpse', return_value=mock_lpse):
            result = await handle_get_tender_detail(
                "get_tender_detail",
                {"lpse_host": "kemenkeu", "package_id": "99999999"}
            )

        data = json.loads(result[0].text)
        self.assertTrue(data["error"])


class TestHandleBulkDetails(unittest.TestCase):

    def _mock_detail_result(self, package_id, name, success=True):
        """Build a result dict matching what fetch_details_parallel returns."""
        item = {
            "package_id": package_id,
            "success": success,
            "detail": {
                "id_paket": package_id,
                "pengumuman": {"nama_tender": name},
                "peserta": [],
                "hasil": None,
                "pemenang": None,
                "pemenang_berkontrak": None,
                "jadwal": None,
            },
        }
        if not success:
            item["error"] = "Paket tidak ditemukan"
        return item

    def _mock_lpse_pool(self, count=4):
        """Return a list of dummy Lpse instances."""
        return [MagicMock() for _ in range(count)]

    @async_test
    async def test_get_tender_details_bulk(self):
        from pyproc.mcp.tools import handle_get_tender_details_bulk

        mock_results = [
            self._mock_detail_result("100", "Tender A"),
            self._mock_detail_result("101", "Tender B"),
        ]
        mock_pool = self._mock_lpse_pool()

        with patch('pyproc.mcp.tools.create_worker_lpse_pool', return_value=mock_pool), \
             patch('pyproc.mcp.tools.fetch_details_parallel', return_value=mock_results):
            result = await handle_get_tender_details_bulk(
                "get_tender_details_bulk",
                {"lpse_host": "kemenkeu", "package_ids": ["100", "101"]},
            )

        data = json.loads(result[0].text)
        self.assertEqual(data["package_type"], "tender")
        self.assertEqual(data["success_count"], 2)
        self.assertEqual(data["error_count"], 0)
        self.assertEqual(len(data["details"]), 2)

    @async_test
    async def test_get_non_tender_details_bulk_partial_failure(self):
        from pyproc.mcp.tools import handle_get_non_tender_details_bulk

        mock_results = [
            self._mock_detail_result("200", "Non Tender A"),
            self._mock_detail_result("201", None, success=False),
            self._mock_detail_result("202", "Non Tender C"),
        ]
        mock_pool = self._mock_lpse_pool()

        with patch('pyproc.mcp.tools.create_worker_lpse_pool', return_value=mock_pool), \
             patch('pyproc.mcp.tools.fetch_details_parallel', return_value=mock_results):
            result = await handle_get_non_tender_details_bulk(
                "get_non_tender_details_bulk",
                {
                    "lpse_host": "jakarta",
                    "package_ids": ["200", "201", "202"],
                    "continue_on_error": True,
                },
            )

        data = json.loads(result[0].text)
        self.assertEqual(data["package_type"], "non_tender")
        self.assertEqual(data["success_count"], 2)
        self.assertEqual(data["error_count"], 1)
        self.assertFalse(data["details"][1]["success"])

    @async_test
    async def test_get_tender_details_bulk_stops_on_error(self):
        from pyproc.mcp.tools import handle_get_tender_details_bulk

        mock_results = [
            self._mock_detail_result("100", None, success=False),
        ]
        mock_pool = self._mock_lpse_pool()

        with patch('pyproc.mcp.tools.create_worker_lpse_pool', return_value=mock_pool), \
             patch('pyproc.mcp.tools.fetch_details_parallel', return_value=mock_results):
            result = await handle_get_tender_details_bulk(
                "get_tender_details_bulk",
                {
                    "lpse_host": "kemenkeu",
                    "package_ids": ["100", "101"],
                    "continue_on_error": False,
                },
            )

        data = json.loads(result[0].text)
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["error_count"], 1)


class TestHandleValidateLpseHost(unittest.TestCase):

    @async_test
    async def test_valid_host(self):
        from pyproc.mcp.tools import handle_validate_lpse_host

        mock_lpse = MagicMock()
        mock_lpse.get_auth_token.return_value = "TEST_TOKEN_ABC123"

        with patch('pyproc.mcp.tools.Lpse', return_value=mock_lpse):
            result = await handle_validate_lpse_host(
                "validate_lpse_host",
                {"lpse_host": "kemenkeu"}
            )

        data = json.loads(result[0].text)
        self.assertTrue(data["valid"])
        self.assertEqual(data["host"], "kemenkeu")
        self.assertEqual(data["url"], "https://spse.inaproc.id/kemenkeu")

    @async_test
    async def test_invalid_host(self):
        from pyproc.mcp.tools import handle_validate_lpse_host

        mock_lpse = MagicMock()
        mock_lpse.get_auth_token.side_effect = Exception("Connection refused")

        with patch('pyproc.mcp.tools.Lpse', return_value=mock_lpse):
            result = await handle_validate_lpse_host(
                "validate_lpse_host",
                {"lpse_host": "invalid-host-xyz"}
            )

        data = json.loads(result[0].text)
        self.assertFalse(data["valid"])
        self.assertIn("not accessible", data["message"])


class TestHandleSearchNonTenderPackages(unittest.TestCase):

    @async_test
    async def test_search_non_tender_mocked(self):
        from pyproc.mcp.tools import handle_search_non_tender_packages

        mock_lpse = MagicMock()
        mock_lpse.get_paket_non_tender.return_value = [
            ["200", "Pengadaan Langsung A", "INSTANSI X", "Selesai",
             "Rp 50.000.000,00", "", "", "", "2025"],
        ]
        mock_lpse.__enter__ = MagicMock(return_value=mock_lpse)
        mock_lpse.__exit__ = MagicMock(return_value=False)

        with patch('pyproc.mcp.tools.Lpse', return_value=mock_lpse):
            result = await handle_search_non_tender_packages(
                "search_non_tender_packages",
                {"lpse_host": "jakarta", "length": "5"}
            )

        data = json.loads(result[0].text)
        self.assertEqual(data["lpse_host"], "jakarta")
        self.assertEqual(len(data["packages"]), 1)


class TestHandleGetNonTenderDetail(unittest.TestCase):

    @async_test
    async def test_detail_non_tender_mocked(self):
        from pyproc.mcp.tools import handle_get_non_tender_detail

        mock_detil = MagicMock()
        mock_detil.get_all_detil.return_value = {"error": False, "error_message": []}
        mock_detil.todict.return_value = {
            "id_paket": "200",
            "pengumuman": {"nama_paket": "PL Test"},
            "peserta": [],
            "hasil": None,
            "pemenang": None,
            "pemenang_berkontrak": None,
            "jadwal": None,
        }

        mock_lpse = MagicMock()
        mock_lpse.detil_paket_non_tender.return_value = mock_detil
        mock_lpse.__enter__ = MagicMock(return_value=mock_lpse)
        mock_lpse.__exit__ = MagicMock(return_value=False)

        with patch('pyproc.mcp.tools.Lpse', return_value=mock_lpse):
            result = await handle_get_non_tender_detail(
                "get_non_tender_detail",
                {"lpse_host": "jakarta", "package_id": "200"}
            )

        data = json.loads(result[0].text)
        self.assertEqual(data["package_id"], "200")
        self.assertIn("pengumuman", data)


class TestHandleProcurementSearchIndexes(unittest.TestCase):

    @async_test
    async def test_create_procurement_search_index(self):
        from pyproc.mcp.tools import handle_create_procurement_search_index

        mock_result = {
            "index_id": "idx-1",
            "indexed_packages": 1,
        }

        with patch("pyproc.mcp.tools.create_procurement_search_index", return_value=mock_result):
            result = await handle_create_procurement_search_index(
                "create_procurement_search_index",
                {
                    "lpse_host": "kemenkeu",
                    "max_packages": 1,
                    "confirm_download": True,
                },
            )

        data = json.loads(result[0].text)
        self.assertEqual(data["index_id"], "idx-1")
        self.assertEqual(data["indexed_packages"], 1)

    @async_test
    async def test_search_procurement_index(self):
        from pyproc.mcp.tools import handle_search_procurement_index

        mock_result = {
            "index_id": "idx-1",
            "query": "laptop",
            "count": 1,
            "matches": [{"id_paket": "100"}],
        }

        with patch("pyproc.mcp.tools.search_procurement_index", return_value=mock_result):
            result = await handle_search_procurement_index(
                "search_procurement_index",
                {"index_id": "idx-1", "query": "laptop"},
            )

        data = json.loads(result[0].text)
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["matches"][0]["id_paket"], "100")

    @async_test
    async def test_list_procurement_indexes(self):
        from pyproc.mcp.tools import handle_list_procurement_indexes

        with patch("pyproc.mcp.tools.list_procurement_indexes", return_value={"count": 0, "indexes": []}):
            result = await handle_list_procurement_indexes(
                "list_procurement_indexes", {}
            )

        data = json.loads(result[0].text)
        self.assertEqual(data["count"], 0)

    @async_test
    async def test_delete_procurement_index(self):
        from pyproc.mcp.tools import handle_delete_procurement_index

        with patch("pyproc.mcp.tools.delete_procurement_index", return_value={"index_id": "idx-1", "deleted": True}):
            result = await handle_delete_procurement_index(
                "delete_procurement_index",
                {"index_id": "idx-1"},
            )

        data = json.loads(result[0].text)
        self.assertTrue(data["deleted"])


class TestHandleGetMasterLpse(unittest.TestCase):

    @async_test
    async def test_mocked(self):
        from pyproc.mcp.tools import handle_get_master_lpse

        mock_lpse_sample = [
            {"kd_lpse": 119,
             "nama_lpse": "LPSE Lembaga Kebijakan Pengadaan Barang/Jasa Pemerintah",
             "_event_date": "2026-01-16"},
            {"kd_lpse": 10,
             "nama_lpse": "LPSE Kota Surabaya",
             "_event_date": "2026-01-16"},
        ]

        with patch(
            'pyproc.mcp.tools.Lpse.get_master_lpse', return_value=mock_lpse_sample
        ):
            result = await handle_get_master_lpse(
                "get_master_lpse",
                {"query": "surabaya", "save_to_file": False},
            )

        data = json.loads(result[0].text)
        self.assertEqual(data["total_matches"], 1)
        self.assertEqual(data["count"], 1)
        self.assertEqual(len(data["lpse"]), 1)
        self.assertEqual(data["lpse"][0]["kd_lpse"], 10)
        self.assertIn("usage", data)
        self.assertIn("get_tender_umum_publik", data["usage"])

    @async_test
    async def test_filter_by_kd_lpse(self):
        from pyproc.mcp.tools import handle_get_master_lpse

        mock_lpse_sample = [
            {"kd_lpse": 119, "nama_lpse": "LPSE LKPP",
             "_event_date": "2026-01-16"},
            {"kd_lpse": 10, "nama_lpse": "LPSE Kota Surabaya",
             "_event_date": "2026-01-16"},
        ]

        with patch(
            'pyproc.mcp.tools.Lpse.get_master_lpse', return_value=mock_lpse_sample
        ):
            result = await handle_get_master_lpse(
                "get_master_lpse",
                {"kd_lpse": "119", "save_to_file": False},
            )

        data = json.loads(result[0].text)
        self.assertEqual(data["total_matches"], 1)
        self.assertEqual(data["lpse"][0]["kd_lpse"], 119)

    @async_test
    async def test_validation_error(self):
        from pyproc.mcp.tools import handle_get_master_lpse

        result = await handle_get_master_lpse(
            "get_master_lpse",
            {"kd_lpse": "abc"},
        )

        self.assertIn("Error", result[0].text)


class TestHandleGetTenderUmumPublik(unittest.TestCase):

    @async_test
    async def test_step1_discovery_returns_choice_prompt(self):
        from pyproc.mcp.tools import handle_get_tender_umum_publik

        mock_tender_data = [
            {"Kode Tender": 10109010000, "Nama Paket": "Pekerjaan Jasa Sewa", "Pagu": 20000000000},
            {"Kode Tender": 10109010001, "Nama Paket": "Pengadaan Alat", "Pagu": 5000000000},
        ]

        with patch(
            'pyproc.mcp.tools.Lpse.get_tender_umum_publik',
            return_value=mock_tender_data,
        ), patch(
            'pyproc.mcp.tools._get_api_data_dir',
            return_value=Path(self._tmp_dir()),
        ):
            result = await handle_get_tender_umum_publik(
                "get_tender_umum_publik",
                {"tahun_anggaran": "2026", "kd_lpse": "119"},
            )

        data = json.loads(result[0].text)
        self.assertEqual(data["status"], "choose_output_mode")
        self.assertEqual(data["record_count"], 2)
        self.assertEqual(data["kd_lpse"], 119)
        self.assertEqual(data["tahun_anggaran"], 2026)
        self.assertIn("preview", data)
        self.assertIn("output_options", data)
        self.assertIn("local_index", data["output_options"])
        self.assertIn("file", data["output_options"])
        self.assertIn("inline", data["output_options"])
        self.assertIn("next_step", data)
        self.assertNotIn("tenders", data)

    @async_test
    async def test_step2_local_index(self):
        import tempfile
        from pyproc.mcp.tools import handle_get_tender_umum_publik

        mock_tender_data = [
            {"Kode Tender": "100", "Nama Paket": "Test Paket", "Pagu": 1000},
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            # Pre-create temp file as if step 1 already ran
            import hashlib
            params_hash = hashlib.md5(f"119_2026".encode()).hexdigest()[:8]
            temp_file = Path(tmpdir) / f".isb_temp_kd119_2026_{params_hash}.json"
            with open(temp_file, "w") as f:
                json.dump(mock_tender_data, f)

            with patch(
                'pyproc.mcp.tools._get_api_data_dir',
                return_value=Path(tmpdir),
            ), patch(
                'pyproc.mcp.tools.create_isb_data_index',
                return_value={
                    "index_id": "isb-119-2026-test123",
                    "indexed_records": 1,
                    "usage_hint": "test",
                },
            ) as mock_create:
                result = await handle_get_tender_umum_publik(
                    "get_tender_umum_publik",
                    {
                        "tahun_anggaran": "2026",
                        "kd_lpse": "119",
                        "output_mode": "local_index",
                    },
                )

        data = json.loads(result[0].text)
        self.assertEqual(data["index_id"], "isb-119-2026-test123")
        self.assertEqual(data["indexed_records"], 1)
        mock_create.assert_called_once()

    @async_test
    async def test_step2_file(self):
        import tempfile
        from pyproc.mcp.tools import handle_get_tender_umum_publik

        mock_tender_data = [
            {"Kode Tender": "100", "Nama Paket": "Test", "Pagu": 1000},
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            import hashlib
            params_hash = hashlib.md5(f"119_2026".encode()).hexdigest()[:8]
            temp_file = Path(tmpdir) / f".isb_temp_kd119_2026_{params_hash}.json"
            with open(temp_file, "w") as f:
                json.dump(mock_tender_data, f)

            with patch(
                'pyproc.mcp.tools._get_api_data_dir',
                return_value=Path(tmpdir),
            ), patch(
                'pyproc.mcp.tools._save_json_to_file',
                return_value={
                    "status": "saved_to_file",
                    "file_path": "/tmp/test.json",
                    "record_count": 1,
                    "preview": [],
                    "processing_hints": "hints",
                    "confirmation_hint": "",
                },
            ) as mock_save:
                result = await handle_get_tender_umum_publik(
                    "get_tender_umum_publik",
                    {
                        "tahun_anggaran": "2026",
                        "kd_lpse": "119",
                        "output_mode": "file",
                    },
                )

        data = json.loads(result[0].text)
        self.assertEqual(data["status"], "saved_to_file")
        mock_save.assert_called_once()

    @async_test
    async def test_step2_inline(self):
        import tempfile
        from pyproc.mcp.tools import handle_get_tender_umum_publik

        mock_tender_data = [
            {"Kode Tender": "100", "Nama Paket": "Test", "Pagu": 1000},
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            import hashlib
            params_hash = hashlib.md5(f"119_2026".encode()).hexdigest()[:8]
            temp_file = Path(tmpdir) / f".isb_temp_kd119_2026_{params_hash}.json"
            with open(temp_file, "w") as f:
                json.dump(mock_tender_data, f)

            with patch(
                'pyproc.mcp.tools._get_api_data_dir',
                return_value=Path(tmpdir),
            ):
                result = await handle_get_tender_umum_publik(
                    "get_tender_umum_publik",
                    {
                        "tahun_anggaran": "2026",
                        "kd_lpse": "119",
                        "output_mode": "inline",
                    },
                )

        data = json.loads(result[0].text)
        self.assertEqual(data["status"], "inline_with_warning")
        self.assertIn("warning", data)
        self.assertEqual(data["record_count"], 1)
        self.assertEqual(len(data["tenders"]), 1)

    @async_test
    async def test_step2_missing_temp_file(self):
        import tempfile
        from pyproc.mcp.tools import handle_get_tender_umum_publik

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch(
                'pyproc.mcp.tools._get_api_data_dir',
                return_value=Path(tmpdir),
            ):
                result = await handle_get_tender_umum_publik(
                    "get_tender_umum_publik",
                    {
                        "tahun_anggaran": "2026",
                        "kd_lpse": "119",
                        "output_mode": "local_index",
                    },
                )

        self.assertIn("Error", result[0].text)
        self.assertIn("not found", result[0].text)

    @async_test
    async def test_validation_error(self):
        from pyproc.mcp.tools import handle_get_tender_umum_publik

        result = await handle_get_tender_umum_publik(
            "get_tender_umum_publik",
            {},
        )

        self.assertIn("Error", result[0].text)

    @async_test
    async def test_empty_result(self):
        from pyproc.mcp.tools import handle_get_tender_umum_publik

        with patch(
            'pyproc.mcp.tools.Lpse.get_tender_umum_publik',
            return_value=[],
        ):
            result = await handle_get_tender_umum_publik(
                "get_tender_umum_publik",
                {"tahun_anggaran": "2026", "kd_lpse": "999"},
            )

        data = json.loads(result[0].text)
        self.assertEqual(data["count"], 0)
        self.assertEqual(data["tenders"], [])
        self.assertNotIn("status", data)

    @staticmethod
    def _tmp_dir():
        import tempfile
        return tempfile.mkdtemp()

    @async_test
    async def test_existing_index_found_returns_choice(self):
        from pyproc.mcp.tools import handle_get_tender_umum_publik

        existing_metadata = {
            "index_id": "isb-119-2026-existing",
            "source": "isb_satudata",
            "kd_lpse": 119,
            "tahun_anggaran": 2026,
            "indexed_records": 450,
            "created_at": 1700000000,
        }

        with patch(
            'pyproc.mcp.tools.find_existing_isb_index',
            return_value=existing_metadata,
        ):
            result = await handle_get_tender_umum_publik(
                "get_tender_umum_publik",
                {"tahun_anggaran": "2026", "kd_lpse": "119"},
            )

        data = json.loads(result[0].text)
        self.assertEqual(data["status"], "existing_index_found")
        self.assertEqual(data["index_id"], "isb-119-2026-existing")
        self.assertIn("choices", data)
        self.assertIn("reuse", data["choices"])
        self.assertIn("refresh", data["choices"])

    @async_test
    async def test_force_refresh_skips_existing_check(self):
        from pyproc.mcp.tools import handle_get_tender_umum_publik

        mock_tender_data = [
            {"Kode Tender": "100", "Nama Paket": "Test", "Pagu": 1000},
        ]

        with patch(
            'pyproc.mcp.tools.find_existing_isb_index',
            return_value={"index_id": "old-index"},
        ), patch(
            'pyproc.mcp.tools.Lpse.get_tender_umum_publik',
            return_value=mock_tender_data,
        ), patch(
            'pyproc.mcp.tools._get_api_data_dir',
            return_value=Path(self._tmp_dir()),
        ):
            result = await handle_get_tender_umum_publik(
                "get_tender_umum_publik",
                {
                    "tahun_anggaran": "2026",
                    "kd_lpse": "119",
                    "force_refresh": True,
                },
            )

        data = json.loads(result[0].text)
        self.assertEqual(data["status"], "choose_output_mode")
        self.assertEqual(data["record_count"], 1)

    @async_test
    async def test_no_existing_index_fetches_data(self):
        from pyproc.mcp.tools import handle_get_tender_umum_publik

        mock_tender_data = [
            {"Kode Tender": "100", "Nama Paket": "Test", "Pagu": 1000},
        ]

        with patch(
            'pyproc.mcp.tools.find_existing_isb_index',
            return_value=None,
        ), patch(
            'pyproc.mcp.tools.Lpse.get_tender_umum_publik',
            return_value=mock_tender_data,
        ), patch(
            'pyproc.mcp.tools._get_api_data_dir',
            return_value=Path(self._tmp_dir()),
        ):
            result = await handle_get_tender_umum_publik(
                "get_tender_umum_publik",
                {"tahun_anggaran": "2026", "kd_lpse": "119"},
            )

        data = json.loads(result[0].text)
        self.assertEqual(data["status"], "choose_output_mode")


class TestHandleClearAllData(unittest.TestCase):

    @async_test
    async def test_clear_confirmed(self):
        from pyproc.mcp.tools import handle_clear_all_data

        with patch(
            'pyproc.mcp.tools.cleanup_all_data',
            return_value={
                "indexes_deleted": 3,
                "files_deleted": 5,
                "index_dir": "/tmp/indexes",
                "data_dir": "/tmp/data",
            },
        ) as mock_cleanup:
            result = await handle_clear_all_data(
                "clear_all_data",
                {"confirm": True},
            )

        data = json.loads(result[0].text)
        self.assertEqual(data["indexes_deleted"], 3)
        self.assertEqual(data["files_deleted"], 5)
        self.assertIn("message", data)
        mock_cleanup.assert_called_once()

    @async_test
    async def test_clear_not_confirmed(self):
        from pyproc.mcp.tools import handle_clear_all_data

        result = await handle_clear_all_data(
            "clear_all_data",
            {"confirm": False},
        )

        self.assertIn("Error", result[0].text)
        self.assertIn("confirm", result[0].text)

    @async_test
    async def test_clear_missing_confirm(self):
        from pyproc.mcp.tools import handle_clear_all_data

        result = await handle_clear_all_data(
            "clear_all_data",
            {},
        )

        self.assertIn("Error", result[0].text)


class TestHandleSearchIsbIndex(unittest.TestCase):

    @async_test
    async def test_search_mocked(self):
        from pyproc.mcp.tools import handle_search_isb_index

        mock_result = {
            "index_id": "isb-119-2026-test",
            "query": "laptop",
            "count": 1,
            "matches": [{"kode_tender": "100", "nama_paket": "Pengadaan Laptop", "snippet": "...", "rank": -1.0}],
        }

        with patch(
            'pyproc.mcp.tools.search_isb_index',
            return_value=mock_result,
        ):
            result = await handle_search_isb_index(
                "search_isb_index",
                {"index_id": "isb-119-2026-test", "query": "laptop"},
            )

        data = json.loads(result[0].text)
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["matches"][0]["kode_tender"], "100")

    @async_test
    async def test_search_validation_error(self):
        from pyproc.mcp.tools import handle_search_isb_index

        result = await handle_search_isb_index(
            "search_isb_index",
            {},
        )

        self.assertIn("Error", result[0].text)

    @async_test
    async def test_search_index_not_found(self):
        from pyproc.mcp.tools import handle_search_isb_index

        with patch(
            'pyproc.mcp.tools.search_isb_index',
            side_effect=ValueError("ISB index 'nonexistent' was not found"),
        ):
            result = await handle_search_isb_index(
                "search_isb_index",
                {"index_id": "nonexistent", "query": "test"},
            )

        self.assertIn("Error", result[0].text)
        self.assertIn("not found", result[0].text)


class TestHandleGetMasterKlpdFileOutput(unittest.TestCase):

    @async_test
    async def test_save_to_file_true(self):
        from pyproc.mcp.tools import handle_get_master_klpd

        mock_klpd_data = [
            {"kd_klpd": "K66", "nama_klpd": "KEMENTERIAN KEUANGAN", "jenis_klpd": "KEMENTERIAN"},
            {"kd_klpd": "K01", "nama_klpd": "KEMENTERIAN DALAM NEGERI", "jenis_klpd": "KEMENTERIAN"},
        ]

        with patch(
            'pyproc.mcp.tools.Lpse.get_master_klpd',
            return_value=mock_klpd_data,
        ), patch(
            'pyproc.mcp.tools._save_json_to_file',
            return_value={
                "status": "saved_to_file",
                "file_path": "/tmp/test_klpd.json",
                "record_count": 2,
                "preview": mock_klpd_data[:3],
                "processing_hints": "test hints",
                "confirmation_hint": "test confirmation",
            },
        ) as mock_save:
            result = await handle_get_master_klpd(
                "get_master_klpd",
                {"query": "keuangan", "save_to_file": True},
            )

        data = json.loads(result[0].text)
        self.assertEqual(data["status"], "saved_to_file")
        self.assertEqual(data["record_count"], 2)
        self.assertNotIn("klpd", data)
        mock_save.assert_called_once()

    @async_test
    async def test_save_to_file_false(self):
        from pyproc.mcp.tools import handle_get_master_klpd

        mock_klpd_data = [
            {"kd_klpd": "K66", "nama_klpd": "KEMENTERIAN KEUANGAN", "jenis_klpd": "KEMENTERIAN"},
        ]

        with patch(
            'pyproc.mcp.tools.Lpse.get_master_klpd',
            return_value=mock_klpd_data,
        ):
            result = await handle_get_master_klpd(
                "get_master_klpd",
                {"query": "keuangan", "save_to_file": False},
            )

        data = json.loads(result[0].text)
        self.assertNotIn("status", data)
        self.assertIn("klpd", data)
        self.assertEqual(len(data["klpd"]), 1)

    @async_test
    async def test_default_save_to_file(self):
        from pyproc.mcp.tools import handle_get_master_klpd

        mock_klpd_data = [
            {"kd_klpd": "K66", "nama_klpd": "KEMENTERIAN KEUANGAN"},
        ]

        with patch(
            'pyproc.mcp.tools.Lpse.get_master_klpd',
            return_value=mock_klpd_data,
        ), patch(
            'pyproc.mcp.tools._save_json_to_file',
            return_value={
                "status": "saved_to_file",
                "file_path": "/tmp/test.json",
                "record_count": 1,
                "preview": [],
                "processing_hints": "hints",
                "confirmation_hint": "",
            },
        ):
            result = await handle_get_master_klpd(
                "get_master_klpd",
                {"query": "keuangan"},
            )

        data = json.loads(result[0].text)
        self.assertEqual(data["status"], "saved_to_file")


class TestHandleGetMasterLpseFileOutput(unittest.TestCase):

    @async_test
    async def test_save_to_file_true(self):
        from pyproc.mcp.tools import handle_get_master_lpse

        mock_lpse_data = [
            {"kd_lpse": 119, "nama_lpse": "LPSE LKPP"},
            {"kd_lpse": 10, "nama_lpse": "LPSE Kota Surabaya"},
        ]

        with patch(
            'pyproc.mcp.tools.Lpse.get_master_lpse',
            return_value=mock_lpse_data,
        ), patch(
            'pyproc.mcp.tools._save_json_to_file',
            return_value={
                "status": "saved_to_file",
                "file_path": "/tmp/test_lpse.json",
                "record_count": 2,
                "preview": mock_lpse_data[:3],
                "processing_hints": "test hints",
                "confirmation_hint": "test confirmation",
            },
        ) as mock_save:
            result = await handle_get_master_lpse(
                "get_master_lpse",
                {"query": "surabaya", "save_to_file": True},
            )

        data = json.loads(result[0].text)
        self.assertEqual(data["status"], "saved_to_file")
        self.assertEqual(data["record_count"], 2)
        self.assertNotIn("lpse", data)
        mock_save.assert_called_once()

    @async_test
    async def test_save_to_file_false(self):
        from pyproc.mcp.tools import handle_get_master_lpse

        mock_lpse_data = [
            {"kd_lpse": 10, "nama_lpse": "LPSE Kota Surabaya"},
        ]

        with patch(
            'pyproc.mcp.tools.Lpse.get_master_lpse',
            return_value=mock_lpse_data,
        ):
            result = await handle_get_master_lpse(
                "get_master_lpse",
                {"query": "surabaya", "save_to_file": False},
            )

        data = json.loads(result[0].text)
        self.assertNotIn("status", data)
        self.assertIn("lpse", data)
        self.assertEqual(len(data["lpse"]), 1)


class TestResourceHandlers(unittest.TestCase):

    @async_test
    async def test_get_categories_resource(self):
        from pyproc.mcp.resources import _get_categories
        content = await _get_categories()
        data = json.loads(content)
        self.assertEqual(data["count"], 6)
        self.assertEqual(len(data["categories"]), 6)

    @async_test
    async def test_get_tool_docs_resource(self):
        from pyproc.mcp.resources import _get_tool_docs
        content = await _get_tool_docs()
        self.assertIn("PyProc MCP Tools", content)
        self.assertIn("search_tender_packages", content)
        self.assertIn("search_lpse_hosts", content)
        self.assertIn("full-text", content)
        self.assertIn("not affiliated", content)

    @async_test
    async def test_get_responsible_use_resource(self):
        from pyproc.mcp.resources import _get_responsible_use
        content = await _get_responsible_use()
        self.assertIn("not affiliated", content)
        self.assertIn("LKPP", content)
        self.assertIn("Penulis tidak terafiliasi", content)
        self.assertIn("PyProc ada karena SPSE ada", content)

    @async_test
    async def test_get_lpse_host_guide_resource(self):
        from pyproc.mcp.resources import _get_lpse_host_guide
        content = await _get_lpse_host_guide()
        self.assertIn("search_lpse_hosts", content)
        self.assertIn("kementerian keuangan", content)
        self.assertIn("search_tender_packages", content)


if __name__ == '__main__':
    unittest.main()
