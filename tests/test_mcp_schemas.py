"""Tests for pyproc.mcp.schemas — validation and normalization."""
import unittest

from pyproc.mcp.schemas import (
    validate_lpse_host,
    validate_package_id,
    validate_kategori,
    validate_tahun_anggaran,
    validate_search_params,
    validate_detail_params,
    validate_bulk_detail_params,
    validate_search_index_create_params,
    validate_search_index_query_params,
    validate_master_klpd_params,
    sanitize_text,
    sanitize_dict_keys,
    normalize_search_results,
    normalize_detail_result,
    normalize_categories,
    normalize_host_validation,
    MAX_SEARCH_LENGTH,
    DEFAULT_SEARCH_LENGTH,
    MAX_TEXT_FIELD_LENGTH,
)
from pyproc.lpse import By


class TestSanitize(unittest.TestCase):

    def test_sanitize_text_none(self):
        self.assertIsNone(sanitize_text(None))

    def test_sanitize_text_normal(self):
        self.assertEqual(sanitize_text("Hello World"), "Hello World")

    def test_sanitize_text_control_chars(self):
        self.assertEqual(sanitize_text("test\x00data"), "testdata")

    def test_sanitize_text_truncation(self):
        long_text = "x" * (MAX_TEXT_FIELD_LENGTH + 100)
        result = sanitize_text(long_text)
        self.assertEqual(len(result), MAX_TEXT_FIELD_LENGTH + 3)  # +3 for "..."
        self.assertTrue(result.endswith("..."))

    def test_sanitize_text_non_string(self):
        self.assertEqual(sanitize_text(123), "123")
        self.assertEqual(sanitize_text(45.67), "45.67")

    def test_sanitize_dict_keys_recursive(self):
        data = {
            "name": "test\x00value",
            "nested": {"key": "a" * 2000},
            "list": ["item\x01"]
        }
        result = sanitize_dict_keys(data)
        self.assertNotIn("\x00", result["name"])
        self.assertLessEqual(len(result["nested"]["key"]), MAX_TEXT_FIELD_LENGTH + 3)


class TestValidateLpseHost(unittest.TestCase):

    def test_valid_host(self):
        self.assertEqual(validate_lpse_host("kemenkeu"), "kemenkeu")

    def test_valid_host_with_hyphen(self):
        self.assertEqual(validate_lpse_host("tanjabtim-kab"), "tanjabtim-kab")

    def test_valid_host_strips_whitespace(self):
        self.assertEqual(validate_lpse_host("  kemenkeu  "), "kemenkeu")

    def test_valid_host_lowercases(self):
        self.assertEqual(validate_lpse_host("KEMENKEU"), "kemenkeu")

    def test_empty_host(self):
        with self.assertRaises(ValueError):
            validate_lpse_host("")

    def test_whitespace_only_host(self):
        with self.assertRaises(ValueError):
            validate_lpse_host("   ")

    def test_invalid_chars(self):
        with self.assertRaises(ValueError):
            validate_lpse_host("host/name")


class TestValidatePackageId(unittest.TestCase):

    def test_valid_int(self):
        self.assertEqual(validate_package_id(10080116000), "10080116000")

    def test_valid_string(self):
        self.assertEqual(validate_package_id("10080116000"), "10080116000")

    def test_invalid_none(self):
        with self.assertRaises(ValueError):
            validate_package_id(None)

    def test_invalid_text(self):
        with self.assertRaises(ValueError):
            validate_package_id("abc")

    def test_negative(self):
        self.assertEqual(validate_package_id(-1), "-1")


class TestValidateKategori(unittest.TestCase):

    def test_valid(self):
        self.assertEqual(validate_kategori("PENGADAAN_BARANG"), "PENGADAAN_BARANG")

    def test_none(self):
        self.assertIsNone(validate_kategori(None))

    def test_invalid(self):
        with self.assertRaises(ValueError):
            validate_kategori("INVALID_CATEGORY")


class TestValidateTahunAnggaran(unittest.TestCase):

    def test_valid(self):
        self.assertEqual(validate_tahun_anggaran(2025), 2025)

    def test_valid_string(self):
        self.assertEqual(validate_tahun_anggaran("2025"), 2025)

    def test_none(self):
        self.assertIsNone(validate_tahun_anggaran(None))

    def test_before_2000(self):
        with self.assertRaises(ValueError):
            validate_tahun_anggaran(1999)

    def test_far_future(self):
        with self.assertRaises(ValueError):
            validate_tahun_anggaran(2101)

    def test_invalid(self):
        with self.assertRaises(ValueError):
            validate_tahun_anggaran("abc")


class TestValidateSearchParams(unittest.TestCase):

    def test_minimal_params(self):
        result = validate_search_params({"lpse_host": "kemenkeu"})
        self.assertEqual(result["lpse_host"], "kemenkeu")
        self.assertEqual(result["keyword"], "")
        self.assertEqual(result["start"], 0)
        self.assertEqual(result["length"], DEFAULT_SEARCH_LENGTH)
        self.assertEqual(result["keywords"], [])
        self.assertEqual(result["keyword_match_mode"], "any")

    def test_full_params(self):
        result = validate_search_params({
            "lpse_host": "kemenkeu",
            "keyword": "sekolah",
            "tahun_anggaran": "2025",
            "kategori": "PEKERJAAN_KONSTRUKSI",
            "start": "10",
            "length": "50",
        })
        self.assertEqual(result["lpse_host"], "kemenkeu")
        self.assertEqual(result["keyword"], "sekolah")
        self.assertEqual(result["tahun_anggaran"], 2025)
        self.assertEqual(result["kategori"], "PEKERJAAN_KONSTRUKSI")
        self.assertEqual(result["start"], 10)
        self.assertEqual(result["length"], 50)

    def test_search_sort_instansi_rekanan_and_kontrak_status(self):
        result = validate_search_params({
            "lpse_host": "kemenkeu",
            "rekanan": "PT Test",
            "instansi_id": "K66",
            "order_by": "hps",
            "order_dir": "desc",
            "kontrak_status": "0",
        })
        self.assertEqual(result["rekanan"], "PT Test")
        self.assertEqual(result["instansi_id"], "K66")
        self.assertEqual(result["order"], By.HPS)
        self.assertFalse(result["ascending"])
        self.assertEqual(result["kontrak_status"], 0)

    def test_search_legacy_nama_penyedia_alias(self):
        result = validate_search_params({
            "lpse_host": "kemenkeu",
            "nama_penyedia": "PT Legacy",
        })
        self.assertEqual(result["rekanan"], "PT Legacy")

    def test_invalid_order_by(self):
        with self.assertRaises(ValueError):
            validate_search_params({
                "lpse_host": "kemenkeu",
                "order_by": "tanggal",
            })

    def test_invalid_kontrak_status(self):
        with self.assertRaises(ValueError):
            validate_search_params({
                "lpse_host": "kemenkeu",
                "kontrak_status": "9",
            })

    def test_keywords_list(self):
        result = validate_search_params({
            "lpse_host": "kemenkeu",
            "keywords": ["laptop", "notebook", "laptop"],
            "keyword_match_mode": "all",
        })
        self.assertEqual(result["keywords"], ["laptop", "notebook"])
        self.assertEqual(result["keyword_match_mode"], "all")

    def test_keywords_too_many(self):
        with self.assertRaises(ValueError):
            validate_search_params({
                "lpse_host": "kemenkeu",
                "keywords": ["a", "b", "c", "d", "e", "f"],
            })

    def test_invalid_keyword_match_mode(self):
        with self.assertRaises(ValueError):
            validate_search_params({
                "lpse_host": "kemenkeu",
                "keyword_match_mode": "phrase",
            })

    def test_length_clamped_max(self):
        result = validate_search_params({
            "lpse_host": "kemenkeu",
            "length": "500",
        })
        self.assertEqual(result["length"], MAX_SEARCH_LENGTH)

    def test_length_clamped_min(self):
        result = validate_search_params({
            "lpse_host": "kemenkeu",
            "length": "0",
        })
        self.assertEqual(result["length"], 1)

    def test_start_negative_clamped(self):
        result = validate_search_params({
            "lpse_host": "kemenkeu",
            "start": "-5",
        })
        self.assertEqual(result["start"], 0)

    def test_missing_host(self):
        with self.assertRaises(ValueError):
            validate_search_params({})

    def test_invalid_kategori(self):
        with self.assertRaises(ValueError):
            validate_search_params({
                "lpse_host": "kemenkeu",
                "kategori": "INVALID",
            })

    def test_invalid_tahun(self):
        with self.assertRaises(ValueError):
            validate_search_params({
                "lpse_host": "kemenkeu",
                "tahun_anggaran": "abc",
            })


class TestValidateDetailParams(unittest.TestCase):

    def test_valid(self):
        result = validate_detail_params({
            "lpse_host": "kemenkeu",
            "package_id": "10080116000",
        })
        self.assertEqual(result["lpse_host"], "kemenkeu")
        self.assertEqual(result["package_id"], "10080116000")

    def test_missing_host(self):
        with self.assertRaises(ValueError):
            validate_detail_params({"package_id": "123"})

    def test_missing_package_id(self):
        with self.assertRaises(ValueError):
            validate_detail_params({"lpse_host": "kemenkeu"})


class TestValidateBulkDetailParams(unittest.TestCase):

    def test_valid(self):
        result = validate_bulk_detail_params({
            "lpse_host": "kemenkeu",
            "package_ids": ["100", 200],
        })
        self.assertEqual(result["lpse_host"], "kemenkeu")
        self.assertEqual(result["package_ids"], ["100", "200"])
        self.assertTrue(result["continue_on_error"])

    def test_continue_on_error_false(self):
        result = validate_bulk_detail_params({
            "lpse_host": "kemenkeu",
            "package_ids": ["100"],
            "continue_on_error": "false",
        })
        self.assertFalse(result["continue_on_error"])

    def test_empty_package_ids(self):
        with self.assertRaises(ValueError):
            validate_bulk_detail_params({
                "lpse_host": "kemenkeu",
                "package_ids": [],
            })

    def test_too_many_package_ids(self):
        with self.assertRaises(ValueError):
            validate_bulk_detail_params({
                "lpse_host": "kemenkeu",
                "package_ids": list(range(21)),
            })


class TestValidateSearchIndexParams(unittest.TestCase):

    def test_create_index_params_minimal(self):
        result = validate_search_index_create_params({
            "lpse_host": "kemenkeu",
            "confirm_download": True,
        })
        self.assertEqual(result["lpse_host"], "kemenkeu")
        self.assertEqual(result["package_type"], "tender")
        self.assertEqual(result["max_packages"], 100)
        self.assertTrue(result["confirm_download"])

    def test_create_index_params_full(self):
        result = validate_search_index_create_params({
            "lpse_host": "kemenkeu",
            "package_type": "non_tender",
            "tahun_anggaran": "2025",
            "kategori": "PENGADAAN_BARANG",
            "keyword_seed": "laptop",
            "max_packages": "20",
            "confirm_download": True,
        })
        self.assertEqual(result["package_type"], "non_tender")
        self.assertEqual(result["tahun_anggaran"], 2025)
        self.assertEqual(result["kategori"], "PENGADAAN_BARANG")
        self.assertEqual(result["keyword_seed"], "laptop")
        self.assertEqual(result["max_packages"], 20)

    def test_create_index_invalid_package_type(self):
        with self.assertRaises(ValueError):
            validate_search_index_create_params({
                "lpse_host": "kemenkeu",
                "package_type": "all",
                "confirm_download": True,
            })


class TestValidateMasterKlpdParams(unittest.TestCase):

    def test_defaults(self):
        result = validate_master_klpd_params({})
        self.assertEqual(result["query"], "")
        self.assertIsNone(result["kd_klpd"])
        self.assertIsNone(result["jenis_klpd"])
        self.assertEqual(result["limit"], 50)

    def test_full_params(self):
        result = validate_master_klpd_params({
            "query": "bkkbn",
            "kd_klpd": "K66",
            "jenis_klpd": "KEMENTERIAN",
            "limit": "10",
        })
        self.assertEqual(result["query"], "bkkbn")
        self.assertEqual(result["kd_klpd"], "K66")
        self.assertEqual(result["jenis_klpd"], "KEMENTERIAN")
        self.assertEqual(result["limit"], 10)

    def test_invalid_kd_klpd(self):
        with self.assertRaises(ValueError):
            validate_master_klpd_params({"kd_klpd": "K/66"})

    def test_create_index_requires_confirmation(self):
        with self.assertRaises(ValueError):
            validate_search_index_create_params({"lpse_host": "kemenkeu"})

    def test_query_index_params(self):
        result = validate_search_index_query_params({
            "index_id": "idx-1",
            "query": "laptop",
            "limit": "5",
        })
        self.assertEqual(result["index_id"], "idx-1")
        self.assertEqual(result["query"], "laptop")
        self.assertEqual(result["limit"], 5)


class TestNormalizeSearchResults(unittest.TestCase):

    def test_basic(self):
        raw = [
            ["10080116000", "Pengadaan Barang Test", "KEMENTERIAN KEUANGAN",
             "Tender Sudah Selesai", "Rp 950.000.000,00", "", "Pengadaan Barang", "", "2025"],
        ]
        result = normalize_search_results(raw, "kemenkeu", 1, 0, 20)
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["lpse_host"], "kemenkeu")
        self.assertEqual(result["lpse_url"], "https://spse.inaproc.id/kemenkeu")
        pkg = result["packages"][0]
        self.assertEqual(pkg["id_paket"], "10080116000")
        self.assertEqual(pkg["nama_paket"], "Pengadaan Barang Test")
        self.assertIsInstance(pkg["hps"], float)
        self.assertEqual(pkg["hps"], 950000000.0)

    def test_empty(self):
        result = normalize_search_results([], "kemenkeu", 0, 0, 20)
        self.assertEqual(result["packages"], [])
        self.assertEqual(result["count"], 0)


class TestNormalizeDetailResult(unittest.TestCase):

    def test_empty(self):
        result = normalize_detail_result({})
        self.assertIn("error", result)

    def test_full_detail(self):
        detail = {
            "id_paket": "10080116000",
            "pengumuman": {
                "kode_tender": "10080116000",
                "nama_tender": "Test Tender",
                "nilai_pagu_paket": 1000000000.0,
            },
            "peserta": [
                {"nama_peserta": "PT. Test", "npwp": "01.234.567.8-012.000"}
            ],
            "hasil": [
                {"nama_peserta": "PT. Test", "pemenang": True}
            ],
            "pemenang": [
                {"nama_pemenang": "PT. Test", "npwp": "01.234.567.8-012.000",
                 "harga_penawaran": 900000000.0}
            ],
            "pemenang_berkontrak": None,
            "jadwal": [
                {"tahap": "Evaluasi", "mulai": "20 Jan 2025"}
            ],
        }
        result = normalize_detail_result(detail)
        self.assertEqual(result["package_id"], "10080116000")
        self.assertIn("pengumuman", result)
        self.assertEqual(result["peserta_count"], 1)
        self.assertEqual(result["hasil_count"], 1)
        # NPWP should be redacted
        winner_npwp = result["pemenang"][0]["npwp"]
        self.assertIn("*", winner_npwp)

    def test_npwp_short_not_redacted(self):
        detail = {
            "id_paket": "123",
            "pemenang": [{"nama_pemenang": "X", "npwp": "12345"}],
        }
        result = normalize_detail_result(detail)
        self.assertEqual(result["pemenang"][0]["npwp"], "12345")


class TestNormalizeCategories(unittest.TestCase):

    def test_returns_all_categories(self):
        result = normalize_categories()
        self.assertEqual(result["count"], 6)
        self.assertEqual(len(result["categories"]), 6)
        names = [c["name"] for c in result["categories"]]
        self.assertIn("PENGADAAN_BARANG", names)
        self.assertIn("PEKERJAAN_KONSTRUKSI", names)


class TestNormalizeHostValidation(unittest.TestCase):

    def test_valid(self):
        result = normalize_host_validation(True, "kemenkeu", "https://spse.inaproc.id/kemenkeu", "OK")
        self.assertTrue(result["valid"])
        self.assertEqual(result["host"], "kemenkeu")

    def test_invalid(self):
        result = normalize_host_validation(False, "badhost", "https://spse.inaproc.id/badhost", "Not accessible")
        self.assertFalse(result["valid"])


if __name__ == '__main__':
    unittest.main()
