from abc import abstractmethod, ABCMeta

import requests
import re

from bs4 import BeautifulSoup as Bs
from .exceptions import LpseVersionError


class Lpse(object):
    version = None
    host = None

    def __init__(self, host):
        self.session = requests.session()
        self.session.verify = False
        self.update_info(host)

    def update_info(self, url):
        """
        Update Informasi mengenai versi SPSE dan waktu update data terakhir
        :param url: url LPSE
        :return:
        """
        r = self.session.get(url, verify=False)

        footer = Bs(r.content, 'html5lib').find('div', {'id': 'footer'}).text.strip()

        if not self._is_v4(footer):
            raise LpseVersionError("Versi SPSE harus >= 4")

        self.host = r.url.strip('/')
        self._get_last_update(footer)

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
                  kategori=None, search_keyword=None, nama_penyedia=None):
        """
        Melakukan pencarian paket pengadaan
        :param jenis_paket: Paket Pengadaan Lelang (lelang) atau Penunjukkan Langsung (pl)
        :param start: index data awal
        :param length: jumlah data yang ditampilkan
        :param data_only: hanya menampilkan data tanpa menampilkan informasi lain
        :param kategori: kategori pengadaan (lihat di pypro.kategori)
        :param search_keyword: keyword pencarian paket pengadaan
        :param nama_penyedia: filter berdasarkan nama penyedia
        :return: dictionary dari hasil pencarian paket (atau list jika data_only=True)
        """

        # TODO: Header dari data berbeda untuk tiap SPSE masing-masing ILAP. Cek tiap LPSE tiap ilap untuk menentukan header dari data

        params = {
            'draw': 1,
            'start': start,
            'length': length,
            'search[value]': search_keyword,
            'search[regex]': False
        }

        if kategori:
            params.update({'kategori': kategori})

        if nama_penyedia:
            params.update({'rkn_nama': nama_penyedia})

        if search_keyword:
            for i in range(13):
                params.update({'columns[{}][searchable]'.format(i): 'true'})

        data = requests.get(
            self.host + '/dt/' + jenis_paket,
            params=params,
            verify=False
        )

        data.encoding = 'UTF-8'

        if data_only:
            return data.json()['data']

        return data.json()

    def get_paket_tender(self, start=0, length=0, data_only=False,
                         kategori=None, search_keyword=None, nama_penyedia=None):
        """
        Wrapper pencarian paket tender
        :param start: index data awal
        :param length: jumlah data yang ditampilkan
        :param data_only: hanya menampilkan data tanpa menampilkan informasi lain
        :param kategori: kategori pengadaan (lihat di pypro.kategori)
        :param search_keyword: keyword pencarian paket pengadaan
        :param nama_penyedia: filter berdasarkan nama penyedia
        :return: dictionary dari hasil pencarian paket (atau list jika data_only=True)
        """
        return self.get_paket('lelang', start, length, data_only, kategori, search_keyword)

    def get_paket_non_tender(self, start=0, length=0, data_only=False,
                             kategori=None, search_keyword=None, nama_penyedia=None):
        """
        Wrapper pencarian paket non tender
        :param start: index data awal
        :param length: jumlah data yang ditampilkan
        :param data_only: hanya menampilkan data tanpa menampilkan informasi lain
        :param kategori: kategori pengadaan (lihat di pypro.kategori)
        :param search_keyword: keyword pencarian paket pengadaan
        :param nama_penyedia: filter berdasarkan nama penyedia
        :return: dictionary dari hasil pencarian paket (atau list jika data_only=True)
        """
        return self.get_paket('pl', start, length, data_only, kategori, search_keyword)

    def get_detil(self, id_paket):
        return LpseDetil(self, id_paket)

    def __del__(self):
        self.session.close()
        del self.session


class LpseDetil(object):

    def __init__(self, lpse, id_paket):
        self._lpse = lpse
        self.id_paket = id_paket
        self.get_detil()

    def get_detil(self):
        self.pengumuman = LpseDetilPengumumanParser(self._lpse, self.id_paket).get_detil()

    def __str__(self):
        return str(self.todict())

    def todict(self):
        data = self.__dict__
        data.pop('_lpse')
        return data


class BaseLpseDetilParser(object):

    def __init__(self, lpse, detil_path):
        self.lpse = lpse
        self.detil_path = detil_path

    def get_detil(self):
        r = self.lpse.session.get(self.lpse.host+self.detil_path)
        return self._parse_detil(r.content)

    @abstractmethod
    def _parse_detil(self, content):
        pass


class LpseDetilPengumumanParser(BaseLpseDetilParser):

    def __init__(self, lpse, id_paket):
        super().__init__(lpse, '/lelang/{}/pengumumanlelang'.format(id_paket))

    def _parse_detil(self, content):
        soup = Bs(content, 'html5lib')

        content = soup.find('div', {'class': 'content'})
        table = content.find('table', {'class': 'table-bordered'}).find('tbody')

        return self._parse_table(table)

    def _parse_table(self, table):
        data = {}

        for tr in table.find_all('tr', recursive=False):
            ths = tr.find_all('th', recursive=False)
            tds = tr.find_all('td', recursive=False)

            for th, td in zip(ths, tds):
                data_key = '_'.join(th.text.strip().split()).lower()

                td_sub_table = td.find('table', recursive=False)

                if td_sub_table and data_key == 'rencana_umum_pengadaan':
                    data_value = self._parse_rup(td_sub_table.find('tbody'))
                elif data_key == 'syarat_kualifikasi':
                    # TODO: Buat parser syarat kualifikasi, tapi perlu tahu dulu kemungkinan format dan isinya
                    continue
                elif data_key == 'lokasi_pekerjaan':
                    data_value = self._parse_lokasi_pekerjaan(td)
                else:
                    data_value = ' '.join(td.text.strip().split())

                data.update({
                    data_key: data_value
                })

        return data

    def _parse_rup(self, tbody_rup):
        raw_data = []
        for tr in tbody_rup.find_all('tr', recursive=False):
            raw_data.append([' '.join(i.text.strip().split()) for i in tr.children])

        header = ['_'.join(i.split()).lower() for i in raw_data[0]]
        data = {}

        for row in raw_data[1:]:
            data.update(zip(header, row))

        data.pop('')

        return data

    def _parse_lokasi_pekerjaan(self, td_pekerjaan):
        return [' '.join(li.text.strip().split()) for li in td_pekerjaan.find_all('li')]
