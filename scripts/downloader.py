import csv
import json
from pyproc import Lpse
from math import ceil
import os

from urllib3.exceptions import InsecureRequestWarning
from urllib3 import disable_warnings
from urllib.parse import urlparse

INFO = '''
    ____        ____                 
   / __ \__  __/ __ \_________  _____
  / /_/ / / / / /_/ / ___/ __ \/ ___/
 / ____/ /_/ / ____/ /  / /_/ / /__  
/_/    \__, /_/   /_/   \____/\___/  
      /____/ v0.1.0                        
SPSE V.4 Downloader

'''

folder_name = None


def download(host, detil=False, fetch_size=30):
    global folder_name
    lpse = Lpse(host)
    folder_name = urlparse(host).netloc.lower().replace('.', '_')
    os.makedirs(folder_name, exist_ok=True)
    total_data = lpse.get_paket_tender()['recordsTotal']
    batch_size = int(ceil(total_data / fetch_size))
    list_id_paket = []

    with open(os.path.join(folder_name, 'index.csv'), 'w', newline='') as f:
        print("> Download Daftar Paket")
        csv_writer = csv.writer(f, delimiter='|', quoting=csv.QUOTE_ALL)
        for page in range(batch_size):
            print("Batch {} of {}".format(page+1, batch_size), end='\r')
            data = lpse.get_paket_tender(start=page*fetch_size, length=fetch_size, data_only=True)
            csv_writer.writerows(data)

            if detil:
                list_id_paket += [i[0] for i in data]
        print("")
        print("Download selesai..")

    if detil:
        print("")
        print("> Download Detil")

        detil_dir = os.path.join(folder_name, 'detil')
        os.makedirs(detil_dir, exist_ok=True)

        total = len(list_id_paket)
        current = 0

        for id_paket in list_id_paket:
            current += 1
            detil_paket = lpse.detil_paket_tender(id_paket=id_paket)

            try:
                with open(os.path.join(detil_dir, 'pengumuman-{}'.format(id_paket)), 'w') as f:
                    f.write(json.dumps(detil_paket.get_pengumuman()))
            except Exception as e:
                write_error('{}|pengumuman|{}'.format(id_paket, str(e)))

            try:
                with open(os.path.join(detil_dir, 'pemenang-{}'.format(id_paket)), 'w') as f:
                    f.write(json.dumps(detil_paket.get_pemenang()))
            except Exception as e:
                write_error('{}|pemenang|{}'.format(id_paket, str(e)))

            print("{} of {}".format(current, total), end='\r')

        print("")
        print("Download selesai..")


def write_error(error_message):
    global folder_name
    with open(os.path.join(folder_name, 'detil-error.log'), 'a') as f:
        f.write(error_message)
        f.write('\n')


def main():
    print(INFO)
    disable_warnings(InsecureRequestWarning)
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("host")
    parser.add_argument("--detil", help="Download Detil Paket Pengadaan (Pengumuman, Pemenang)",
                        action="store_true")
    parser.add_argument("--fetch-size", help="Jumlah row yang didownload per halaman", default=30, type=int)

    args = parser.parse_args()

    download(args.host, args.detil, args.fetch_size)
