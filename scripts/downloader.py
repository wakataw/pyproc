import csv
import glob
import json
import re
import os
import argparse
from datetime import datetime
from shutil import copyfile, rmtree
from pyproc import Lpse,  __version__
from math import ceil
from urllib3.exceptions import InsecureRequestWarning
from urllib3 import disable_warnings
from urllib.parse import urlparse

from pyproc.helpers import DetilDownloader

VERSION = __version__
INFO = '''
    ____        ____                 
   / __ \__  __/ __ \_________  _____
  / /_/ / / / / /_/ / ___/ __ \/ ___/
 / ____/ /_/ / ____/ /  / /_/ / /__  
/_/    \__, /_/   /_/   \____/\___/  
      /____/ v{}                        
SPSE V.4 Downloader
'''.format(VERSION)


def write_error(error_message, filename='error.log'):
    with open(os.path.join(filename), 'a', encoding='utf8') as f:
        f.write(error_message)
        f.write('\n')


def combine_data(FOLDER_NAME, tender=True):
    detil_dir = os.path.join(FOLDER_NAME, 'detil', '*')
    detil_combined = os.path.join(FOLDER_NAME, 'detil.dat')
    detil_all = glob.glob(detil_dir)

    pengumuman_nontender_keys = {
        'id_paket': None,
        'kode_paket': None,
        'nama_paket': None,
        'tanggal_pembuatan': None,
        'keterangan': None,
        'tahap_paket_saat_ini': None,
        'instansi': None,
        'satuan_kerja': None,
        'kategori': None,
        'metode_pengadaan': None,
        'tahun_anggaran': None,
        'nilai_pagu_paket': None,
        'nilai_hps_paket': None,
        'lokasi_pekerjaan': None,
        'npwp': None,
        'nama_pemenang': None,
        'alamat': None,
        'hasil_negosiasi': None,
    }

    pengumuman_keys = {
        'id_paket': None,
        'kode_tender': None,
        'nama_tender': None,
        'tanggal_pembuatan': None,
        'keterangan': None,
        'tahap_tender_saat_ini': None,
        'instansi': None,
        'satuan_kerja': None,
        'kategori': None,
        'sistem_pengadaan': None,
        'tahun_anggaran': None,
        'nilai_pagu_paket': None,
        'nilai_hps_paket': None,
        'lokasi_pekerjaan': None,
        'npwp': None,
        'nama_pemenang': None,
        'alamat': None,
        'harga_penawaran': None,
        'harga_terkoreksi': None,
        'hasil_negosiasi': None,
    }

    with open(detil_combined, 'w', encoding='utf8', errors="ignore") as csvf:
        writer = csv.DictWriter(csvf, fieldnames=pengumuman_keys.keys() if tender else pengumuman_nontender_keys.keys())

        writer.writeheader()

        for detil_file in detil_all:
            detil = pengumuman_keys.copy() if tender else pengumuman_nontender_keys.copy()

            with open(detil_file, 'r', encoding='utf8', errors="ignore") as f:
                data = json.loads(f.read())

            detil['id_paket'] = data['id_paket']

            if data['pengumuman']:
                detil.update((k, data['pengumuman'][k]) for k in detil.keys() & data['pengumuman'].keys())

                detil['lokasi_pekerjaan'] = ' || '.join(detil['lokasi_pekerjaan'])

                if tender:
                    tahap = 'tahap_tender_saat_ini'
                else:
                    tahap = 'tahap_paket_saat_ini'

                if detil[tahap]:
                    detil[tahap] = detil[tahap].strip(r' [...]')

            if data['pemenang']:
                detil.update((k, data['pemenang'][k]) for k in detil.keys() & data['pemenang'].keys())

            writer.writerow(detil)

            del detil


def get_detil(host, file_name, tender, detil_dir, total, workers=8, timeout=None):
    downloader = DetilDownloader(host, workers=workers, timeout=timeout)
    downloader.spawn_worker()
    downloader.download_dir = detil_dir
    downloader.error_log = detil_dir+".err"
    downloader.is_tender = tender
    downloader.total = total
    downloader.workers = workers

    os.makedirs(detil_dir, exist_ok=True)

    with open(file_name, 'r', encoding='utf8', errors="ignore") as f:
        reader = csv.reader(f, delimiter='|')

        for row in reader:
            downloader.queue.put(row[0])

    downloader.queue.join()

    del downloader


def copy_result(FOLDER_NAME, result):
    copyfile(os.path.join(FOLDER_NAME, result), FOLDER_NAME + '.csv')

    if os.path.isfile(os.path.join(FOLDER_NAME, 'detil.err')):
        copyfile(os.path.join(FOLDER_NAME, 'detil.err'), FOLDER_NAME + '_error.log')
    rmtree(FOLDER_NAME)


def download(host, detil, tahun_stop, fetch_size=30, pool_size=2, tender=True, workers=8, timeout=None):
    global total_detil

    print("")
    print("Processing "+host)

    jenis = 'tender' if tender else 'non_tender'
    lpse_pool = [Lpse(host)]*pool_size

    for l in lpse_pool:
        l.timeout = timeout
    print("="*len(lpse_pool[0].host))
    print(lpse_pool[0].host)
    print("="*len(lpse_pool[0].host))
    print("Versi SPSE  : ", lpse_pool[0].version)
    print("Last Update : ", lpse_pool[0].last_update or None)
    print("")

    FOLDER_NAME = urlparse(lpse_pool[0].host).netloc.lower().replace('.', '_') + '_' + jenis
    os.makedirs(FOLDER_NAME, exist_ok=True)

    if tender:
        total_data = lpse_pool[0].get_paket_tender()['recordsTotal']
    else:
        total_data = lpse_pool[0].get_paket_non_tender()['recordsTotal']

    batch_size = int(ceil(total_data / fetch_size))
    total_detil = 0

    with open(os.path.join(FOLDER_NAME, 'index.dat'), 'w', newline='', encoding='utf8', errors="ignore") as f:
        print("> Download Daftar Paket")
        csv_writer = csv.writer(f, delimiter='|', quoting=csv.QUOTE_ALL)
        stop = False

        for page in range(batch_size):
            lpse = lpse_pool[page % pool_size]

            print("Batch {} of {}".format(page+1, batch_size), end='\r')

            if tender:
                data = lpse.get_paket_tender(start=page*fetch_size, length=fetch_size, data_only=True)
            else:
                data = lpse.get_paket_non_tender(start=page*fetch_size, length=fetch_size, data_only=True)

            for row in data:

                ta = re.findall(r'(20\d{2})', row[8] if tender else row[6])

                if ta and tahun_stop is not None:
                    ta.sort(reverse=True)

                    if int(ta[0]) < tahun_stop:
                        stop = True

                if stop:
                    break

                csv_writer.writerow(row)

                if detil:
                    total_detil += 1

            if stop:
                break

        print("")
        print("Download selesai..")

    result_name = 'index.dat'

    if detil:
        print("")
        print("> Download Detil")

        get_detil(
            lpse_pool[0].host, os.path.join(FOLDER_NAME, 'index.dat'), tender,
            os.path.join(FOLDER_NAME, 'detil'), total_detil, workers=workers, timeout=timeout
        )

        print("")
        print("Download selesai..")

        print("")
        print("> Menggabungkan Data")
        combine_data(FOLDER_NAME, tender=tender)
        print("OK")

        result_name = 'detil.dat'

    copy_result(FOLDER_NAME, result_name)


def main():
    disable_warnings(InsecureRequestWarning)

    parser = argparse.ArgumentParser()
    parser.add_argument("--host", help="Alamat Website LPSE", default=None, type=str)
    parser.add_argument("-r", "--read", help="Membaca host dari file", default=None, type=str)
    parser.add_argument("--simple", help="Download Paket LPSE tanpa detil dan pemenang", action="store_true")
    parser.add_argument("--batas-tahun", help="Batas tahun anggaran untuk didownload", default=0, type=int)
    parser.add_argument("--workers", help="Jumlah worker untuk download detil paket", default=8, type=int)
    parser.add_argument("--pool-size", help="Jumlah koneksi pada pool untuk download index paket", default=4, type=int)
    parser.add_argument("--fetch-size", help="Jumlah row yang didownload per halaman", default=30, type=int)
    parser.add_argument("--timeout", help="Set timeout", default=10, type=int)
    parser.add_argument("--all", help="Download Data LPSE semua tahun anggaran", action="store_true")
    parser.add_argument("--keep", help="Tidak menghapus folder cache", action="store_true")
    parser.add_argument("--non-tender", help="Download paket non tender (penunjukkan langsung)", action="store_true")
    parser.add_argument("--no-logo", help="Tidak menampilkan logo PyProc", action="store_true")

    args = parser.parse_args()

    if not args.no_logo:
        print(INFO)

    download_detil = True
    batas_tahun = datetime.now().year
    tender = False if args.non_tender else True

    if args.batas_tahun > 0:
        batas_tahun = args.batas_tahun

    if args.simple:
        download_detil = False

    if args.all:
        batas_tahun = None

    if args.host is not None:
        list_host = args.host.strip().split(',')
    elif args.read is not None:
        with open(args.read, 'r', encoding="utf8", errors="ignore") as host_file:
            list_host = host_file.read().strip().split()
    else:
        print(parser.print_help())
        print("ERROR: argument host or read not found")
        exit(1)

    for host_name in list_host:
        try:
            download(host=host_name, detil=download_detil, fetch_size=args.fetch_size, tahun_stop=batas_tahun,
                     tender=tender, pool_size=args.pool_size, workers=args.workers, timeout=args.timeout)
        except KeyboardInterrupt:
            print("")
            print("INFO: Proses dibatalkan oleh user, bye!")
            exit(1)
        except Exception as e:
            print("")
            print("ERROR: ", e)

            error = "{} {}".format(host_name, e)

            write_error(error)


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(e)

