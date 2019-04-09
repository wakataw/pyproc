import csv
import glob
import json
import re
import os
import argparse
import time
from datetime import datetime, timedelta
from shutil import copyfile, rmtree

from pyproc import Lpse,  __version__
from math import ceil
from urllib3.exceptions import InsecureRequestWarning
from urllib3 import disable_warnings
from urllib.parse import urlparse

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

FOLDER_NAME = None


def write_error(error_message):
    global FOLDER_NAME
    with open(os.path.join(FOLDER_NAME, 'detil-error.log'), 'a') as f:
        f.write(error_message)
        f.write('\n')


def combine_data(tender=True):
    global FOLDER_NAME

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

    with open(detil_combined, 'w') as csvf:
        writer = csv.DictWriter(csvf, fieldnames=pengumuman_keys.keys() if tender else pengumuman_nontender_keys.keys())

        writer.writeheader()

        for detil_file in detil_all:
            detil = pengumuman_keys.copy() if tender else pengumuman_nontender_keys.copy()

            with open(detil_file, 'r') as f:
                data = json.loads(f.read())

            detil['id_paket'] = data['id_paket']
            detil.update((k, data['pengumuman'][k]) for k in detil.keys() & data['pengumuman'].keys())

            if data['pemenang']:
                detil.update((k, data['pemenang'][k]) for k in detil.keys() & data['pemenang'].keys())

            detil['lokasi_pekerjaan'] = ' || '.join(detil['lokasi_pekerjaan'])

            if tender:
                tahap = 'tahap_tender_saat_ini'
            else:
                tahap = 'tahap_paket_saat_ini'

            if detil[tahap]:
                detil[tahap] = detil[tahap].strip(r' [...]')

            writer.writerow(detil)


def download(host, detil, tahun_stop, fetch_size=30, pool_size=4, tender=True):
    global FOLDER_NAME

    jenis = 'tender' if tender else 'non_tender'
    lpse_pool = [Lpse(host)]*pool_size

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
    list_id_paket = []

    with open(os.path.join(FOLDER_NAME, 'index.dat'), 'w', newline='', encoding='utf8') as f:
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
                    list_id_paket.append(row[0])

            if stop:
                break

        print("")
        print("Download selesai..")

    if detil:
        print("")
        print("> Download Detil")

        detil_dir = os.path.join(FOLDER_NAME, 'detil')
        os.makedirs(detil_dir, exist_ok=True)

        total = len(list_id_paket)
        current = 0

        start_time = time.time()

        for id_paket in list_id_paket:
            lpse = lpse_pool[current % pool_size]
            current += 1
            if tender:
                detil_paket = lpse.detil_paket_tender(id_paket=id_paket)
            else:
                detil_paket = lpse.detil_paket_non_tender(id_paket=id_paket)

            try:
                detil_paket.get_pengumuman()
            except Exception as e:
                write_error('{}|pengumuman|{}'.format(id_paket, str(e)))

            try:
                detil_paket.get_pemenang()
            except Exception as e:
                write_error('{}|pemenang|{}'.format(id_paket, str(e)))

            with open(os.path.join(detil_dir, str(id_paket)), 'w', encoding='utf8') as f:
                f.write(json.dumps(detil_paket.todict()))

            est_time = timedelta(seconds=int((time.time() - start_time) / current * (total - current)))

            print("{} of {} (est {})".format(current, total, est_time), end='\r')

        print("")
        print("Download selesai..")

        print("")
        print("> Menggabungkan Data")
        combine_data(tender=tender)
        print("OK")


def main():
    print(INFO)
    disable_warnings(InsecureRequestWarning)

    parser = argparse.ArgumentParser()
    parser.add_argument("host", help="Alamat Website LPSE")
    parser.add_argument("--fetch-size", help="Jumlah row yang didownload per halaman", default=30, type=int)
    parser.add_argument("--simple", help="Download Paket LPSE tanpa detil dan pemenang", action="store_true")
    parser.add_argument("--batas-tahun", help="Batas tahun anggaran untuk didownload", default=0, type=int)
    parser.add_argument("--all", help="Download Data LPSE semua tahun anggaran", action="store_true")
    parser.add_argument("--keep", help="Tidak menghapus folder cache", action="store_true")
    parser.add_argument("--non-tender", help="Download paket non tender (penunjukkan langsung)", action="store_true")

    detil = True
    batas_tahun = datetime.now().year
    args = parser.parse_args()
    tender = False if args.non_tender else True

    if args.batas_tahun > 0:
        batas_tahun = args.batas_tahun

    if args.simple:
        detil = False

    if args.all:
        batas_tahun = None

    try:
        download(host=args.host, detil=detil, fetch_size=args.fetch_size, tahun_stop=batas_tahun, tender=tender)
    except KeyboardInterrupt:
        print("")
        print("INFO: Proses dibatalkan oleh user, bye!")
        exit(1)
    except Exception as e:
        print("")
        print("ERROR: ", e)
        exit(1)

    if args.simple:
        result = 'index.dat'
    else:
        result = 'detil.dat'

    copyfile(os.path.join(FOLDER_NAME, result), FOLDER_NAME + '.csv')

    if not args.keep:
        rmtree(FOLDER_NAME)
