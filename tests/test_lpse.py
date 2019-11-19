import unittest
import re

from pyproc import Lpse
from pyproc.exceptions import LpseHostExceptions, LpseServerExceptions


class TestLpse(unittest.TestCase):
    def setUp(self):
        self.lpse = Lpse('https://lpse.bengkuluprov.go.id', timeout=30)

    def test_version(self):
        v = self.lpse.version
        v_2 = ''.join(re.findall(r'(SPSE v\d+\.\d+u\d+)', v))

        self.assertEqual(v, v_2)

    def test_get_auth_token(self):
        token = self.lpse.get_auth_token()
        token_from_session = self.lpse.session.cookies['SPSE_SESSION'].split('___')[1].split('=')[1].strip('&')
        self.assertEqual(token, token_from_session)

    def test_get_paket_tender_kosong(self):
        data = self.lpse.get_paket_tender()

        self.assertIsInstance(data, dict)

    def test_get_paket_tender_isi(self):
        data = self.lpse.get_paket_tender(length=2)

        self.assertEqual(2, len(data['data']))

    def test_get_paket_tender_pagination(self):
        data_1 = self.lpse.get_paket_tender(length=5)
        data_2 = self.lpse.get_paket_tender(start=4, length=5)

        self.assertEqual(data_1['data'][-1], data_2['data'][0])

    def test_get_paket_tender_search(self):
        keyword = 'konsentrat'
        data = self.lpse.get_paket_tender(length=1, search_keyword=keyword)

        for i in data['data']:
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
        detil = self.lpse.detil_paket_tender(3676267)

        detil.get_hasil_evaluasi()

        self.assertIsInstance(detil.hasil, list)

    def test_get_pemenang_tender(self):
        detil = self.lpse.detil_paket_tender(3676267)
        detil.get_pemenang()

        nama_pemenang = 'CV. PELANGI NUSANTARA'
        npwp_pemenang = '02.352.426.7-311.000'

        self.assertEqual(nama_pemenang, detil.pemenang[0]['nama_pemenang'])
        self.assertEqual(npwp_pemenang, detil.pemenang[0]['npwp'])

    def test_get_pemenang_tender_kosong(self):
        data = self.lpse.get_paket_tender(length=1)
        id_paket = data['data'][0][0]
        detil = self.lpse.detil_paket_tender(id_paket)
        pemenang = detil.get_pemenang()

        self.assertEqual(pemenang, None)

    def test_get_pemenang_berkontrak_tender(self):
        detil = self.lpse.detil_paket_tender(3676267)
        detil.get_pemenang_berkontrak()

        expected_result = {
            'nama_pemenang': 'CV. PELANGI NUSANTARA',
            'alamat': 'Jl. Meranti 03 No. 11 Sawah Lebar Bengkulu - Bengkulu (Kota) - Bengkulu',
            'npwp': '02.352.426.7-311.000',
            'harga_penawaran': 791309449.11,
            'hasil_negosiasi': 791309449.11
        }

        self.assertEqual(expected_result, detil.pemenang_berkontrak[0])

    def test_get_jadwal_tender(self):
        data = self.lpse.get_paket_tender(length=1)
        detil = self.lpse.detil_paket_tender(data['data'][0][0])
        detil.get_jadwal()
        jadwal_key = ['no', 'tahap', 'mulai', 'sampai', 'perubahan']

        self.assertIsInstance(detil.jadwal, list)
        for key in detil.jadwal[0]:
            self.assertEqual(True, key in jadwal_key)

    def test_detil_todict(self):
        detil = self.lpse.detil_paket_tender(3676267)
        detil.get_all_detil()

        self.assertIsInstance(detil.todict(), dict)

    def test_detil_todict_todict(self):
        detil = self.lpse.detil_paket_tender(3676267)
        detil.get_all_detil()
        detil.todict()
        detil.todict()

        self.assertIsInstance(detil.todict(), dict)

    def test_detil_id_random(self):
        detil = self.lpse.detil_paket_tender(111)

        self.assertRaises(LpseServerExceptions, detil.get_all_detil)


class TestPaketNonTender(unittest.TestCase):

    def setUp(self):
        self.lpse = Lpse('http://lpse.padang.go.id', timeout=30)
        self.lpse.auth_token = self.lpse.get_auth_token()

    def test_get_paket_non_tender(self):
        paket = self.lpse.get_paket_non_tender(length=5)

        self.assertEqual(len(paket['data']), 5)

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

        self.assertEqual(detil.peserta, expected_result)

    def test_get_detil_hasil_non_tender(self):
        detil = self.lpse.detil_paket_non_tender('2189624')
        expected_result = [
            {
                'no': '1', 'nama_peserta': 'cv.samudera fiber', 'a': 1, 't': 1, 'penawaran': 199280125.0,
                'penawaran_terkoreksi': 199280125.0, 'hasil_negosiasi': 198992750.0, 'h': 1, 'p': True, 'pk': True,
                'alasan': '', 'npwp': '83.134.137.5-202.000'
            }
        ]
        detil.get_hasil_evaluasi()

        self.assertEqual(detil.hasil, expected_result)

    def test_get_detil_pemenang_non_tender(self):
        detil = self.lpse.detil_paket_non_tender('4130624')
        expected_result = [{
            'alamat': 'JL.SOSIOLOGI 1 A NO. 22 KOMPL. PGRI I SITEBA PADANG - Padang (Kota) - Sumatera Barat',
            'harga_penawaran': 12155000.0,
            'harga_terkoreksi': 12155000.0,
            'hasil_negosiasi': 12155000.0,
            'nama_pemenang': 'CV.DESIGN ENGINEERING CONSULTAN',
            'npwp': '02.591.921.8-201.000'
        }]
        detil.get_pemenang()

        self.assertEqual(expected_result, detil.pemenang)

    def test_get_detil_pemenang_berkontrak_non_tender(self):
        detil = self.lpse.detil_paket_non_tender('2189624')
        expected_result = [{
            'alamat': 'Jorong Ketaping Nagari Lawang Kec. Matur - Agam (Kab.) - Sumatera Barat',
            'harga_penawaran': 199280125.0,
            'hasil_negosiasi': 198992750.0,
            'nama_pemenang': 'cv.samudera fiber',
            'npwp': '83.134.137.5-202.000'
        }]
        detil.get_pemenang_berkontrak()
        self.assertEqual(expected_result, detil.pemenang_berkontrak)

    def test_get_detil_jadwal_non_tender(self):
        detil = self.lpse.detil_paket_non_tender('2189624')
        expected_result = [
            {'no': '1', 'tahap': 'Upload Dokumen Penawaran', 'mulai': '18 Februari 2019 08:00',
             'sampai': '20 Februari 2019 15:59', 'perubahan': '1 kali perubahan'},
            {'no': '2', 'tahap': 'Pembukaan Dokumen Penawaran', 'mulai': '21 Februari 2019 08:00',
             'sampai': '21 Februari 2019 15:59', 'perubahan': '1 kali perubahan'},
            {'no': '3', 'tahap': 'Evaluasi Penawaran', 'mulai': '22 Februari 2019 08:00',
             'sampai': '22 Februari 2019 15:59', 'perubahan': '2 kali perubahan'},
            {'no': '4', 'tahap': 'Klarifikasi Teknis dan Negosiasi', 'mulai': '25 Februari 2019 08:00',
             'sampai': '25 Februari 2019 15:59', 'perubahan': '1 kali perubahan'},
            {'no': '5', 'tahap': 'Penandatanganan Kontrak', 'mulai': '26 Februari 2019 08:00',
             'sampai': '28 Februari 2019 15:59', 'perubahan': '2 kali perubahan'}
        ]
        detil.get_jadwal()

        self.assertEqual(detil.jadwal, expected_result)

    def test_detil_todict(self):
        detil = self.lpse.detil_paket_non_tender(2189624)
        detil.get_all_detil()

        self.assertIsInstance(detil.todict(), dict)

    def test_detil_todict_todict(self):
        detil = self.lpse.detil_paket_non_tender(2189624)
        detil.get_all_detil()
        detil.todict()
        detil.todict()

        self.assertIsInstance(detil.todict(), dict)

    def test_detil_id_random(self):
        detil = self.lpse.detil_paket_tender(111)

        self.assertRaises(LpseServerExceptions, detil.get_all_detil)


class TestLpseHostError(unittest.TestCase):

    def test_host_without_scheme(self):
        host = 'https://lpse.bengkuluprov.go.id'
        lpse = Lpse(host)

        self.assertEqual(lpse.host.startswith('http'), True)
        self.assertEqual(True, host in lpse.host)

    def test_host_error(self):
        host = 'http://www.pajak.go.id'

        with self.assertRaises(LpseHostExceptions) as context:
            Lpse(host)

        self.assertIn('sepertinya bukan aplikasi SPSE'.format(host), str(context.exception))


class TestLpseDetailKosong(unittest.TestCase):

    def setUp(self):
        host = 'https://lpse.bengkuluprov.go.id'

        lpse = Lpse(host)
        paket = lpse.get_paket_tender(start=0, length=1)['data']
        self.detil = lpse.detil_paket_tender(paket[0][0])

    def test_hasil_evaluasi_kosong(self):
        hasil_evaluasi = self.detil.get_hasil_evaluasi()

        self.assertEqual(None, hasil_evaluasi)

    def test_pemenang_kosong(self):
        pemenang = self.detil.get_pemenang()

        self.assertEqual(None, pemenang)

    def test_pemenang_berkontrak_kosong(self):
        pemenang_kontrak = self.detil.get_pemenang_berkontrak()

        self.assertEqual(None, pemenang_kontrak)


class TestLpseDetailKosongNonTender(unittest.TestCase):

    def setUp(self):
        host = 'http://lpse.bengkuluprov.go.id'

        lpse = Lpse(host)
        paket = lpse.get_paket_non_tender(start=0, length=1)['data']
        self.detil = lpse.detil_paket_non_tender(paket[0][0])

    def test_hasil_evaluasi(self):
        hasil_evaluasi = self.detil.get_hasil_evaluasi()

        for row in hasil_evaluasi:
            for key in ['no', 'nama_peserta', 'npwp']:
                self.assertEqual(key in row, True)

    def test_pemenang(self):
        pemenang = self.detil.get_pemenang()

        self.assertEqual(None, pemenang)

    def test_pemenang_berkontrak(self):
        pemenang_berkontrak = self.detil.get_pemenang_berkontrak()

        self.assertEqual(None, pemenang_berkontrak)


class TestLpsePemenangDoubleTender(unittest.TestCase):

    def setUp(self):
        host = 'http://lpse.tanjabtimkab.go.id'
        self.lpse = Lpse(host)

    def test_pemenang(self):
        expected_winner = {
            3346331: ['CV. NIBUNG PUTIH', '02.005.160.3-334.000'],
            3349331: ['CV. CAHAYA ERVIN GEMILANG', '02.714.891.5-331.000'],
        }

        for id_tender in expected_winner:
            detil = self.lpse.detil_paket_tender(id_tender)
            pemenang = detil.get_pemenang()

            self.assertEqual(expected_winner[id_tender][0], pemenang[0]['nama_pemenang'])
            self.assertEqual(expected_winner[id_tender][1], pemenang[0]['npwp'])

    def test_pemenang_hasil_evaluasi(self):
        detil = self.lpse.detil_paket_tender(3346331)
        detil.get_hasil_evaluasi()
        pemenang = list(filter(lambda x: x['p'], detil.hasil))[0]

        self.assertEqual(pemenang['nama_peserta'], 'CV. NIBUNG PUTIH')
        self.assertEqual(pemenang['npwp'], '02.005.160.3-334.000')




class TestLpseKolomPemenangTidakLengkap(unittest.TestCase):

    def setUp(self):
        host = 'http://www.lpse-kaltara.go.id'
        self.lpse = Lpse(host)

    def test_get_pemenang(self):
        detil = self.lpse.detil_paket_tender(1569716)
        pemenang = detil.get_pemenang()
        self.assertEqual(
            pemenang,
            [{'nama_pemenang': 'CV. NAJAH',
              'alamat': 'JL. IMAM BONJOL TANJUNG SELOR - Bulungan (Kab.) - Kalimantan Utara',
              'npwp': '02.673.860.9-727.000', 'harga_penawaran': '', 'hasil_negosiasi': ''}]
        )


if __name__ == '__main__':
    unittest.main()
