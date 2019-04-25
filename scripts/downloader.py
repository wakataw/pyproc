import argparse
import csv
import glob
import json
import os
import re
from math import ceil
from shutil import copyfile, rmtree
from urllib.parse import urlparse

import requests

from pyproc import Lpse
from pyproc.helpers import DetilDownloader
from urllib3 import disable_warnings
from urllib3.exceptions import InsecureRequestWarning
from datetime import datetime


def print_info():
    print(r'''    ____        ____                 
   / __ \__  __/ __ \_________  _____
  / /_/ / / / / /_/ / ___/ __ \/ ___/
 / ____/ /_/ / ____/ /  / /_/ / /__  
/_/    \__, /_/   /_/   \____/\___/  
      /____/                        
SPSE4 Downloader
''')


def download_index(_lpse, pool_size, fetch_size, timeout, non_tender, index_path, index_path_exists, force):
    _lpse.timeout = timeout
    lpse_pool = [_lpse]*pool_size

    for i in lpse_pool:
        i.session = requests.session()
        i.session.verify = False

    print("url SPSE       :", lpse_pool[0].host)
    print("versi SPSE     :", lpse_pool[0].version)
    print("last update    :", lpse_pool[0].last_update)
    print("\nIndexing Data")

    if index_path_exists and not force:
        yield "- Menggunakan cache"
    else:
        if non_tender:
            total_data = lpse_pool[0].get_paket_non_tender()['recordsTotal']
        else:
            total_data = lpse_pool[0].get_paket_tender()['recordsTotal']

        batch_size = int(ceil(total_data / fetch_size))
        downloaded_row = 0

        with open(index_path, 'w', newline='', encoding='utf8',
                  errors="ignore") as index_file:

            writer = csv.writer(index_file, delimiter='|', quoting=csv.QUOTE_ALL)

            for page in range(batch_size):

                lpse = lpse_pool[page % pool_size]

                if non_tender:
                    data = lpse.get_paket_non_tender(start=page*fetch_size, length=fetch_size, data_only=True)
                    min_data = list(map(lambda x: [x[0], x[6]], data))
                else:
                    data = lpse.get_paket_tender(start=page*fetch_size, length=fetch_size, data_only=True)
                    min_data = list(map(lambda x: [x[0], x[8]], data))

                writer.writerows(min_data)

                downloaded_row += len(min_data)

                yield [page+1, batch_size, downloaded_row]

    del lpse_pool


def get_detil(downloader, jenis_paket, tahun_anggaran, index_path):
    detail_dir = os.path.join(get_folder_name(downloader.lpse.host, jenis_paket), 'detil')

    os.makedirs(detail_dir, exist_ok=True)

    downloader.download_dir = detail_dir
    downloader.error_log = detail_dir+".err"
    downloader.is_tender = True if jenis_paket == 'tender' else False

    with open(index_path, 'r', encoding='utf8', errors="ignore") as f:
        reader = csv.reader(f, delimiter='|')

        for row in reader:
            tahun_anggaran_data = re.findall(r'(20\d{2})', row[1])

            if not download_by_ta(tahun_anggaran_data, tahun_anggaran):
                continue

            downloader.queue.put(row[0])

    downloader.queue.join()


def combine_data(host, jenis_paket, remove=True):
    folder_name = get_folder_name(host, jenis_paket=jenis_paket)
    detil_dir = os.path.join(folder_name, 'detil', '*')
    detil_combined = os.path.join(folder_name, 'detil.dat')
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
        fieldnames = list(pengumuman_keys.keys() if jenis_paket == 'tender' else pengumuman_nontender_keys.keys())
        fieldnames += ['penetapan_pemenang_mulai', 'penetapan_pemenang_sampai', 'penandatanganan_kontrak_mulai',
                       'penandatanganan_kontrak_sampai']

        writer = csv.DictWriter(
            csvf,
            fieldnames=fieldnames
        )

        writer.writeheader()

        for detil_file in detil_all:
            detil = pengumuman_keys.copy() if jenis_paket == 'tender' else pengumuman_nontender_keys.copy()

            detil.update(
                {
                    'penetapan_pemenang_mulai': None,
                    'penetapan_pemenang_sampai': None,
                }
            )

            with open(detil_file, 'r', encoding='utf8', errors="ignore") as f:
                data = json.loads(f.read())

            detil['id_paket'] = data['id_paket']

            if data['pengumuman']:
                detil.update((k, data['pengumuman'][k]) for k in detil.keys() & data['pengumuman'].keys())

                detil['lokasi_pekerjaan'] = ' || '.join(detil['lokasi_pekerjaan'])

                if jenis_paket == 'tender':
                    tahap = 'tahap_tender_saat_ini'
                else:
                    tahap = 'tahap_paket_saat_ini'

                if detil[tahap]:
                    detil[tahap] = detil[tahap].strip(r' [...]')

            if data['pemenang']:
                detil.update((k, data['pemenang'][k]) for k in detil.keys() & data['pemenang'].keys())

            if data['jadwal']:
                data_pemenang = list(filter(lambda x: x['tahap'] == 'Penetapan Pemenang', data['jadwal']))
                data_kontrak = list(filter(lambda x: x['tahap'] == 'Penandatanganan Kontrak', data['jadwal']))

                if data_pemenang:
                    detil['penetapan_pemenang_mulai'] = data_pemenang[0]['mulai']
                    detil['penetapan_pemenang_sampai'] = data_pemenang[0]['sampai']

                if data_kontrak:
                    detil['penandatanganan_kontrak_mulai'] = data_kontrak[0]['mulai']
                    detil['penandatanganan_kontrak_sampai'] = data_kontrak[0]['sampai']

            writer.writerow(detil)

            del detil

    copy_result(folder_name, remove=remove)


def error_writer(error):
    with open('error.log', 'a', encoding='utf8', errors="ignore") as error_file:
        error_file.write(error+'\n')


def get_folder_name(host, jenis_paket):
    _url = urlparse(host)
    netloc = _url.netloc if _url.netloc != '' else _url.path

    return netloc.lower().replace('.', '_') + '_' + jenis_paket


def get_index_path(cache_folder, host, jenis_paket, last_paket_id):
    index_dir = os.path.join(cache_folder, get_folder_name(host, jenis_paket))

    os.makedirs(index_dir, exist_ok=True)

    index_path = os.path.join(index_dir, 'index-{}-{}-{}'.format(*last_paket_id))

    return os.path.isfile(index_path), index_path


def parse_tahun_anggaran(tahun_anggaran):
    parsed_ta = tahun_anggaran.strip().split(',')
    error = False

    for i in range(len(parsed_ta)):
        try:
            parsed_ta[i] = int(parsed_ta[i])
        except ValueError:
            parsed_ta[i] = 0

    if len(parsed_ta) > 2:
        error = True
    elif parsed_ta[-1] == 0:
        parsed_ta[-1] = 9999

    return error, parsed_ta


def download_by_ta(ta_data, ta_argumen):

    if not ta_data:
        return True

    ta_data = [int(i) for i in ta_data]

    for i in ta_data:
        if ta_argumen[0] <= i <= ta_argumen[-1]:
            return True

    return False


def copy_result(folder_name, remove=True):
    copyfile(os.path.join(folder_name, 'detil.dat'), folder_name + '.csv')

    if os.path.isfile(os.path.join(folder_name, 'detil.err')):
        copyfile(os.path.join(folder_name, 'detil.err'), folder_name + '_error.log')

    if remove:
        rmtree(folder_name)


def get_last_paket_id(lpse: Lpse, tender=True):
    # first
    if tender:
        data_first = lpse.get_paket_tender(start=0, length=1)
        data_last = lpse.get_paket_tender(start=0, length=1, ascending=True)
    else:
        data_first = lpse.get_paket_non_tender(start=0, length=1)
        data_last = lpse.get_paket_non_tender(start=0, length=1, ascending=True)

    if data_first and data_last:
        return [data_first['data'][0][0], data_last['data'][0][0], data_first['recordsTotal']]

    return None


def create_cache_folder():
    from pathlib import Path

    home = str(Path.home())
    cache_folder = os.path.join(home, '.pyproc')

    os.makedirs(cache_folder, exist_ok=True)

    return cache_folder


def lock_index(index_path):
    return index_path+".lock"


def unlock_index(index_path):
    unlocked_path = index_path.split(".lock")[0]
    os.rename(index_path, unlocked_path)

    return unlocked_path


def main():
    print_info()
    cache_folder = create_cache_folder()
    disable_warnings(InsecureRequestWarning)

    parser = argparse.ArgumentParser()
    parser.add_argument("--host", help="Alamat Website LPSE", default=None, type=str)
    parser.add_argument("-r", "--read", help="Membaca host dari file", default=None, type=str)
    parser.add_argument("--tahun-anggaran", help="Tahun Anggaran untuk di download", default=str(datetime.now().year),
                        type=str)
    parser.add_argument("--workers", help="Jumlah worker untuk download detil paket", default=8, type=int)
    parser.add_argument("--pool-size", help="Jumlah koneksi pada pool untuk download index paket", default=4, type=int)
    parser.add_argument("--fetch-size", help="Jumlah row yang didownload per halaman", default=100, type=int)
    parser.add_argument("--timeout", help="Set timeout", default=30, type=int)
    parser.add_argument("--keep", help="Tidak menghapus folder cache", action="store_true")
    parser.add_argument("--non-tender", help="Download paket non tender (penunjukkan langsung)", action="store_true")
    parser.add_argument("--force", "-f", help="Clear index sebelum mendownload data", action="store_true")

    args = parser.parse_args()

    error, tahun_anggaran = parse_tahun_anggaran(args.tahun_anggaran)
    jenis_paket = 'non_tender' if args.non_tender else 'tender'

    if error:
        print("ERROR: format tahun anggaran tidak dikenal ", args.tahun_anggaran)
        exit(1)

    if args.host:
        host_list = args.host.strip().split(',')
    elif args.read:
        with open(args.read, 'r', encoding='utf8', errors="ignore") as host_file:
            host_list = host_file.read().strip().split()
    else:
        parser.print_help()
        print("\nERROR: Argumen --host atau --read tidak ditemukan!")
        exit(1)

    # download index
    detil_downloader = DetilDownloader(workers=args.workers, timeout=args.timeout)
    detil_downloader.spawn_worker()

    try:
        for host in host_list:
            try:
                print("=" * len(host))
                print(host)
                print("=" * len(host))
                print("tahun anggaran :", ' - '.join(map(str, tahun_anggaran)))
                _lpse = Lpse(host=host, timeout=args.timeout)
                last_paket_id = get_last_paket_id(_lpse, not args.non_tender)

                if last_paket_id is None:
                    print("- Data kosong")
                    continue

                index_path_exists, index_path = get_index_path(cache_folder, _lpse.host, jenis_paket, last_paket_id)

                if args.force:
                    rmtree(os.path.dirname(index_path))
                    os.mkdir(os.path.dirname(index_path))
                    index_path_exists = False

                if not index_path_exists:
                    index_path = lock_index(index_path)

                for downloadinfo in download_index(_lpse, args.pool_size, args.fetch_size, args.timeout,
                                                   args.non_tender, index_path, index_path_exists, args.force):
                    if index_path_exists and not args.force:
                        print(downloadinfo, end='\r')
                        continue

                    print("- halaman {} of {} ({} row)".format(*downloadinfo), end='\r')

                print("\n- download selesai\n")

                index_path = unlock_index(index_path)

            except Exception as e:
                print("ERROR:", str(e))
                error_writer('{}|{}'.format(host, str(e)))
                continue

            print("Downloading")

            detil_downloader.reset()
            detil_downloader.set_host(lpse=_lpse)

            get_detil(downloader=detil_downloader, jenis_paket=jenis_paket, tahun_anggaran=tahun_anggaran,
                      index_path=index_path)
            print("\n- download selesai\n")

            print("Menggabungkan Data")
            combine_data(_lpse.host, jenis_paket, not args.keep)
            print("- proses selesai")

    except KeyboardInterrupt:
        print("\n\nERROR: Proses dibatalkan oleh user, bye!")
        detil_downloader.stop_process()
    except Exception as e:
        print("\n\nERROR:", e)
        error_writer("{}|{}".format(detil_downloader.lpse.host, str(e)))
        detil_downloader.stop_process()
    finally:
        for i in range(detil_downloader.workers):
            detil_downloader.queue.put(None)

        for t in detil_downloader.threads_pool:
            t.join()


if __name__ == '__main__':
    main()
