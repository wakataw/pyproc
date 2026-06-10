"""Mocked unit tests for pyproc.utils."""

import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pyproc.utils


HOST_FIXTURE = [
    {
        "name": "Kementerian Keuangan > LPSE Kementerian Keuangan",
        "oldUrl": "https://lpse.kemenkeu.go.id",
        "newUrlPath": "kemenkeu",
    },
    {
        "name": "Invalid Host",
        "oldUrl": "https://legacy.example.test",
        "newUrlPath": "",
    },
]


class TestHostExports(unittest.TestCase):

    def test_get_host_metadata_strips_old_url(self):
        response = MagicMock()
        response.json.return_value = HOST_FIXTURE
        response.raise_for_status.return_value = None

        with patch("pyproc.utils.requests.get", return_value=response):
            data = pyproc.utils.get_host_metadata()

        self.assertEqual(data[0]["newUrlPath"], "kemenkeu")
        self.assertNotIn("oldUrl", data[0])

    def test_download_host_uses_gist_metadata_and_new_url_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "hosts.csv"
            with patch("pyproc.utils.get_host_metadata", return_value=HOST_FIXTURE):
                pyproc.utils.download_host(name=str(output))

            with output.open(newline="", encoding="utf-8") as f:
                rows = list(csv.reader(f, delimiter=";"))

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], "https://spse.inaproc.id/kemenkeu")
        self.assertEqual(rows[0][1], "Kementerian Keuangan > LPSE Kementerian Keuangan")
        self.assertNotIn("lpse.kemenkeu.go.id", rows[0][0])

    def test_old_get_all_host_removed(self):
        self.assertFalse(hasattr(pyproc.utils, "get_all_host"))


if __name__ == "__main__":
    unittest.main()
