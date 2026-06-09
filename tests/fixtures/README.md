# Test Fixtures

This directory contains captured SPSE HTML/JSON responses used by mocked unit tests.

## Files

| File | Source | Description |
|------|--------|-------------|
| `lelang_page.html` | `GET /{instansi}/lelang` | Main lelang page with auth token in JavaScript |
| `dt_lelang.json` | `POST /dt/lelang` | DataTables JSON response (full) |
| `dt_lelang_data_only.json` | `POST /dt/lelang` | DataTables JSON response (data_only=True) |
| `pengumuman_lelang.html` | `GET /lelang/{id}/pengumumanlelang` | Tender announcement detail page |
| `peserta.html` | `GET /lelang/{id}/peserta` | Participant list page |
| `hasil_evaluasi.html` | `GET /evaluasi/{id}/hasil` | Evaluation results page |
| `pemenang.html` | `GET /evaluasi/{id}/pemenang` | Winner page |
| `jadwal.html` | `GET /lelang/{id}/jadwal` | Schedule page |
| `error_page.html` | Synthetic | SPSE error page with error code |
| `not_found_page.html` | Synthetic | SPSE 404 page |

## Refreshing Fixtures

To refresh fixtures with real data:

```python
from pyproc import Lpse

lpse = Lpse("kemenkeu", timeout=30)

# Auth page
resp = lpse.session.get(lpse.url + '/lelang')
with open('lelang_page.html', 'w') as f:
    f.write(resp.text)

# DataTables
resp = lpse.session.post(lpse.url + '/dt/lelang', data={...})
with open('dt_lelang.json', 'w') as f:
    f.write(resp.text)

# Detail pages
resp = lpse.session.get(lpse.url + '/lelang/10080116000/pengumumanlelang')
with open('pengumuman_lelang.html', 'w') as f:
    f.write(resp.text)
```
