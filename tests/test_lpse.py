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

    def test_get_pemenang_tender(self):
        lpse = Lpse('http://lpse.padang.go.id')
        detil = lpse.detil_paket_tender('2120624')
        expected_result = {
            'nama_pemenang': 'PT. PAMULINDO BUANA ABADI',
            'alamat': 'KOMPLEK PERTOKOAN PAMULANG PERMAI 1 BLOK SH IV/4 - Tangerang Selatan (Kota) - Banten',
            'npwp': '71.035.593.4-411.000', 'harga_penawaran': 1248500000.0, 'harga_terkoreksi': 1248500000.0,
            'reverse_auction': 1248500000.0
        }

        self.assertEqual(detil.get_pemenang(), expected_result)
        self.assertEqual(detil.pemenang, expected_result)

    def test_get_pemenang_tender_kosong(self):
        detil = self.lpse.detil_paket_tender('51026064')
        pemenang = detil.get_pemenang()

        self.assertEqual(pemenang, None)

    def test_get_pemenang_berkontrak_tender(self):
        lpse = Lpse('http://lpse.padang.go.id')
        detil = lpse.detil_paket_tender('2096624')
        detil.get_pemenang_berkontrak()

        expected_result = {
            'nama_pemenang': 'PT.MEGATAMA CITRA LESTARI',
            'alamat': 'JL.RAYA KRESEK RUKO KRESEK NO.88 I DURIKOSAMBI - Jakarta Barat (Kota) - DKI Jakarta',
            'npwp': '66.623.166.7-034.000',
            'harga_penawaran': 567471410.0,
            'hasil_negosiasi': ''
        }

        self.assertEqual(expected_result, detil.pemenang_berkontrak)

    def test_get_jadwal_tender(self):
        data = self.lpse.get_paket_tender(length=1)
        detil = self.lpse.detil_paket_tender(data['data'][0][0])
        detil.get_jadwal()
        jadwal_key = ['no', 'tahap', 'mulai', 'sampai', 'perubahan']

        self.assertIsInstance(detil.jadwal, list)
        for key in detil.jadwal[0]:
            self.assertEqual(True, key in jadwal_key)


class TestPaketNonTender(unittest.TestCase):

    def setUp(self):
        self.lpse = Lpse('http://lpse.padang.go.id')

    def test_get_paket_non_tender(self):
        paket = self.lpse.get_paket_non_tender(length=5)

        print(paket)

    def test_get_detil_pengumuman_non_tender(self):
        detil = self.lpse.detil_paket_non_tender('2189624')
        detil.get_pengumuman()

        expected_result = {'kode_paket': '2189624',
                           'nama_paket': 'Pengadaan fishbox fiber kapasitas 50 liter, 75 liter dan 100 liter',
                           'tanggal_pembuatan': '11 Februari 2019', 'keterangan': '',
                           'tahap_paket_saat_ini': 'Paket Sudah Selesai', 'instansi': 'Pemerintah Daerah Kota Padang',
                           'satuan_kerja': 'DINAS KELAUTAN DAN PERIKANAN', 'kategori': 'Pengadaan Barang',
                           'metode_pengadaan': 'Pengadaan Langsung', 'tahun_anggaran': 'APBD 2019',
                           'nilai_pagu_paket': 199490000.0, 'nilai_hps_paket': 199481975.0,
                           'lokasi_pekerjaan': ['7 Kec. wilayah pesisir Kota Padang - Padang (Kota)'],
                           'kualifikasi_usaha': 'Perusahaan Kecil'}

        self.assertEqual(detil.pengumuman, expected_result)

    def test_get_detil_peserta_non_tender(self):
        detil = self.lpse.detil_paket_non_tender('2189624')
        detil.get_peserta()

        expected_result = [
            {
                'no': '1',
                'nama_peserta': 'cv.samudera fiber',
                'npwp': '83.134.137.5-202.000',
                'harga_penawaran': 'Rp 199.280.125,00',
                'harga_terkoreksi': 'Rp 199.280.125,00'
            }
        ]

        print(detil.peserta)

        self.assertEqual(detil.peserta, expected_result)

if __name__ == '__main__':
    unittest.main()
