"""Mocked unit tests for pyproc.lpse — no network required."""
import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

from pyproc.lpse import (
    Lpse, LpseDetil, LpseDetilNonTender,
    LpseDetilPengumumanParser, LpseDetilPesertaParser,
    LpseDetilHasilEvaluasiParser, LpseDetilPemenangParser,
    LpseDetilJadwalParser, By, JenisPengadaan,
    KontrakStatus, TipeSwakelola,
    LpseDetilPencatatanNonTender, LpseDetilSwakelola,
    LpseDetilPengadaanDarurat,
    LpseDetilPengumumanPencatatanNonTenderParser,
    LpseDetilPemenangBerkontrakPencatatanNonTenderParser,
    LpseDetilPengumumanSwakelolaParser,
    LpseDetilPelaksanaSwakelolaParser,
    LpseDetilPengumumanPengadaanDaruratParser,
    LpseDetilPemenangBerkontrakPengadaanDaruratParser,
)
from pyproc.exceptions import LpseServerExceptions

FIXTURES = Path(__file__).parent / 'fixtures'


def load_fixture(name):
    return (FIXTURES / name).read_text(encoding='utf-8')


def load_fixture_bytes(name):
    return (FIXTURES / name).read_bytes()


def mock_response(text='', status_code=200, url='http://test', json_data=None, cookies=None):
    """Create a mock requests.Response."""
    resp = MagicMock()
    resp.text = text
    resp.content = text.encode('utf-8') if isinstance(text, str) else text
    resp.status_code = status_code
    resp.url = url
    resp.encoding = 'UTF-8'
    if json_data is not None:
        resp.json.return_value = json_data
    if cookies:
        resp.cookies = cookies
    return resp


class TestLpseInit(unittest.TestCase):

    def test_url_construction(self):
        lpse = Lpse("kemenkeu")
        self.assertEqual(lpse.url, "https://spse.inaproc.id/kemenkeu")

    def test_default_timeout(self):
        lpse = Lpse("test")
        self.assertEqual(lpse.timeout, 10)

    def test_custom_timeout(self):
        lpse = Lpse("test", timeout=30)
        self.assertEqual(lpse.timeout, 30)

    def test_auth_token_initially_none(self):
        lpse = Lpse("test")
        self.assertIsNone(lpse.auth_token)

    def test_verify_default_false(self):
        lpse = Lpse("test")
        self.assertFalse(lpse.session.verify)

    def test_default_user_agent(self):
        """Lpse should use a default User-Agent when none is provided."""
        lpse = Lpse("test")
        ua = lpse.session.headers.get('user-agent', '')
        self.assertIn('Chrome', ua)
        self.assertIn('Safari', ua)

    def test_custom_user_agent(self):
        """Lpse should accept a custom User-Agent string."""
        custom_ua = 'Mozilla/5.0 CustomBot/1.0'
        lpse = Lpse("test", user_agent=custom_ua)
        self.assertEqual(lpse.session.headers['user-agent'], custom_ua)


class TestJitter(unittest.TestCase):

    def test_jitter_returns_float(self):
        from pyproc.lpse import _jitter
        result = _jitter(1.0)
        self.assertIsInstance(result, float)

    def test_jitter_range(self):
        from pyproc.lpse import _jitter
        for _ in range(100):
            result = _jitter(1.0)
            self.assertGreaterEqual(result, 0.5)
            self.assertLessEqual(result, 1.5)

    def test_jitter_zero_delay(self):
        from pyproc.lpse import _jitter
        result = _jitter(0.0)
        self.assertEqual(result, 0.0)


class TestGetAuthToken(unittest.TestCase):

    def test_get_auth_token_from_cookies(self):
        lpse = Lpse("kemenkeu")
        # Mock the session directly on the instance
        lpse.session = MagicMock()
        lpse.session.cookies.get.return_value = 'someprefix___AT=ABC123TOKEN&suffix'
        lpse.session.get.return_value = mock_response(text=load_fixture('lelang_page.html'))

        token = lpse.get_auth_token(from_cookies=True)
        self.assertEqual(token, 'ABC123TOKEN')

    def test_get_auth_token_from_page_js(self):
        lpse = Lpse("kemenkeu")
        lpse.session = MagicMock()
        lpse.session.cookies.get.return_value = ''
        lpse.session.get.return_value = mock_response(text=load_fixture('lelang_page.html'))

        token = lpse.get_auth_token(from_cookies=False)
        self.assertEqual(token, 'TESTTOKENABC123XYZ')


class TestCheckError(unittest.TestCase):

    def test_no_error_on_200(self):
        resp = mock_response(text='<html><body>OK</body></html>', status_code=200)
        # Should not raise
        Lpse.check_error(resp)

    def test_raises_on_400(self):
        resp = mock_response(text='Bad Request', status_code=400, url='http://test/url')
        with self.assertRaises(LpseServerExceptions):
            Lpse.check_error(resp)

    def test_raises_on_spse_error_text(self):
        html = '<html><body>Maaf, terjadi error pada aplikasi SPSE.</body></html>'
        resp = mock_response(text=html, status_code=200, url='http://test/url')
        with self.assertRaises(LpseServerExceptions):
            Lpse.check_error(resp)

    def test_raises_on_spse_error_with_code(self):
        html = '<html><body>Maaf, terjadi error pada aplikasi SPSE. Kode Error: ERR500</body></html>'
        resp = mock_response(text=html, status_code=200, url='http://test/url')
        with self.assertRaises(LpseServerExceptions) as ctx:
            Lpse.check_error(resp)
        self.assertIn('ERR500', str(ctx.exception))

    def test_raises_on_not_found_text(self):
        html = '<html><body>Halaman yang dituju tidak ditemukan</body></html>'
        resp = mock_response(text=html, status_code=200, url='http://test/url')
        with self.assertRaises(LpseServerExceptions) as ctx:
            Lpse.check_error(resp)
        self.assertIn('tidak ditemukan', str(ctx.exception))

    def test_raises_on_terjadi_kesalahan(self):
        html = '<html><body>Terjadi Kesalahan pada sistem</body></html>'
        resp = mock_response(text=html, status_code=200, url='http://test/url')
        with self.assertRaises(LpseServerExceptions):
            Lpse.check_error(resp)


class TestGetPaket(unittest.TestCase):

    def setUp(self):
        self.lpse = Lpse("kemenkeu")
        self.lpse.auth_token = 'TEST_TOKEN'

    @patch.object(Lpse, 'check_error')
    def test_get_paket_returns_dict(self, mock_check_error):
        json_data = json.loads(load_fixture('dt_lelang.json'))
        resp = mock_response(json_data=json_data)
        self.lpse.session.post = MagicMock(return_value=resp)

        result = self.lpse.get_paket('lelang', start=0, length=10)

        self.assertIsInstance(result, dict)
        self.assertIn('data', result)
        self.assertIn('recordsTotal', result)
        self.assertEqual(len(result['data']), 2)

    @patch.object(Lpse, 'check_error')
    def test_get_paket_data_only_returns_list(self, mock_check_error):
        json_data = json.loads(load_fixture('dt_lelang.json'))
        resp = mock_response(json_data=json_data)
        self.lpse.session.post = MagicMock(return_value=resp)

        result = self.lpse.get_paket('lelang', data_only=True)

        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)

    @patch.object(Lpse, 'check_error')
    def test_get_paket_sends_auth_token(self, mock_check_error):
        json_data = json.loads(load_fixture('dt_lelang.json'))
        resp = mock_response(json_data=json_data)
        self.lpse.session.post = MagicMock(return_value=resp)

        self.lpse.get_paket('lelang')

        call_kwargs = self.lpse.session.post.call_args
        posted_data = call_kwargs[1]['data'] if 'data' in call_kwargs[1] else call_kwargs[0][1]
        self.assertEqual(posted_data['authenticityToken'], 'TEST_TOKEN')

    @patch.object(Lpse, 'check_error')
    def test_get_paket_with_kategori(self, mock_check_error):
        json_data = json.loads(load_fixture('dt_lelang.json'))
        resp = mock_response(json_data=json_data)
        self.lpse.session.post = MagicMock(return_value=resp)

        self.lpse.get_paket('lelang', kategori=JenisPengadaan.PENGADAAN_BARANG)

        call_kwargs = self.lpse.session.post.call_args
        posted_data = call_kwargs[1]['data'] if 'data' in call_kwargs[1] else call_kwargs[0][1]
        self.assertEqual(posted_data['kategoriId'], 0)

    @patch.object(Lpse, 'check_error')
    def test_get_paket_with_rekanan_instansi_order_and_kontrak_status(self, mock_check_error):
        json_data = json.loads(load_fixture('dt_lelang.json'))
        resp = mock_response(json_data=json_data)
        self.lpse.session.post = MagicMock(return_value=resp)

        self.lpse.get_paket(
            'lelang',
            rekanan='PT Test',
            instansi_id='K66',
            order=By.HPS,
            ascending=False,
            kontrak_status=KontrakStatus.SELESAI,
        )

        call_kwargs = self.lpse.session.post.call_args
        posted_data = call_kwargs[1]['data'] if 'data' in call_kwargs[1] else call_kwargs[0][1]
        self.assertEqual(posted_data['rekanan'], 'PT Test')
        self.assertEqual(posted_data['rkn_nama'], 'PT Test')
        self.assertEqual(posted_data['instansiId'], 'K66')
        self.assertEqual(posted_data['order[0][column]'], By.HPS.value)
        self.assertEqual(posted_data['order[0][dir]'], 'desc')
        self.assertEqual(posted_data['kontrakStatus'], 0)

    @patch.object(Lpse, 'check_error')
    def test_get_paket_accepts_legacy_nama_penyedia_alias(self, mock_check_error):
        json_data = json.loads(load_fixture('dt_lelang.json'))
        resp = mock_response(json_data=json_data)
        self.lpse.session.post = MagicMock(return_value=resp)

        self.lpse.get_paket('lelang', nama_penyedia='PT Legacy')

        call_kwargs = self.lpse.session.post.call_args
        posted_data = call_kwargs[1]['data'] if 'data' in call_kwargs[1] else call_kwargs[0][1]
        self.assertEqual(posted_data['rekanan'], 'PT Legacy')

    @patch.object(Lpse, 'check_error')
    def test_get_paket_auto_fetches_auth_token(self, mock_check_error):
        self.lpse.auth_token = None
        json_data = json.loads(load_fixture('dt_lelang.json'))
        resp = mock_response(json_data=json_data)
        # Mock session for both post (get_paket) and get (get_auth_token)
        self.lpse.session = MagicMock()
        self.lpse.session.post.return_value = resp
        self.lpse.session.get.return_value = mock_response(text=load_fixture('lelang_page.html'))
        self.lpse.session.cookies.get.return_value = ''

        self.lpse.get_paket('lelang')

        self.assertIsNotNone(self.lpse.auth_token)

    def test_get_paket_tender_calls_get_paket(self):
        self.lpse.get_paket = MagicMock(return_value={'data': []})
        self.lpse.get_paket_tender(start=0, length=5)
        self.lpse.get_paket.assert_called_once_with(
            'lelang', 0, 5, False, None, None, None, By.KODE, None, False, None
        )

    def test_get_paket_non_tender_calls_get_paket(self):
        self.lpse.get_paket = MagicMock(return_value={'data': []})
        self.lpse.get_paket_non_tender(start=0, length=5)
        self.lpse.get_paket.assert_called_once_with(
            'pl', 0, 5, False, None, None, None, By.KODE, None, False, None
        )

    def test_get_paket_non_tender_accepts_rekanan(self):
        self.lpse.get_paket = MagicMock(return_value={'data': []})
        self.lpse.get_paket_non_tender(start=0, length=5, rekanan='PT A')
        self.lpse.get_paket.assert_called_once_with(
            'pl', 0, 5, False, None, None, 'PT A', By.KODE, None, False, None
        )

    def test_get_paket_non_tender_accepts_legacy_nama_penyedia_alias(self):
        self.lpse.get_paket = MagicMock(return_value={'data': []})
        self.lpse.get_paket_non_tender(start=0, length=5, nama_penyedia='PT Legacy')
        self.lpse.get_paket.assert_called_once_with(
            'pl', 0, 5, False, None, None, 'PT Legacy', By.KODE, None, False, None
        )

    def test_get_paket_pencatatan_non_tender_calls_get_paket(self):
        self.lpse.get_paket = MagicMock(return_value={'data': []})
        self.lpse.get_paket_pencatatan_non_tender(start=0, length=5, rekanan='PT A')
        self.lpse.get_paket.assert_called_once_with(
            'nonspk', 0, 5, False, None, None, 'PT A', By.KODE, None, False, None, column_count=9
        )

    def test_get_paket_swakelola_calls_get_paket_with_tipe(self):
        self.lpse.get_paket = MagicMock(return_value={'data': []})
        self.lpse.get_paket_swakelola(start=0, length=5, tipe_swakelola=TipeSwakelola.KLPD_LAIN)
        self.lpse.get_paket.assert_called_once_with(
            'swakelola', 0, 5, False, None, None, None, By.KODE, None, False, None,
            column_count=8, extra_params={'tipeSwakelolaId': 2}
        )

    def test_get_paket_pengadaan_darurat_calls_get_paket(self):
        self.lpse.get_paket = MagicMock(return_value={'data': []})
        self.lpse.get_paket_pengadaan_darurat(start=0, length=5, kategori=JenisPengadaan.PEKERJAAN_KONSTRUKSI)
        self.lpse.get_paket.assert_called_once_with(
            'darurat-list', 0, 5, False, JenisPengadaan.PEKERJAAN_KONSTRUKSI, None, None,
            By.KODE, None, False, None, column_count=8
        )

    @patch('pyproc.lpse._get_ssl_verify', return_value=True)
    @patch('pyproc.lpse.requests.get')
    def test_get_master_klpd(self, mock_get, _mock_verify):
        mock_get.return_value = mock_response(json_data=[
            {
                "kd_klpd": "K66",
                "nama_klpd": "Kementerian Kependudukan dan Pembangunan Keluarga/BKKBN",
                "jenis_klpd": "KEMENTERIAN",
                "kd_provinsi": 11,
                "kd_kabupaten": 14748,
            }
        ])

        result = Lpse.get_master_klpd(timeout=5)

        self.assertEqual(result[0]["kd_klpd"], "K66")
        mock_get.assert_called_once_with(
            'https://isb.lkpp.go.id/isb-2/api/satudata/MasterKLPD',
            timeout=5, verify=True,
        )

    def tearDown(self):
        del self.lpse


class TestIsbApis(unittest.TestCase):
    """Tests for ISB Satu Data static methods on Lpse."""

    @patch('pyproc.lpse._get_ssl_verify', return_value=True)
    @patch('pyproc.lpse.requests.get')
    def test_get_master_lpse(self, mock_get, _mock_verify):
        mock_get.return_value = mock_response(json_data=[
            {
                "kd_lpse": 119,
                "nama_lpse": "LPSE Lembaga Kebijakan Pengadaan Barang/Jasa Pemerintah",
                "_event_date": "2026-01-16",
            },
            {
                "kd_lpse": 10,
                "nama_lpse": "LPSE Kota Surabaya",
                "_event_date": "2026-01-16",
            },
        ])

        result = Lpse.get_master_lpse(timeout=10)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["kd_lpse"], 119)
        self.assertEqual(result[0]["nama_lpse"],
                         "LPSE Lembaga Kebijakan Pengadaan Barang/Jasa Pemerintah")
        mock_get.assert_called_once_with(
            'https://isb.lkpp.go.id/isb-2/api/satudata/MasterLPSE',
            timeout=10, verify=True,
        )

    @patch('pyproc.lpse.requests.get')
    def test_get_master_lpse_dict_wrapper(self, mock_get):
        """Response wrapped in {'data': [...]} should be unwrapped."""
        mock_get.return_value = mock_response(json_data={
            "data": [
                {"kd_lpse": 1, "nama_lpse": "LPSE Test",
                 "_event_date": "2026-01-01"},
            ]
        })

        result = Lpse.get_master_lpse()

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["kd_lpse"], 1)

    @patch('pyproc.lpse.requests.get')
    def test_get_master_lpse_empty(self, mock_get):
        mock_get.return_value = mock_response(json_data=[])

        result = Lpse.get_master_lpse()

        self.assertEqual(result, [])

    @patch('pyproc.lpse._get_ssl_verify', return_value=True)
    @patch('pyproc.lpse.requests.get')
    def test_get_tender_umum_publik(self, mock_get, _mock_verify):
        mock_get.return_value = mock_response(json_data=[
            {
                "Kode Tender": 10109010000,
                "LPSE": "LPSE Lembaga Kebijakan Pengadaan Barang/Jasa Pemerintah",
                "Nama Paket": "Pekerjaan Jasa Sewa",
                "Pagu": 20000000000,
            }
        ])

        result = Lpse.get_tender_umum_publik(
            tahun_anggaran=2026, kd_lpse=119, timeout=10,
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["Kode Tender"], 10109010000)
        self.assertEqual(result[0]["Nama Paket"], "Pekerjaan Jasa Sewa")
        mock_get.assert_called_once_with(
            'https://isb.lkpp.go.id/isb-2/api/satudata/TenderUmumPublik/2026/119',
            timeout=10, verify=True,
        )

    @patch('pyproc.lpse.requests.get')
    def test_get_tender_umum_publik_dict_wrapper(self, mock_get):
        """Response wrapped in {'result': [...]} should be unwrapped."""
        mock_get.return_value = mock_response(json_data={
            "result": [
                {"Kode Tender": 1, "Nama Paket": "Test"},
            ]
        })

        result = Lpse.get_tender_umum_publik(
            tahun_anggaran=2025, kd_lpse=99,
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["Kode Tender"], 1)

    @patch('pyproc.lpse.requests.get')
    def test_get_tender_umum_publik_empty(self, mock_get):
        mock_get.return_value = mock_response(json_data=[])

        result = Lpse.get_tender_umum_publik(
            tahun_anggaran=2026, kd_lpse=999,
        )

        self.assertEqual(result, [])

    @patch('pyproc.lpse.requests.get')
    def test_get_tender_umum_publik_http_error(self, mock_get):
        from requests.exceptions import HTTPError
        resp = mock_response(status_code=500)
        resp.raise_for_status.side_effect = HTTPError("500 Server Error")
        mock_get.return_value = resp

        with self.assertRaises(HTTPError):
            Lpse.get_tender_umum_publik(
                tahun_anggaran=2026, kd_lpse=1,
            )

    @patch('pyproc.lpse.requests.get')
    def test_get_tender_umum_publik_non_json_error(self, mock_get):
        """API returns text error like URL-NOT-DEFINED for invalid kd_lpse."""
        resp = mock_response(
            text='URL-NOT-DEFINED: /isb-2/api/satudata/TenderUmumPublik/2026/x',
            status_code=200,
        )
        resp.json.side_effect = ValueError("JSON decode error")
        mock_get.return_value = resp

        result = Lpse.get_tender_umum_publik(
            tahun_anggaran=2026, kd_lpse=99999,
        )

        self.assertEqual(result, [])

    @patch('pyproc.lpse.requests.get')
    def test_get_master_lpse_non_json_error(self, mock_get):
        resp = mock_response(
            text='Some error text',
            status_code=200,
        )
        resp.json.side_effect = ValueError("JSON decode error")
        mock_get.return_value = resp

        result = Lpse.get_master_lpse()

        self.assertEqual(result, [])


class TestDetilPaket(unittest.TestCase):

    def setUp(self):
        self.lpse = Lpse("kemenkeu")

    def test_detil_paket_tender_returns_lpse_detil(self):
        detil = self.lpse.detil_paket_tender(10080116000)
        self.assertIsInstance(detil, LpseDetil)
        self.assertEqual(detil.id_paket, 10080116000)

    def test_detil_paket_non_tender_returns_lpse_detil_non_tender(self):
        detil = self.lpse.detil_paket_non_tender(10080116000)
        self.assertIsInstance(detil, LpseDetilNonTender)

    def test_detil_pencatatan_non_tender_returns_detail(self):
        detil = self.lpse.detil_paket_pencatatan_non_tender(10942236000)
        self.assertIsInstance(detil, LpseDetilPencatatanNonTender)

    def test_detil_swakelola_returns_detail(self):
        detil = self.lpse.detil_paket_swakelola(10336514000)
        self.assertIsInstance(detil, LpseDetilSwakelola)

    def test_detil_pengadaan_darurat_returns_detail(self):
        detil = self.lpse.detil_paket_pengadaan_darurat(106802)
        self.assertIsInstance(detil, LpseDetilPengadaanDarurat)

    def test_detil_initial_attributes_are_none(self):
        detil = self.lpse.detil_paket_tender(10080116000)
        self.assertIsNone(detil.pengumuman)
        self.assertIsNone(detil.peserta)
        self.assertIsNone(detil.hasil)
        self.assertIsNone(detil.pemenang)
        self.assertIsNone(detil.pemenang_berkontrak)
        self.assertIsNone(detil.jadwal)

    def tearDown(self):
        del self.lpse


class TestBaseLpseDetil(unittest.TestCase):

    def setUp(self):
        self.lpse = Lpse("kemenkeu")
        self.detil = self.lpse.detil_paket_tender(10080116000)

    def test_todict_excludes_lpse(self):
        d = self.detil.todict()
        self.assertNotIn('_lpse', d)
        self.assertIn('id_paket', d)

    def test_todict_returns_dict(self):
        d = self.detil.todict()
        self.assertIsInstance(d, dict)

    def test_todict_called_twice(self):
        d1 = self.detil.todict()
        d2 = self.detil.todict()
        self.assertIsInstance(d1, dict)
        self.assertIsInstance(d2, dict)

    def test_get_all_detil_returns_error_info(self):
        # With no network, all detail fetches will fail
        # But get_all_detil should catch exceptions and return error info
        info = self.detil.get_all_detil()
        self.assertIsInstance(info, dict)
        self.assertIn('error', info)
        self.assertIn('error_message', info)

    def tearDown(self):
        del self.lpse


class TestPengumumanParser(unittest.TestCase):

    def test_parse_pengumuman(self):
        content = load_fixture_bytes('pengumuman_lelang.html')
        lpse = Lpse("kemenkeu")
        parser = LpseDetilPengumumanParser(lpse, 10080116000)
        result = parser.parse_detil(content)

        self.assertIsInstance(result, dict)
        self.assertEqual(result['kode_tender'], '10080116000')
        self.assertIn('nama_tender', result)
        self.assertIn('tahun_anggaran', result)
        self.assertIn('nilai_pagu_paket', result)
        self.assertIn('nilai_hps_paket', result)
        self.assertEqual(result['label_paket'], ['Pengadaan Barang'])

    def test_parse_pengumuman_currency(self):
        content = load_fixture_bytes('pengumuman_lelang.html')
        lpse = Lpse("kemenkeu")
        parser = LpseDetilPengumumanParser(lpse, 10080116000)
        result = parser.parse_detil(content)

        self.assertIsInstance(result['nilai_pagu_paket'], float)
        self.assertEqual(result['nilai_pagu_paket'], 1000000000.0)
        self.assertEqual(result['nilai_hps_paket'], 950000000.0)

    def test_parse_pengumuman_peserta_count(self):
        content = load_fixture_bytes('pengumuman_lelang.html')
        lpse = Lpse("kemenkeu")
        parser = LpseDetilPengumumanParser(lpse, 10080116000)
        result = parser.parse_detil(content)

        self.assertEqual(result['peserta_tender'], 5)

    def test_parse_pengumuman_lokasi(self):
        content = load_fixture_bytes('pengumuman_lelang.html')
        lpse = Lpse("kemenkeu")
        parser = LpseDetilPengumumanParser(lpse, 10080116000)
        result = parser.parse_detil(content)

        self.assertIsInstance(result['lokasi_pekerjaan'], list)
        self.assertIn('Jakarta - DKI Jakarta', result['lokasi_pekerjaan'])

    def test_parse_pengumuman_rup(self):
        content = load_fixture_bytes('pengumuman_lelang.html')
        lpse = Lpse("kemenkeu")
        parser = LpseDetilPengumumanParser(lpse, 10080116000)
        result = parser.parse_detil(content)

        self.assertIsInstance(result['rencana_umum_pengadaan'], list)
        self.assertEqual(len(result['rencana_umum_pengadaan']), 1)
        self.assertEqual(result['rencana_umum_pengadaan'][0]['kode_rup'], 'RUP-001')


class TestPesertaParser(unittest.TestCase):

    def test_parse_peserta(self):
        content = load_fixture_bytes('peserta.html')
        lpse = Lpse("kemenkeu")
        parser = LpseDetilPesertaParser(lpse, 10080116000)
        result = parser.parse_detil(content)

        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)
        self.assertIn('nama_peserta', result[0])
        self.assertEqual(result[0]['nama_peserta'], 'PT. Test Satu')


class TestHasilEvaluasiParser(unittest.TestCase):

    def test_parse_hasil_evaluasi(self):
        content = load_fixture_bytes('hasil_evaluasi.html')
        lpse = Lpse("kemenkeu")
        parser = LpseDetilHasilEvaluasiParser(lpse, 10080116000)
        result = parser.parse_detil(content)

        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)

        # First row: winner (star icon)
        self.assertTrue(result[0]['pemenang'])
        self.assertEqual(result[0]['evaluasi_administrasi'], 1)  # fa-check
        self.assertEqual(result[0]['evaluasi_teknis'], 1)  # fa-check

        # Second row: not winner (fa-minus -> None -> False via parse_children)
        self.assertFalse(result[1]['pemenang'])
        self.assertEqual(result[1]['evaluasi_administrasi'], 1)  # fa-check
        self.assertEqual(result[1]['evaluasi_teknis'], 0)  # fa-close

    def test_parse_hasil_evaluasi_scores(self):
        content = load_fixture_bytes('hasil_evaluasi.html')
        lpse = Lpse("kemenkeu")
        parser = LpseDetilHasilEvaluasiParser(lpse, 10080116000)
        result = parser.parse_detil(content)

        self.assertEqual(result[0]['skor_teknis'], 85.0)
        self.assertEqual(result[0]['skor_harga'], 95.0)
        self.assertEqual(result[0]['skor_akhir'], 90.0)

    def test_parse_hasil_evaluasi_currency(self):
        content = load_fixture_bytes('hasil_evaluasi.html')
        lpse = Lpse("kemenkeu")
        parser = LpseDetilHasilEvaluasiParser(lpse, 10080116000)
        result = parser.parse_detil(content)

        self.assertEqual(result[0]['penawaran'], 900000000.0)
        self.assertEqual(result[0]['penawaran_terkoreksi'], 900000000.0)
        self.assertEqual(result[0]['hasil_negosiasi'], 900000000.0)

    def test_parse_hasil_evaluasi_empty_table(self):
        lpse = Lpse("kemenkeu")
        parser = LpseDetilHasilEvaluasiParser(lpse, 10080116000)
        result = parser.parse_detil(b'<html><body><div class="content"></div></body></html>')
        self.assertIsNone(result)


class TestPemenangParser(unittest.TestCase):

    def test_parse_pemenang(self):
        content = load_fixture_bytes('pemenang.html')
        lpse = Lpse("kemenkeu")
        parser = LpseDetilPemenangParser(lpse, 10080116000)
        result = parser.parse_detil(content)

        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['nama_pemenang'], 'PT. Test Satu')
        self.assertEqual(result[0]['alamat'], 'Jl. Test No. 1, Jakarta')
        self.assertEqual(result[0]['npwp'], '01.234.567.8-012.000')

    def test_parse_pemenang_currency(self):
        content = load_fixture_bytes('pemenang.html')
        lpse = Lpse("kemenkeu")
        parser = LpseDetilPemenangParser(lpse, 10080116000)
        result = parser.parse_detil(content)

        self.assertEqual(result[0]['harga_penawaran'], 900000000.0)
        self.assertEqual(result[0]['harga_terkoreksi'], 900000000.0)
        self.assertEqual(result[0]['hasil_negosiasi'], 880000000.0)

    def test_parse_pemenang_empty_table(self):
        lpse = Lpse("kemenkeu")
        parser = LpseDetilPemenangParser(lpse, 10080116000)
        result = parser.parse_detil(b'<html><body><div class="content"></div></body></html>')
        self.assertIsNone(result)

    def test_parse_pemenang_all_flag(self):
        content = load_fixture_bytes('pemenang.html')
        lpse = Lpse("kemenkeu")
        parser = LpseDetilPemenangParser(lpse, 10080116000, all=True)
        result = parser.parse_detil(content)

        self.assertIsInstance(result, list)


class TestJadwalParser(unittest.TestCase):

    def test_parse_jadwal(self):
        content = load_fixture_bytes('jadwal.html')
        lpse = Lpse("kemenkeu")
        parser = LpseDetilJadwalParser(lpse, 10080116000)
        result = parser.parse_detil(content)

        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)
        self.assertIn('tahap', result[0])
        self.assertIn('mulai', result[0])
        self.assertIn('sampai', result[0])

    def test_parse_jadwal_empty_table(self):
        lpse = Lpse("kemenkeu")
        parser = LpseDetilJadwalParser(lpse, 10080116000)
        result = parser.parse_detil(b'<html><body></body></html>')
        self.assertIsNone(result)


class TestPencatatanParsers(unittest.TestCase):

    def test_parse_pencatatan_non_tender_pengumuman(self):
        lpse = Lpse("nasional")
        parser = LpseDetilPengumumanPencatatanNonTenderParser(lpse, 10942236000)
        result = parser.parse_detil(load_fixture_bytes('nonspk_pengumuman.html'))
        self.assertEqual(result['kode_paket'], '10942236000')
        self.assertEqual(result['jenis_pengadaan'], 'Jasa Lainnya')
        self.assertEqual(result['nilai_pagu_paket'], 3800000.0)
        self.assertEqual(result['rencana_umum_pengadaan'][0]['kode_rup'], '62075727')

    def test_parse_pencatatan_non_tender_pemenang_berkontrak(self):
        lpse = Lpse("nasional")
        parser = LpseDetilPemenangBerkontrakPencatatanNonTenderParser(lpse, 10942236000)
        result = parser.parse_detil(load_fixture_bytes('nonspk_pemenang_berkontrak.html'))
        self.assertEqual(result[0]['realisasi']['nilai_realisasi'], 266400.0)
        self.assertEqual(result[0]['realisasi']['jenis_realisasi'], 'Dokumen FA Detail')

    def test_parse_pencatatan_non_tender_pemenang_berkontrak_nested_penyedia(self):
        lpse = Lpse("kemenkeu")
        parser = LpseDetilPemenangBerkontrakPencatatanNonTenderParser(lpse, 10941898000)
        result = parser.parse_detil(load_fixture_bytes('nonspk_pemenang_bug_10941898000.html'))
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['realisasi']['jenis_realisasi'], 'Kuitansi')
        self.assertEqual(result[0]['realisasi']['nilai_realisasi'], 375000.0)
        self.assertEqual(result[0]['penyedia'][0]['nama_penyedia'], 'Diana Safitri')
        self.assertEqual(result[1]['realisasi']['nilai_realisasi'], 120000.0)
        self.assertEqual(result[1]['penyedia'][0]['alamat'], 'Mataram (Kota) Nusa Tenggara Barat')

    def test_parse_swakelola_pengumuman(self):
        lpse = Lpse("nasional")
        parser = LpseDetilPengumumanSwakelolaParser(lpse, 10336514000)
        result = parser.parse_detil(load_fixture_bytes('swakelola_pengumuman.html'))
        self.assertEqual(result['kode_swakelola'], '10336514000')
        self.assertEqual(result['tipe_pelaksana_swakelola'], 'K/L/PD Penanggung Jawab Anggaran')
        self.assertEqual(result['nilai_pagu_paket'], 176320000.0)

    def test_parse_swakelola_pelaksana(self):
        lpse = Lpse("nasional")
        parser = LpseDetilPelaksanaSwakelolaParser(lpse, 10336514000)
        result = parser.parse_detil(load_fixture_bytes('swakelola_pelaksana.html'))
        self.assertEqual(result['nilai_total_realisasi'], 800000.0)
        self.assertEqual(result['realisasi'][0]['pelaksana'][0]['nama_pelaksana'],
                         'SEKRETARIAT KEMENTERIAN/SEKRETARIAT UTAMA KEMENTERIAN EKONOMI KREATIF/BADAN EKONOMI KREATIF')

    def test_parse_pengadaan_darurat_pengumuman(self):
        lpse = Lpse("nasional")
        parser = LpseDetilPengumumanPengadaanDaruratParser(lpse, 106802)
        result = parser.parse_detil(load_fixture_bytes('darurat_pengumuman.html'))
        self.assertEqual(result['kode_paket'], '106802')
        self.assertEqual(result['metode_pengadaan'], 'Darurat')
        self.assertEqual(result['nilai_pagu_paket'], 500000000.0)

    def test_parse_pengadaan_darurat_pemenang(self):
        lpse = Lpse("nasional")
        parser = LpseDetilPemenangBerkontrakPengadaanDaruratParser(lpse, 106802)
        result = parser.parse_detil(load_fixture_bytes('darurat_pemenang.html'))
        self.assertEqual(result, [])


class TestEnums(unittest.TestCase):

    def test_by_enum_values(self):
        self.assertEqual(By.KODE.value, 0)
        self.assertEqual(By.NAMA_PAKET.value, 1)
        self.assertEqual(By.INSTANSI.value, 2)
        self.assertEqual(By.HPS.value, 4)

    def test_jenis_pengadaan_enum_values(self):
        self.assertEqual(JenisPengadaan.PENGADAAN_BARANG.value, 0)
        self.assertEqual(JenisPengadaan.JASA_KONSULTANSI_BADAN_USAHA_NON_KONSTRUKSI.value, 1)
        self.assertEqual(JenisPengadaan.PEKERJAAN_KONSTRUKSI.value, 2)
        self.assertEqual(JenisPengadaan.JASA_LAINNYA.value, 3)
        self.assertEqual(JenisPengadaan.JASA_KONSULTANSI_PERORANGAN.value, 4)
        self.assertEqual(JenisPengadaan.JASA_KONSULTANSI_BADAN_USAHA_KONSTRUKSI.value, 5)

    def test_jenis_pengadaan_lookup_by_name(self):
        self.assertEqual(JenisPengadaan['PENGADAAN_BARANG'], JenisPengadaan.PENGADAAN_BARANG)

    def test_jenis_pengadaan_lookup_invalid(self):
        with self.assertRaises(KeyError):
            JenisPengadaan['INVALID_CATEGORY']


class TestCurrencyParser(unittest.TestCase):

    def test_parse_currency_rupiah(self):
        from pyproc.lpse import BaseLpseDetilParser
        self.assertEqual(BaseLpseDetilParser.parse_currency('Rp 1.000.000.000,00'), 1000000000.0)

    def test_parse_currency_no_prefix(self):
        from pyproc.lpse import BaseLpseDetilParser
        self.assertEqual(BaseLpseDetilParser.parse_currency('500.000,00'), 500000.0)

    def test_parse_currency_empty(self):
        from pyproc.lpse import BaseLpseDetilParser
        self.assertEqual(BaseLpseDetilParser.parse_currency(''), 0)

    def test_parse_currency_invalid(self):
        from pyproc.lpse import BaseLpseDetilParser
        self.assertEqual(BaseLpseDetilParser.parse_currency('abc'), 0)


if __name__ == '__main__':
    unittest.main()
