from pyproc import __version__

##########################
# downloader header logo #
##########################
INFO = r'''    ____        ____                 
   / __ \__  __/ __ \_________  _____
  / /_/ / / / / /_/ / ___/ __ \/ ___/
 / ____/ /_/ / ____/ /  / /_/ / /__  
/_/    \__, /_/   /_/   \____/\___/  
      /____/                        
SPSE4 Downloader, PyProc v{}
'''.format(__version__)

##############################
#    argument help text      #
##############################
HELP_KEYWORD = "filter pencarian index paket berdasarkan kata kunci tertentu"
HELP_TAHUN_ANGGARAN = "filter download detail berdasarkan tahun anggaran. Format tahun anggaran bisa " \
                      "dilihat di dokumentasi"
HELP_CHUNK_SIZE = "jumlah daftar index per-halaman yang diunduh dalam satu iterasi"
HELP_WORKERS = "jumlah workers untuk mengunduh detil paket secara paralel"
HELP_TIMEOUT = "besaran waktu timeout untuk menunggu respon dari server"
HELP_NONTENDER = "flag untuk mengunduh data paket pengadaan langsung"
HELP_INDEX_DOWNLOAD_DELAY = "waktu delay untuk setiap iterasi halaman index dalam detik"
HELP_KEEP = "tidak menghapus working direktori dari downloader"
HELP_LPSE_HOST = "host LPSE atau file teks berisi daftar host LPSE. Format dapat dilihat di dokumentasi"
HELP_LOG_LEVEL = "Set log level"
HELP_KATEGORI = "filter pencarian index paket berdasarkan kategori"
HELP_PENYEDIA = "filter pencarian index paket berdasarkan nama penyedia"
HELP_OUTPUT = "format output hasil download"
HELP_RESUME = "melanjutkan proses sebelumnya"

#####################
# Error Information #
#####################

ERROR_CTX_TAHUN_ANGGARAN = "Gagal parsing tahun anggaran, format yang diperbolehkan X-Y atau X;Y;Z"
ERROR_CTX_RANGE_TAHUN = "Nilai tahun harus di antara 2000 dan {}"
ERROR_CTX_HOST_SKEMA = "Skema URL tidak ditemukan. URL harus diawali http/https"
ERROR_CTX_HOST_FORMAT = "Argumen host `{}` tidak sesuai format"
