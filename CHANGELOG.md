# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## 0.1.7

### Fix
- [downloader] fix error saat menggabungkan file detil jika pemenang tidak ditemukan
- [downloader] ketika retry download , detil downloader akan menggunakan cache dari proses sebelumnya
- [downloader] pemilihan pemenang berdasarkan hirarki pemenang berkontrak > pemenang terverifikasi > pemenang
- [downloader] fix filter tahun anggaran, jika tidak ada data tahun anggaran maka filter akan berdasarkan data tanggal pembuatan
- [package] Fix NPWP - Nama Peserta splitter pada hasil evaluasi
- [package] menghilangkan fungsi pengecekan url rewrite dengan hardcoded path `/eproc4` pada host SPSE
- [package] bypass parsing auth token jika versi SPSE < 20191009

### Add
- [downloader] jika proses download index gagal di tengah jalan, aplikasi akan melanjutkan berdasarkan posisi batch terakhir
- [downloader] menambahkan jenis paket pengadaan pada header informasi
- [downloader] menambahkan argument `--skip-spse-check`
- [package] menambahkan parameter `skip_spse_checking` untuk menghindari proses parsing info LPSE yang gagal jika aplikasi menggunakan custom homepage

## Change
- update test case

## 0.1.6

### Change
- Mengganti tipe data menjadi boolean untuk kolom pemenang dan pemenang berkontrak pada hasil evaluasi
- Set default index download delay menjadi 1 detik
- Set pemenang tender dari hasil evaluasi
- Mengganti separator tahun anggaran (range) dari '-' (koma) menjadi '-' (dash)
- update test case
- minor update

## 0.1.5

### Add
- menambahkan parameter `--index-download-delay` pada downloader CLI karena beberapa situs LPSE membatasi jumlah request

### Fix
- fix `LpseDetil.get_pemenang` error karena menggunakan kolom hasil negosiasi sebagai parameter pengurutan

## 0.1.4

### Fix
- Fix lpse pool error pada downloader karena belum implementasi authenticity token

## 0.1.3

### Fix
- Fix download index paket error karena penambahan parameter pada API SPSE

### Add
- Menambahkan method `Lpse.get_auth_token` untuk mendapatkan `auth_token` yang digunakan pada saat mendapatkan data index paket

## 0.1.2

### Fix
- Fix downloader error karena perubahan api pada 0.1.1

## 0.1.1

### Fix
- Fix pemenang double pada package dan downloader dengan memilih nilai penawaran paling rendah

## 0.1
Release versi stable pertama

### Fitur

- Dukungan Penuh untuk API SPSE Versi 4
    - Mendapatkan Daftar Paket Tender dan Non Tender
    - Mendapatkan Detil Paket (Pengumuman, Peserta, Hasil Evaluasi, Pemenang, Pemenang Berkontrak, Jadwal Penetapan Pemenang, Jadwal Penandatangan Kontrak)
    - Filter pencarian paket tender/non tender berdasarkan kategori pengadaan.
    - Mengurutkan Pencarian paket berdasarkan id paket, nama instansi, tahap paket, dan HPS
- CLI Downloader
