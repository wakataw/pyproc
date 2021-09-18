import time
import bs4
import requests
import re
import logging
import backoff
from . import utils
from bs4 import BeautifulSoup as Bs, NavigableString
from .exceptions import LpseVersionException, LpseHostExceptions, LpseServerExceptions, LpseAuthTokenNotFound
from enum import Enum
from abc import abstractmethod
from urllib.parse import urlparse


class By(Enum):
    KODE = 0
    NAMA_PAKET = 1
    INSTANSI = 2
    HPS = 4


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


class Lpse(object):

    def __init__(self, host, timeout=10, info=True, skip_spse_check=False):
        self.session = requests.session()
        self.session.verify = False
        self.host = host
        self.is_lpse = False
        self.skip_spse_check = skip_spse_check
        self.version = None
        self.build_version = 0
        self.last_update = None
        self.timeout = timeout
        self.auth_token = None

        if info:
            self.host = self._check_host(self.host)
            self.update_info()

    def _check_host(self, host):
        parsed_url = urlparse(host)

        scheme = parsed_url.scheme
        netloc = parsed_url.netloc

        if parsed_url.scheme == '':
            scheme = 'http'
            netloc = parsed_url.path

        return '{}://{}'.format(scheme, netloc.strip('/'))

    @staticmethod
    def check_error(resp):
        error_message = None
        content = resp.text

        if resp.status_code >= 400 or \
                re.findall(r'Maaf, terjadi error pada aplikasi SPSE.', content) or \
                re.findall(r'Terjadi Kesalahan', content):
            error_message = "Terjadi error pada aplikasi SPSE."
            error_code = re.findall(r'Kode Error: ([0-9a-zA-Z]+)', content)

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

    def update_info(self):
        """
        Update Informasi mengenai versi SPSE dan waktu update data terakhir
        :param url: url LPSE
        :return:
        """
        r = self.session.get(self.host, verify=False, timeout=self.timeout)
        s = Bs(r.content, 'html5lib')

        if not self.skip_spse_check:
            if not self._is_spse(r.text):
                raise LpseHostExceptions("{} sepertinya bukan aplikasi SPSE".format(self.host))

            footer = s.find('div', {'id': 'footer'}).text.strip()

            if not self._is_v4(footer):
                raise LpseVersionException("Versi SPSE harus >= 4")

            self._get_last_update(footer)

        self.host = self._check_host(r.url) + '/eproc4'

    def _is_spse(self, content):
        self.is_lpse = False
        text = 'harap aktifkan fitur javascript pada browser anda'.lower()

        if text in content.lower():
            self.is_lpse = True
            return self.is_lpse

        return self.is_lpse

    def _is_v4(self, footer):
        """
        Melakukan pengecekan versi LPSE
        :param footer: content footer dari halaman LPSE
        :return: Boolean
        """
        version = re.findall(r'SPSE v(\d+\.\d+)u([0-9]+)', footer, flags=re.DOTALL)

        if version:
            self.version = version[0][0]
            try:
                self.build_version = int(version[0][1])
            except ValueError:
                pass

            if self.version.startswith('4'):
                return True

        return False

    def _get_last_update(self, footer):
        """
        Melakukan pengambilan waktu update terakhir
        :param footer: content footer dari halaman LPSE
        :return:
        """
        last_update = re.findall(r'Update terakhir (\d+-\d+-\d+ \d+:\d+),', footer)

        if last_update:
            self.last_update = last_update[0]

    def get_auth_token(self, from_cookies=True):
        """
        Melakukan pengambilan auth token
        :return: token (str)
        """

        # bypass jika versi kurang dari veri bulan 09

        if self.build_version != 0 and self.build_version < 20191009:
            return None

        r = self.session.get(self.host + '/lelang')

        if from_cookies:
            auth_token = re.findall(r'___AT=([A-Za-z0-9]+)&', self.session.cookies.get('SPSE_SESSION'))

            if auth_token:
                return auth_token[0]

        return utils.parse_token(r.text)

    @backoff.on_exception(backoff.fibo,
                          (LpseServerExceptions, requests.exceptions.RequestException,
                           requests.exceptions.ConnectionError),
                          jitter=None, max_tries=3)
    def get_paket(self, jenis_paket, start=0, length=0, data_only=False,
                  kategori=None, search_keyword=None, nama_penyedia=None,
                  order=By.KODE, tahun=None, ascending=False, instansi_id=None):
        """
        Melakukan pencarian paket pengadaan
        :param jenis_paket: Paket Pengadaan Lelang (lelang) atau Penunjukkan Langsung (pl)
        :param start: index data awal
        :param length: jumlah data yang ditampilkan
        :param data_only: hanya menampilkan data tanpa menampilkan informasi lain
        :param kategori: kategori pengadaan (lihat di lpse.JenisPengadaan)
        :param search_keyword: keyword pencarian paket pengadaan
        :param nama_penyedia: filter berdasarkan nama penyedia
        :param order: Mengurutkan data berdasarkan kolom
        :param tahun: Tahun Pengadaan
        :param ascending: Ascending, descending jika diset False
        :param instansi_id: Filter pencarian berdasarkan instansi atau satker tertentu
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

        for i in range(0, 5):
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

        if nama_penyedia:
            params.update({'rekanan': nama_penyedia})

        if instansi_id:
            params.update({'instansiId': instansi_id})

        data = self.session.get(
            self.host + '/dt/' + jenis_paket,
            params=params,
            verify=False,
            timeout=self.timeout,
            headers={
                'X-Requested-With': 'XMLHttpRequest',
                'Referer': self.host + '/lelang',
                'Sec-Fetch-Mode': 'cors',
                'Sec-Fetch-Site': 'same-origin',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                              'AppleWebKit/537.36 (KHTML, like Gecko) '
                              'Chrome/77.0.3865.90 Safari/537.36'
            }
        )

        logging.debug(data.content)
        self.check_error(data)

        data.encoding = 'UTF-8'

        if data_only:
            return data.json()['data']

        return data.json()

    def get_paket_tender(self, start=0, length=0, data_only=False,
                         kategori=None, search_keyword=None, nama_penyedia=None,
                         order=By.KODE, tahun=None, ascending=False, instansi_id=None):
        """
        Wrapper pencarian paket tender
        :param start: index data awal
        :param length: jumlah data yang ditampilkan
        :param data_only: hanya menampilkan data tanpa menampilkan informasi lain
        :param kategori: kategori pengadaan (lihat di pypro.kategori)
        :param search_keyword: keyword pencarian paket pengadaan
        :param nama_penyedia: filter berdasarkan nama penyedia
        :param order: Mengurutkan data berdasarkan kolom
        :param tahun: Tahun Pengadaan
        :param ascending: Ascending, descending jika diset False
        :param instansi_id: Filter pencarian berdasarkan instansi atau satker tertentu
        :return: dictionary dari hasil pencarian paket (atau list jika data_only=True)
        """
        return self.get_paket('lelang', start, length, data_only, kategori, search_keyword, nama_penyedia,
                              order, tahun, ascending, instansi_id)

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

    def detil_paket_tender(self, id_paket):
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

    def __del__(self):
        self.session.close()
        del self.session


class BaseLpseDetil(object):
    def __init__(self, lpse, id_paket):
        self._lpse = lpse
        self.id_paket = id_paket
        self.pengumuman = None
        self.peserta = None
        self.hasil = None
        self.pemenang = None
        self.pemenang_berkontrak = None
        self.jadwal = None

    def get_all_detil(self):
        info = {
            'error': False,
            'error_message': []
        }
        for name in ['get_pengumuman', 'get_peserta', 'get_hasil_evaluasi', 'get_pemenang', 'get_pemenang_berkontrak',
                     'get_jadwal']:
            try:
                getattr(self, name)()
            except Exception as e:
                info['error'] = True
                info['error_message'].append(
                    '{} - {} - {}'.format(e, self.id_paket, name)
                )
        return info

    def __str__(self):
        return str(self.todict())

    def todict(self):
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
        url = self.lpse.host+self.detil_path.format(self.id_paket)
        r = self.lpse.session.get(url, timeout=self.lpse.timeout)

        self.lpse.check_error(r)

        return self.parse_detil(r.content)

    @abstractmethod
    def parse_detil(self, content):
        pass

    def parse_currency(self, nilai):
        result = ''.join(re.findall(r'([\d+,])', nilai)).replace(',', '.')
        try:
            return float(result)
        except ValueError:
            return -1


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
                is_header = False
            else:
                children = [self.parse_icon(i) for i in filter(lambda x: type(x) == bs4.element.Tag, tr.children)]
                children_dict = self.parse_children(dict(zip(header, children)))

                data.append(children_dict)

        return data

    def parse_children(self, children):
        for key, value in children.items():
            if key.startswith('skor'):
                try:
                    children[key] = float(value)
                except ValueError:
                    children[key] = 0.0
            elif key in ['penawaran', 'penawaran_terkoreksi', 'hasil_negosiasi']:
                children[key] = self.parse_currency(value)
            elif key in ['v', 'p', 'pk'] and children[key] != True:
                children[key] = False

        try:
            nama_npwp = self.parse_nama_npwp(children['nama_peserta'])
            children['nama_peserta'] = nama_npwp[0].strip()
            children['npwp'] = nama_npwp[1].strip()
        except KeyError:
            pass

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
                    pemenang = dict()
                    for i, v in zip(header, data):
                        if 'reverse_auction' in i:
                            i = 'hasil_negosiasi'

                        pemenang[i] = self.parse_currency(v) if v.lower().startswith('rp') else v

                    all_pemenang.append(pemenang)

            if all_pemenang and self.all:
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
