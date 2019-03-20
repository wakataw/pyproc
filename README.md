# PyProc

PyProc (Python Procurement) merupakan wrapper untuk API SPSE Versi 4 yang ditulis dalam bahasa Python. Sistem Pengadaan Secara Elektronik (SPSE) SPSE merupakan aplikasi e-Procurement yang dikembangkan oleh LKPP untuk digunakan oleh LPSE di instansi pemerintah seluruh Indonesia (termasuk Kementerian Keuangan).

> **PERHATIAN: PAKET MASIH DALAM PROSES PENGEMBANGAN SEHINGGA PERUBAHAN PADA API AKAN SANGAT MUNGKIN DILAKUKAN**

# Quickstart

## Pemasangan

Pemasangan PyProc via `pip`:
```bash
pip install pyproc
```

Pemasangan PyProc langsung melalui repository:
```bash
pip install git+https://gitlab.com/wakataw/pyproc.git
```

## Testing

Anda bisa menjalankan beberapa Test Case untuk memastikan semua fungsi berjalan dengan baik

```bash
python -m tests.test_lpse
```

## Penggunaan

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

## License
Paket ini di-release di bawah lisensi MIT.