import argparse
import re
import logging
import sqlite3
from time import sleep
from pyproc import Lpse
from scripts import text
from datetime import datetime
from pathlib import Path


def set_up_log(level):
    numeric_level = getattr(logging, level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError('Invalid log level: {}'.format(level))

    logging.basicConfig(level=numeric_level, format='[%(asctime)s %(levelname)s] %(message)s')


class DownloaderContextException(Exception):
    pass


class LpseHost(object):

    def __init__(self, args):
        self.is_valid = False
        self.error = None
        self.url, self.filename = self.parse_host(args)

    def parse_host(self, args):
        # cek jika terdapat skema url
        if not args.startswith('http'):
            self.error = text.ERROR_CTX_HOST_SKEMA
            return None, None

        url_and_filename = args.split(';')
        logging.debug("Url dan Filename {}".format(url_and_filename))

        # cek jika hasil split lebih < 1 atau lebih dari 2
        if len(url_and_filename) < 1 or len(url_and_filename) > 2:
            self.error = text.ERROR_CTX_HOST_FORMAT.format(args)
            return None, None

        # split url dan filename, jika filename tidak disediakan, generate filename berdasarkan hostname
        url = url_and_filename[0]
        try:
            filename = url_and_filename[1]
        except IndexError:
            filename = '_'.join(re.findall(r'([a-z0-9]+)', url.lower())) + '.csv'

        # set host is valid
        self.is_valid = True

        logging.debug("Hasil parsing {} & {}".format(url, filename))
        return [url, Path.cwd() / filename]

    def __str__(self):
        return str(self.__dict__)


class DownloaderContext(object):
    """
    Objek untuk menyimpan downloader context
    """

    def __init__(self, args):
        self.keyword = args.keyword
        self.tahun_anggaran = self.parse_tahun_anggaran(args.tahun_anggaran)
        self.kategori = args.kategori
        self.nama_penyedia = args.nama_penyedia
        self.chunk_size = args.chunk_size
        self.workers = args.workers
        self.timeout = args.timeout
        self.non_tender = args.non_tender
        self.index_download_delay = args.index_download_delay
        self.keep_workdir = args.keep_workdir
        self.force = args.force
        self.clear = args.clear
        self.__lpse_host = args.lpse_host

    def parse_tahun_anggaran(self, tahun_anggaran):
        """
        Parse tahun anggaran untuk menghasilkan list dari tahun anggaran yang akan diunduh
        :param tahun_anggaran: argumen tipe string dengan format X-Y (untuk range tahun anggaran) dan A,B,X,Z untuk beberapa tahun anggaran
        :return: list dari tahun anggaran
        """
        tahun_anggaran = re.sub(r'\s+', '', tahun_anggaran)
        list_tahun_anggaran = []

        # split argumen tahun anggaran berdasarkan separator koma
        for i in tahun_anggaran.split(','):
            try:
                # untuk setiap item, split berdasarkan dash lalu convert integer
                # raise exception jika proses convert gagal, atau nilai tahun tidak berada antara 2000
                # dan tahun berjalan
                range_tahun = list(map(lambda x: int(x), i.split('-')))

                for tahun in range(min(range_tahun), max(range_tahun) + 1):
                    if not 200 < tahun <= datetime.now().year:
                        raise DownloaderContextException(text.ERROR_CTX_RANGE_TAHUN.format(datetime.now().year))
                    list_tahun_anggaran.append(tahun)
            except ValueError:
                raise DownloaderContextException(text.ERROR_CTX_TAHUN_ANGGARAN)

        list_tahun_anggaran = list(set(list_tahun_anggaran))
        list_tahun_anggaran.sort()

        if not list_tahun_anggaran:
            raise DownloaderContextException(text.ERROR_CTX_TAHUN_ANGGARAN)

        return list_tahun_anggaran

    def __get_host_from_file(self, file):
        logging.debug("List LPSE host dari file")
        with file.open('r') as f:
            for line in f:
                logging.debug("Parsing host {}".format(line.strip()))
                yield LpseHost(line.strip())

    def __get_host_from_argumen(self, arg):
        logging.debug("List LPSE host dari argumen {}".format(arg))
        for line in arg.strip().split(','):
            logging.debug("Parsing host {}".format(line))
            yield LpseHost(line)

    @property
    def lpse_host_list(self):
        """
        Parse argument host, asumsi awal nilai yang diberikan oleh user adalah nama file. Jika file tidak ditemukan,
        nilai tersebut dianggap sebagai host name dari aplikasi SPSE instansi.
        :return:
        """
        lpse_host_file = Path.cwd() / self.__lpse_host
        try:
            host_is_file = lpse_host_file.is_file()
        except OSError:
            host_is_file = False

        if host_is_file:
            host_generator = self.__get_host_from_file(lpse_host_file)
        else:
            host_generator = self.__get_host_from_argumen(self.__lpse_host)

        return host_generator

    def __str__(self):
        return str(self.__dict__)


class LpseIndex():
    """Lpse Index object"""

    def __init__(self, kwargs):
        self.row_id = kwargs['row_id']
        self.id_paket = kwargs['id_paket']
        self.jenis_paket = kwargs['jenis_paket']
        self.kategori_tahun_anggaran = kwargs['kategori_tahun_anggaran']
        self.status = kwargs['status']

    def __str__(self):
        return str(self.__dict__)


class IndexDownloader(object):

    def __init__(self, ctx, lpse_host):
        self.ctx = ctx
        self.lpse_host = lpse_host
        self.lpse = Lpse(lpse_host.url)
        self.db = self.get_index_db(self.lpse_host.filename)
        self.db.row_factory = self.index_factory

    def get_index_db(self, filename):
        """
        Generate index database and table
        table columns:
            - data_id, concat(jenis, idpaket).
            - nama_instansi
            - jenis_paket
            - kategori_tahun_anggaran
            - status (0 belum download, 1 oke)
        :param filename: Database Filename
        :return: SQLite database object
        """
        db_filename = filename.name + ".idx"
        db_file = Path.cwd() / db_filename
        logging.debug("Generate index database: {}".format(db_file.name))
        db = sqlite3.connect(db_file)
        logging.debug("Create index table")

        try:
            db.execute("DROP TABLE IF EXISTS INDEX_PAKET")
            db.execute("""CREATE TABLE INDEX_PAKET
            (
            ROW_ID varchar(100) unique primary key,
            ID_PAKET VARCHAR(50),
            JENIS_PAKET VARCHAR(32),
            KATEGORI_TAHUN_ANGGARAN varchar (100),
            STATUS int default 0
            );""")
            db.execute("CREATE INDEX INDEX_PAKET_KATEGORI_TAHUN_ANGGARAN_IDX ON INDEX_PAKET(KATEGORI_TAHUN_ANGGARAN);")
            db.execute("CREATE INDEX INDEX_PAKET_ID_PAKET_IDX ON INDEX_PAKET(ID_PAKET);")
            db.execute("CREATE INDEX INDEX_PAKET_JENIS_PAKET ON INDEX_PAKET(JENIS_PAKET);")
            db.execute("CREATE INDEX INDEX_PAKET_STATUS_IDX ON INDEX_PAKET(STATUS);")
        except sqlite3.OperationalError as e:
            if 'INDEX_PAKET already exists' in str(e):
                pass
            else:
                raise e

        db.commit()

        return db

    def get_jenis_paket(self):
        """
        Wrapper variable jenis paket
        :return:
        """
        if self.ctx.non_tender:
            jenis_paket = 'pl'
        else:
            jenis_paket = 'lelang'

        return jenis_paket

    def get_total_package(self):
        """
        Fungsi untuk mendapatkan total data dengan melakukan requests dengan length 0 data
        :return: Integer jumlah data
        """
        jenis_paket = self.get_jenis_paket()

        data = self.lpse.get_paket(jenis_paket=jenis_paket, kategori=self.ctx.kategori,
                                   nama_penyedia=self.ctx.nama_penyedia, search_keyword=self.ctx.keyword)

        logging.debug("Jumlah record {}".format(str(data)))
        return data['recordsTotal']

    def start(self):
        """
        Start index downloader
        :return:
        """
        total = self.get_total_package()
        batch_total = -(-total//self.ctx.chunk_size)

        for batch in range(batch_total):
            logging.debug("Starting batch {} for host {}".format(batch, self.lpse_host.url))
            data = self.lpse.get_paket(jenis_paket=self.get_jenis_paket(), start=batch*self.ctx.chunk_size,
                                       length=self.ctx.chunk_size, kategori=self.ctx.kategori,
                                       search_keyword=self.ctx.keyword, nama_penyedia=self.ctx.nama_penyedia,
                                       data_only=True)
            self.db.executemany("INSERT OR IGNORE INTO INDEX_PAKET VALUES(?, ?, ?, ?, ?)",
                                self.convert_index_for_db(data))
            self.db.commit()

            sleep(self.ctx.index_download_delay)

    def convert_index_for_db(self, data):
        """
        Fungsi untuk menyesuaikan format index dari aplikasi spse ke database
        :param data:
        :return:
        """
        for row in data:
            yield [
                '{}-{}'.format('nontender' if self.ctx.non_tender else 'tender', row[0]),
                row[0],
                'nontender' if self.ctx.non_tender else 'tender',
                row[8],
                0
            ]

    @staticmethod
    def index_factory(cursor, row):
        d = {}
        for idx, col in enumerate(cursor.description):
            d[col[0].lower()] = row[idx]

        return LpseIndex(d)

    def get_index(self):
        logging.debug("[SQL] get index from database")
        result = self.db.execute("SELECT * FROM INDEX_PAKET")

        for row in result.fetchall():
            logging.debug("row data {}".format(row))
            yield row

    def resume(self):
        """
        Fungsi untuk melanjutkan proses pengunduhan index berdasarkan kondisi terakhir
        :return:
        """
        pass

    def __del__(self):
        """
        Make sure everything is closed when object is garbage collected
        :return:
        """
        if self.db:
            self.db.close()
            del self.db

        del self.lpse


class DetailDownloader(object):

    def __init__(self, index_downloader):
        self.index_downloader = index_downloader

    def start(self):
        pass


class Downloader(object):

    ctx = None

    def __init__(self):
        print(text.INFO)

    def get_ctx(self, sys_args):
        """
        Parse command line argument.
        -h, --help                  : menampilkan pesan bantuan
        -k, --keyword               : filter pencarian index paket berdasarkan kata kunci
        -t, --tahun-anggaran        : filter download detail berdasarkan tahun anggaran,
                                      format X-Y atau X;Y;Z
        --kategori                  : filter pencarian index paket berdasarkan kategori
        --nama-penyedia             : filter pencarian index paket berdasarkan nama penyedia
        -c, --chunk-size            : jumlah index per-halaman yang diunduh dalam satu iterasi
        -w, --workers               : jumlah workers yang berjalan secara paralel untuk mengunduh detail paket
        -x, --timeout               : waktu timeout respon dari server dalam detik
        -n, --non-tender            : flag untuk melakukan pengunduhan data paket pengadaan langsung
        -d, --index-download-delay  : waktu delay untuk setiap iterasi halaman index dalam detik
        -k, --keep-workdir          : tidak menghapus working direktori dari downloader
        -f, --force                 : menjalankan program tanpa memperhatikan cache yang sudah ada sebelumnya
        --clear                     : membersihkan folder cache di direktori home
        LPSE_HOST                   : host LPSE atau file teks berisi daftar host LPSE.
                                      Jika terdapat file teks dengan nama yang sama dengan hostname LPSE, prioritas
                                      pertama dari program adalah membaca file.
        :return: Lpse Downloader Context
        """
        parser = argparse.ArgumentParser()
        parser.add_argument('lpse_host', type=str, help=text.HELP_LPSE_HOST)
        parser.add_argument('-k', '--keyword', type=str, default="", help=text.HELP_KEYWORD)
        parser.add_argument('-t', '--tahun-anggaran', type=str, default="{}".format(datetime.now().year),
                            help=text.HELP_TAHUN_ANGGARAN)
        parser.add_argument('--kategori',
                            choices=['PENGADAAN_BARANG', 'PEKERJAAN_KONSTRUKSI', 'KONSULTANSI', 'KONSULTANSI_PERORANGAN'
                                     'JASA_LAINNYA', None],
                            help=text.HELP_KATEGORI, default=None)
        parser.add_argument('--nama-penyedia', type=str, default=None, help=text.HELP_PENYEDIA)
        parser.add_argument('-c', '--chunk-size', type=int, default=100, help=text.HELP_CHUNK_SIZE)
        parser.add_argument('-w', '--workers', type=int, default=8, help=text.HELP_WORKERS)
        parser.add_argument('-x', '--timeout', type=int, default=30, help=text.HELP_TIMEOUT)
        parser.add_argument('-n', '--non-tender', action='store_true', help=text.HELP_NONTENDER)
        parser.add_argument('-d', '--index-download-delay', type=int, default=1, help=text.HELP_INDEX_DOWNLOAD_DELAY)
        parser.add_argument('-f', '--force', action='store_true', help=text.HELP_FORCE)
        parser.add_argument('--clear', action='store_true', help=text.HELP_CLEAR)
        parser.add_argument('--keep-workdir', action='store_true', help=text.HELP_KEEP)
        parser.add_argument('--log', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], default='INFO',
                            help=text.HELP_LOG_LEVEL)

        args = parser.parse_args(sys_args)

        set_up_log(args.log)

        logging.debug('Parsing context')

        self.ctx = DownloaderContext(args)

        return self.ctx

    def download_index(self):
        for lpse_host in self.ctx.lpse_host_list:
            index_downloader = IndexDownloader(self.ctx, lpse_host)
            index_downloader.start()
            del index_downloader


if __name__ == '__main__':
    import sys

    downloader = Downloader()
    downloader.get_ctx(sys.argv[1:])
