import json
import os
import threading
from abc import abstractmethod
from queue import Queue

import requests

from .lpse import Lpse


class BaseDownloader(object):

    def __init__(self, host, is_tender=True, workers=4, timeout=None):
        self.queue = Queue()
        self.lock = threading.Lock()
        self.lpse = Lpse(host)
        self.lpse.timeout = timeout
        self.downloaded = 0
        self.workers = workers
        self.is_tender = is_tender
        self.error_log = 'error.log'
        self.download_dir = ''
        self.max_retry = 3

    @abstractmethod
    def download(self, *args, **kwargs):
        raise NotImplementedError

    @abstractmethod
    def worker(self):
        raise NotImplementedError

    def spawn_worker(self):
        for i in range(self.workers):
            t = threading.Thread(target=self.worker, daemon=True)
            t.start()

    def write_error(self, error):
        with self.lock:
            with open(self.error_log, 'a', encoding='utf8', errors='ignore') as error_f:
                error_f.write(error)
                error_f.write('\n')

    def __del__(self):
        self.lpse.session.close()
        del self.lpse


class DetilDownloader(BaseDownloader):

    def __init__(self, *args, **kwargs):
        self.total = 0
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
        except Exception as e:

            if retry < self.max_retry:
                with self.lock:
                    self.lpse.session = requests.session()
                    self.lpse.session.verify = False

                return self.download(retry=retry+1, id_paket=id_paket)

            error = "{}|{}".format(id_paket, e)
            self.write_error(error)

        with open(os.path.join(self.download_dir, id_paket), 'w', encoding='utf8', errors="ignore") as result_file:
            result_file.write(json.dumps(detil.todict()))

        with self.lock:
            self.downloaded += 1
            print(self.downloaded, "of", self.total, end='\r')

        del detil

    def worker(self):
        while True:
            id_paket = self.queue.get()
            self.download(id_paket=id_paket)
            self.queue.task_done()
