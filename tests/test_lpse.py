import unittest
import re
import csv
import os
import pyproc.utils

from pyproc import Lpse
from pyproc.exceptions import LpseHostExceptions, LpseServerExceptions


class TestLpse(unittest.TestCase):
    def setUp(self):
        self.lpse = Lpse('lpse.jakarta.go.id', timeout=60, skip_spse_check=True)
        self.id_tender_selesai = self.get_id_for_testing()

    def get_id_for_testing(self):
        paket = self.lpse.get_paket_tender(start=0, length=50)

        for i in paket['data']:
            if i[3].lower().strip() == 'tender sudah selesai':
                return i[0]

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
        keyword = 'sekolah'
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
        detil = self.lpse.detil_paket_tender(self.id_tender_selesai)

        detil.get_hasil_evaluasi()

        self.assertIsInstance(detil.hasil, list)

    def test_get_pemenang_tender(self):
        detil = self.lpse.detil_paket_tender(self.id_tender_selesai)
        detil.get_pemenang()
        for i, v in detil.pemenang[0].items():
            self.assertIsNotNone(v)

    def test_get_pemenang_tender_kosong(self):
        # data = self.lpse.get_paket_tender(length=1)
        # id_paket = data['data'][0][0]
        # detil = self.lpse.detil_paket_tender(id_paket)
        # pemenang = detil.get_pemenang()
        # print(pemenang)
        #
        # self.assertEqual(pemenang, None)
        print("Data terlalu dinamis untuk di test. Uncomment fungsi ini lalu masukan ID tender secara manual untuk di test")
        pass

    def test_get_pemenang_berkontrak_tender(self):
        detil = self.lpse.detil_paket_tender(self.id_tender_selesai)
        detil.get_pemenang_berkontrak()

        if not detil.pemenang_berkontrak:
            print("Belum ada pemenang berkontrak")
            return

        for i, v in detil.pemenang_berkontrak[0].items():
            self.assertIsNotNone(v)

    def test_get_jadwal_tender(self):
        data = self.lpse.get_paket_tender(length=1)
        detil = self.lpse.detil_paket_tender(data['data'][0][0])
        detil.get_jadwal()
        jadwal_key = ['no', 'tahap', 'mulai', 'sampai', 'perubahan']

        self.assertIsInstance(detil.jadwal, list)
        for key in detil.jadwal[0]:
            self.assertEqual(True, key in jadwal_key)

    def test_detil_todict(self):
        detil = self.lpse.detil_paket_tender(self.id_tender_selesai)
        detil.get_all_detil()

        self.assertIsInstance(detil.todict(), dict)

    def test_detil_todict_todict(self):
        detil = self.lpse.detil_paket_tender(self.id_tender_selesai)
        detil.get_all_detil()
        detil.todict()
        detil.todict()

        self.assertIsInstance(detil.todict(), dict)

    def test_detil_id_random(self):
        detil = self.lpse.detil_paket_tender(111)

        self.assertRaises(LpseServerExceptions, detil.get_all_detil)

    def tearDown(self):
        del self.lpse

class TestPaketNonTender(unittest.TestCase):

    def setUp(self):
        self.lpse = Lpse('http://lpse.jakarta.go.id', timeout=30)
        self.lpse.skip_spse_check = True
        self.lpse.auth_token = self.lpse.get_auth_token()
        self.id_non_tender_for_testing = self.get_id_for_testing()

    def get_id_for_testing(self):
        paket = self.lpse.get_paket_non_tender(start=0, length=50)

        for i in paket['data']:
            if i[3].lower().strip() == 'paket sudah selesai':
                return i[0]

    def test_get_paket_non_tender(self):
        paket = self.lpse.get_paket_non_tender(length=5)

        self.assertEqual(len(paket['data']), 5)

    def test_get_detil_pengumuman_non_tender(self):
        detil = self.lpse.detil_paket_non_tender(self.id_non_tender_for_testing)
        detil.get_pengumuman()

        for i, v in detil.pengumuman.items():
            self.assertIsNotNone(v)

    def test_get_detil_peserta_non_tender(self):
        detil = self.lpse.detil_paket_non_tender(self.id_non_tender_for_testing)
        detil.get_peserta()

        for peserta in detil.peserta:
            for i, v in peserta.items():
                self.assertIsNotNone(v)

    def test_get_detil_hasil_non_tender(self):
        detil = self.lpse.detil_paket_non_tender(self.id_non_tender_for_testing)
        detil.get_hasil_evaluasi()

        for hasil in detil.hasil:
            for i, v in hasil.items():
                self.assertIsNotNone(v)

    def test_get_detil_pemenang_non_tender(self):
        detil = self.lpse.detil_paket_non_tender(self.id_non_tender_for_testing)
        detil.get_pemenang()

        for pemenang in detil.pemenang:
            for i, v in pemenang.items():
                self.assertIsNotNone(v)

    def test_get_detil_jadwal_non_tender(self):
        detil = self.lpse.detil_paket_non_tender(self.id_non_tender_for_testing)
        detil.get_jadwal()

        for row in detil.jadwal:
            for i, v in row.items():
                self.assertIsNotNone(v)

    def test_detil_todict(self):
        detil = self.lpse.detil_paket_non_tender(self.id_non_tender_for_testing)
        detil.get_all_detil()

        self.assertIsInstance(detil.todict(), dict)

    def test_detil_todict_todict(self):
        detil = self.lpse.detil_paket_non_tender(self.id_non_tender_for_testing)
        detil.get_all_detil()
        detil.todict()
        detil.todict()

        self.assertIsInstance(detil.todict(), dict)

    def test_detil_id_random(self):
        detil = self.lpse.detil_paket_tender(111)

        self.assertRaises(LpseServerExceptions, detil.get_all_detil)

    def tearDown(self):
        del self.lpse


class TestLpseHostError(unittest.TestCase):

    def test_host_without_scheme(self):
        host = 'lpse.padang.go.id'
        lpse = Lpse(host, timeout=30)

        self.assertEqual(lpse.host.startswith('http'), True)
        self.assertEqual(True, host in lpse.host)

        del lpse

    def test_host_error(self):
        host = 'http://www.pajak.go.id'

        with self.assertRaises(LpseHostExceptions) as context:
            Lpse(host)

        self.assertIn('sepertinya bukan aplikasi SPSE'.format(host), str(context.exception))


# Data terlalu dinamis untuk di test
# class TestLpseDetailKosong(unittest.TestCase):
#
#     def setUp(self):
#         host = 'lpse.padang.go.id'
#
#         lpse = Lpse(host, timeout=30)
#         paket = lpse.get_paket_tender(start=0, length=1)['data']
#         self.detil = lpse.detil_paket_tender(paket[0][0])
#
#     def test_hasil_evaluasi_kosong(self):
#         hasil_evaluasi = self.detil.get_hasil_evaluasi()
#
#         self.assertEqual(None, hasil_evaluasi)
#
#     def test_pemenang_kosong(self):
#         pemenang = self.detil.get_pemenang()
#
#         self.assertEqual(None, pemenang)
#
#     def test_pemenang_berkontrak_kosong(self):
#         pemenang_kontrak = self.detil.get_pemenang_berkontrak()
#
#         self.assertEqual(None, pemenang_kontrak)


# Data terlalu dinamis untuk di test
# class TestLpseDetailKosongNonTender(unittest.TestCase):
#
#     def setUp(self):
#         host = 'http://lpse.bengkuluprov.go.id'
#
#         lpse = Lpse(host)
#         paket = lpse.get_paket_non_tender(start=0, length=1)['data']
#         self.detil = lpse.detil_paket_non_tender(paket[0][0])
#
#     def test_hasil_evaluasi(self):
#         hasil_evaluasi = self.detil.get_hasil_evaluasi()
#
#         for row in hasil_evaluasi:
#             for key in ['no', 'nama_peserta', 'npwp']:
#                 self.assertEqual(key in row, True)
#
#     def test_pemenang(self):
#         pemenang = self.detil.get_pemenang()
#
#         self.assertEqual(None, pemenang)
#
#     def test_pemenang_berkontrak(self):
#         pemenang_berkontrak = self.detil.get_pemenang_berkontrak()
#
#         self.assertEqual(None, pemenang_berkontrak)
#
#     def tearDown(self):
#         del self.detil


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

    def tearDown(self):
        del self.lpse

# akun lpse kaltara di suspend pihak penyedia hosting
# class TestLpseKolomPemenangTidakLengkap(unittest.TestCase):
#
#     def setUp(self):
#         host = 'www.lpse-kaltara.go.id'
#         self.lpse = Lpse(host, skip_spse_check=True)
#
#     def test_get_pemenang(self):
#         detil = self.lpse.detil_paket_tender(1569716)
#         pemenang = detil.get_pemenang()
#         self.assertEqual(
#             pemenang,
#             [{'nama_pemenang': 'CV. NAJAH',
#               'alamat': 'JL. IMAM BONJOL TANJUNG SELOR - Bulungan (Kab.) - Kalimantan Utara',
#               'npwp': '02.673.860.9-727.000', 'harga_penawaran': '', 'hasil_negosiasi': ''}]
#         )
#
#     def tearDown(self):
#         del self.lpse


class TestNpwpNamaSplitter(unittest.TestCase):

    def test_hasil_evaluasi_npwp_nama_split(self):
        with open(
            os.path.join(
                os.path.dirname(os.path.realpath(__file__)),
                'supporting_files',
                'hasil_evaluasi_nama_npwp_test.txt'
            )
        ) as f:
            f.readline()
            csv_reader = csv.reader(f)
            total = 0
            success = 0

            for row in csv_reader:
                status = "ERROR"
                print("{}Test package {} from {} ...".format(" "*4, row[0], row[-1]), end='')

                try:
                    lpse = Lpse(row[-1], timeout=60)
                    detil = lpse.detil_paket_non_tender(row[0])
                    detil.get_hasil_evaluasi()
                except Exception:
                    pass
                else:
                    pemenang = pyproc.utils.get_pemenang_from_hasil_evaluasi(detil.hasil)
                    non_digit = re.findall('[a-zA-Z]+', pemenang[0]['npwp'])

                    self.assertEqual([], non_digit)
                    status = "OK"
                    del lpse

                total += 1
                success = success + (1 if status == "OK" else 0)
                print(status)

            print("Success Rate", success/total)
            self.assertEqual(True, success/total >= 0.8)

if __name__ == '__main__':
    unittest.main()
