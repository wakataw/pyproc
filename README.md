# PyProc

![Build Status](https://github.com/wakataw/pyproc/actions/workflows/pyproc-pypi.yml/badge.svg) [![Version](https://img.shields.io/badge/version-v0.1.10-blue)](https://travis-ci.org/wakataw/pyproc) [![Python >=3.6](https://img.shields.io/badge/python->=3.6-yellow.svg)](https://www.python.org/downloads/) [![Open Source Love](https://badges.frapsoft.com/os/v1/open-source.svg?v=102)](https://github.com/ellerbrock/open-source-badge/)

PyProc (Python Procurement) merupakan wrapper untuk API SPSE Versi 4 yang ditulis dalam bahasa Python. Sistem Pengadaan Secara Elektronik (SPSE) SPSE merupakan aplikasi e-Procurement yang dikembangkan oleh LKPP untuk digunakan oleh LPSE di instansi pemerintah seluruh Indonesia.

> DISCLAIMER: 
> 
> Penulis tidak terafiliasi dengan pengembang SPSE atau pemilik aplikasi SPSE. Software ini dikembangkan dengan tujuan akademis, bentuk pengawasan oleh masyarakat, dan membantu pengusaha untuk mempermudah otomasi perolehan informasi pengadaan dari pemerintah.
> 
> Penggunaan yang tidak wajar dan mengganggu sebagian atau seluruh fungsi aplikasi SPSE pada satuan kerja menjadi tanggung jawab masing-masing pengguna.
> 
> PyProc ada karena SPSE ada, jadi gunakanlah dengan bijak dan secukupnya.

## Pemasangan

Pemasangan PyProc via `pip`:
```bash
$ pip install pyproc
```

Upgrade PyProc via `pip`:
```bash
$ pip install pyproc --upgrade
```

Instalasi versi unstable:
```bash
$ pip install git+https://github.com/wakataw/pyproc.git
```

atau, Download executeable file (.exe) untuk windows [di sini](https://github.com/wakataw/pyproc/releases) (experimental).

## Testing

Anda bisa menjalankan beberapa Test Case untuk memastikan semua fungsi berjalan dengan baik.
Clone repository ini lalu jalankan perintah berikut:

```bash
$ git clone https://github.com/wakataw/pyproc.git
$ cd pyproc
$ python setup.py test
```

## Penggunaan Command Line Interface

### Download Data LPSE
Format Command
```bash
$ pyproc [ARGUMENT] DAFTAR_LPSE
```
**Arguments**

argumen | contoh | diperlukan | default | keterangan
---|---|---|---|---
`DAFTAR_LPSE` | `pyproc http://lpse.pu.go.id` | Ya | - | Daftar alamat LPSE yang akan diunduh. <br>[Format Daftar LPSE](#format-daftar-lpse-lanjutan)
`-h --help` | `pyproc --help` | optional | - | menampilkan keterangan dan bantuan
`-k --keyword` | `pyproc --keyword "mobil dinas" ...` | optional | - | filter pencarian index paket berdasarkan kata kunci tertentu
`-t --tahun-anggaran` | `pyproc --tahun-anggaran 2021 ...` | optional | Tahun Berjalan | Filter pencarian index paket berdasarkan tahun anggaran tertentu. Fungsi ini hanya berlaku mulai dari SPSE 4.4. <br><br>Format Penulisan: <br>**ALL**: mengunduh seluruh data <br>**2021**: mengunduh data untuk tahun 2021 <br>**2015,2018,2019**: mengunduh data untuk tahun 2015, 2018, dan 2019<br>**2011-2020** mengunduh data untuk tahun 2011 s.d. 2020
`--kategori` | `pyproc --kategori PENGADAAN_BARANG ...` | optional | - | Filter pencarian berdasarkan kategori pengadaan. <br>Daftar kategori: `PENGADAAN_BARANG`, `JASA_KONSULTANSI_BADAN_USAHA_NON_KONSTRUKSI`, `PEKERJAAN_KONSTRUKSI`, `JASA_LAINNYA`, `JASA_KONSULTANSI_PERORANGAN`, `JASA_KONSULTANSI_BADAN_USAHA_KONSTRUKSI`
`--nama-penyedia` | `pyproc --nama-penyedia "PT SUKA MAJU" ...` | optional | - | Filter pencarian index paket berdasarkan nama penyedia
`-c --chunk-size` | `pyproc --chunk-size 25 ...` | optional | 25 | Jumlah daftar paket per halaman yang diunduh. Semakin besar jumlah tidak menjamin proses download semakin cepat. Gunakanlah jumlah data yang wajar sehingga tidak membebani server SPSE.
`-w --workers` | `pyproc --workers 4 ...` | optional | 8 | Jumlah koneksi yang berjalan secara bersamaan saat mengunduh detil paket dengan maksimal 10 worker.
`-x --timeout` | `pyproc --timeout 60 ...` | optional | 30 | Waktu tunggu jika koneksi lambat (dalam detik)
`-n --non-tender` | `pyproc --non-tender ...` | optional | FALSE | Tambahkan argumen ini untuk mengunduh data non-tender/pengadaan langsung
`-d --index-download-delay` | `pyproc --index-download-delay 5 ...` | optional | 1 | Waktu jeda download index paket untuk setiap halaman/batch
`-o --output` | `pyproc --ouput csv ...` | optional | csv | Jenis data keluaran/hasil dari download. Format yang didukung csv dan json. Karena keterbatasan format, tidak semua data ditampilkan pada format csv. Jika memerlukan data detil yang komprehensif, gunakan format json karena mencangkup semua data detail.
`--keep-index` | `pyproc --keep-index ...` | optinal | FALSE | pyproc akan membentuk file idx (sqlite3 database) saat proses download dan akan dihapus ketika proses selesai. Tambahkan argumen ini jika tidak ingin menghapus database tersebut.
`-r --resume` | `pyproc --resume ...` | optinal | FALSE | Tambahkan argument ini untuk melanjutkan proses yang gagal (karena internet putus atau gangguan koneksi lainnya). Namun pastikan bahwa seluruh index sudah berhasil diunduh karena argumen --resume akan melewati proses download index.
`--log` | `pyproc --log INFO ...` | optional | INFO | Argumen untuk setting informasi yang ditampilkan pyproc pada terminal. Daftar nilai yang didukung: <br>`DEBUG`: menampilkan informasi sedetil mungkin<br>`INFO`: menampilkan informasi penting saja <br>`WARNING`: hanya menampilkan informasi yang bersifat warning <br>`ERROR`: hanya menampilkan error <br>`CRITICAL`: hanya menampilkan permasalahan yang bersifat kritis saja

### Format Daftar LPSE (lanjutan)
PyProc dapat mengunduh data dari 1 atau lebih LPSE. Proses tersebut akan berjalan sesuai dengan nilai `DAFTAR_LPSE` yang diberikan user. Beberapa format yang didukung oleh PyProc adalah sebagai berikut:
- Download data dengan menyertakan nama file hasil download
  
  Untuk set nama file secara manual, gunakan format `"alamatlpse[titik_koma]namafile"`.
  
  ```bash
  $ pyproc "http://lpse.pu.go.id;namaoutput" --output json
  ```
  
  perintah ini akan mengunduh data LPSE PU dan mengekspor data ke file `namaoutput.json`

- Download data lebih dari 1 LPSE
  
  Untuk mengunduh lebih dari 1 lpse secara bersamaan, gunakan format `"alamat1[koma]alamat2[koma]alamat3"`

  ```bash
  $ pyproc https://lpse.jakarta.go.id,http://lpse.pu.go.id
  ```
  
  atau dengan menyertakan namafile dengan format `"alamat1[titikkoma]nama1[koma]alamat2[titikkoma]nama2"`

  ```bash
  $ pyproc "https://lpse.jakarta.go.id;filejakarta,http://lpse.pu.go.id;filepu"
  ```

  - Download data berdasrakan daftar lpse pada file csv
  Download paket LPSE dengan sumber alamat dari file
  ```bash
  $ pyproc daftarlpse.csv

  # konten daftarlpse.csv
  lpse.sumbarprov.go.id
  lpse.pu.go.id
  lpse.kemenkeu.go.id
  
  # konten daftarlpse.csv dengan nama hasil download
  lpse.sumbarprov.go.id;lpse-sumbar
  lpse.pu.go.id;lpse-pu.csv
  lpse.kemenkeu.go.id;lpse-kemenkeu
  ```

### Download Daftar LPSE
Untuk mengunduh daftar alamat LPSE berdasarkan situs inaproc (https://inaproc.id/lpse), jalankan perintah berikut:
```bash
$ pyproc daftarlpse
```

Perintah tersebut akan mengunduh daftar alamat lpse dan mengekspornya ke file `daftarlpse.csv`.

## Penggunaan PyProc Sebagai Package

Untuk dapat menggunakan PyProc, anda harus mengimpornya terlebih dahulu dan menginisiasi objek `Lpse`

```python
from pyproc import Lpse

# Inisiasi objek lpse kementerian pu
lpse = Lpse('http://lpse.pu.go.id')

# Print versi dan last update aplikasi SPSE
print(lpse.version)
print(lpse.last_update)
```

### Pencarian Daftar Paket Lelang

```python
from pyproc import Lpse

lpse = Lpse('http://lpse.pu.go.id')

# mendapatkan daftar paket lelang
daftar_lelang = lpse.get_paket_tender(start=0, length=2)
print(daftar_lelang)

# pencarian paket non tender (penunjukkan langsung)
daftar_pl = lpse.get_paket_non_tender(start=0, length=30)
```

Pencarian Paket dengan mengurutkan berdasarkan kolom tertentu
```python
from pyproc import Lpse
from pyproc.lpse import By

lpse = Lpse('http://lpse.padang.go.id')

# pencarian daftar lelang, urutkan berdasarkan Harga Perkiraan Sendiri
daftar_lelang = lpse.get_paket_tender(start=0, length=30, order=By.HPS)
```

Filter pencarian paket berdasarkan kategori pengadaan
```python
from pyproc import Lpse
from pyproc import JenisPengadaan
lpse = Lpse('http://lpse.padang.go.id')

# Kategori Pengadaan Barang
paket_pengadaan_barang = lpse.get_paket_tender(start=0, length=30, kategori=JenisPengadaan.PENGADAAN_BARANG)
paket_konstruksi = lpse.get_paket_tender(start=0, length=30, kategori=JenisPengadaan.PEKERJAAN_KONSTRUKSI)

# dst untuk kategori lainnya
```

### Pencarian Detil Paket Lelang

```python
from pyproc import Lpse

lpse = Lpse('http://lpse.padang.go.id')

# mendapatkan semua detil paket lelang
detil = lpse.detil_paket_tender(id_paket='48658064')
detil.get_all_detil()
print(detil)

# mendapatkan hanya pemenang lelang
pemenang = detil.get_pemenang()
print(pemenang)
```

## Uninstall 

Untuk uninstall package jalankan perintah berikut:
```bash
$ pip uninstall pyproc
```

## License
Paket ini di-release di bawah lisensi MIT.

## Donatur ☕️
Orang-orang yang berjasa menyediakan kopi sehingga pengembangan paket tetap berjalan
- Angga Rinaldi Rizal (50 cangkir ☕️)
