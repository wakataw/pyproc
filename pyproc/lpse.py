import bs4
import requests
import re

from bs4 import BeautifulSoup as Bs, NavigableString
from .exceptions import LpseVersionException, LpseHostExceptions, LpseServerExceptions
from enum import Enum
from abc import abstractmethod
from urllib.parse import urlparse


class By(Enum):
    KODE = 0
    NAMA_PAKET = 1
    INSTANSI = 2
    HPS = 4


class Lpse(object):

    def __init__(self, host, timeout=10, info=True):
        self.session = requests.session()
        self.session.verify = False
        self.host = host
        self.version = None
        self.last_update = None
        self.timeout = timeout
        self._check_host()

        if info:
            self.update_info()

    def _check_host(self):
        parsed_url = urlparse(self.host)

        scheme = parsed_url.scheme
        netloc = parsed_url.netloc

        if parsed_url.scheme == '':
            scheme = 'http'
            netloc = parsed_url.path

        self.host = '{}://{}'.format(scheme, netloc)

    def update_info(self):
        """
        Update Informasi mengenai versi SPSE dan waktu update data terakhir
        :param url: url LPSE
        :return:
        """
        r = self.session.get(self.host, verify=False, timeout=self.timeout)

        if not self._is_spse(r.text):
            raise LpseHostExceptions("{} sepertinya bukan aplikasi SPSE".format(self.host))

        footer = Bs(r.content, 'html5lib').find('div', {'id': 'footer'}).text.strip()

        if not self._is_v4(footer):
            raise LpseVersionException("Versi SPSE harus >= 4")

        self.host = r.url.strip('/')
        self._get_last_update(footer)

    def _is_spse(self, content):
        text = 'Untuk tampilan aplikasi SPSE yang lebih baik, harap aktifkan fitur javascript pada browser anda'.lower()
        if text in content.lower():
            return True

        return False

    def _is_v4(self, footer):
        """
        Melakukan pengecekan versi LPSE
        :param footer: content footer dari halaman LPSE
        :return: Boolean
        """
        version = re.findall(r'(SPSE v4\.\d+u\d+)', footer, flags=re.DOTALL)

        if version:
            self.version = version[0]
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

    def get_paket(self, jenis_paket, start=0, length=0, data_only=False,
                  kategori=None, search_keyword=None, nama_penyedia=None,
                  order=By.KODE, ascending=False):
        """
        Melakukan pencarian paket pengadaan
        :param jenis_paket: Paket Pengadaan Lelang (lelang) atau Penunjukkan Langsung (pl)
        :param start: index data awal
        :param length: jumlah data yang ditampilkan
        :param data_only: hanya menampilkan data tanpa menampilkan informasi lain
        :param kategori: kategori pengadaan (lihat di pypro.kategori)
        :param search_keyword: keyword pencarian paket pengadaan
        :param nama_penyedia: filter berdasarkan nama penyedia
        :param order: Mengurutkan data berdasarkan kolom
        :param ascending: Ascending, descending jika diset False
        :return: dictionary dari hasil pencarian paket (atau list jika data_only=True)
        """

        # TODO: Header dari data berbeda untuk tiap SPSE masing-masing ILAP. Cek tiap LPSE tiap ilap untuk menentukan header dari data

        params = {
            'draw': 1,
            'start': start,
            'length': length,
            'search[value]': search_keyword,
            'search[regex]': False,
            'order[0][column]': order.value,
            'order[0][dir]': 'asc' if ascending else 'desc',
        }

        for i in range(0, 5):
            params.update(
                {
                    'columns[{}][searchable]'.format(i): 'true' if i != 3 else 'false',
                    'columns[{}][orderable]'.format(i): 'true' if i != 3 else 'false',
                    'columns[{}][search][value]'.format(i): '',
                    'columns[{}][search][regex]'.format(i): 'false'
                }
            )

        if kategori:
            params.update({'kategori': kategori})

        if nama_penyedia:
            params.update({'rkn_nama': nama_penyedia})

        data = requests.get(
            self.host + '/dt/' + jenis_paket,
            params=params,
            verify=False,
            timeout=self.timeout
        )

        data.encoding = 'UTF-8'

        if data_only:
            return data.json()['data']

        return data.json()

    def get_paket_tender(self, start=0, length=0, data_only=False,
                         kategori=None, search_keyword=None, nama_penyedia=None,
                         order=By.KODE, ascending=False):
        """
        Wrapper pencarian paket tender
        :param start: index data awal
        :param length: jumlah data yang ditampilkan
        :param data_only: hanya menampilkan data tanpa menampilkan informasi lain
        :param kategori: kategori pengadaan (lihat di pypro.kategori)
        :param search_keyword: keyword pencarian paket pengadaan
        :param nama_penyedia: filter berdasarkan nama penyedia
        :param order: Mengurutkan data berdasarkan kolom
        :param ascending: Ascending, descending jika diset False
        :return: dictionary dari hasil pencarian paket (atau list jika data_only=True)
        """
        return self.get_paket('lelang', start, length, data_only, kategori, search_keyword, nama_penyedia,
                              order, ascending)

    def get_paket_non_tender(self, start=0, length=0, data_only=False,
                             kategori=None, search_keyword=None, order=By.KODE, ascending=False):
        """
        Wrapper pencarian paket non tender
        :param start: index data awal
        :param length: jumlah data yang ditampilkan
        :param data_only: hanya menampilkan data tanpa menampilkan informasi lain
        :param kategori: kategori pengadaan (lihat di pypro.kategori)
        :param search_keyword: keyword pencarian paket pengadaan
        :param nama_penyedia: filter berdasarkan nama penyedia
        :param order: Mengurutkan data berdasarkan kolom
        :param ascending: Ascending, descending jika diset False
        :return: dictionary dari hasil pencarian paket (atau list jika data_only=True)
        """
        return self.get_paket('pl', start, length, data_only, kategori, search_keyword, None, order, ascending)

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


class LpseDetil(object):

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
        self.get_pengumuman()
        self.get_peserta()
        self.get_hasil_evaluasi()
        self.get_pemenang()
        self.get_pemenang_berkontrak()
        self.get_jadwal()

    def get_pengumuman(self):
        self.pengumuman = LpseDetilPengumumanParser(self._lpse, self.id_paket).get_detil()

        return self.pengumuman

    def get_peserta(self):
        self.peserta = LpseDetilPesertaParser(self._lpse, self.id_paket).get_detil()

        return self.peserta

    def get_hasil_evaluasi(self):
        self.hasil = LpseDetilHasilEvaluasiParser(self._lpse, self.id_paket).get_detil()

        return self.hasil

    def get_pemenang(self):
        self.pemenang = LpseDetilPemenangParser(self._lpse, self.id_paket).get_detil()

        return self.pemenang

    def get_pemenang_berkontrak(self):
        self.pemenang_berkontrak = LpseDetilPemenangBerkontrakParser(self._lpse, self.id_paket).get_detil()

        return self.pemenang_berkontrak

    def get_jadwal(self):
        self.jadwal = LpseDetilJadwalParser(self._lpse, self.id_paket).get_detil()

        return self.jadwal

    def __str__(self):
        return str(self.todict())

    def todict(self):
        data = self.__dict__.copy()
        data.pop('_lpse')
        return data


class LpseDetilNonTender(object):

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
        self.get_pengumuman()
        self.get_peserta()
        self.get_hasil_evaluasi()
        self.get_pemenang()
        self.get_pemenang_berkontrak()
        self.get_jadwal()

    def get_pengumuman(self):
        self.pengumuman = LpseDetilPengumumanNonTenderParser(self._lpse, self.id_paket).get_detil()

        return self.pengumuman

    def get_peserta(self):
        self.peserta = LpseDetilPesertaNonTenderParser(self._lpse, self.id_paket).get_detil()

        return self.peserta

    def get_hasil_evaluasi(self):
        self.hasil = LpseDetilHasilEvaluasiNonTenderParser(self._lpse, self.id_paket).get_detil()

        return self.hasil

    def get_pemenang(self):
        self.pemenang = LpseDetilPemenangNonTenderParser(self._lpse, self.id_paket).get_detil()

        return self.pemenang

    def get_pemenang_berkontrak(self):
        self.pemenang_berkontrak = LpseDetilPemenangBerkontrakNonTenderParser(self._lpse, self.id_paket).get_detil()

        return self.pemenang_berkontrak

    def get_jadwal(self):
        self.jadwal = LpseDetilJadwalNonTenderParser(self._lpse, self.id_paket).get_detil()

        return self.jadwal

    def __str__(self):
        return str(self.todict())

    def todict(self):
        data = self.__dict__.copy()
        data.pop('_lpse')
        return data


class BaseLpseDetilParser(object):

    detil_path = None

    def __init__(self, lpse, id_paket):
        self.lpse = lpse
        self.id_paket = id_paket

    def get_detil(self):
        r = self.lpse.session.get(self.lpse.host+self.detil_path.format(self.id_paket), timeout=self.lpse.timeout)

        self._check_error(r.text)

        return self.parse_detil(r.content)

    def _check_error(self, content):
        if re.findall(r'Maaf, terjadi error pada aplikasi SPSE.', content):
            error_message = "Terjadi error pada aplikasi SPSE."
            error_code = re.findall(r'Kode Error: ([0-9a-zA-Z]{9})', content)

            if error_code:
                error_message += ' Kode Error: ' + error_code[0]

            raise LpseServerExceptions(error_message)

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
                else:
                    data_value = ' '.join(td.text.strip().split())

                data.update({
                    data_key: data_value
                })

        return data

    def parse_rup(self, tbody_rup):
        raw_data = []
        for tr in tbody_rup.find_all('tr', recursive=False):
            raw_data.append([' '.join(i.text.strip().split()) for i in tr.children if not isinstance(i, NavigableString)])

        header = ['_'.join(i.split()).lower() for i in raw_data[0]]
        data = {}

        for row in raw_data[1:]:
            data.update(zip(header, row))

        try:
            data.pop('')
        except KeyError:
            pass

        return data

    def parse_lokasi_pekerjaan(self, td_pekerjaan):
        return [' '.join(li.text.strip().split()) for li in td_pekerjaan.find_all('li')]


class LpseDetilPesertaParser(BaseLpseDetilParser):

    detil_path = '/lelang/{}/peserta'

    def parse_detil(self, content):
        soup = Bs(content, 'html5lib')
        table = soup.find('div', {'class': 'content'})\
            .find('table', {'class': 'table-condensed'})

        raw_data = [[i for i in tr.stripped_strings] for tr in table.find_all('tr')]

        header = ['_'.join(i.strip().split()).lower() for i in raw_data[0]]

        return [dict(zip(header, i)) for i in raw_data[1:]]


class LpseDetilHasilEvaluasiParser(BaseLpseDetilParser):

    detil_path = '/evaluasi/{}/hasil'

    def parse_detil(self, content):
        soup = Bs(content, 'html5lib')
        table = soup.find('div', {'class': 'content'})\
            .find('table', {'class': 'table-condensed'})

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

        try:
            nama_npwp = children['nama_peserta'].split('-', maxsplit=1)
            children['nama_peserta'] = nama_npwp[0].strip()
            children['npwp'] = nama_npwp[1].strip()
        except KeyError:
            pass

        return children

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
            return '*'
        return child.text.strip()


class LpseDetilPemenangParser(BaseLpseDetilParser):

    detil_path = '/evaluasi/{}/pemenang'

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
            data = [' '.join(td.text.strip().split()) for td in table_pemenang.find_all('td')]

            if header and data:
                pemenang = dict()
                for i, v in zip(header, data):
                    if 'reverse_auction' in i:
                        i = 'hasil_negosiasi'

                    pemenang[i] = self.parse_currency(v) if v.lower().startswith('rp') else v

                return pemenang
        return


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


class LpseDetilPemenangNonTenderParser(BaseLpseDetilParser):

    detil_path = '/evaluasinontender/{}/pemenang'

    def parse_detil(self, content):
        soup = Bs(content, 'html5lib')
        table_pemenang = soup.find('table')

        if table_pemenang:
            data = dict([(key, value) for key, value in self._parse_table_pemenang(table_pemenang)])

            return None if not data else data

        return

    def _parse_table_pemenang(self, table_pemenang):
        for tr in table_pemenang.find_all('tr'):
            key = '_'.join(tr.find('th').text.strip().split()).lower()
            value = ' '.join(tr.find('td').text.strip().split())

            if key in ['hps', 'pagu', 'hasil_negosiasi']:
                value = self.parse_currency(value)

            yield (key, value)


class LpseDetilPemenangBerkontrakNonTenderParser(LpseDetilPemenangNonTenderParser):

    detil_path = '/evaluasinontender/{}/pemenangberkontrak'


class LpseDetilJadwalNonTenderParser(LpseDetilJadwalParser):

    detil_path = '/nontender/{}/jadwal'
