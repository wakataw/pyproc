from __future__ import annotations

import time
import bs4
import requests
import re
import logging
import backoff
from . import utils
from bs4 import BeautifulSoup as Bs, NavigableString
from .exceptions import LpseVersionException, LpseServerExceptions, LpseHostExceptions
from enum import Enum
from abc import abstractmethod
from typing import Optional, Any
from urllib.parse import urlparse
from urllib3.exceptions import InsecureRequestWarning
from urllib3 import disable_warnings


class By(Enum):
    KODE = 0
    NAMA_PAKET = 1
    INSTANSI = 2
    HPS = 4


class KontrakStatus(Enum):
    SELESAI = 0
    PEMUTUSAN_KONTRAK = 1
    PENGHENTIAN_KONTRAK = 2


class JenisPengadaan(Enum):
    """
    Objek untuk menampung data kodifikasi jenis pengadaan
    """
    PENGADAAN_BARANG = 0
    JASA_KONSULTANSI_BADAN_USAHA_NON_KONSTRUKSI = 1
    PEKERJAAN_KONSTRUKSI = 2
    JASA_LAINNYA = 3
    JASA_KONSULTANSI_PERORANGAN = 4
    JASA_KONSULTANSI_BADAN_USAHA_KONSTRUKSI = 5


class TipeSwakelola(Enum):
    KLPD_PENANGGUNG_JAWAB_ANGGARAN = 1
    KLPD_LAIN = 2
    ORGANISASI_MASYARAKAT = 3
    KELOMPOK_MASYARAKAT = 4


class Lpse(object):

    def __init__(self, instansi: str, timeout: int = 10, verify: bool = False):
        self.session = requests.session()
        self.session.verify = verify
        if not verify:
            disable_warnings(InsecureRequestWarning)
        self.session.headers = {
            'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/102.0.5005.61 Safari/537.36'
        }
        self.timeout = timeout
        self.auth_token: Optional[str] = None
        self.url = f"https://spse.inaproc.id/{instansi}"

    def __enter__(self) -> Lpse:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        self.session.close()
        return False


    @staticmethod
    def check_error(resp: requests.Response) -> None:
        error_message = None
        content = resp.text

        if resp.status_code >= 400 or \
                re.findall(r'Maaf, terjadi error pada aplikasi SPSE.', content) or \
                re.findall(r'Terjadi Kesalahan', content):
            error_message = "Terjadi error pada aplikasi SPSE."
            error_code = re.findall(r'Kode Error: ([\da-zA-Z]+)', content)

            if error_code:
                error_message += ' Kode Error: ' + error_code[0]
        elif re.findall('Halaman yang dituju tidak ditemukan', content):
            error_message = "Paket tidak ditemukan"

        if error_message is not None:
            error_message = "{} - {}".format(
                resp.url,
                error_message
            )
            raise LpseServerExceptions(error_message)

    def get_auth_token(self, from_cookies: bool = True) -> Optional[str]:
        """
        Melakukan pengambilan auth token
        :return: token (str)
        """

        r = self.session.get(self.url + '/lelang')

        if from_cookies:
            auth_token = re.findall(r'___AT=([A-Za-z0-9]+)&', self.session.cookies.get('SPSE_SESSION'))

            if auth_token:
                return auth_token[0]

        return utils.parse_token(r.text)

    @backoff.on_exception(backoff.fibo,
                          (LpseServerExceptions, requests.exceptions.RequestException,
                           requests.exceptions.ConnectionError),
                          jitter=None, max_tries=3)
    def get_paket(self, jenis_paket: str, start: int = 0, length: int = 0,
                  data_only: bool = False, kategori: Optional[JenisPengadaan] = None,
                  search_keyword: Optional[str] = None, rekanan: Optional[str] = None,
                  order: By = By.KODE, tahun: Optional[int] = None, ascending: bool = False,
                  instansi_id: Optional[str] = None,
                  kontrak_status: Optional[KontrakStatus | int] = None,
                  nama_penyedia: Optional[str] = None,
                  column_count: int = 5,
                  extra_params: Optional[dict] = None) -> dict | list:
        """
        Melakukan pencarian paket pengadaan
        :param jenis_paket: Paket Pengadaan Lelang (lelang) atau Penunjukkan Langsung (pl)
        :param start: index data awal
        :param length: jumlah data yang ditampilkan
        :param data_only: hanya menampilkan data tanpa menampilkan informasi lain
        :param kategori: kategori pengadaan (lihat di lpse.JenisPengadaan)
        :param search_keyword: keyword pencarian paket pengadaan
        :param rekanan: filter berdasarkan nama penyedia/rekanan
        :param order: Mengurutkan data berdasarkan kolom
        :param tahun: Tahun Pengadaan
        :param ascending: Ascending, descending jika diset False
        :param instansi_id: Filter pencarian berdasarkan instansi atau satker tertentu
        :param kontrak_status: Filter status kontrak tender: 0 selesai, 1 pemutusan kontrak,
                               2 penghentian kontrak, None semua
        :param nama_penyedia: alias lama untuk rekanan
        :return: dictionary dari hasil pencarian paket (atau list jika data_only=True)
        """

        # TODO: Header dari data berbeda untuk tiap SPSE masing-masing ILAP.
        #  Cek tiap LPSE tiap ilap untuk menentukan header dari data

        if not self.auth_token:
            self.auth_token = self.get_auth_token()

        params = {
            'draw': 1,
            'start': start,
            'length': length,
            'tahun': tahun,
            'search[value]': search_keyword if search_keyword else '',
            'search[regex]': 'false',
            'order[0][column]': order.value,
            'order[0][dir]': 'asc' if ascending else 'desc',
            'authenticityToken': self.auth_token,
            '_': int(time.time()*1000)
        }

        for i in range(0, column_count):
            params.update(
                {
                    'columns[{}][data]'.format(i): i,
                    'columns[{}][name]'.format(i): '',
                    'columns[{}][searchable]'.format(i): 'true' if i != 3 else 'false',
                    'columns[{}][orderable]'.format(i): 'true' if i != 3 else 'false',
                    'columns[{}][search][value]'.format(i): '',
                    'columns[{}][search][regex]'.format(i): 'false'
                }
            )

        if kategori:
            params.update({'kategoriId': kategori.value})

        rekanan = rekanan or nama_penyedia
        if rekanan:
            params.update({'rekanan': rekanan})
            params.update({'rkn_nama': rekanan})

        if instansi_id:
            params.update({'instansiId': instansi_id})

        if kontrak_status is not None:
            if isinstance(kontrak_status, KontrakStatus):
                kontrak_status = kontrak_status.value
            params.update({'kontrakStatus': kontrak_status})

        if extra_params:
            params.update(extra_params)

        # prepare request GET dan POST untuk spse 4.5.20221227
        headers = {
            'X-Requested-With': 'XMLHttpRequest',
            'Referer': self.url + '/lelang',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/77.0.3865.90 Safari/537.36'
        }
        url = self.url + '/dt/' + jenis_paket

        data = self.session.post(
            url,
            data=params,
            verify=False,
            timeout=self.timeout,
            headers=headers
        )

        logging.debug(data.content)
        self.check_error(data)

        data.encoding = 'UTF-8'

        if data_only:
            return data.json()['data']

        return data.json()

    def get_paket_tender(self, start=0, length=0, data_only=False,
                         kategori=None, search_keyword=None, rekanan=None,
                         order=By.KODE, tahun=None, ascending=False, instansi_id=None,
                         kontrak_status=None, nama_penyedia=None):
        """
        Wrapper pencarian paket tender
        :param start: index data awal
        :param length: jumlah data yang ditampilkan
        :param data_only: hanya menampilkan data tanpa menampilkan informasi lain
        :param kategori: kategori pengadaan (lihat di pypro.kategori)
        :param search_keyword: keyword pencarian paket pengadaan
        :param rekanan: filter berdasarkan nama penyedia/rekanan
        :param order: Mengurutkan data berdasarkan kolom
        :param tahun: Tahun Pengadaan
        :param ascending: Ascending, descending jika diset False
        :param instansi_id: Filter pencarian berdasarkan instansi atau satker tertentu
        :param kontrak_status: Filter status kontrak: 0 selesai, 1 pemutusan kontrak,
                               2 penghentian kontrak, None semua
        :param nama_penyedia: alias lama untuk rekanan
        :return: dictionary dari hasil pencarian paket (atau list jika data_only=True)
        """
        if kontrak_status is None and nama_penyedia is None:
            return self.get_paket('lelang', start, length, data_only, kategori, search_keyword, rekanan,
                                  order, tahun, ascending, instansi_id)
        return self.get_paket(
            'lelang', start, length, data_only, kategori, search_keyword, rekanan,
            order, tahun, ascending, instansi_id, kontrak_status, nama_penyedia
        )

    def get_paket_non_tender(self, start=0, length=0, data_only=False, kategori=None, search_keyword=None,
                             order=By.KODE, tahun=None, ascending=False, instansi_id=None):
        """
        Wrapper pencarian paket non tender
        :param start: index data awal
        :param length: jumlah data yang ditampilkan
        :param data_only: hanya menampilkan data tanpa menampilkan informasi lain
        :param kategori: kategori pengadaan (lihat di pypro.kategori)
        :param search_keyword: keyword pencarian paket pengadaan
        :param nama_penyedia: filter berdasarkan nama penyedia
        :param order: Mengurutkan data berdasarkan kolom
        :param tahun: Tahun pengadaan
        :param ascending: Ascending, descending jika diset False
        :param instansi_id: Filter pencarian berdasarkan instansi atau satker tertentu
        :return: dictionary dari hasil pencarian paket (atau list jika data_only=True)
        """
        return self.get_paket('pl', start, length, data_only, kategori, search_keyword, None, order, tahun,
                              ascending, instansi_id)

    def get_paket_pencatatan_non_tender(self, start=0, length=0, data_only=False, kategori=None,
                                        search_keyword=None, rekanan=None, order=By.KODE, tahun=None,
                                        ascending=False, instansi_id=None):
        return self.get_paket(
            'nonspk', start, length, data_only, kategori, search_keyword, rekanan, order, tahun,
            ascending, instansi_id, column_count=9
        )

    def get_paket_swakelola(self, start=0, length=0, data_only=False, search_keyword=None, rekanan=None,
                            order=By.KODE, tahun=None, ascending=False, instansi_id=None,
                            tipe_swakelola: Optional[TipeSwakelola | int] = None):
        extra_params = {}
        if tipe_swakelola is not None:
            if isinstance(tipe_swakelola, TipeSwakelola):
                tipe_swakelola = tipe_swakelola.value
            extra_params['tipeSwakelolaId'] = tipe_swakelola
        return self.get_paket(
            'swakelola', start, length, data_only, None, search_keyword, rekanan, order, tahun,
            ascending, instansi_id, column_count=8, extra_params=extra_params
        )

    def get_paket_pengadaan_darurat(self, start=0, length=0, data_only=False, kategori=None,
                                    search_keyword=None, rekanan=None, order=By.KODE, tahun=None,
                                    ascending=False, instansi_id=None):
        return self.get_paket(
            'darurat-list', start, length, data_only, kategori, search_keyword, rekanan, order, tahun,
            ascending, instansi_id, column_count=8
        )

    @staticmethod
    def get_master_klpd(timeout: int = 30) -> list[dict]:
        """
        Mengambil master data K/L/PD dari LKPP Satu Data.
        kd_klpd dapat digunakan sebagai instansi_id pada pencarian paket.
        """
        resp = requests.get(
            'https://isb.lkpp.go.id/isb-2/api/satudata/MasterKLPD',
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict):
            data = data.get('data', data.get('result', []))
        return data if isinstance(data, list) else []

    def detil_paket_tender(self, id_paket: int | str) -> LpseDetil:
        """
        Mengambil detil pengadaan
        :param id_paket:
        :return:
        """
        return LpseDetil(self, id_paket)

    def detil_paket_non_tender(self, id_paket):
        """
        Mengambil detil pengadaan non tender (penunjukkan langsung)
        :param id_paket: id_paket non tender
        :return:
        """
        return LpseDetilNonTender(self, id_paket)

    def detil_paket_pencatatan_non_tender(self, id_paket):
        return LpseDetilPencatatanNonTender(self, id_paket)

    def detil_paket_swakelola(self, id_paket):
        return LpseDetilSwakelola(self, id_paket)

    def detil_paket_pengadaan_darurat(self, id_paket):
        return LpseDetilPengadaanDarurat(self, id_paket)

    def __del__(self):
        self.session.close()
        del self.session


class BaseLpseDetil(object):
    detail_methods = [
        'get_pengumuman', 'get_peserta', 'get_hasil_evaluasi',
        'get_pemenang', 'get_pemenang_berkontrak', 'get_jadwal'
    ]

    def __init__(self, lpse: Lpse, id_paket: int | str):
        self._lpse = lpse
        self.id_paket = id_paket
        self.pengumuman: Optional[dict] = None
        self.peserta: Optional[list] = None
        self.hasil: Optional[list] = None
        self.pemenang: Optional[list] = None
        self.pemenang_berkontrak: Optional[list] = None
        self.jadwal: Optional[list] = None

    def get_all_detil(self) -> dict:
        info: dict = {
            'error': False,
            'error_message': []
        }
        for name in self.detail_methods:
            try:
                getattr(self, name)()
            except Exception as e:
                info['error'] = True
                info['error_message'].append(
                    '{} - {} - {}'.format(e, self.id_paket, name)
                )
        return info

    def __str__(self) -> str:
        return str(self.todict())

    def todict(self) -> dict:
        data = self.__dict__.copy()
        data.pop('_lpse')
        return data


class LpseDetil(BaseLpseDetil):

    @backoff.on_exception(backoff.fibo,
                          (LpseServerExceptions, requests.exceptions.RequestException,
                           requests.exceptions.ConnectionError),
                          max_tries=3, jitter=None)
    def get_pengumuman(self):
        self.pengumuman = LpseDetilPengumumanParser(self._lpse, self.id_paket).get_detil()

        return self.pengumuman

    @backoff.on_exception(backoff.fibo,
                          (LpseServerExceptions, requests.exceptions.RequestException,
                           requests.exceptions.ConnectionError),
                          max_tries=3, jitter=None)
    def get_peserta(self):
        self.peserta = LpseDetilPesertaParser(self._lpse, self.id_paket).get_detil()

        return self.peserta

    @backoff.on_exception(backoff.fibo,
                          (LpseServerExceptions, requests.exceptions.RequestException,
                           requests.exceptions.ConnectionError),
                          max_tries=3, jitter=None)
    def get_hasil_evaluasi(self):
        self.hasil = LpseDetilHasilEvaluasiParser(self._lpse, self.id_paket).get_detil()

        return self.hasil

    @backoff.on_exception(backoff.fibo,
                          (LpseServerExceptions, requests.exceptions.RequestException,
                           requests.exceptions.ConnectionError),
                          max_tries=3, jitter=None)
    def get_pemenang(self, all=False, key='hasil_negosiasi'):
        self.pemenang = LpseDetilPemenangParser(
            self._lpse,
            self.id_paket,
            all=all,
            key=key
        ).get_detil()

        return self.pemenang

    @backoff.on_exception(backoff.fibo,
                          (LpseServerExceptions, requests.exceptions.RequestException,
                           requests.exceptions.ConnectionError),
                          max_tries=3, jitter=None)
    def get_pemenang_berkontrak(self):
        self.pemenang_berkontrak = LpseDetilPemenangBerkontrakParser(self._lpse, self.id_paket).get_detil()

        return self.pemenang_berkontrak

    @backoff.on_exception(backoff.fibo,
                          (LpseServerExceptions, requests.exceptions.RequestException,
                           requests.exceptions.ConnectionError),
                          max_tries=3, jitter=None)
    def get_jadwal(self):
        self.jadwal = LpseDetilJadwalParser(self._lpse, self.id_paket).get_detil()

        return self.jadwal


class LpseDetilNonTender(BaseLpseDetil):

    @backoff.on_exception(backoff.fibo,
                          (LpseServerExceptions, requests.exceptions.RequestException,
                           requests.exceptions.ConnectionError),
                          max_tries=3, jitter=None)
    def get_pengumuman(self):
        self.pengumuman = LpseDetilPengumumanNonTenderParser(self._lpse, self.id_paket).get_detil()

        return self.pengumuman

    @backoff.on_exception(backoff.fibo,
                          (LpseServerExceptions, requests.exceptions.RequestException,
                           requests.exceptions.ConnectionError),
                          max_tries=3, jitter=None)
    def get_peserta(self):
        self.peserta = LpseDetilPesertaNonTenderParser(self._lpse, self.id_paket).get_detil()

        return self.peserta

    @backoff.on_exception(backoff.fibo,
                          (LpseServerExceptions, requests.exceptions.RequestException,
                           requests.exceptions.ConnectionError),
                          max_tries=3, jitter=None)
    def get_hasil_evaluasi(self):
        self.hasil = LpseDetilHasilEvaluasiNonTenderParser(self._lpse, self.id_paket).get_detil()

        return self.hasil

    @backoff.on_exception(backoff.fibo,
                          (LpseServerExceptions, requests.exceptions.RequestException,
                           requests.exceptions.ConnectionError),
                          max_tries=3, jitter=None)
    def get_pemenang(self):
        self.pemenang = LpseDetilPemenangNonTenderParser(self._lpse, self.id_paket).get_detil()

        return self.pemenang

    @backoff.on_exception(backoff.fibo,
                          (LpseServerExceptions, requests.exceptions.RequestException,
                           requests.exceptions.ConnectionError),
                          max_tries=3, jitter=None)
    def get_pemenang_berkontrak(self):
        self.pemenang_berkontrak = LpseDetilPemenangBerkontrakNonTenderParser(self._lpse, self.id_paket).get_detil()

        return self.pemenang_berkontrak

    @backoff.on_exception(backoff.fibo,
                          (LpseServerExceptions, requests.exceptions.RequestException,
                           requests.exceptions.ConnectionError),
                          max_tries=3, jitter=None)
    def get_jadwal(self):
        self.jadwal = LpseDetilJadwalNonTenderParser(self._lpse, self.id_paket).get_detil()

        return self.jadwal


class LpseDetilPencatatanNonTender(BaseLpseDetil):
    detail_methods = ['get_pengumuman', 'get_pemenang_berkontrak']

    def get_pengumuman(self):
        self.pengumuman = LpseDetilPengumumanPencatatanNonTenderParser(self._lpse, self.id_paket).get_detil()
        return self.pengumuman

    def get_pemenang_berkontrak(self):
        self.pemenang_berkontrak = LpseDetilPemenangBerkontrakPencatatanNonTenderParser(
            self._lpse, self.id_paket
        ).get_detil()
        return self.pemenang_berkontrak


class LpseDetilSwakelola(BaseLpseDetil):
    detail_methods = ['get_pengumuman', 'get_pelaksana']

    def __init__(self, lpse: Lpse, id_paket: int | str):
        super().__init__(lpse, id_paket)
        self.pelaksana: Optional[dict] = None

    def get_pengumuman(self):
        self.pengumuman = LpseDetilPengumumanSwakelolaParser(self._lpse, self.id_paket).get_detil()
        return self.pengumuman

    def get_pelaksana(self):
        self.pelaksana = LpseDetilPelaksanaSwakelolaParser(self._lpse, self.id_paket).get_detil()
        return self.pelaksana


class LpseDetilPengadaanDarurat(BaseLpseDetil):
    detail_methods = ['get_pengumuman', 'get_pemenang_berkontrak']

    def get_pengumuman(self):
        self.pengumuman = LpseDetilPengumumanPengadaanDaruratParser(self._lpse, self.id_paket).get_detil()
        return self.pengumuman

    def get_pemenang_berkontrak(self):
        self.pemenang_berkontrak = LpseDetilPemenangBerkontrakPengadaanDaruratParser(
            self._lpse, self.id_paket
        ).get_detil()
        return self.pemenang_berkontrak


class BaseLpseDetilParser(object):

    detil_path = None

    def __init__(self, lpse, id_paket):
        self.lpse = lpse
        self.id_paket = id_paket

    @backoff.on_exception(backoff.fibo,
                          (LpseServerExceptions, requests.exceptions.RequestException,
                           requests.exceptions.ConnectionError),
                          max_tries=3, jitter=None)
    def get_detil(self):
        url = self.lpse.url+self.detil_path.format(self.id_paket)
        r = self.lpse.session.get(
            url,
            timeout=self.lpse.timeout,
            headers={
                "referer": self.lpse.url
            }
        )

        self.lpse.check_error(r)

        return self.parse_detil(r.content)

    @abstractmethod
    def parse_detil(self, content):
        pass

    @staticmethod
    def parse_currency(nilai):
        result = ''.join(re.findall(r'([\d+,])', nilai)).replace(',', '.')
        try:
            return float(result)
        except ValueError:
            return 0


class LpseDetilPengumumanParser(BaseLpseDetilParser):

    detil_path = '/lelang/{}/pengumumanlelang'

    def parse_detil(self, content):
        soup = Bs(content, 'html5lib')

        content = soup.find('div', {'class': 'content'})
        table = content.find('table', {'class': 'table-bordered'}).find('tbody')

        return self.parse_table(table)

    def parse_table(self, table):
        data = {}

        for tr in table.find_all('tr', recursive=False):
            ths = tr.find_all('th', recursive=False)
            tds = tr.find_all('td', recursive=False)

            for th, td in zip(ths, tds):
                data_key = '_'.join(th.text.strip().split()).lower()

                td_sub_table = td.find('table', recursive=False)

                if td_sub_table and data_key == 'rencana_umum_pengadaan':
                    data_value = self.parse_rup(td_sub_table.find('tbody'))
                elif data_key == 'syarat_kualifikasi':
                    # TODO: Buat parser syarat kualifikasi, tapi perlu tahu dulu kemungkinan format dan isinya
                    continue
                elif data_key == 'lokasi_pekerjaan':
                    data_value = self.parse_lokasi_pekerjaan(td)
                elif data_key in ('nilai_hps_paket', 'nilai_pagu_paket'):
                    data_value = self.parse_currency(' '.join(td.text.strip().split()))
                elif data_key == 'peserta_tender':
                    try:
                        data_value = int(td.text.strip().split()[0])
                    except ValueError:
                        data_value = -1
                elif data_key == 'nama_tender' or data_key == 'nama_paket':
                    data_value, label = self.parse_nama_tender(td)
                    data.update({
                        'label_paket': label
                    })
                else:
                    data_value = ' '.join(td.text.strip().split())

                data.update({
                    data_key: data_value
                })

        return data

    def parse_rup(self, tbody_rup):
        raw_data = []
        for tr in tbody_rup.find_all('tr'):
            raw_data.append([' '.join(i.text.strip().split()) for i in tr.children if not isinstance(i, NavigableString)])

        header = ['_'.join(i.split()).lower() for i in raw_data[0]]
        data = []

        for row in raw_data[1:]:
            item = {}
            item.update(zip(header, row))
            try:
                item.pop('')
            except KeyError:
                pass
            data.append(item)

        return data

    def parse_lokasi_pekerjaan(self, td_pekerjaan):
        return [' '.join(li.text.strip().split()) for li in td_pekerjaan.find_all('li')]

    def parse_nama_tender(self, element):
        label = []
        for i in element.find_all('span'):
            label.append(i.text.strip())
            i.decompose()

        text = element.text.strip()

        return text, label


class LpseDetilPesertaParser(BaseLpseDetilParser):

    detil_path = '/lelang/{}/peserta'

    def parse_detil(self, content):
        soup = Bs(content, 'html5lib')
        table = soup.find('div', {'class': 'content'})\
            .find('table')

        raw_data = [[i for i in tr.stripped_strings] for tr in table.find_all('tr')]

        header = ['_'.join(i.strip().split()).lower() for i in raw_data[0]]

        return [dict(zip(header, i)) for i in raw_data[1:]]


class LpseDetilHasilEvaluasiParser(BaseLpseDetilParser):

    detil_path = '/evaluasi/{}/hasil'
    header_ref = {
        "a": "evaluasi_administrasi",
        "t": "evaluasi_teknis",
        "st": "skor_teknis",
        "p_1": "penawaran",
        "pt": "penawaran_terkoreksi",
        "hn": "hasil_negosiasi",
        "sh": "skor_harga",
        "sa": "skor_akhir",
        "b": "pembuktian_kualifikasi",
        "k": "evaluasi_kualifikasi",
        "sk": "skor_kualifikasi",
        "sb": "skor_pembuktian",
        "h": "evaluasi_harga_biaya",
        "p_2": "pemenang",
        "pk": "pemenang_berkontrak"
    }

    def parse_detil(self, content):
        soup = Bs(content, 'html5lib')
        table = soup.find('div', {'class': 'content'})\
            .find('table')

        if not table:
            return

        is_header = True
        header = []
        data = []

        for tr in table.find_all('tr'):

            if is_header:
                header = ['_'.join(i.text.strip().split()).lower() for i in filter(lambda x: type(x) == bs4.element.Tag, tr.children)]

                # fix duplicate header key for p
                if header.count('p') > 1:
                    first_p_idx = header.index('p')
                    second_p_idx = header.index('p', first_p_idx + 1)
                    header[first_p_idx] = 'p_1'
                    header[second_p_idx] = 'p_2'

                # map header key to reference
                header = list(map(lambda x: self.header_ref.get(x, x), header))

                is_header = False
            else:
                children = [self.parse_icon(i) for i in filter(lambda x: type(x) == bs4.element.Tag, tr.children)]
                children_dict = self.parse_children(dict(zip(header, children)))

                data.append(children_dict)

        return data

    def parse_children(self, children):
        for key, value in children.items():
            if key.startswith('s'):
                try:
                    children[key] = float(value)
                except ValueError:
                    children[key] = 0.0
            elif key in ['penawaran', 'penawaran_terkoreksi', 'hasil_negosiasi']:
                children[key] = self.parse_currency(value)
            elif key in ['evaluasi_harga_biaya', 'pemenang', 'pemenang_berkontrak'] and children[key] != True:
                children[key] = False

        return children

    def parse_nama_npwp(self, peserta):
        return str(peserta).rsplit(' - ', maxsplit=1)

    def parse_icon(self, child):
        status = {
            'fa-check': 1,
            'fa-close': 0,
            'fa-minus': None
        }

        icon = re.findall(r'fa (fa-.*)">', str(child))
        if icon:
            return status[icon[0]]
        elif re.findall(r'star.gif', str(child)):
            return True
        return child.text.strip()


class LpseDetilPemenangParser(BaseLpseDetilParser):

    detil_path = '/evaluasi/{}/pemenang'

    def __init__(self, lpse, id_paket, all=False, key='hasil_negosiasi'):
        super().__init__(lpse, id_paket)
        self.key = key
        self.all = all

    def parse_detil(self, content):
        soup = Bs(content, 'html5lib')

        try:
            table_pemenang = soup.find('div', {'class': 'content'})\
                .table\
                .tbody\
                .find_all('tr', recursive=False)[-1]\
                .find('table')
        except AttributeError:
            return

        if table_pemenang:
            header = ['_'.join(th.text.strip().split()).lower() for th in table_pemenang.find_all('th')]
            all_pemenang = []

            for tr in table_pemenang.find_all('tr'):
                data = [' '.join(td.text.strip().split()) for td in tr.find_all('td')]

                if data:
                    # set default dict untuk data pemenang karena nama header beda-beda
                    # ref: https://github.com/wakataw/pyproc/pull/53
                    pemenang = {
                        'nama_pemenang': None,
                        'alamat': None,
                        'npwp': None,
                        'harga_penawaran': 0,
                        'harga_terkoreksi': 0,
                        'hasil_negosiasi': 0,
                        'harga_negosiasi': 0
                    }

                    for i, v in zip(header, data):
                        if 'reverse_auction' in i:
                            i = 'hasil_negosiasi'

                        pemenang[i] = self.parse_currency(v) \
                            if (v.lower().startswith('rp') or i.startswith('harga') or i.startswith('hasil')) else v

                    all_pemenang.append(pemenang)

            if not all_pemenang:
                return []
            elif self.all:
                all_pemenang = self._check_col_harga_negosiasi(all_pemenang)
                return all_pemenang
            else:
                try:
                    return [min(all_pemenang, key=lambda x: x[self.key])]
                except KeyError:
                    # fallback ke kolom harga penawaran untuk sorting jika kolom hasil negosiasi tidak ditemukan
                    all_pemenang = self._check_col_harga_negosiasi(all_pemenang)
                    return [min(all_pemenang, key=lambda x: x['harga_penawaran'])]
        return

    @staticmethod
    def _check_col_harga_negosiasi(all_pemenang):
        if 'hasil_negosiasi' not in all_pemenang[0]:
            all_pemenang[0]['hasil_negosiasi'] = ''

        return all_pemenang


class LpseDetilPemenangBerkontrakParser(LpseDetilPemenangParser):
    
    detil_path = '/evaluasi/{}/pemenangberkontrak'


class LpseDetilJadwalParser(BaseLpseDetilParser):

    detil_path = '/lelang/{}/jadwal'

    def parse_detil(self, content):
        soup = Bs(content, 'html5lib')
        table = soup.find('table')

        if not table:
            return

        is_header = True
        header = None
        jadwal = []

        for tr in table.find_all('tr'):

            if is_header:
                header = ['_'.join(th.text.strip().split()).lower() for th in tr.find_all('th')]
                is_header = False
            else:
                data = [' '.join(td.text.strip().split()) for td in tr.find_all('td')]
                jadwal.append(dict(zip(header, data)))

        return jadwal


class LpseDetilPengumumanNonTenderParser(LpseDetilPengumumanParser):

    detil_path = '/nontender/{}/pengumumanpl'


class LpseDetilPesertaNonTenderParser(LpseDetilPesertaParser):

    detil_path = '/nontender/{}/peserta'


class LpseDetilHasilEvaluasiNonTenderParser(LpseDetilHasilEvaluasiParser):

    detil_path = '/evaluasinontender/{}/hasil'


class LpseDetilPemenangNonTenderParser(LpseDetilPemenangParser):

    detil_path = '/evaluasinontender/{}/pemenang'


class LpseDetilPemenangBerkontrakNonTenderParser(LpseDetilPemenangNonTenderParser):

    detil_path = '/evaluasinontender/{}/pemenangberkontrak'


class LpseDetilJadwalNonTenderParser(LpseDetilJadwalParser):

    detil_path = '/nontender/{}/jadwal'


class PencatatanTableParserMixin:
    @staticmethod
    def normalize_key(text):
        key = '_'.join(text.strip().split()).lower()
        return key.replace('k/l/pd/instansi_lainnya', 'k/l/pd')

    def parse_table_rows(self, table):
        data = {}
        for tr in self.top_level_rows(table):
            th = tr.find('th', recursive=False)
            td = tr.find('td', recursive=False)
            if not th or not td:
                continue
            data_key = self.normalize_key(th.text)
            sub_table = td.find('table', recursive=False)
            if sub_table and data_key == 'rencana_umum_pengadaan':
                data_value = self.parse_simple_table(sub_table)
            elif data_key.startswith('nilai_'):
                data_value = self.parse_currency(' '.join(td.text.strip().split()))
            else:
                data_value = ' '.join(td.stripped_strings)
            data[data_key] = data_value
        return data

    def parse_simple_table(self, table):
        header = []
        data_rows = []
        for tr in table.find_all('tr'):
            ths = tr.find_all('th', recursive=False)
            if ths and not header:
                header = [self.normalize_key(' '.join(th.stripped_strings)) for th in ths]
                continue
            tds = tr.find_all('td', recursive=False)
            if tds:
                data_rows.append([' '.join(td.stripped_strings) for td in tds])
        if not header:
            return []
        return [dict(zip(header, row)) for row in data_rows if row]

    def parse_realisasi(self, content):
        callout = content.find('div', string=lambda text: text and 'Realisasi' in text)
        if not callout:
            return []
        table = callout.find_next('table')
        if not table:
            return []
        rows = []
        header = []
        for tr in self.top_level_rows(table):
            ths = tr.find_all('th', recursive=False)
            if ths:
                header = [self.normalize_key(th.text) for th in ths]
                continue
            tds = tr.find_all('td', recursive=False)
            if not tds or not header:
                continue
            item = {}
            for key, td in zip(header, tds):
                nested_table = td.find('table')
                if nested_table:
                    nested_header = ' '.join(th.text.strip() for th in nested_table.find_all('th'))
                    nested_key = 'pelaksana' if 'Nama Pelaksana' in nested_header else 'detail'
                    item[nested_key] = self.parse_simple_table(nested_table)
                else:
                    value = ' '.join(td.stripped_strings)
                    if key.startswith('nilai_'):
                        value = self.parse_currency(value)
                    item[key] = value
            has_nested = any(key in item for key in ('pelaksana', 'detail'))
            has_regular_data = any(
                value not in (None, '', [])
                for key, value in item.items()
                if key not in ('pelaksana', 'detail')
            )
            if has_nested and not has_regular_data and rows:
                rows[-1].update({key: value for key, value in item.items() if key in ('pelaksana', 'detail')})
            elif any(value not in (None, '', []) for value in item.values()):
                rows.append(item)
        for nested_table in content.find_all('table'):
            header_text = ' '.join(
                th.text.strip()
                for tr in self.top_level_rows(nested_table)
                for th in tr.find_all('th', recursive=False)
            )
            if 'Nama Pelaksana' not in header_text:
                continue
            pelaksana = self.parse_simple_table(nested_table)
            if pelaksana and rows and not rows[-1].get('pelaksana'):
                rows[-1]['pelaksana'] = pelaksana
        return rows

    def parse_realisasi_groups(self, content):
        callout = content.find('div', string=lambda text: text and 'Realisasi' in text)
        if not callout:
            return []
        table = callout.find_next('table')
        if not table:
            return []

        groups = []
        header = []
        current = None
        for tr in self.top_level_rows(table):
            ths = tr.find_all('th', recursive=False)
            if ths:
                header = [self.normalize_key(th.text) for th in ths]
                continue

            tds = tr.find_all('td', recursive=False)
            if not tds or not header:
                continue

            nested_tables = []
            for td in tds:
                nested_tables.extend(td.find_all('table'))

            values = [' '.join(td.stripped_strings) for td in tds[:len(header)]]
            is_realisasi_row = bool(values and values[0].strip())
            if is_realisasi_row:
                realisasi = {}
                for key, value in zip(header, values):
                    if key.startswith('nilai_'):
                        value = self.parse_currency(value)
                    realisasi[key] = value
                current = {'realisasi': realisasi}
                groups.append(current)

            if not nested_tables:
                continue

            if current is None:
                current = {'realisasi': {}}
                groups.append(current)

            for nested_table in nested_tables:
                nested_key = self.table_group_key(nested_table)
                nested_rows = self.parse_simple_table(nested_table)
                if nested_rows:
                    current.setdefault(nested_key, []).extend(nested_rows)

        return groups

    @staticmethod
    def table_group_key(table):
        header_text = ' '.join(th.text.strip() for th in table.find_all('th'))
        if 'Nama Penyedia' in header_text:
            return 'penyedia'
        if 'Nama Pelaksana' in header_text:
            return 'pelaksana'
        return 'detail'

    @staticmethod
    def top_level_rows(table):
        tbody = table.find('tbody', recursive=False)
        parent = tbody if tbody else table
        return parent.find_all('tr', recursive=False)


class LpseDetilPengumumanPencatatanParser(BaseLpseDetilParser, PencatatanTableParserMixin):
    def parse_detil(self, content):
        soup = Bs(content, 'html5lib')
        content = soup.find('div', {'class': 'content'})
        if not content:
            return {}
        table = content.find('table')
        if not table:
            return {}
        return self.parse_table_rows(table)


class LpseDetilRealisasiPencatatanParser(BaseLpseDetilParser, PencatatanTableParserMixin):
    def parse_detil(self, content):
        soup = Bs(content, 'html5lib')
        content = soup.find('div', {'class': 'content'})
        if not content:
            return {}
        table = content.find('table')
        data = self.parse_table_rows(table) if table else {}
        data['realisasi'] = self.parse_realisasi(content)
        return data


class LpseDetilPemenangBerkontrakPencatatanParser(LpseDetilRealisasiPencatatanParser):
    def parse_detil(self, content):
        soup = Bs(content, 'html5lib')
        content = soup.find('div', {'class': 'content'})
        if not content:
            return []
        return self.parse_realisasi_groups(content)


class LpseDetilPengumumanPencatatanNonTenderParser(LpseDetilPengumumanPencatatanParser):
    detil_path = '/pencatatan/pengumumannonspk?id={}'


class LpseDetilPemenangBerkontrakPencatatanNonTenderParser(LpseDetilPemenangBerkontrakPencatatanParser):
    detil_path = '/pencatatan/pengumumannonspkpemenang?id={}'


class LpseDetilPengumumanSwakelolaParser(LpseDetilPengumumanPencatatanParser):
    detil_path = '/swakelola/{}/pengumuman'


class LpseDetilPelaksanaSwakelolaParser(LpseDetilRealisasiPencatatanParser):
    detil_path = '/swakelola/pengumumanswakelolapelaksana/{}'


class LpseDetilPengumumanPengadaanDaruratParser(LpseDetilPengumumanPencatatanParser):
    detil_path = '/darurat/pengumumandarurat?id={}'


class LpseDetilPemenangBerkontrakPengadaanDaruratParser(LpseDetilPemenangBerkontrakPencatatanParser):
    detil_path = '/darurat/pengumumandaruratpemenang?id={}'
