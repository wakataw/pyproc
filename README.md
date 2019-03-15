# PyProc

Python Wrapper untuk aplikasi SPSE Versi 4.

DANGER: **Perhatian:**
Paket masih dalam proses pengembangan sehingga perubahan pada API akan sangat mungkin terjadi.

## Instalasi

`pip install pyproc`

## Penggunaan

```python
from pyproc.lpse import Lpse

lpse = Lpse("https://lpse.pu.go.id")

print(lpse.version) 

# hasil
# SPSE v4.XuXXXXXXX

# mendapatkan detil paket lelang
daftar_lelang = lpse.get_paket_tender(start=0, length=2)
print(daftar_lelang)

# hasil
# {'draw': '1', 'recordsTotal': 31475, 'recordsFiltered': 31475, 'data': [['48658064', "Konsultan Manajemen Provinsi <span class='label label-warning'>Seleksi Ulang</span>", 'Kementerian Pekerjaan Umum dan Perumahan Rakyat', 'Masa Sanggah Hasil Tender', '1,7 M', 'Prakualifikasi Dua File', 'Seleksi', 'Kualitas dan Biaya', 'Jasa Konsultansi Badan Usaha - TA 2019', '3', 'Nilai Kontrak belum dibuat', '1', None, '0'], ['50800064', 'Paket 03 : Perencanaan Teknik Jalan dan Jembatan Semarang dan Kota Besar', 'Kementerian Pekerjaan Umum dan Perumahan Rakyat', 'Pengumuman Prakualifikasi [...]', '1,7 M', 'Prakualifikasi Dua File', 'Seleksi', 'Kualitas dan Biaya', 'Jasa Konsultansi Badan Usaha - TA 2019', '3', 'Nilai Kontrak belum dibuat', None, None, '0']]}

# mendapatkan detil peserta
detil = lpse.detil_paket_tender('48658064')
detil.get_all_detil()

print(detil.pengumuman)

## hasil
## {'kode_tender': '48658064', 'nama_tender': 'Konsultan Manajemen Provinsi Tender Ulang', 'rencana_umum_pengadaan': {'kode_rup': '1238867798', 'nama_paket': 'Konsultan Manajemen Provinsi', 'sumber_dana': 'APBN'}, 'tanggal_pembuatan': '07 Januari 2019', 'keterangan': '', 'tahap_tender_saat_ini': 'Masa Sanggah Hasil Tender', 'instansi': 'Kementerian Pekerjaan Umum dan Perumahan Rakyat', 'satuan_kerja': 'SNVT PENYEDIAAN PERUMAHAN PROVINSI JAMBI', 'kategori': 'Jasa Konsultansi Badan Usaha', 'sistem_pengadaan': 'Seleksi - Prakualifikasi Dua File - Kualitas dan Biaya', 'tahun_anggaran': 'APBN 2019', 'nilai_pagu_paket': 1710000000.0, 'nilai_hps_paket': 1709510000.0, 'jenis_kontrak': 'Harga Satuan', 'lokasi_pekerjaan': ['Wilayah Provinsi Jambi - Jambi (Kota)'], 'peserta_tender': 57}

```

## License
Paket ini di-release di bawah lisensi MIT.