"""Tests for pyproc.mcp.hosts — LPSE host discovery helpers."""

import unittest
from unittest.mock import patch
import requests

from pyproc.mcp import hosts


HOST_FIXTURE = [
    {
        "name": "Kementerian Keuangan > LPSE Kementerian Keuangan",
        "oldUrl": "https://lpse.kemenkeu.go.id",
        "newUrlPath": "kemenkeu",
    },
    {
        "name": "Pemerintah Provinsi DKI Jakarta > LPSE Provinsi DKI Jakarta",
        "oldUrl": "https://lpse.jakarta.go.id",
        "newUrlPath": "jakarta",
    },
    {
        "name": "Kementerian Pekerjaan Umum dan Perumahan Rakyat > LPSE Kementerian PUPR",
        "oldUrl": "https://lpse.pu.go.id",
        "newUrlPath": "pu",
    },
]


class TestHostDiscovery(unittest.TestCase):

    def setUp(self):
        hosts.reset_host_cache()

    def tearDown(self):
        hosts.reset_host_cache()

    def test_normalize_host_record(self):
        result = hosts.normalize_host_record(HOST_FIXTURE[0])
        self.assertEqual(result["host"], "kemenkeu")
        self.assertEqual(result["name"], "Kementerian Keuangan > LPSE Kementerian Keuangan")
        self.assertEqual(result["url"], "https://spse.inaproc.id/kemenkeu")
        self.assertEqual(result["source"], "gist")
        self.assertNotIn("oldUrl", result)
        self.assertNotIn("source_url", result)
        self.assertIn("kementerian keuangan", result["aliases"])

    def test_search_kementerian_keuangan_returns_kemenkeu(self):
        with patch("pyproc.mcp.hosts.utils.get_host_metadata", return_value=HOST_FIXTURE):
            result = hosts.search_lpse_hosts("kementerian keuangan")

        self.assertGreaterEqual(result["count"], 1)
        self.assertEqual(result["hosts"][0]["host"], "kemenkeu")
        self.assertGreaterEqual(result["hosts"][0]["match_score"], 0.9)

    def test_search_abbreviation_returns_host(self):
        with patch("pyproc.mcp.hosts.utils.get_host_metadata", return_value=HOST_FIXTURE):
            result = hosts.search_lpse_hosts("pu")

        self.assertEqual(result["hosts"][0]["host"], "pu")

    def test_search_nasional_builtin_host(self):
        with patch("pyproc.mcp.hosts.utils.get_host_metadata", return_value=HOST_FIXTURE):
            result = hosts.search_lpse_hosts("nasional")

        self.assertEqual(result["hosts"][0]["host"], "nasional")
        self.assertEqual(result["hosts"][0]["source"], "builtin")
        self.assertEqual(result["hosts"][0]["url"], "https://spse.inaproc.id/nasional")

    def test_search_returns_multiple_candidates_for_common_query(self):
        with patch("pyproc.mcp.hosts.utils.get_host_metadata", return_value=HOST_FIXTURE):
            result = hosts.search_lpse_hosts("kementerian", limit=3)

        self.assertGreaterEqual(result["count"], 2)
        returned_hosts = [item["host"] for item in result["hosts"]]
        self.assertIn("kemenkeu", returned_hosts)
        self.assertIn("pu", returned_hosts)

    def test_host_detail(self):
        with patch("pyproc.mcp.hosts.utils.get_host_metadata", return_value=HOST_FIXTURE):
            result = hosts.get_lpse_host_detail("kemenkeu")

        self.assertEqual(result["host"], "kemenkeu")

    def test_host_detail_nasional_builtin_host(self):
        with patch("pyproc.mcp.hosts.utils.get_host_metadata", return_value=HOST_FIXTURE):
            result = hosts.get_lpse_host_detail("nasional")

        self.assertEqual(result["host"], "nasional")
        self.assertEqual(result["source"], "builtin")
        self.assertIn("usage_hint", result)

    def test_host_list_is_cached(self):
        with patch("pyproc.mcp.hosts.utils.get_host_metadata", return_value=HOST_FIXTURE) as get_host_metadata:
            hosts.search_lpse_hosts("kementerian keuangan")
            hosts.search_lpse_hosts("jakarta")

        get_host_metadata.assert_called_once()

    def test_refresh_bypasses_cache(self):
        with patch("pyproc.mcp.hosts.utils.get_host_metadata", return_value=HOST_FIXTURE) as get_host_metadata:
            hosts.search_lpse_hosts("kementerian keuangan")
            hosts.search_lpse_hosts("kementerian keuangan", refresh=True)

        self.assertEqual(get_host_metadata.call_count, 2)

    def test_metadata_timeout_has_host_specific_error(self):
        with patch("pyproc.mcp.hosts.utils.get_host_metadata", side_effect=requests.exceptions.Timeout):
            with self.assertRaises(hosts.HostMetadataError) as ctx:
                hosts.search_lpse_hosts("kementerian keuangan")

        self.assertIn("Host metadata source timed out", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
