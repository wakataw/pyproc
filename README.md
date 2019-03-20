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
lpse_pu = Lpse('http://lpse.pu.go.id')

# Print versi dan last update aplikasi SPSE
print(lpse_pu.version)
print(lpse_pu.last_update)
```

### Pencarian Daftar Paket Lelang

```python
# mendapatkan daftar paket lelang
daftar_lelang = lpse.get_paket_tender(start=0, length=2)
print(daftar_lelang)
```

Pencarian Paket dengan mengurutkan berdasarkan kolom tertentu
```python

from pyproc import Lpse
from pyproc.lpse import By

lpse = Lpse('http://lpse.padang.go.id')

# pencarian daftar lelang, urutkan berdasarkan Harga Perkiraan Sendiri
daftar_lelang = lpse.get_paket_tender(start=0, length=30, order=By.HPS)
```

### Pencarian Detil Paket Lelang

```python
# mendapatkan semua detil paket lelang
detil = lpse.detil_paket_tender('48658064')
detil.get_all_detil()
print(detil)

# mendapatkan hanya pemenang lelang
pemenang = detil.get_pemenang()
print(pemenang)
```

## License
Paket ini di-release di bawah lisensi MIT.