import argparse
import csv
import json
import re
import logging
import signal
import sqlite3
import threading
import requests
import pyproc
from time import sleep
from pyproc.exceptions import DownloaderContextException
from scripts import text
from datetime import datetime
from pathlib import Path
from urllib3.exceptions import InsecureRequestWarning
from urllib3 import disable_warnings

disable_warnings(InsecureRequestWarning)


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


class Killer:
    kill_now = False

    def __init__(self):
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)

    def exit_gracefully(self, *args):
        logging.debug("Get {} signal".format(args))
        logging.error("Proses dibatalkan user")
        self.kill_now = True


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
        self.nama_penyedia = args.nama_penyedia
        self.chunk_size = args.chunk_size
        self.workers = args.workers
        self.timeout = args.timeout
        self.non_tender = args.non_tender
        self.index_download_delay = args.index_download_delay
        self.keep_index = args.keep_index
        self.log_level = args.log
        self.output_format = args.output_format
        self.resume = args.resume
        self.__lpse_host = args.lpse_host

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
        except TypeError:
            return {}

    def __str__(self):
        return str(self.__dict__)


class IndexDownloader(object):
    __tahun_anggaran_pattern = re.compile('(\d+)')
    db = None
    db_status_for_resume = False
    db_file = None
    lpse = None

    def __init__(self, ctx, lpse_host):
        self.ctx = ctx
        self.lpse_host = lpse_host
        self.lpse = pyproc.Lpse(lpse_host.url, timeout=ctx.timeout)
        self.db = self.get_index_db(self.lpse_host.filename)

        logging.info("{} - Mulai pengunduhan data {} tahun {}".format(
            lpse_host.url, "Pengadaan Langsung" if self.ctx.non_tender else "Tender",
            ', '.join(map(str, self.ctx.tahun_anggaran)) if self.ctx.tahun_anggaran[0] is not None else 'ALL'
        ))

    def __check_index_db(self, db):
        status = False
        try:
            total = db.execute("SELECT COUNT(1) FROM INDEX_PAKET").fetchone()[0]
            logging.info("{} - total previous index {}".format(self.lpse_host.url, total))
            if total > 0:
                status = True
        except Exception as e:
            logging.error("{} - check index db gagal, error: {}".format(self.lpse_host.url, e))
            status = False

        logging.info("{} - status previous index db {}".format(self.lpse_host.url, status))
        self.db_status_for_resume = status
        return status

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
        self.db_file = Path.cwd() / db_filename
        db = sqlite3.connect(str(self.db_file), check_same_thread=False)

        if self.ctx.resume and self.__check_index_db(db):
            logging.info("{} - skip db init, melanjutkan proses".format(self.lpse_host.url))
            return db

        logging.debug("Generate index database: {}".format(self.db_file.name))
        logging.debug("Create index table")

        try:
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

    def get_total_package(self, tahun):
        """
        Fungsi untuk mendapatkan total data dengan melakukan requests dengan length 0 data
        :return: Integer jumlah data
        """
        jenis_paket = self.get_jenis_paket()

        data = self.lpse.get_paket(jenis_paket=jenis_paket, kategori=self.ctx.kategori,
                                   nama_penyedia=self.ctx.nama_penyedia, search_keyword=self.ctx.keyword,
                                   tahun=tahun)

        logging.debug("Jumlah record {}".format(str(data)))
        return data['recordsFiltered']

    def start(self):
        """
        Start index downloader
        :return:
        """
        if self.ctx.resume and self.db_status_for_resume:
            return

        killer = Killer()

        for tahun in self.ctx.tahun_anggaran:
            total = self.get_total_package(tahun=tahun)
            batch_total = -(-total // self.ctx.chunk_size)
            data_count = 0

            for batch in range(batch_total):
                if killer.kill_now:
                    del self.db
                    exit(1)

                data = self.lpse.get_paket(jenis_paket=self.get_jenis_paket(), start=batch * self.ctx.chunk_size,
                                           length=self.ctx.chunk_size, kategori=self.ctx.kategori,
                                           search_keyword=self.ctx.keyword, nama_penyedia=self.ctx.nama_penyedia,
                                           data_only=True, tahun=tahun)
                self.db.executemany("INSERT OR IGNORE INTO INDEX_PAKET VALUES(?, ?, ?, ?, ?, ?)",
                                    self.convert_index_for_db(data))
                self.db.commit()

                # update data count
                data_count += len(data)
                logging.info(
                    "{host} - TA {tahun} - Indexing halaman {batch} dari {total_batch}, "
                    "{data_count}/{data_total} data ({persentase:,.2f}%)".format(
                        host=self.lpse_host.url,
                        batch=batch + 1,
                        total_batch=batch_total,
                        data_count=data_count,
                        data_total=total,
                        persentase=data_count / total * 100,
                        tahun=tahun if tahun is not None else 'ALL'
                    )
                )

                sleep(self.ctx.index_download_delay)

            if not self.lpse.version.startswith('4.4'):
                logging.info("{} - SKIP tahun lain".format(self.lpse_host.url, self.lpse.version))
                break

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
                row[6] if self.ctx.non_tender else row[8],
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
        result = self.db.execute("SELECT * FROM INDEX_PAKET WHERE STATUS = 0")

        for row in result.fetchall():
            row = self.index_factory(result, row)

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

        if self.lpse is not None:
            del self.lpse


class DetailDownloader(object):

    def __init__(self, index_downloader):
        self.index_downloader = index_downloader
        self.lock = threading.Lock()

        logging.info("{} - Mulai pengunduhan detail data".format(self.index_downloader.lpse_host.url))

    def __pre_process_index_db(self):
        total = self.index_downloader.db.execute(
            """SELECT COUNT(1) FROM INDEX_PAKET WHERE STATUS = 0"""
        ).fetchone()[0]
        deleted = 0

        if not self.index_downloader.lpse.version.startswith('4.4') \
                and self.index_downloader.ctx.tahun_anggaran != [None]:
            logging.info("{} - {}u{} tidak mendukung filter tahun anggaran, menjalankan filter manual"
                         .format(self.index_downloader.lpse_host.url, self.index_downloader.lpse.version,
                                 self.index_downloader.lpse.build_version)
                         )

            for row in self.index_downloader.get_index():
                contain_ta = sum([1 for tahun in self.index_downloader.ctx.tahun_anggaran
                                  if str(tahun) in row.kategori_tahun_anggaran])
                if contain_ta == 0:
                    self.index_downloader.db.execute("""DELETE FROM INDEX_PAKET WHERE ROW_ID = ?""", (row.row_id,))
                    deleted += 1

            logging.info("{} - {} data sesuai kriteria tahun anggaran".format(
                self.index_downloader.lpse_host.url, total-deleted)
            )

            logging.info("{} - menghapus {} data index yang tidak relevan".format(
                self.index_downloader.lpse_host.url,
                deleted
            ))
            self.index_downloader.db.commit()

        return total, deleted

    def get_detail(self, lpse_index):
        """
        Get detail paket berdasarkan paket ID
        :param package_id:
        :return:
        """
        logging.debug("[DETAIL DOWNLOADER] download detail for {}".format(lpse_index))
        if self.index_downloader.ctx.non_tender:
            package_detail = self.index_downloader.lpse.detil_paket_non_tender(lpse_index.id_paket)
        else:
            package_detail = self.index_downloader.lpse.detil_paket_tender(lpse_index.id_paket)

        info = package_detail.get_all_detil()

        if info['error']:
            logging.error('{} - Terjadi kesalahan untuk paket {}'.format(
                self.index_downloader.lpse_host.url, info['error_message']
            ))
        lpse_index.detail = package_detail

        logging.debug("[DETAIL DOWNLOADER] update database detail data")
        self.update_detail(lpse_index)

    def update_detail(self, lpse_index):
        with self.lock:
            logging.debug("[DETAIL DOWNLOADER] update detail data {}".format(lpse_index))
            self.index_downloader.db.execute(
                "UPDATE INDEX_PAKET SET DETAIL = ?, STATUS = 1 WHERE ROW_ID = ?",
                (json.dumps(lpse_index.detail.todict()), lpse_index.row_id)
            )
            self.index_downloader.db.commit()

    def start(self):
        total, deleted = self.__pre_process_index_db()
        total_to_download = total - deleted
        killer = Killer()
        index_generator = self.index_downloader.get_index()
        total_downloaded = 0

        while not killer.kill_now:
            lpse_index = []

            for i in range(self.index_downloader.ctx.workers):
                try:
                    lpse_index.append(index_generator.__next__())
                except StopIteration:
                    pass

            logging.debug("[DETAIL DOWNLOADER] starting batch for {}".format(lpse_index))

            threads = []

            for i, index in enumerate(lpse_index):
                t = threading.Thread(target=self.get_detail, args=(index,), name='detail-thread-{}'.format(i))
                t.start()
                logging.debug("[DETAIL DOWNLOADER] {} started".format(t.name))
                threads.append(t)

            for t in threads:
                logging.debug("[DETAIL DOWNLOADER] thread {} join".format(t.name))
                t.join()

            for t in threads:
                logging.debug("[DETAIL DOWNLOADER] thread {} deleted".format(t.name))
                del t

            del threads

            total_downloaded += len(lpse_index)

            if self.index_downloader.ctx.log_level == 'INFO':
                print(
                    "\rMemproses {}/{} ({:,.2f}%) data".format(
                        total_downloaded,
                        total_to_download,
                        total_downloaded/total_to_download*100 if total_to_download > 0 else 0.0
                    ),
                    end=' '
                )

            if len(lpse_index) != self.index_downloader.ctx.workers:
                break

        if killer.kill_now:
            del killer
            exit(1)

        print()
        logging.info("{} - {} data selesai diproses".format(self.index_downloader.lpse_host.url, total_downloaded))


class Exporter:
    def __init__(self, index_downloader):
        self.index_downloader = index_downloader

    def get_detail(self):
        """
        Query data detail dari database untuk diekspor
        :return: generator result row
        """
        logging.info("{} - Export Data".format(self.index_downloader.lpse_host.url))
        result = self.index_downloader.db.execute("SELECT * from INDEX_PAKET WHERE STATUS = 1")
        for data in result.fetchall():
            data = self.index_downloader.index_factory(result, data)
            yield data.detail

    def get_file_obj(self, ext):
        """
        Fungsi untuk mempermudah inisiasi objek file untuk export data
        :param ext:
        :return: file object
        """
        filename = self.index_downloader.lpse_host.filename.name + '.' + ext
        file_obj = Path.cwd() / filename

        return file_obj

    def get_pemenang(self, detil):
        """
        Pengambilan data pemenang dari halaman hasil evaluasi
        :param detil:
        :return:
        """
        field = ['npwp', 'nama_peserta', 'penawaran', 'penawaran_terkoreksi', 'hasil_negosiasi', 'alamat', 'p', 'pk']
        pemenang_field = ['npwp', 'nama_pemenang', 'harga_penawaran', 'harga_terkoreksi', 'hasil_negosiasi', 'alamat',
                          'p', 'pk']
        data = [None] * 8

        if detil['pemenang_berkontrak']:
            p = detil['pemenang_berkontrak'][0]
            data = [p.get(i) for i in pemenang_field]
        elif detil['pemenang']:
            p = detil['pemenang'][0]
            data = [p.get(i) for i in pemenang_field]
        if detil['hasil']:
            pemenang_hasil_evaluasi = list(filter(lambda x: x.get('pk') is True or x.get('p') is True, detil['hasil']))

            if pemenang_hasil_evaluasi:
                p = pemenang_hasil_evaluasi[0]
                if not data:
                    data = [p.get(i) for i in field]
                else:
                    data[6] = p.get('p')
                    data[7] = p.get('pk')

        return data

    def to_csv(self):
        """
        Export detail data ke csv
        :return:
        """
        is_tender = not self.index_downloader.ctx.non_tender
        version = self.index_downloader.lpse.version
        header = [
            'id_paket',
            'nama_tender',
            'tanggal_pembuatan',
            'tahap_tender_saat_ini',
            'k/l/pd',
            'satuan_kerja',
            'jenis_pengadaan' if version.startswith('4.4') else 'kategori',
            'metode_pengadaan' if version.startswith('4.4') else 'sistem_pengadaan',
            'tahun_anggaran',
            'nilai_pagu_paket',
            'nilai_hps_paket',
            'jenis_kontrak',
            'lokasi_pekerjaan',
            'kualifikasi_usaha',
            'peserta_tender',
            'label_paket',
            'khusus_pelaku_usaha_oap'
        ]

        if not is_tender:
            header[1] = 'nama_paket'
            header[3] = 'tahap_paket_saat_ini'
            header[7] = 'metode_pengadaan'
            header[-3] = 'peserta_non_tender'

        header_pemenang = ['npwp', 'nama_peserta', 'penawaran', 'penawaran_terkoreksi', 'hasil_negosiasi', 'alamat',
                           'p', 'pk']
        other_header = ['jadwal', 'peserta']

        with self.get_file_obj('csv').open('w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['url'] + header + header_pemenang + other_header)

            for item in self.get_detail():
                if item.get('pengumuman'):
                    base_data = [item.get('pengumuman', {}).get(i) for i in header[1:]]
                else:
                    base_data = [None]*len(header[1:])

                writer.writerow(
                    [self.index_downloader.lpse_host.url, item.get('id_paket')] +
                    base_data +
                    self.get_pemenang(item) +
                    [item.get('jadwal'), item.get('peserta')],
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
        all_data = self.index_downloader.db.execute("SELECT STATUS, COUNT(1) FROM INDEX_PAKET GROUP BY STATUS")
        result = dict(all_data.fetchall())
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
        is_tender = input("Jenis pengadan [tender/pl]: ").lower().strip()

        if is_tender in ['tender', 'pl']:
            if is_tender == 'pl':
                args.append('--non-tender')
        else:
            print("Pilihan {} tidak valid".format(is_tender))
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
        parser.add_argument('--nama-penyedia', type=str, default=None, help=text.HELP_PENYEDIA)
        parser.add_argument('-c', '--chunk-size', type=int, default=100, help=text.HELP_CHUNK_SIZE)
        parser.add_argument('-w', '--workers', type=int, default=8, help=text.HELP_WORKERS)
        parser.add_argument('-x', '--timeout', type=int, default=30, help=text.HELP_TIMEOUT)
        parser.add_argument('-n', '--non-tender', action='store_true', help=text.HELP_NONTENDER)
        parser.add_argument('-d', '--index-download-delay', type=int, default=1, help=text.HELP_INDEX_DOWNLOAD_DELAY)
        parser.add_argument('-o', '--output-format', choices=['json', 'csv'], default='csv', help=text.HELP_OUTPUT)
        parser.add_argument('--keep-index', action='store_true', help=text.HELP_KEEP)
        parser.add_argument('-r', '--resume', action='store_true', help=text.HELP_RESUME)
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
            except Exception as e:
                logging.error("{} - {} {}".format(lpse_host.url, e.__class__, str(e)))
                continue
            index_downloader.start()

            detail_downloader = DetailDownloader(index_downloader)
            detail_downloader.start()

            exporter = Exporter(index_downloader)

            if self.ctx.output_format == 'json':
                exporter.to_json()
            elif self.ctx.output_format == 'csv':
                exporter.to_csv()

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
                index_downloader.db.close()
                try:
                    index_downloader.db_file.unlink()
                except FileNotFoundError:
                    pass

            del index_downloader
            del detail_downloader
            del exporter


def main():
    import sys

    print(text.INFO)

    downloader = Downloader()
    downloader.get_ctx(sys.argv[1:])

    try:
        status, current, new = check_new_version()
        if status:
            logging.info(f"Anda menggunakan PyProc versi {current}, "
                         f"tersedia versi baru {new}. "
                         f"Mohon untuk memperbarui aplikasi.")
            exit(1)
        else:
            if len(sys.argv) > 1 and sys.argv[1] == 'daftarlpse':
                pyproc.utils.get_all_host(logging)
                exit(0)
            else:
                downloader.start()
    except Exception as e:
        logging.error(f"Terjadi galat {e}")
    finally:
        del downloader


if __name__ == '__main__':
    main()
