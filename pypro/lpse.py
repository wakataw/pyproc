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

    def __del__(self):
        self.session.close()
        del self.session
