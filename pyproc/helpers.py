import json
import os
import threading
from abc import abstractmethod
from queue import Queue
from pyproc import Lpse


class BaseDownloader(object):

    def __init__(self, host, is_tender=True, workers=4):
        self.queue = Queue()
        self.lock = threading.Lock()
        self.lpse = Lpse(host)
        self.downloaded = 0
        self.workers = workers
        self.is_tender = is_tender
        self.error_log = 'error.log'
        self.download_dir = ''

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
            with open(self.error_log, 'a') as error_f:
                error_f.write(error)
                error_f.write('\n')


class DetilDownloader(BaseDownloader):

    def __init__(self, *args, **kwargs):
        self.total = 0
        super(DetilDownloader, self).__init__(*args, **kwargs)

    def download(self, *args, **kwargs):

        id_paket = kwargs['id_paket']

        if self.is_tender:
            detil = self.lpse.detil_paket_tender(id_paket)
        else:
            detil = self.lpse.detil_paket_non_tender(id_paket)

        try:
            try:
                detil.get_pengumuman()
            except Exception as e:
                self.write_error("{}|pengumuman|{}".format(id_paket, str(e)))

            try:
                detil.get_pemenang()
            except Exception as e:
                self.write_error("{}|pemenang|{}".format(id_paket, str(e)))

        except Exception as e:
            error = "{}|general|{}".format(id_paket, e)
            self.write_error(error)

        finally:
            with open(os.path.join(self.download_dir, id_paket), 'w') as result_file:
                result_file.write(json.dumps(detil.todict()))

            with self.lock:
                self.downloaded += 1
                print(self.downloaded, "of", self.total, end='\r')

    def worker(self):
        while True:
            id_paket = self.queue.get()
            self.download(id_paket=id_paket)
            self.queue.task_done()
