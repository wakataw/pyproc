# Plan: Remove max_packages cap, default to all data, paginate at 100/req, add progress

## Context

The `create_procurement_search_index` MCP tool has `MAX_INDEX_PACKAGES = 500` capping the **total** number of packages that can be downloaded. Remove this cap so users can download all available data for a host/year. Default behavior becomes "download all available data." Per-request batch size stays fixed at 100 (internal, not exposed). Progress is reported as a running count via stderr logging — no percentage since we don't rely on `recordsTotal`/`recordsFiltered`.

## Parameter design

| Parameter | Type | Default | Description |
|---|---|---|---|
| `max_packages` | int | `0` | `0` = download all (paginate until exhausted). Positive value caps the total. No upper bound. |
| Batch size | int (internal) | `100` | Fixed `CHUNK_SIZE`, not a user-facing parameter. Matches CLI `--chunk-size` default. |

## Changes

### 1. `pyproc/mcp/schemas.py`

- Delete `MAX_INDEX_PACKAGES = 500` (line 33)
- Change `DEFAULT_INDEX_MAX_PACKAGES = 100` → `DEFAULT_INDEX_MAX_PACKAGES = 0` (0 = all)
- Line 410: `max(1, min(max_packages, MAX_INDEX_PACKAGES))` → `max(0, max_packages)` (0 means unlimited)
- `CREATE_SEARCH_INDEX_SCHEMA` (lines 952-960):
  - Remove `"maximum": MAX_INDEX_PACKAGES`
  - Update description to `"Maximum packages to download. 0 = all available. Default 0."`

### 2. `pyproc/mcp/search_index.py`

- Add `import logging` → `logger = logging.getLogger(__name__)`
- Add `CHUNK_SIZE = 100`

Replace the single-request block (lines 127-139) with a pagination loop:

```python
CHUNK_SIZE = 100
all_rows = []
start = 0
limit = max_packages if max_packages > 0 else float('inf')

while len(all_rows) < limit:
    remaining = limit - len(all_rows)
    req_length = min(CHUNK_SIZE, int(remaining))
    chunk_kwargs = {**kwargs, "start": start, "length": req_length}
    chunk = search_method(**chunk_kwargs)
    if not chunk:
        break
    all_rows.extend(chunk)
    logger.info("Scrolled: %d rows from %s (TA %s)", len(all_rows), lpse_host, tahun_anggaran)
    start += len(chunk)
    if len(chunk) < req_length:
        break  # partial page → end of data

to_process = len(all_rows)
logger.info("Will index %d packages from %s (%s, %s)", to_process, lpse_host, package_type, tahun_anggaran)
```

Progress logging in the detail loop:

```python
for idx, row in enumerate(all_rows, start=1):
    title = _package_title(row)
    logger.info("[%d/%d] Indexing: %s", idx, to_process, title)
    # ... existing fetch + index + rate_limit ...
```

### 3. `pyproc/mcp/tools.py`

- Update tool description string to mention "0 = all" default
- No code changes needed — progress is handled in `search_index.py`'s logger

### 4. Tests

**`tests/test_mcp_schemas.py`** (`TestValidateSearchIndexParams`):
- Default `max_packages` → 0 (all)
- `max_packages=5000` → 5000 (not clamped)
- `max_packages=-1` → 0 (floor at 0)

**`tests/test_mcp_search_index.py`** (`TestSearchIndex`):
- Pagination: mock returns [100, 100, 50] → all 250 collected
- Stops on empty chunk
- Stops on partial chunk (< requested length)
- Respects max_packages limit when positive

## Verification

```bash
python -m pytest tests/test_mcp_schemas.py::TestValidateSearchIndexParams tests/test_mcp_search_index.py -v
python -m pytest tests/ --ignore=tests/test_lpse.py --ignore=tests/test_downloader.py -v
```
