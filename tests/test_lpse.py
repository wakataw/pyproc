import unittest
import re

from pyproc.lpse import Lpse


class TestLpse(unittest.TestCase):
    def setUp(self):
        self.lpse = Lpse('https://lpse.pu.go.id')

    def test_version(self):
        v = self.lpse.version
        v_2 = ''.join(re.findall(r'(SPSE v\d+\.\d+u\d+)', v))

        self.assertEqual(v, v_2)

    def test_last_update(self):
        last_update = self.lpse.last_update

        self.assertIsInstance(last_update, str)

    def test_get_paket_tender_kosong(self):
        data = self.lpse.get_paket_tender()

        self.assertIsInstance(data, dict)

    def test_get_paket_tender_isi(self):
        data = self.lpse.get_paket_tender(length=2)

        print(data)

        self.assertEqual(2, len(data['data']))

    def test_get_paket_tender_pagination(self):
        data_1 = self.lpse.get_paket_tender(length=5)
        data_2 = self.lpse.get_paket_tender(start=4, length=5)

        self.assertEqual(data_1['data'][-1], data_2['data'][0])

    def test_get_paket_tender_search(self):
        keyword = 'api kertosono'
        data = self.lpse.get_paket_tender(length=1, search_keyword=keyword)

        for i in data['data']:
            print(i)
            self.assertEqual(True, keyword.lower() in i[1].lower())

    def test_get_detil_tender(self):
        data = self.lpse.get_paket_tender(length=1)
        id_paket = data['data'][0][0]
        detil = self.lpse.detil_paket_tender(id_paket)

        detil.get_pengumuman()

        self.assertEqual(id_paket, detil.pengumuman['kode_tender'])

    def test_get_peserta_tender(self):
        data = self.lpse.get_paket_tender(length=1)
        id_paket = data['data'][0][0]
        detil = self.lpse.detil_paket_tender(id_paket)

        detil.get_peserta()

        self.assertIsInstance(detil.peserta, list)

    def test_get_hasil_evaluasi_tender(self):
        data = self.lpse.get_paket_tender(length=1)
        id_paket = data['data'][0][0]
        detil = self.lpse.detil_paket_tender(id_paket)

        detil.get_hasil_evaluasi()

        self.assertIsInstance(detil.hasil, list)


if __name__ == '__main__':
    unittest.main()
