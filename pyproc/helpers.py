import json
import os
import threading
from abc import abstractmethod
from queue import Queue, Empty

import requests


class BaseDownloader(object):

    def __init__(self, is_tender=True, workers=4, timeout=None):
        self.queue = Queue()
        self.lock = threading.Lock()
        self.downloaded = 0
        self.workers = workers
        self.is_tender = is_tender
        self.error_log = 'error.log'
        self.download_dir = ''
        self.max_retry = 3
        self.threads_pool = []
        self.timeout = timeout
        self.lpse = None
        self.stop = False

    def set_host(self, lpse):
        self.lpse = lpse

    def reset(self):
        self.downloaded = 0
        self.lpse = None
        self.stop = False

    @abstractmethod
    def download(self, *args, **kwargs):
        raise NotImplementedError

    @abstractmethod
    def worker(self):
        raise NotImplementedError

    def spawn_worker(self):
        for i in range(self.workers):
            t = threading.Thread(target=self.worker)
            t.start()
            self.threads_pool.append(t)

    def write_error(self, error):
        with self.lock:
            with open(self.error_log, 'a', encoding='utf8', errors='ignore') as error_f:
                error_f.write(error)
                error_f.write('\n')

    def __del__(self):
        if self.lpse:
            self.lpse.session.close()
            del self.lpse


# TODO: throttling detail downloader to avoid app makes too many concurrent requests

class DetilDownloader(BaseDownloader):

    def __init__(self, *args, **kwargs):
        super(DetilDownloader, self).__init__(*args, **kwargs)

    def download(self, retry=0, *args, **kwargs):

        id_paket = kwargs['id_paket']

        if self.is_tender:
            detil = self.lpse.detil_paket_tender(id_paket)
        else:
            detil = self.lpse.detil_paket_non_tender(id_paket)

        try:
            detil.get_pengumuman()
            detil.get_pemenang()
            detil.get_jadwal()
        except Exception as e:

            if retry < self.max_retry:
                with self.lock:
                    self.lpse.session = requests.session()
                    self.lpse.session.verify = False

                return self.download(retry=retry+1, id_paket=id_paket)

            error = "{}|{}".format(id_paket, e)
            self.write_error(error)

        with self.lock:
            with open(os.path.join(self.download_dir, id_paket), 'w', encoding='utf8', errors="ignore") as result_file:
                result_file.write(json.dumps(detil.todict()))

        with self.lock:
            self.downloaded += 1
            print("-", self.downloaded, "data berhasil di download", end='\r')

    def stop_process(self):
        with self.lock:
            self.stop = True

    def worker(self):
        while True:
            try:
                id_paket = self.queue.get(block=False)

                if id_paket is None:
                    break
            except Empty:
                pass
            else:
                if not self.stop:
                    self.download(id_paket=id_paket)
                self.queue.task_done()
