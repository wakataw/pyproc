import csv
import json
import re
import os
import argparse
from datetime import datetime
from pyproc import Lpse
from math import ceil
from urllib3.exceptions import InsecureRequestWarning
from urllib3 import disable_warnings
from urllib.parse import urlparse

VERSION = '0.1.0b'
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


def combine_data():
    # TODO: Gabungkan detil hasi download
    global FOLDER_NAME


def download(host, detil, tahun_stop, fetch_size=30):
    global FOLDER_NAME

    lpse = Lpse(host)

    # buat folder download
    FOLDER_NAME = urlparse(lpse.host).netloc.lower().replace('.', '_')
    os.makedirs(FOLDER_NAME, exist_ok=True)

    total_data = lpse.get_paket_tender()['recordsTotal']
    batch_size = int(ceil(total_data / fetch_size))
    list_id_paket = []

    with open(os.path.join(FOLDER_NAME, 'index.csv'), 'w', newline='') as f:
        print("> Download Daftar Paket")
        csv_writer = csv.writer(f, delimiter='|', quoting=csv.QUOTE_ALL)
        stop = False

        for page in range(batch_size):

            print("Batch {} of {}".format(page+1, batch_size), end='\r')
            data = lpse.get_paket_tender(start=page*fetch_size, length=fetch_size, data_only=True)

            for row in data:

                ta = re.findall(r'TA (\d+)', row[8])

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

        for id_paket in list_id_paket:
            current += 1
            detil_paket = lpse.detil_paket_tender(id_paket=id_paket)

            try:
                detil_paket.get_pengumuman()
            except Exception as e:
                write_error('{}|pengumuman|{}'.format(id_paket, str(e)))

            try:
                detil_paket.get_pemenang()
            except Exception as e:
                write_error('{}|pemenang|{}'.format(id_paket, str(e)))

            with open(os.path.join(detil_dir, str(id_paket)), 'w') as f:
                f.write(json.dumps(detil_paket.todict()))

            print("{} of {}".format(current, total), end='\r')

        print("")
        print("Download selesai..")


def main():
    print(INFO)
    disable_warnings(InsecureRequestWarning)

    parser = argparse.ArgumentParser()
    parser.add_argument("host")
    parser.add_argument("--fetch-size", help="Jumlah row yang didownload per halaman", default=30, type=int)
    parser.add_argument("--simple", help="Download Paket LPSE tanpa detil dan pemenang", action="store_true")
    parser.add_argument("--batas-tahun", help="Batas tahun anggaran untuk didownload", default=0, type=int)
    parser.add_argument("--all", help="Download Data LPSE semua tahun anggaran", action="store_true")

    detil = True
    batas_tahun = datetime.now().year

    args = parser.parse_args()

    if args.batas_tahun > 0:
        batas_tahun = args.batas_tahun

    if args.simple:
        detil = False

    if args.all:
        batas_tahun = None

    try:
        download(host=args.host, detil=detil, fetch_size=args.fetch_size, tahun_stop=batas_tahun)
    except Exception as e:
        print(e)
        exit(1)
