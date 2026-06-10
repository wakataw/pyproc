"""Mocked unit tests for CLI components — no network required."""
import csv
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from pyproc.cache import CacheStore
from pyproc.cli import (
    Downloader, DownloaderContext, LpseHost, LpseIndex,
    IndexDownloader, Exporter, QualityAssurance,
)
from pyproc.exceptions import DownloaderContextException


class TestLpseHost(unittest.TestCase):

    def test_parse_host_simple(self):
        host = LpseHost("kemenkeu")
        self.assertTrue(host.is_valid)
        self.assertIsNone(host.error)
        self.assertEqual(host.url, "kemenkeu")
        self.assertEqual(host.filename.name, "kemenkeu")

    def test_parse_host_with_filename(self):
        host = LpseHost("kemenkeu;my_output")
        self.assertTrue(host.is_valid)
        self.assertIsNone(host.error)
        self.assertEqual(host.url, "kemenkeu")
        self.assertEqual(host.filename.name, "my_output")

    def test_parse_host_url_with_dots(self):
        host = LpseHost("sumbarprov")
        self.assertTrue(host.is_valid)
        self.assertEqual(host.url, "sumbarprov")
        self.assertEqual(host.filename.name, "sumbarprov")

    def test_parse_host_generates_filename_from_url(self):
        host = LpseHost("bengkuluprov")
        self.assertTrue(host.is_valid)
        self.assertEqual(host.filename.name, "bengkuluprov")


class TestDownloaderContext(unittest.TestCase):

    def _make_args(self, **kwargs):
        """Create a mock args namespace with defaults."""
        defaults = {
            'lpse_host': 'kemenkeu',
            'keyword': '',
            'tahun_anggaran': '2025',
            'kategori': None,
            'nama_penyedia': None,
            'chunk_size': 100,
            'workers': 8,
            'timeout': 30,
            'jenis_paket': 'tender',
            'index_download_delay': 1,
            'keep_index': False,
            'log': 'INFO',
            'output_format': 'csv',
            'resume': False,
            'separator': ';',
        }
        defaults.update(kwargs)
        return MagicMock(**defaults)

    def test_basic_context(self):
        args = self._make_args()
        ctx = DownloaderContext(args)
        self.assertEqual(ctx.keyword, '')
        self.assertEqual(ctx.chunk_size, 100)
        self.assertEqual(ctx.timeout, 30)
        self.assertEqual(ctx.jenis_paket, 'tender')

    def test_tahun_anggaran_single(self):
        args = self._make_args(tahun_anggaran='2020')
        ctx = DownloaderContext(args)
        self.assertEqual(ctx.tahun_anggaran, [2020])

    def test_tahun_anggaran_multiple(self):
        args = self._make_args(tahun_anggaran='2020,2021,2022')
        ctx = DownloaderContext(args)
        self.assertEqual(ctx.tahun_anggaran, [2020, 2021, 2022])

    def test_tahun_anggaran_range(self):
        args = self._make_args(tahun_anggaran='2020-2023')
        ctx = DownloaderContext(args)
        self.assertEqual(ctx.tahun_anggaran, [2020, 2021, 2022, 2023])

    def test_tahun_anggaran_mixed(self):
        args = self._make_args(tahun_anggaran='2020-2022,2025')
        ctx = DownloaderContext(args)
        self.assertEqual(ctx.tahun_anggaran, [2020, 2021, 2022, 2025])

    def test_tahun_anggaran_all(self):
        args = self._make_args(tahun_anggaran='all')
        ctx = DownloaderContext(args)
        self.assertEqual(ctx.tahun_anggaran, [None])

    def test_tahun_anggaran_invalid_separator(self):
        args = self._make_args(tahun_anggaran='2020;2021')
        with self.assertRaises(DownloaderContextException):
            DownloaderContext(args)

    def test_tahun_anggaran_invalid_range(self):
        args = self._make_args(tahun_anggaran='1999-2030')
        with self.assertRaises(DownloaderContextException):
            DownloaderContext(args)

    def test_kategori_valid(self):
        args = self._make_args(kategori='PEKERJAAN_KONSTRUKSI')
        ctx = DownloaderContext(args)
        from pyproc.lpse import JenisPengadaan
        self.assertEqual(ctx.kategori, JenisPengadaan.PEKERJAAN_KONSTRUKSI)

    def test_kategori_invalid(self):
        args = self._make_args(kategori='INVALID')
        ctx = DownloaderContext(args)
        self.assertIsNone(ctx.kategori)

    def test_kategori_none(self):
        args = self._make_args(kategori=None)
        ctx = DownloaderContext(args)
        self.assertIsNone(ctx.kategori)

    def test_lpse_host_list_from_arg(self):
        args = self._make_args(lpse_host='kemenkeu')
        ctx = DownloaderContext(args)
        hosts = list(ctx.lpse_host_list)
        self.assertEqual(len(hosts), 1)
        self.assertEqual(hosts[0].url, 'kemenkeu')

    def test_lpse_host_list_multiple(self):
        args = self._make_args(lpse_host='kemenkeu,sumbarprov')
        ctx = DownloaderContext(args)
        hosts = list(ctx.lpse_host_list)
        self.assertEqual(len(hosts), 2)
        urls = [h.url for h in hosts]
        self.assertIn('kemenkeu', urls)
        self.assertIn('sumbarprov', urls)

    def test_lpse_host_list_from_file(self):
        file_path = Path(__file__).parent / 'supporting_files' / 'list-host.txt'
        args = self._make_args(lpse_host=str(file_path))
        ctx = DownloaderContext(args)
        hosts = list(ctx.lpse_host_list)
        self.assertEqual(len(hosts), 2)
        for h in hosts:
            self.assertTrue(h.is_valid)


class TestLpseIndex(unittest.TestCase):

    def test_from_kwargs(self):
        kwargs = {
            'row_id': 'tender-10080116000',
            'id_paket': '10080116000',
            'jenis_paket': 'tender',
            'kategori_tahun_anggaran': '2025',
            'status': 0,
            'detail': None,
        }
        idx = LpseIndex(kwargs)
        self.assertEqual(idx.row_id, 'tender-10080116000')
        self.assertEqual(idx.id_paket, '10080116000')
        self.assertEqual(idx.status, 0)
        # parse_detail(None) returns None after fix
        self.assertIsNone(idx.detail)

    def test_from_kwargs_with_detail(self):
        kwargs = {
            'row_id': 'tender-10080116000',
            'id_paket': '10080116000',
            'jenis_paket': 'tender',
            'kategori_tahun_anggaran': '2025',
            'status': 1,
            'detail': '{"pengumuman": {"kode_tender": "123"}}',
        }
        idx = LpseIndex(kwargs)
        self.assertIsNotNone(idx.detail)
        self.assertEqual(idx.detail['pengumuman']['kode_tender'], '123')

    def test_parse_detail_valid_json(self):
        detail_str = '{"pengumuman": {"kode_tender": "123"}}'
        result = LpseIndex.parse_detail(detail_str)
        self.assertIsInstance(result, dict)
        self.assertEqual(result['pengumuman']['kode_tender'], '123')

    def test_parse_detail_none(self):
        result = LpseIndex.parse_detail(None)
        self.assertIsNone(result)

    def test_parse_detail_invalid_json(self):
        result = LpseIndex.parse_detail('not json')
        self.assertIsNone(result)


class TestIndexDownloaderDB(unittest.TestCase):

    def test_create_schema(self):
        with tempfile.NamedTemporaryFile(suffix='.idx', delete=False) as f:
            db_path = Path(f.name)

        try:
            db = sqlite3.connect(str(db_path))
            db.execute("DROP TABLE IF EXISTS INDEX_PAKET")
            db.execute("""CREATE TABLE INDEX_PAKET
            (
            ROW_ID varchar(100) unique primary key,
            ID_PAKET VARCHAR(50),
            JENIS_PAKET VARCHAR(32),
            KATEGORI_TAHUN_ANGGARAN varchar (100),
            STATUS int default 0,
            DETAIL text
            );""")
            db.execute("CREATE INDEX INDEX_PAKET_KATEGORI_TAHUN_ANGGARAN_IDX ON INDEX_PAKET(KATEGORI_TAHUN_ANGGARAN);")
            db.execute("CREATE INDEX INDEX_PAKET_ID_PAKET_IDX ON INDEX_PAKET(ID_PAKET);")
            db.execute("CREATE INDEX INDEX_PAKET_JENIS_PAKET ON INDEX_PAKET(JENIS_PAKET);")
            db.execute("CREATE INDEX INDEX_PAKET_STATUS_IDX ON INDEX_PAKET(STATUS);")
            db.commit()

            # Verify table exists
            result = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='INDEX_PAKET'").fetchone()
            self.assertIsNotNone(result)

            # Verify indexes
            indexes = db.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='INDEX_PAKET'").fetchall()
            index_names = [i[0] for i in indexes]
            self.assertIn('INDEX_PAKET_KATEGORI_TAHUN_ANGGARAN_IDX', index_names)
            self.assertIn('INDEX_PAKET_STATUS_IDX', index_names)

            db.close()
        finally:
            db_path.unlink(missing_ok=True)

    def test_insert_and_query(self):
        with tempfile.NamedTemporaryFile(suffix='.idx', delete=False) as f:
            db_path = Path(f.name)

        try:
            db = sqlite3.connect(str(db_path))
            db.execute("""CREATE TABLE INDEX_PAKET (
                ROW_ID varchar(100) unique primary key,
                ID_PAKET VARCHAR(50),
                JENIS_PAKET VARCHAR(32),
                KATEGORI_TAHUN_ANGGARAN varchar(100),
                STATUS int default 0,
                DETAIL text
            )""")

            db.execute("INSERT INTO INDEX_PAKET VALUES (?, ?, ?, ?, ?, ?)",
                       ('tender-100', '100', 'tender', '2025', 0, None))
            db.execute("INSERT INTO INDEX_PAKET VALUES (?, ?, ?, ?, ?, ?)",
                       ('tender-200', '200', 'tender', '2025', 1, '{"pengumuman": {}}'))
            db.commit()

            # Query pending
            pending = db.execute("SELECT COUNT(1) FROM INDEX_PAKET WHERE STATUS = 0").fetchone()[0]
            self.assertEqual(pending, 1)

            # Query completed
            completed = db.execute("SELECT COUNT(1) FROM INDEX_PAKET WHERE STATUS = 1").fetchone()[0]
            self.assertEqual(completed, 1)

            # Update status
            db.execute("UPDATE INDEX_PAKET SET STATUS = 1, DETAIL = ? WHERE ROW_ID = ?",
                       ('{"pengumuman": {}}', 'tender-100'))
            db.commit()

            pending = db.execute("SELECT COUNT(1) FROM INDEX_PAKET WHERE STATUS = 0").fetchone()[0]
            self.assertEqual(pending, 0)

            db.close()
        finally:
            db_path.unlink(missing_ok=True)

    def test_insert_or_ignore(self):
        with tempfile.NamedTemporaryFile(suffix='.idx', delete=False) as f:
            db_path = Path(f.name)

        try:
            db = sqlite3.connect(str(db_path))
            db.execute("""CREATE TABLE INDEX_PAKET (
                ROW_ID varchar(100) unique primary key,
                ID_PAKET VARCHAR(50),
                JENIS_PAKET VARCHAR(32),
                KATEGORI_TAHUN_ANGGARAN varchar(100),
                STATUS int default 0,
                DETAIL text
            )""")

            db.execute("INSERT OR IGNORE INTO INDEX_PAKET VALUES (?, ?, ?, ?, ?, ?)",
                       ('tender-100', '100', 'tender', '2025', 0, None))
            db.execute("INSERT OR IGNORE INTO INDEX_PAKET VALUES (?, ?, ?, ?, ?, ?)",
                       ('tender-100', '100', 'tender', '2025', 0, None))
            db.commit()

            count = db.execute("SELECT COUNT(1) FROM INDEX_PAKET").fetchone()[0]
            self.assertEqual(count, 1)

            db.close()
        finally:
            db_path.unlink(missing_ok=True)


class TestExporter(unittest.TestCase):

    def _create_test_db(self):
        """Create a temporary SQLite DB with test data using CacheStore."""
        f = tempfile.NamedTemporaryFile(suffix='.idx', delete=False)
        f.close()
        db_path = Path(f.name)

        detail = {
            'id_paket': '10080116000',
            'pengumuman': {
                'nama_tender': 'Test Tender',
                'tanggal_pembuatan': '15 Januari 2025',
                'tahap_tender_saat_ini': 'Selesai',
                'k/l/pd': 'KEMENTERIAN KEUANGAN',
                'satuan_kerja': 'DJP',
                'jenis_pengadaan': 'Pengadaan Barang',
                'metode_pengadaan': 'Tender Terbuka',
                'tahun_anggaran': '2025',
                'nilai_pagu_paket': 1000000000,
                'nilai_hps_paket': 950000000,
                'jenis_kontrak': 'Lumpsum',
                'kualifikasi_usaha': 'Kecil',
                'peserta_tender': 5,
                'khusus_pelaku_usaha_oap': 'Tidak',
                'lokasi_pekerjaan': ['Jakarta'],
                'label_paket': ['Pengadaan Barang'],
            },
            'peserta': [{'nama_peserta': 'PT. Test'}],
            'hasil': [{'nama_peserta': 'PT. Test', 'pemenang': True}],
            'pemenang': [{'nama_pemenang': 'PT. Test', 'harga_penawaran': 900000000}],
            'pemenang_berkontrak': None,
            'jadwal': [{'tahap': 'Evaluasi', 'mulai': '20 Jan 2025'}],
        }

        with CacheStore(db_path) as store:
            store.create_schema()
            store.insert_rows([
                ('tender-10080116000', '10080116000', 'tender', '2025', 1, json.dumps(detail))
            ])

        return db_path

    def test_export_csv(self):
        db_path = self._create_test_db()
        csv_path = db_path.with_suffix('.csv')

        try:
            mock_index_downloader = MagicMock()
            store = CacheStore(db_path)
            store.__enter__()
            mock_index_downloader.store = store
            mock_index_downloader.ctx = MagicMock()
            mock_index_downloader.ctx.non_tender = False

            mock_host = MagicMock()
            mock_host.url = 'https://spse.inaproc.id/kemenkeu'
            mock_host.filename = csv_path.with_suffix('')
            mock_index_downloader.lpse_host = mock_host

            exporter = Exporter(mock_index_downloader)
            exporter.get_file_obj = lambda ext: db_path.with_suffix('.' + ext)

            exporter.to_csv(delimiter=';')

            self.assertTrue(csv_path.exists())

            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f, delimiter=';')
                rows = list(reader)
                self.assertGreater(len(rows), 1)  # header + data
                self.assertIn('url', rows[0])
                self.assertIn('id_paket', rows[0])

            store.close()
        finally:
            db_path.unlink(missing_ok=True)
            csv_path.unlink(missing_ok=True)

    def test_export_json(self):
        db_path = self._create_test_db()
        json_path = db_path.with_suffix('.json')

        try:
            mock_index_downloader = MagicMock()
            store = CacheStore(db_path)
            store.__enter__()
            mock_index_downloader.store = store
            mock_index_downloader.ctx = MagicMock()
            mock_index_downloader.ctx.non_tender = False

            mock_host = MagicMock()
            mock_host.url = 'https://spse.inaproc.id/kemenkeu'
            mock_host.filename = json_path.with_suffix('')
            mock_index_downloader.lpse_host = mock_host

            exporter = Exporter(mock_index_downloader)
            exporter.get_file_obj = lambda ext: db_path.with_suffix('.' + ext)

            exporter.to_json()

            self.assertTrue(json_path.exists())

            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.assertIsInstance(data, list)
                self.assertEqual(len(data), 1)
                self.assertIn('pengumuman', data[0])

            store.close()
        finally:
            db_path.unlink(missing_ok=True)
            json_path.unlink(missing_ok=True)


class TestQualityAssurance(unittest.TestCase):

    def test_check_counts(self):
        with tempfile.NamedTemporaryFile(suffix='.idx', delete=False) as f:
            db_path = Path(f.name)

        try:
            with CacheStore(db_path) as store:
                store.create_schema()
                rows = [(f'tender-{i}', str(i), 'tender', '2025', 1 if i < 5 else 0, None) for i in range(8)]
                store.insert_rows(rows)

                mock_index_downloader = MagicMock()
                mock_index_downloader.store = store

                qa = QualityAssurance(mock_index_downloader)
                total, success, fail = qa.check()

                self.assertEqual(total, 8)
                self.assertEqual(success, 5)
                self.assertEqual(fail, 3)
        finally:
            db_path.unlink(missing_ok=True)

    def test_check_empty_db(self):
        with tempfile.NamedTemporaryFile(suffix='.idx', delete=False) as f:
            db_path = Path(f.name)

        try:
            with CacheStore(db_path) as store:
                store.create_schema()

                mock_index_downloader = MagicMock()
                mock_index_downloader.store = store

                qa = QualityAssurance(mock_index_downloader)
                total, success, fail = qa.check()

                self.assertEqual(total, 0)
                self.assertEqual(success, 0)
                self.assertEqual(fail, 0)
        finally:
            db_path.unlink(missing_ok=True)


class TestDownloaderGetCtx(unittest.TestCase):

    def test_get_ctx_basic(self):
        downloader = Downloader()
        ctx = downloader.get_ctx(['kemenkeu'])
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx.keyword, '')

    def test_get_ctx_with_options(self):
        downloader = Downloader()
        ctx = downloader.get_ctx([
            '--keyword', 'sekolah',
            '--tahun-anggaran', '2025',
            '--timeout', '60',
            '--jenis-paket', 'non_tender',
            'kemenkeu'
        ])
        self.assertEqual(ctx.keyword, 'sekolah')
        self.assertEqual(ctx.tahun_anggaran, [2025])
        self.assertEqual(ctx.timeout, 60)
        self.assertEqual(ctx.jenis_paket, 'non_tender')

    def test_get_ctx_kategori_choices(self):
        downloader = Downloader()
        ctx = downloader.get_ctx(['--kategori', 'PEKERJAAN_KONSTRUKSI', 'kemenkeu'])
        from pyproc.lpse import JenisPengadaan
        self.assertEqual(ctx.kategori, JenisPengadaan.PEKERJAAN_KONSTRUKSI)

    def test_get_ctx_invalid_kategori_exits(self):
        downloader = Downloader()
        with self.assertRaises(SystemExit):
            downloader.get_ctx(['--kategori', 'INVALID', 'kemenkeu'])

    def test_get_ctx_resume_flag(self):
        downloader = Downloader()
        ctx = downloader.get_ctx(['--resume', 'kemenkeu'])
        self.assertTrue(ctx.resume)

    def test_get_ctx_keep_index_flag(self):
        downloader = Downloader()
        ctx = downloader.get_ctx(['--keep-index', 'kemenkeu'])
        self.assertTrue(ctx.keep_index)

    def test_get_ctx_output_format_json(self):
        downloader = Downloader()
        ctx = downloader.get_ctx(['--output-format', 'json', 'kemenkeu'])
        self.assertEqual(ctx.output_format, 'json')

    def test_get_ctx_separator(self):
        downloader = Downloader()
        ctx = downloader.get_ctx(['--separator', '|', 'kemenkeu'])
        self.assertEqual(ctx.separator, '|')


if __name__ == '__main__':
    unittest.main()
