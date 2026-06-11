import argparse
import csv
import re
import logging
import random
import signal
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from time import sleep

import requests
import pyproc
import json
from time import sleep
from .exceptions import DownloaderContextException
from .cache import CacheStore
from . import text
from datetime import datetime
from pathlib import Path


PACKAGE_TYPES = {
    'tender': {
        'label': 'Tender',
        'search_method': 'get_paket_tender',
        'detail_method': 'detil_paket_tender',
        'cache_prefix': 'tender',
        'year_column': 8,
    },
    'non_tender': {
        'label': 'Non Tender',
        'search_method': 'get_paket_non_tender',
        'detail_method': 'detil_paket_non_tender',
        'cache_prefix': 'non_tender',
        'year_column': 6,
    },
    'pencatatan_non_tender': {
        'label': 'Pencatatan Non Tender',
        'search_method': 'get_paket_pencatatan_non_tender',
        'detail_method': 'detil_paket_pencatatan_non_tender',
        'cache_prefix': 'pencatatan_non_tender',
        'year_column': 6,
    },
    'swakelola': {
        'label': 'Swakelola',
        'search_method': 'get_paket_swakelola',
        'detail_method': 'detil_paket_swakelola',
        'cache_prefix': 'swakelola',
        'year_column': 5,
    },
    'darurat': {
        'label': 'Pengadaan Darurat',
        'search_method': 'get_paket_pengadaan_darurat',
        'detail_method': 'detil_paket_pengadaan_darurat',
        'cache_prefix': 'darurat',
        'year_column': 4,
    },
}


def set_up_log(level):
    """
    Set log level berdasarkan argumen yang diberikan user
    :param level:
    :return:
    """
    numeric_level = getattr(logging, level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError('Invalid log level: {}'.format(level))

    logging.basicConfig(level=numeric_level, format='[%(asctime)s %(levelname)s] %(message)s')


def check_new_version():
    resp = requests.get('https://pypi.org/pypi/pyproc/json').json()
    current_version = pyproc.__version__
    pypi_version = resp['info']['version']
    status = current_version != pypi_version

    return status, current_version, pypi_version


class IWillFindYouAndIWillKillYou:
    def __init__(self):
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)

    def exit_gracefully(self, *args):
        logging.debug("Get {} signal".format(args))
        logging.error("Proses dibatalkan user")
        exit(1)


class LpseHost(object):

    def __init__(self, args):
        self.is_valid = False
        self.error = None
        self.url, self.filename = self.parse_host(args)

    def parse_host(self, args):
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
            filename = '_'.join(re.findall(r'([a-z0-9]+)', url.lower()))

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
        self._kategori = args.kategori
        rekanan = getattr(args, 'rekanan', None)
        nama_penyedia = getattr(args, 'nama_penyedia', None)
        self.nama_penyedia = (rekanan if isinstance(rekanan, str) else None) or \
            (nama_penyedia if isinstance(nama_penyedia, str) else None)
        self.chunk_size = args.chunk_size
        self.workers = args.workers
        self.timeout = args.timeout
        jenis_paket = getattr(args, 'jenis_paket', 'tender')
        self.jenis_paket = jenis_paket if isinstance(jenis_paket, str) else 'tender'
        self.non_tender = self.jenis_paket == 'non_tender'
        instansi_id = getattr(args, 'instansi_id', None)
        tipe_swakelola_id = getattr(args, 'tipe_swakelola_id', None)
        self.instansi_id = instansi_id if isinstance(instansi_id, str) else None
        self.tipe_swakelola_id = tipe_swakelola_id if isinstance(tipe_swakelola_id, int) else None
        self.index_download_delay = args.index_download_delay
        self.keep_index = args.keep_index
        self.log_level = args.log
        self.output_format = args.output_format
        self.resume = args.resume
        self.separator = args.separator
        self.__lpse_host = args.lpse_host
        if self.jenis_paket == 'swakelola' and self._kategori:
            raise DownloaderContextException('--kategori tidak berlaku untuk jenis paket swakelola')
        if self.tipe_swakelola_id is not None and self.jenis_paket != 'swakelola':
            raise DownloaderContextException('--tipe-swakelola-id hanya berlaku untuk jenis paket swakelola')

    @property
    def package_config(self):
        return PACKAGE_TYPES[self.jenis_paket]

    @property
    def rekanan(self):
        return self.nama_penyedia

    @property
    def kategori(self):
        try:
            return pyproc.JenisPengadaan[self._kategori]
        except KeyError:
            return None

    def parse_tahun_anggaran(self, tahun_anggaran):
        """
        Parse tahun anggaran untuk menghasilkan list dari tahun anggaran yang akan diunduh
        :param tahun_anggaran: argumen tipe string dengan format X-Y (untuk range tahun anggaran) dan A,B,X,Z untuk beberapa tahun anggaran
        :return: list dari tahun anggaran
        """
        list_tahun_anggaran = []

        if tahun_anggaran.lower().strip() == 'all':
            return [None]

        tahun_anggaran = re.sub(r'\s+', '', tahun_anggaran)

        # split argumen tahun anggaran berdasarkan separator koma
        for i in tahun_anggaran.split(','):
            try:
                # untuk setiap item, split berdasarkan dash lalu convert integer
                # raise exception jika proses convert gagal, atau nilai tahun tidak berada antara 2000
                # dan tahun berjalan
                range_tahun = list(map(lambda x: int(x), i.split('-')))

                for tahun in range(min(range_tahun), max(range_tahun) + 1):
                    if not 2000 < tahun <= datetime.now().year + 5:
                        raise DownloaderContextException(text.ERROR_CTX_RANGE_TAHUN.format(datetime.now().year + 5))
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


class LpseIndex:
    def __init__(self, kwargs):
        self.row_id = kwargs['row_id']
        self.id_paket = kwargs['id_paket']
        self.jenis_paket = kwargs['jenis_paket']
        self.kategori_tahun_anggaran = kwargs['kategori_tahun_anggaran']
        self.status = kwargs['status']
        self.detail = self.parse_detail(kwargs['detail'])

    @staticmethod
    def parse_detail(detail):
        try:
            return json.loads(detail)
        except (TypeError, json.JSONDecodeError, ValueError):
            return None

    def __str__(self):
        return str(self.__dict__)


class IndexDownloader(object):
    __tahun_anggaran_pattern = re.compile(r'(\d+)')
    store = None
    db_status_for_resume = False
    db_file = None
    lpse = None

    def __init__(self, ctx, lpse_host):
        self.ctx = ctx
        self.lpse_host = lpse_host
        self.lpse = pyproc.Lpse(lpse_host.url, timeout=ctx.timeout)
        self.store = self._init_cache(self.lpse_host.filename)
        # Keep self.db as alias for backward compatibility
        self.db = self.store.db

        logging.info("{} - Mulai pengunduhan data {} tahun {}".format(
            lpse_host.url, "Pengadaan Langsung" if self.ctx.non_tender else "Tender",
            ', '.join(map(str, self.ctx.tahun_anggaran)) if self.ctx.tahun_anggaran[0] is not None else 'ALL'
        ))

    def _init_cache(self, filename):
        """
        Initialize the cache store for this downloader.

        :param filename: Path object for the host filename
        :return: CacheStore instance (already entered as context manager)
        """
        db_filename = filename.name + ".idx"
        self.db_file = Path.cwd() / db_filename

        store = CacheStore(self.db_file)
        store.__enter__()

        if self.ctx.resume and store.has_rows():
            logging.info("{} - skip db init, melanjutkan proses".format(self.lpse_host.url))
            self.db_status_for_resume = True
            return store

        logging.debug("Generate index database: {}".format(self.db_file.name))
        store.reset()
        return store

    def get_total_package(self, tahun):
        """
        Fungsi untuk mendapatkan total data dengan melakukan requests dengan length 0 data
        :return: Integer jumlah data
        """
        data = self.search_packages(start=0, length=0, data_only=False, tahun=tahun)

        logging.debug("Jumlah record {}".format(str(data)))
        return data['recordsFiltered']

    def search_packages(self, start, length, data_only, tahun):
        kwargs = {
            'start': start,
            'length': length,
            'data_only': data_only,
            'search_keyword': self.ctx.keyword,
            'rekanan': self.ctx.rekanan,
            'tahun': tahun,
            'instansi_id': self.ctx.instansi_id,
        }
        if self.ctx.jenis_paket != 'swakelola':
            kwargs['kategori'] = self.ctx.kategori
        else:
            kwargs['tipe_swakelola'] = self.ctx.tipe_swakelola_id
        method = getattr(self.lpse, self.ctx.package_config['search_method'])
        return method(**kwargs)

    def start(self):
        """
        Start index downloader
        :return:
        """
        if self.ctx.resume and self.db_status_for_resume:
            return

        for tahun in self.ctx.tahun_anggaran:
            total = self.get_total_package(tahun=tahun)
            batch_total = -(-total // self.ctx.chunk_size)
            data_count = 0

            for batch in range(batch_total):
                data = self.search_packages(
                    start=batch * self.ctx.chunk_size,
                    length=self.ctx.chunk_size,
                    data_only=True,
                    tahun=tahun,
                )

                if not data:
                    break

                self.store.insert_rows(self.convert_index_for_db(data))

                # update data count
                data_count += len(data)
                logging.info(
                    "{host} - TA {tahun} - Indexing halaman ke-{batch}.".format(
                        host=self.lpse_host.url,
                        batch=batch + 1,
                        tahun=tahun if tahun is not None else 'ALL'
                    )
                )

                sleep(self.ctx.index_download_delay)

    def convert_index_for_db(self, data):
        """
        Fungsi untuk menyesuaikan format index dari aplikasi spse ke database
        :param data:
        :return:
        """
        for row in data:
            prefix = self.ctx.package_config['cache_prefix']
            year_column = self.ctx.package_config['year_column']
            yield [
                '{}-{}'.format(prefix, row[0]),
                row[0],
                prefix,
                row[year_column] if len(row) > year_column else None,
                0,
                None  # detail paket kosong
            ]

    @staticmethod
    def index_factory(cursor, row):
        d = {}
        for idx, col in enumerate(cursor.description):
            d[col[0].lower()] = row[idx]

        return LpseIndex(d)

    def get_index(self):
        logging.debug("[SQL] get index from database")
        for row_dict in self.store.get_pending():
            yield LpseIndex(row_dict)

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
        if self.store:
            self.store.close()

        if self.lpse is not None:
            del self.lpse


class DetailDownloader(object):

    def __init__(self, index_downloader, lpse_pool=None):
        self.index_downloader = index_downloader
        self.lock = threading.Lock()
        self.lpse_pool = lpse_pool or []

        logging.info("{} - Mulai pengunduhan detail data".format(self.index_downloader.lpse_host.url))

    def __pre_process_index_db(self):
        counts = self.index_downloader.store.count_by_status()
        total = counts.get(0, 0)
        deleted = 0

        return total, deleted

    def _ensure_lpse_pool(self, count):
        """Populate the Lpse pool with unique-footprint instances, one per worker."""
        from pyproc.user_agents import create_session_headers

        while len(self.lpse_pool) < count:
            worker_id = len(self.lpse_pool)
            headers = create_session_headers(worker_id)
            lpse = pyproc.Lpse(
                self.index_downloader.lpse_host.url,
                timeout=self.index_downloader.ctx.timeout,
                user_agent=headers.pop('User-Agent'),
            )
            # Apply remaining headers (Accept, Accept-Language) from profile
            lpse.session.headers.update(headers)
            self.lpse_pool.append(lpse)
        return self.lpse_pool[:count]

    def _download_worker(self, lpse_index, lpse):
        """Download detail for a single package using the given Lpse instance.

        Each worker gets its own Lpse with unique session/cookies/headers
        so the server sees parallel requests as distinct clients.
        """
        method = getattr(
            lpse,
            self.index_downloader.ctx.package_config['detail_method']
        )
        try:
            package_detail = method(lpse_index.id_paket)
            info = package_detail.get_all_detil()

            if info['error']:
                logging.error('{} - Terjadi kesalahan untuk paket {}: {}'.format(
                    self.index_downloader.lpse_host.url,
                    lpse_index.id_paket,
                    info['error_message']
                ))
            lpse_index.detail = package_detail

            logging.debug("[DETAIL DOWNLOADER] update database detail data")
            self.update_detail(lpse_index)
        except Exception as e:
            logging.error('{} - Worker error untuk paket {}: {}'.format(
                self.index_downloader.lpse_host.url, lpse_index.id_paket, e
            ))
        finally:
            # Desynchronize workers with random delay between packages
            sleep(random.uniform(0.5, 2.5))

    def update_detail(self, lpse_index):
        with self.lock:
            logging.debug("[DETAIL DOWNLOADER] update detail data {}".format(lpse_index))
            self.index_downloader.store.update_detail(
                lpse_index.row_id,
                json.dumps(lpse_index.detail.todict())
            )

    def start(self):
        total, deleted = self.__pre_process_index_db()
        total_to_download = total - deleted
        index_list = list(self.index_downloader.get_index())
        workers = self.index_downloader.ctx.workers
        if workers < 1:
            workers = 1

        lpse_pool = self._ensure_lpse_pool(workers)
        total_downloaded = 0

        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_index = {}
            for i, idx in enumerate(index_list):
                lpse = lpse_pool[i % workers]
                future = executor.submit(self._download_worker, idx, lpse)
                future_to_index[future] = idx

            for future in as_completed(future_to_index):
                total_downloaded += 1
                if self.index_downloader.ctx.log_level == 'INFO':
                    print(
                        "\rMemproses {}/{} ({:,.2f}%) data".format(
                            total_downloaded,
                            total_to_download,
                            total_downloaded / total_to_download * 100
                            if total_to_download > 0 else 0.0
                        ),
                        end=' '
                    )

        print()
        logging.info("{} - {} data selesai diproses".format(
            self.index_downloader.lpse_host.url, total_downloaded
        ))


class Exporter:
    def __init__(self, index_downloader):
        self.index_downloader = index_downloader

    def get_detail(self):
        """
        Query data detail dari database untuk diekspor
        :return: generator result row
        """
        logging.info("{} - Export Data".format(self.index_downloader.lpse_host.url))
        for row_dict in self.index_downloader.store.get_completed():
            detail = row_dict.get('detail')
            if isinstance(detail, str):
                try:
                    detail = json.loads(detail)
                except (json.JSONDecodeError, TypeError):
                    continue
            yield detail

    def get_file_obj(self, ext):
        """
        Fungsi untuk mempermudah inisiasi objek file untuk export data
        :param ext:
        :return: file object
        """
        filename = self.index_downloader.lpse_host.filename.name + '.' + ext
        file_obj = Path.cwd() / filename

        return file_obj

    def to_csv(self, delimiter):
        """
        Export detail data ke csv
        :return:
        """
        jenis_paket = self.index_downloader.ctx.jenis_paket
        header = [
            'id_paket',
            'nama_tender',
            'tanggal_pembuatan',
            'tahap_tender_saat_ini',
            'k/l/pd',
            'satuan_kerja',
            'jenis_pengadaan',
            'metode_pengadaan',
            'tahun_anggaran',
            'nilai_pagu_paket',
            'nilai_hps_paket',
            'jenis_kontrak',
            'kualifikasi_usaha',
            'peserta_tender',
            'khusus_pelaku_usaha_oap',
            'lokasi_pekerjaan',
            'label_paket',
        ]

        if jenis_paket == 'non_tender':
            header[1] = 'nama_paket'
            header[3] = 'tahap_paket_saat_ini'
            header[7] = 'metode_pengadaan'
            header[-4] = 'peserta_non_tender'
        elif jenis_paket in ('pencatatan_non_tender', 'darurat', 'swakelola'):
            header = [
                'id_paket', 'nama_paket', 'tanggal_pembuatan', 'k/l/pd',
                'satuan_kerja', 'jenis_pengadaan', 'metode_pengadaan',
                'tipe_pelaksana_swakelola', 'tahun_anggaran', 'nilai_pagu_paket',
            ]

        json_data_header = ['hasil_evaluasi', 'pemenang', 'pemenang_berkontrak', 'jadwal', 'peserta', 'pelaksana']

        with self.get_file_obj('csv').open('w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f, delimiter=delimiter)
            writer.writerow(['url'] + header + json_data_header)

            for item in self.get_detail():
                if item.get('pengumuman'):
                    base_data = [item.get('pengumuman').get(i) for i in header[1:]]
                    base_data[-1] = json.dumps(base_data[-1])
                    base_data[-2] = json.dumps(base_data[-2])
                else:
                    base_data = [None]*len(header[1:])

                writer.writerow(
                    [self.index_downloader.lpse_host.url, item.get('id_paket')] +
                    base_data +
                    [
                        json.dumps(item.get('hasil')),
                        json.dumps(item.get('pemenang')),
                        json.dumps(item.get('pemenang_berkontrak')),
                        json.dumps(item.get('jadwal')),
                        json.dumps(item.get('peserta')),
                        json.dumps(item.get('pelaksana')),
                    ],
                )

    def to_json(self):
        """
        Export detail data ke format json
        :return:
        """
        with self.get_file_obj('json').open('w') as f:
            f.write("[")
            for item in self.get_detail():
                f.write(json.dumps(item))
                f.write(",")
            f.seek(f.tell() - 1)
            f.write("]")


class QualityAssurance:

    def __init__(self, index_downloader):
        self.index_downloader = index_downloader

    def check(self):
        result = self.index_downloader.store.count_by_status()
        success = result.get(1, 0)
        fail = result.get(0, 0)
        total = sum(result.values())

        return total, success, fail


class Downloader(object):
    ctx = None

    @staticmethod
    def get_args_from_interactive_menu():
        args = [
            input("Alamat LPSE: "),
            "--tahun-anggaran",
            ''.join(input("Tahun Anggaran [X atau X,Y,Z atau X-Z]: ").strip().split()),
            "--keyword",
            input("Kata kunci pencarian [default kosong]: ")
        ]
        jenis_paket = input("Jenis pengadan [tender/non_tender/pencatatan_non_tender/swakelola/darurat]: ").lower().strip()

        if jenis_paket in PACKAGE_TYPES:
            args.extend(['--jenis-paket', jenis_paket])
        else:
            print("Pilihan {} tidak valid".format(jenis_paket))
            exit(1)

        return args

    def get_ctx(self, sys_args):
        """
        Parse command line argument.
        -h, --help                  : menampilkan pesan bantuan
        -k, --keyword               : filter pencarian index paket berdasarkan kata kunci
        -t, --tahun-anggaran        : filter download detail berdasarkan tahun anggaran,
                                      format X-Y atau X;Y;Z
        --kategori                  : filter pencarian index paket berdasarkan kategori
        --rekanan                   : filter pencarian index paket berdasarkan nama penyedia/rekanan
        -c, --chunk-size            : jumlah index per-halaman yang diunduh dalam satu iterasi
        -w, --workers               : jumlah workers yang berjalan secara paralel untuk mengunduh detail paket
        -x, --timeout               : waktu timeout respon dari server dalam detik
        --jenis-paket               : jenis paket yang akan diunduh
        -d, --index-download-delay  : waktu delay untuk setiap iterasi halaman index dalam detik
        -k, --keep-workdir          : tidak menghapus working direktori dari downloader
        -f, --force                 : menjalankan program tanpa memperhatikan cache yang sudah ada sebelumnya
        --clear                     : membersihkan folder cache di direktori home
        LPSE_HOST                   : host LPSE atau file teks berisi daftar host LPSE.
                                      Jika terdapat file teks dengan nama yang sama dengan hostname LPSE, prioritas
                                      pertama dari program adalah membaca file.
        :return: Lpse Downloader Context
        """

        # if there is no argument, show interactive menu
        if len(sys_args) == 0:
            sys_args = self.get_args_from_interactive_menu()

        parser = argparse.ArgumentParser()
        parser.add_argument('lpse_host', type=str, help=text.HELP_LPSE_HOST)
        parser.add_argument('-k', '--keyword', type=str, default="", help=text.HELP_KEYWORD)
        parser.add_argument('-t', '--tahun-anggaran', type=str, default="{}".format(datetime.now().year),
                            help=text.HELP_TAHUN_ANGGARAN)
        parser.add_argument('--kategori',
                            choices=[
                                "PENGADAAN_BARANG",
                                "JASA_KONSULTANSI_BADAN_USAHA_NON_KONSTRUKSI",
                                "PEKERJAAN_KONSTRUKSI",
                                "JASA_LAINNYA",
                                "JASA_KONSULTANSI_PERORANGAN",
                                "JASA_KONSULTANSI_BADAN_USAHA_KONSTRUKSI",
                                None
                            ],
                            help=text.HELP_KATEGORI, default=None)
        parser.add_argument('--rekanan', type=str, default=None, help=text.HELP_PENYEDIA)
        parser.add_argument('--nama-penyedia', type=str, default=None, help=argparse.SUPPRESS)
        parser.add_argument('--instansi-id', type=str, default=None, help=text.HELP_INSTANSI_ID)
        parser.add_argument('--tipe-swakelola-id', type=int, choices=[1, 2, 3, 4], default=None,
                            help=text.HELP_TIPE_SWAKELA)
        parser.add_argument('-c', '--chunk-size', type=int, default=100, help=text.HELP_CHUNK_SIZE)
        parser.add_argument('-w', '--workers', type=int, default=8, help=text.HELP_WORKERS)
        parser.add_argument('-x', '--timeout', type=int, default=30, help=text.HELP_TIMEOUT)
        parser.add_argument('--jenis-paket', choices=list(PACKAGE_TYPES.keys()), default='tender',
                            help=text.HELP_JENIS_PAKET)
        parser.add_argument('-d', '--index-download-delay', type=int, default=1, help=text.HELP_INDEX_DOWNLOAD_DELAY)
        parser.add_argument('-o', '--output-format', choices=['json', 'csv'], default='csv', help=text.HELP_OUTPUT)
        parser.add_argument('--keep-index', action='store_true', help=text.HELP_KEEP)
        parser.add_argument('-r', '--resume', action='store_true', help=text.HELP_RESUME)
        parser.add_argument('-s', '--separator', type=str, default=";", help=text.HELP_CSV_SEPARATOR)
        parser.add_argument('--log', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], default='INFO',
                            help=text.HELP_LOG_LEVEL)

        args = parser.parse_args(sys_args)

        set_up_log(args.log)

        logging.debug('Parsing context')

        self.ctx = DownloaderContext(args)

        return self.ctx

    def start(self):
        for lpse_host in self.ctx.lpse_host_list:
            if not lpse_host.is_valid:
                logging.error("{} - {}".format(lpse_host.url, lpse_host.error))
                continue

            try:
                index_downloader = IndexDownloader(self.ctx, lpse_host)
                index_downloader.start()
            except Exception as e:
                logging.error("{} - Index Downloader Error {} {}".format(lpse_host.url, e.__class__, str(e)))
                continue

            try:
                detail_downloader = DetailDownloader(index_downloader)
                detail_downloader.start()
            except Exception as e:
                logging.error("{} - Detail Downloader Error {} {}".format(lpse_host.url, e.__class__, str(e)))
                continue

            exporter = Exporter(index_downloader)

            if self.ctx.output_format == 'json':
                exporter.to_json()
            elif self.ctx.output_format == 'csv':
                exporter.to_csv(delimiter=self.ctx.separator)

            qa = QualityAssurance(index_downloader)
            total, success, fail = qa.check()

            with open('statistic.txt', 'a') as f:
                f.write("{} total={} success={} fail={} tahun={}\n".format(
                    lpse_host.url, total, success, fail, self.ctx.tahun_anggaran
                ))

            if total == 0:
                logging.info("Proses selesai, tidak ada data yang ditemukan.")
            elif fail == 0:
                logging.info("Proses selesai: {}/{} ({:,.2f}%) terunduh".format(success, total, success/total*100))
            else:
                logging.error("Proses gagal: {}/{} ({:,.2f}%).".format(fail, total, fail/total*100))
                logging.info("Jalankan perintah dengan parameter --resume / -r untuk mengunduh ulang paket yang gagal")

            if not index_downloader.ctx.keep_index and fail == 0:
                logging.info("{} - membersihkan direktori".format(lpse_host.url))
                index_downloader.store.close()
                try:
                    index_downloader.db_file.unlink()
                except FileNotFoundError:
                    pass

            del index_downloader
            del detail_downloader
            del exporter


def main():
    IWillFindYouAndIWillKillYou()

    print(text.INFO)

    # Check for top-level --help / -h before subcommand dispatch
    if len(sys.argv) > 1 and sys.argv[1] in {'-h', '--help'}:
        print("Usage: pyproc [subcommand] [options]")
        print()
        print("Subcommands:")
        print("  spse           Unduh data paket langsung dari SPSE/Inaproc (default)")
        print("  daftarlpse     Unduh daftar host LPSE dalam format CSV")
        print("  daftarhost     " + text.HELP_DAFTARHOST)
        print("  masterklpd     Query Master K/L/PD references dari LKPP ISB")
        print("  satudata       Akses data dari LKPP ISB Satu Data API (alternatif)")
        print("    masterlpse   Cari LPSE secara interaktif dan unduh data tender")
        print("    tenderumum   Unduh data tender umum publik berdasarkan kode LPSE")
        print()
        print(
            "Gunakan 'pyproc <subcommand> --help' "
            "untuk bantuan spesifik subcommand."
        )
        sys.exit(0)

    # Detect subcommands by checking if first arg is a known subcommand
    # For backward compatibility, treat non-subcommand args as download args
    known_subcommands = {'daftarlpse', 'daftarhost', 'masterklpd', 'satudata', 'spse'}

    if len(sys.argv) > 1 and sys.argv[1] in known_subcommands:
        subcommand = sys.argv[1]
        remaining_args = sys.argv[2:]
    else:
        subcommand = 'spse'
        remaining_args = sys.argv[1:]

    if subcommand == 'daftarlpse':
        if remaining_args and remaining_args[0] in {'-h', '--help'}:
            print("Usage: pyproc daftarlpse")
            print()
            print("Unduh daftar host LPSE dalam format CSV dari GitHub Gist.")
            sys.exit(0)
        set_up_log('INFO')
        pyproc.utils.download_host()
        sys.exit(0)

    if subcommand == 'daftarhost':
        if remaining_args and remaining_args[0] in {'-h', '--help'}:
            print("Usage: pyproc daftarhost [directory]")
            print()
            print(text.HELP_DAFTARHOST)
            print()
            print("Arguments:")
            print("  directory    Direktori output (default: direktori saat ini)")
            sys.exit(0)
        directory = remaining_args[0] if remaining_args else '.'
        set_up_log('INFO')
        pyproc.utils.download_host_json(directory=directory)
        sys.exit(0)

    if subcommand == 'masterklpd':
        parser = argparse.ArgumentParser(
            description="Query Master K/L/PD references dari LKPP ISB Satu Data API."
        )
        parser.add_argument('--query', type=str, default="")
        parser.add_argument('--jenis', type=str, default=None)
        parser.add_argument('--kd-klpd', type=str, default=None)
        parser.add_argument('--limit', type=int, default=0)
        parser.add_argument('--timeout', type=int, default=30)
        args = parser.parse_args(remaining_args)
        rows = pyproc.Lpse.get_master_klpd(timeout=args.timeout)
        if args.kd_klpd:
            rows = [row for row in rows if str(row.get('kd_klpd', '')).lower() == args.kd_klpd.lower()]
        if args.jenis:
            rows = [row for row in rows if str(row.get('jenis_klpd', '')).lower() == args.jenis.lower()]
        if args.query:
            query = args.query.lower()
            rows = [
                row for row in rows
                if query in str(row.get('nama_klpd', '')).lower()
                or query in str(row.get('kd_klpd', '')).lower()
            ]
        if args.limit > 0:
            rows = rows[:args.limit]
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        sys.exit(0)

    if subcommand == 'satudata':
        satudata_subs = {'masterlpse', 'tenderumum'}
        if not remaining_args or remaining_args[0] not in satudata_subs:
            print("Usage: pyproc satudata {masterlpse|tenderumum} [options]")
            print()
            print("  masterlpse   Cari LPSE secara interaktif dan unduh data tender")
            print("  tenderumum   Unduh data tender umum publik berdasarkan kode LPSE")
            print()
            print(
                "Gunakan 'pyproc satudata <subcommand> --help' "
                "untuk bantuan spesifik."
            )
            sys.exit(1)
        satudata_cmd = remaining_args[0]
        satudata_args = remaining_args[1:]

        if satudata_cmd == 'masterlpse':
            parser = argparse.ArgumentParser(
                description="Cari LPSE secara interaktif dan unduh data tender."
            )
            parser.add_argument('--timeout', type=int, default=30)
            parser.add_argument(
                '--output', type=str, default='json', choices=['json', 'csv'],
            )
            parser.add_argument(
                '--output-file', type=str, default=None,
                help='Lokasi file output. Dibuat otomatis jika tidak diberikan.',
            )
            args = parser.parse_args(satudata_args)

            print("Mengambil data master LPSE...")
            try:
                rows = pyproc.Lpse.get_master_lpse(timeout=args.timeout)
            except Exception as e:
                print(f"Gagal mengambil data LPSE: {e}")
                sys.exit(1)

            if not rows:
                print("Tidak ada data LPSE ditemukan.")
                sys.exit(1)

            selected_lpse = None
            while selected_lpse is None:
                print("\n" + "=" * 60)
                print(
                    "CARI LPSE (ketik kata kunci, "
                    "kosongkan untuk menampilkan semua)"
                )
                keyword = input("Kata kunci: ").strip().lower()

                filtered = []
                if keyword:
                    filtered = [
                        row for row in rows
                        if keyword in str(row.get('nama_lpse', '')).lower()
                        or keyword in str(row.get('kd_lpse', '')).lower()
                    ]
                else:
                    filtered = rows

                display = filtered[:50]
                print(
                    f"\nMenampilkan {len(display)} dari {len(filtered)} LPSE:"
                )
                for i, row in enumerate(display, 1):
                    print(
                        f"  {i:3d}. [{row.get('kd_lpse')}] "
                        f"{row.get('nama_lpse')}"
                    )
                if len(filtered) > 50:
                    print(f"  ... dan {len(filtered) - 50} lainnya")

                if not filtered:
                    print("Tidak ada LPSE yang cocok. Coba kata kunci lain.")
                    continue

                try:
                    choice = input(
                        "\nPilih nomor LPSE (atau Enter untuk cari lagi, "
                        "q untuk keluar): "
                    ).strip()
                    if choice.lower() == 'q':
                        print("Dibatalkan.")
                        sys.exit(0)
                    if not choice:
                        continue
                    idx = int(choice) - 1
                    if 0 <= idx < len(display):
                        selected_lpse = display[idx]
                    else:
                        print("Nomor tidak valid.")
                except ValueError:
                    print("Masukkan nomor yang valid.")

            # Ask for tahun anggaran
            tahun = None
            while tahun is None:
                try:
                    tahun_input = input(
                        f"\nTahun anggaran (contoh: 2026): "
                    ).strip()
                    tahun = int(tahun_input)
                    if tahun < 2000 or tahun > 2100:
                        print("Tahun di luar jangkauan (2000-2100).")
                        tahun = None
                except ValueError:
                    print("Masukkan tahun yang valid.")

            kd_lpse = selected_lpse['kd_lpse']
            nama_lpse = selected_lpse['nama_lpse']
            print(
                f"\nMengambil data tender untuk LPSE {nama_lpse} "
                f"({kd_lpse}), tahun {tahun}..."
            )

            try:
                tender_data = pyproc.Lpse.get_tender_umum_publik(
                    tahun_anggaran=tahun,
                    kd_lpse=kd_lpse,
                    timeout=args.timeout,
                )
            except Exception as e:
                print(f"Gagal mengambil data tender: {e}")
                sys.exit(1)

            if not tender_data:
                print("Tidak ada data tender ditemukan.")
                sys.exit(1)

            # Determine output file
            safe_name = re.sub(r'[^a-z0-9]', '_', nama_lpse.lower())[:30]
            if args.output_file:
                output_path = Path(args.output_file)
            else:
                output_path = Path(
                    f"tender_{safe_name}_{kd_lpse}_{tahun}.{args.output}"
                )

            if args.output == 'json':
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(tender_data, f, ensure_ascii=False, indent=2)
            else:  # csv
                if tender_data:
                    fieldnames = list(tender_data[0].keys())
                    with open(output_path, 'w', newline='', encoding='utf-8') as f:
                        writer = csv.DictWriter(f, fieldnames=fieldnames)
                        writer.writeheader()
                        writer.writerows(tender_data)

            print(
                f"Berhasil menyimpan {len(tender_data)} tender ke {output_path}"
            )
            sys.exit(0)

        elif satudata_cmd == 'tenderumum':
            parser = argparse.ArgumentParser(
                description="Unduh data tender umum publik dari LKPP ISB."
            )
            parser.add_argument(
                '--tahun-anggaran', type=int, required=True,
                help='Tahun anggaran, misal 2026.',
            )
            parser.add_argument(
                '--kode-lpse', type=int, required=True,
                help='Kode LPSE dari master LPSE, misal 119.',
            )
            parser.add_argument('--timeout', type=int, default=30)
            parser.add_argument(
                '--output', type=str, default='json', choices=['json', 'csv'],
            )
            parser.add_argument(
                '--output-file', type=str, default=None,
                help='Lokasi file output. Dibuat otomatis jika tidak diberikan.',
            )
            args = parser.parse_args(satudata_args)

            if args.tahun_anggaran < 2000 or args.tahun_anggaran > 2100:
                print(
                    f"Tahun anggaran {args.tahun_anggaran} di luar "
                    f"jangkauan (2000-2100)."
                )
                sys.exit(1)

            print(
                f"Mengambil data tender umum publik untuk LPSE "
                f"{args.kode_lpse}, tahun {args.tahun_anggaran}..."
            )

            try:
                rows = pyproc.Lpse.get_tender_umum_publik(
                    tahun_anggaran=args.tahun_anggaran,
                    kd_lpse=args.kode_lpse,
                    timeout=args.timeout,
                )
            except Exception as e:
                print(f"Gagal mengambil data tender: {e}")
                sys.exit(1)

            if not rows:
                print("Tidak ada data tender ditemukan.")
                sys.exit(1)

            if args.output_file:
                output_path = Path(args.output_file)
            else:
                output_path = Path(
                    f"tender_umum_{args.kode_lpse}_{args.tahun_anggaran}"
                    f".{args.output}"
                )

            if args.output == 'json':
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(rows, f, ensure_ascii=False, indent=2)
            else:
                fieldnames = list(rows[0].keys())
                with open(output_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(rows)

            print(
                f"Berhasil menyimpan {len(rows)} tender ke {output_path}"
            )
            sys.exit(0)

    # Default: spse
    downloader = Downloader()
    downloader.get_ctx(remaining_args)

    try:
        status, current, new = check_new_version()
        if status:
            logging.info(f"Anda menggunakan PyProc versi {current}, "
                         f"tersedia versi baru {new}. "
                         f"Mohon untuk memperbarui aplikasi.")

        downloader.start()
    except Exception as e:
        logging.error(f"Terjadi galat {e}")
    finally:
        del downloader


if __name__ == '__main__':
    main()
