import time
import unittest
from pyproc.cli import *


class DownloaderTest(unittest.TestCase):
    LPSE_HOST_1 = 'kemenkeu'
    LPSE_HOST_2 = 'sumbarprov'
    LPSE_HOST_2_FILENAME = 'sumbarprov'
    LPSE_HOST_3 = 'bengkuluprov'
    LPSE_HOST_3_FILENAME = 'bengkuluprov'

    def test_context_parser(self):
        downloader = Downloader()
        ctx = downloader.get_ctx("--keyword WKWK --tahun-anggaran 2020 --workers 999 --chunk-size 1000 --timeout 99 "
                                 "--non-tender --index-download-delay 5 --keep-index "
                                 "--kategori PEKERJAAN_KONSTRUKSI --nama-penyedia HAHA --resume --sep | "
                                 f"{self.LPSE_HOST_2}".split(' '))
        expected_condition = {
            '_DownloaderContext__lpse_host': self.LPSE_HOST_2,
            'chunk_size': 1000,
            'keep_index': True,
            'index_download_delay': 5,
            '_kategori': "PEKERJAAN_KONSTRUKSI",
            'keyword': 'WKWK',
            'nama_penyedia': "HAHA",
            'non_tender': True,
            'tahun_anggaran': [2020],
            'timeout': 99,
            'log_level': 'INFO',
            'output_format': 'csv',
            'resume': True,
            'separator': '|',
            'workers': 1
        }

        for key, v in ctx.__dict__.items():
            self.assertEqual(v, expected_condition[key])

    def test_tahun_anggaran_parser_single_tahun(self):
        downloader = Downloader()
        ctx = downloader.get_ctx(f"--tahun-anggaran 2015 {self.LPSE_HOST_2}".split(' '))
        self.assertEqual([2015], ctx.tahun_anggaran)

    def test_tahun_anggaran_parser_multiple_tahun(self):
        downloader = Downloader()
        ctx = downloader.get_ctx(F"--tahun-anggaran 2015,2016,2020 {self.LPSE_HOST_2}".split(' '))
        self.assertEqual([2015, 2016, 2020], ctx.tahun_anggaran)

    def test_tahun_anggaran_parser_range_tahun(self):
        downloader = Downloader()
        ctx = downloader.get_ctx(f"--tahun-anggaran 2015-2020 {self.LPSE_HOST_2}".split(' '))
        self.assertEqual([i for i in range(2015,2021)], ctx.tahun_anggaran)

    def test_tahun_anggaran_parser_range_and_multiple_tahun(self):
        downloader = Downloader()
        ctx = downloader.get_ctx(f"--tahun-anggaran 2015-2020,2013,2012 {self.LPSE_HOST_2}".split(' '))
        self.assertEqual([2012, 2013, 2015, 2016, 2017, 2018, 2019, 2020], ctx.tahun_anggaran)

    def test_tahun_anggaran_parser_invalid_format_1(self):
        downloader = Downloader()
        self.assertRaises(DownloaderContextException, downloader.get_ctx,
                          f"--tahun-anggaran 2015;2020 {self.LPSE_HOST_2}".split(' '))

    def test_tahun_anggaran_parser_invalid_value(self):
        downloader = Downloader()
        self.assertRaises(DownloaderContextException, downloader.get_ctx,
                          f"--tahun-anggaran 1999-2030 {self.LPSE_HOST_2}".split(' '))

    def test_lpse_host_parser(self):
        downloader = Downloader()
        ctx = downloader.get_ctx(f"--log=DEBUG {self.LPSE_HOST_2}".split(' '))

        for i in ctx.lpse_host_list:
            self.assertTrue(i.is_valid)
            self.assertIsNone(i.error)
            self.assertEqual(self.LPSE_HOST_2, i.url)
            self.assertEqual(self.LPSE_HOST_2_FILENAME, i.filename.name)

    def test_lpse_host_multiple(self):
        downloader = Downloader()
        ctx = downloader.get_ctx(f"--log=DEBUG {self.LPSE_HOST_2},{self.LPSE_HOST_3}".split(' '))
        urls = [self.LPSE_HOST_2, self.LPSE_HOST_3]
        filename = [self.LPSE_HOST_2_FILENAME, self.LPSE_HOST_3_FILENAME]

        for i in ctx.lpse_host_list:
            self.assertTrue(i.is_valid)
            self.assertIsNone(i.error)
            self.assertTrue(i.url in urls and i.filename.name in filename)

    def test_lpse_host_single_with_filename(self):
        downloader = Downloader()
        ctx = downloader.get_ctx(f"--log=DEBUG {self.LPSE_HOST_2};{self.LPSE_HOST_2_FILENAME}".split(' '))

        for i in ctx.lpse_host_list:
            self.assertTrue(i.is_valid)
            self.assertIsNone(i.error)
            self.assertEqual(self.LPSE_HOST_2, i.url)
            self.assertEqual(self.LPSE_HOST_2_FILENAME, i.filename.name)

    def test_lpse_host_multiple_with_filename(self):
        downloader = Downloader()
        ctx = downloader.get_ctx(f"--log=DEBUG {self.LPSE_HOST_2};1.csv,{self.LPSE_HOST_3};2.csv".split(' '))
        urls = [self.LPSE_HOST_2, self.LPSE_HOST_3]
        filename = ['1.csv', '2.csv']

        for i in ctx.lpse_host_list:
            self.assertTrue(i.is_valid)
            self.assertIsNone(i.error)
            self.assertTrue(i.url in urls and i.filename.name in filename)

    def test_lpse_host_from_file(self):
        downloader = Downloader()
        file_path = Path(__file__).parent / 'supporting_files' / 'list-host.txt'
        ctx = downloader.get_ctx(["--log=DEBUG", file_path.as_posix()])
        urls = ['sumbarprov', 'bengkuluprov']
        filename = ['sumbarprov', 'bengkuluprov']

        for i in ctx.lpse_host_list:
            print(i)
            self.assertTrue(i.is_valid)
            self.assertIsNone(i.error)
            self.assertTrue(i.url in urls and i.filename.name in filename)

    def test_lpse_host_from_file_multiple_with_filename(self):
        downloader = Downloader()
        file_path = Path(__file__).parent / 'supporting_files' / 'list-host-with-filename.txt'
        ctx = downloader.get_ctx(["--log=DEBUG", file_path.as_posix()])
        urls = ['sumbarprov', 'bengkuluprov']
        filename = ['sumbar.csv', 'bengkulu.csv']

        for i in ctx.lpse_host_list:
            self.assertTrue(i.is_valid)
            self.assertIsNone(i.error)
            self.assertTrue(i.url in urls and i.filename.name in filename)

    def test_kategori_not_in_choices(self):
        downloader = Downloader()
        self.assertRaises(SystemExit, downloader.get_ctx, f"--kategori HOHO {self.LPSE_HOST_2}".split())

    def test_get_records_total(self):
        downloader = Downloader()
        downloader.get_ctx(f"--log=DEBUG --kategori PEKERJAAN_KONSTRUKSI {self.LPSE_HOST_2},{self.LPSE_HOST_3}".split())

        for lpse_host in downloader.ctx.lpse_host_list:
            index_downloader = IndexDownloader(downloader.ctx, lpse_host)
            total = index_downloader.get_total_package(tahun=2020)
            self.assertTrue(type(total), int)

    def test_download_index(self):
        from pathlib import Path
        import sqlite3
        downloader = Downloader()
        downloader.get_ctx(f"{self.LPSE_HOST_1};test-download-index --tahun-anggaran 2027 --keep-index".split())
        downloader.start()

        db_file = Path.cwd() / 'test-download-index.idx'
        self.assertTrue(db_file.is_file())

        db = sqlite3.connect(str(db_file))
        result = db.execute("SELECT COUNT(1) FROM INDEX_PAKET").fetchone()[0]
        self.assertTrue(result > 0)

    def test_index_db_row_factory(self):
        downloader = Downloader()
        downloader.get_ctx(f"--log=DEBUG {self.LPSE_HOST_1} --tahun-anggaran 2027".split())

        for lpse_host in downloader.ctx.lpse_host_list:
            index_downloader = IndexDownloader(downloader.ctx, lpse_host)
            index_downloader.start()

            for index in index_downloader.get_index():
                self.assertIsInstance(index, LpseIndex)

    def test_detail_downloader(self):
        downloader = Downloader()
        downloader.get_ctx(f"{self.LPSE_HOST_2}".split())

        downloader.ctx.tahun = 2027

        for lpse_host in downloader.ctx.lpse_host_list:
            index_downloader = IndexDownloader(downloader.ctx, lpse_host)

            index_downloader.start()

            detail_downloader = DetailDownloader(index_downloader)
            detail_downloader.start()

            res = index_downloader.db.execute("SELECT COUNT(1) FROM main.INDEX_PAKET WHERE STATUS = 1").fetchone()

            self.assertTrue(res[0] > 0)

    def __init_db(self):
        downloader = Downloader()
        downloader.get_ctx(f"--tahun-anggaran 2027 {self.LPSE_HOST_1}".split())

        logging.info("Start index download without detail")

        for lpse_host in downloader.ctx.lpse_host_list:
            index_downloader = IndexDownloader(downloader.ctx, lpse_host)
            index_downloader.start()

            total = index_downloader.db.execute("SELECT COUNT(1) FROM INDEX_PAKET WHERE DETAIL IS NOT NULL").fetchone()[0]
            self.assertEqual(total, 0)

    def test_resume_download(self):
        self.__init_db()
        downloader = Downloader()
        downloader.get_ctx(f"{self.LPSE_HOST_1} -r --tahun-anggaran 2027".split())

        logging.info("Start index download with detail")

        downloader.start()

        for lpse_host in downloader.ctx.lpse_host_list:
            index_downloader = IndexDownloader(downloader.ctx, lpse_host)
            total = index_downloader.db.execute("SELECT COUNT(1) FROM INDEX_PAKET WHERE DETAIL IS NULL").fetchone()[0]
            self.assertEqual(total, 0)

    def test_resume_without_db(self):
        """
        Test argument resume untuk lpse yang sebenarnya belum pernah didownload
        :return:
        """
        downloader = Downloader()
        timestamp = int(time.time())
        downloader.get_ctx(f"{self.LPSE_HOST_1};{timestamp} -r --tahun-anggaran 2027".split())

        downloader.start()

        for lpse_host in downloader.ctx.lpse_host_list:
            index_downloader = IndexDownloader(downloader.ctx, lpse_host)
            total = index_downloader.db.execute("SELECT COUNT(1) FROM INDEX_PAKET WHERE DETAIL IS NULL").fetchone()[0]
            self.assertEqual(total, 0)

    def test_downloader_separator(self):
        downloader = Downloader()
        downloader.get_ctx('kp2mi;sep --tahun 2026 --sep |'.split())
        downloader.start()

        with (Path.cwd() / 'sep.csv').open('r') as f:
            for row in csv.reader(f, delimiter="|"):
                print(len(row))
                self.assertTrue(len(row) > 0)
                break

    def test_clear_working_dir(self):
        downloader = Downloader()
        downloader.get_ctx(f"{self.LPSE_HOST_1};index-deleted --tahun-anggaran 2027".split())

        logging.info("Start index download with detail")

        downloader.start()

        index_path = Path.cwd() / 'index-deleted.idx'
        csv_path = Path.cwd() / 'index-deleted.csv'

        self.assertFalse(index_path.is_file())
        self.assertTrue(csv_path.is_file())

    def test_args_keep_index(self):
        downloader = Downloader()
        downloader.get_ctx(f"{self.LPSE_HOST_1};index-deleted --log DEBUG --tahun-anggaran 2027 --keep-index".split())

        logging.info("Start index download with detail")

        downloader.start()

        index_path = Path.cwd() / 'index-deleted.idx'
        csv_path = Path.cwd() / 'index-deleted.csv'

        self.assertTrue(index_path.is_file())
        self.assertTrue(csv_path.is_file())

    def tearDown(self):
        csv = Path.cwd().glob('*.csv')
        idx = Path.cwd().glob('*.idx')
        txt = Path.cwd().glob('*.txt')

        for i in csv:
            i.unlink()

        for i in idx:
            try:
                i.unlink()
            except:
                continue

        for i in txt:
            i.unlink()


if __name__ == '__main__':
    unittest.main()
