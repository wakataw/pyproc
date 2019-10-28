# PyProc

[![Build Status](https://travis-ci.org/wakataw/pyproc.svg?branch=master)](https://travis-ci.org/wakataw/pyproc) [![Version](https://img.shields.io/badge/version-v0.1.5-blue)](https://travis-ci.org/wakataw/pyproc) [![Python >=3.5](https://img.shields.io/badge/python->=3.5-yellow.svg)](https://www.python.org/downloads/) [![Open Source Love](https://badges.frapsoft.com/os/v1/open-source.svg?v=102)](https://github.com/ellerbrock/open-source-badge/)

PyProc (Python Procurement) merupakan wrapper untuk API SPSE Versi 4 yang ditulis dalam bahasa Python. Sistem Pengadaan Secara Elektronik (SPSE) SPSE merupakan aplikasi e-Procurement yang dikembangkan oleh LKPP untuk digunakan oleh LPSE di instansi pemerintah seluruh Indonesia.

# Quickstart

## Pemasangan

Pemasangan PyProc via `pip`:
```bash
$ pip install pyproc
```

## Testing

Anda bisa menjalankan beberapa Test Case untuk memastikan semua fungsi berjalan dengan baik.
Clone repository ini lalu jalankan perintah berikut:

```bash
$ python setup.py test
```

## Penggunaan Command Line Interface

```bash
usage: pyproc [-h] [--host HOST] [--out OUT] [-r READ]
              [--tahun-anggaran TAHUN_ANGGARAN] [--workers WORKERS]
              [--pool-size POOL_SIZE] [--fetch-size FETCH_SIZE]
              [--timeout TIMEOUT] [--keep]
              [--index-download-delay INDEX_DOWNLOAD_DELAY] [--non-tender]
              [--force]

```
**Arguments**

argumen | diperlukan | keterangan
---|---|---
`-h, --help`| optional | menampilkan bantuan
`--host` | Optional | Alamat website aplikasi LPSE, pisahkan dengan `,` untuk multiple lpse
`--out OUT` | Optional, default nama domain | Nama file untuk hasil download LPSE
`--read`, `-r` | Optional | Membaca daftar alamat lpse dari file 
`--tahun-anggaran` | Optional, default tahun berjalan | Filter download hanya untuk tahun yang diberikan
`--pool-size POOL_SIZE` | Optional, default 4 | Jumlah koneksi dalam connection pool untuk mendownload index paket
`--fetch-size FETCH_SIZE` | optional, default 30 | Jumlah row yang didownload per halaman
`--workers WORKERS` | optional, default 8 | Workers untuk mendownload detil pengumuman dan pemenang
`--timeout TIMEOUT` | optional, default 10 (dalam detik) | Time out jika server tidak merespon dalam waktu tertentu
`--index-download-delay` | optional, default 0 (dalam detik) | Menambahkan delay untuk setiap iterasi halaman index paket
`--keep` | optional, default `false` | saat download berjalan, `pyproc` akan membentuk sebuah folder yang digunakan sebagai *working directory* dan akan dihapus jika proses download telah selesai. Gunakan argumen `--keep` apabila tidak ingin menghapus *working directory* `pyproc`.
`--non-tender` | optional, default `false` | Download paket non tender
`--force` | optional, default `false` | PyProc akan menyimpan index paket dan hanya akan melakukan indexing ulang jika terdapat perbedaan antara data terbaru dan index cache. Argumen `--force` akan selalu menggunakan index terbaru tanpa memperdulikan index cache.

**Contoh**

Download daftar paket lelang dari https://lpse.pu.go.id untuk tahun berjalan
```bash
$ pyproc --host https://lpse.pu.go.id

# atau dengan memberikan nama spesifik untuk hasil download
$ pyproc --host https://lpse.pu.go.id --out hasil_download_lpse_pu.csv
```

Download daftar paket lelang tahun 2017
```bash
$ pyproc --tahun-anggaran 2017 --host lpse.pu.go.id 
```

Download paket pengadaan non tender (penunjukkan langsung)
```bash
$ pyproc --non-tender --host lpse.jakarta.go.id
```

Download paket pengadaan tender untuk rentang waktu tertentu
```bash
$ pyproc --host lpse.padang.go.id --tahun-anggaran 2017,2019
```

Download paket pengadaan tender dari 2 lpse dengan set jumlah workers, timeout, fetch size secara manual
```bash
$ pyproc --host lpse.pu.go.id,lpse.sumbarprov.go.id --workers 30 --timeout 600 --fetch-size 1000

# jika ingin menambahkan nama file hasil secara manual
$ pyproc --host lpse.pu.go.id;hasil-pu.csv,lpse.sumbarprov.go.id;hasil-sumbar.csv --workers 30 --timeout 600 --fetch-size 1000
```

Download paket LPSE dengan sumber alamat dari file
```bash
$ pyproc -r daftarlpse.csv

# konten daftarlpse.csv
lpse.sumbarprov.go.id
lpse.pu.go.id
lpse.kemenkeu.go.id

# konten daftarlpse.csv dengan nama hasil download
lpse.sumbarprov.go.id;lpse-sumbar.csv
lpse.pu.go.id;lpse-pu.csv
lpse.kemenkeu.go.id;lpse-kemenkeu.csv
```

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
from pyproc import PENGADAAN_BARANG, PEKERJAAN_KONSTRUKSI, JASA_KONSULTANSI, JASA_KONSULTANSI_PERORANGAN, JASA_LAINNYA
lpse = Lpse('http://lpse.padang.go.id')

# Kategori Pengadaan Barang
paket_pengadaan_barang = lpse.get_paket_tender(start=0, length=30, kategori=PENGADAAN_BARANG)
paket_konstruksi = lpse.get_paket_tender(start=0, length=30, kategori=PEKERJAAN_KONSTRUKSI)

# dst untuk kategori lainnya
```

### Pencarian Detil Paket Lelang

```python
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

Pada saat installasi, `PyProc` akan membentuk folder cache. Untuk clean uninstall hapus manual folder di lokasi berikut:

OS |Lokasi
---|---
GNU/Linux | `~/.pyproc`
Windows | `C:\Users\<username>\.pyproc` (asumsi system windows berada di drive `C:`)

## License
Paket ini di-release di bawah lisensi MIT.