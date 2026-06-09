# API and CLI Wrapper Optimization Plan

## 1. Executive Summary

PyProc is a Python wrapper for Indonesia's government e-Procurement system (SPSE at `spse.inaproc.id`). It provides a low-level Python API (`Lpse` class) that scrapes SPSE web pages and a CLI bulk downloader that orchestrates index retrieval, detail downloading, and CSV/JSON export using a local SQLite database.

The project works but has several structural issues:

- **The CLI module (`cli.py`, 808 lines) is monolithic.** It contains argument parsing, SQLite schema management, index downloading, detail downloading, data export, signal handling, progress display, and the main entry point all in one file.
- **Boundary violations exist between the API and CLI layers.** The CLI directly manipulates `requests` session internals, bypasses the `Lpse` class for host list downloads, and the `main()` function handles subcommands with raw `sys.argv` parsing instead of argparse.
- **All tests are live integration tests with no mocks.** Every test hits real SPSE servers, making the test suite fragile, slow, and network-dependent.
- **SQLite usage is embedded directly in CLI classes** with no separation between data access and download orchestration logic.
- **Several dead/inconsistent code paths exist:** a hardcoded `workers = 1` ignoring the CLI argument, a `skip_spse_check` attribute referenced in tests but not on the `Lpse` class, and `LpseIndex.parse_detail()` returning inconsistent types (`{}` vs `None`).

The most impactful improvements are: (1) extracting SQLite cache logic into a dedicated module, (2) adding mocked unit tests to enable safe refactoring, (3) cleaning up boundary violations, and (4) splitting the monolithic `cli.py` into focused modules.

---

## 2. Current Architecture

### Package Layout

```
pyproc/
    __init__.py          # Exports Lpse, JenisPengadaan, __version__
    lpse.py              # 758 lines — API wrapper + all HTML parsers
    cli.py               # 808 lines — CLI, downloader pipeline, SQLite cache, export
    utils.py             # 91 lines — token parsing, host list download, version parsing
    exceptions.py        # 18 lines — 5 exception classes
    text.py              # 44 lines — UI strings and help text

tests/
    test_lpse.py         # 421 lines — API integration tests (live HTTP)
    test_downloader.py   # 295 lines — CLI integration tests (live HTTP)
```

### How the API Wrapper Works

`Lpse(instansi, timeout)` creates a `requests.Session`, builds a URL `https://spse.inaproc.id/{instansi}`, and provides:
- `get_auth_token()` — extracts CSRF token from cookies or page JavaScript
- `get_paket()` — POSTs to DataTables endpoint, returns JSON
- `get_paket_tender()` / `get_paket_non_tender()` — convenience wrappers
- `detil_paket_tender()` / `detil_paket_non_tender()` — returns `LpseDetil` objects

`LpseDetil` and its parsers use BeautifulSoup/html5lib to scrape HTML detail pages. Retry logic is applied via `backoff.on_exception` decorators on `get_paket` and every detail method.

### How the CLI Works

`main()` in `cli.py` handles three paths:
1. `pyproc daftarlpse` — calls `pyproc.utils.download_host()` (bypasses `Lpse`)
2. `pyproc daftarhost [dir]` — calls `pyproc.utils.download_host_json()` (bypasses `Lpse`)
3. Default — runs `Downloader` pipeline

The `Downloader` pipeline per host:
1. `IndexDownloader` — pages through `get_paket()`, inserts rows into SQLite `INDEX_PAKET`
2. `DetailDownloader` — for each `STATUS=0` row, fetches detail via `detil_paket_*()` and `get_all_detil()`, updates SQLite
3. `Exporter` — reads `STATUS=1` rows, writes CSV or JSON
4. `QualityAssurance` — counts success/fail, writes `statistic.txt`

### SQLite Schema

Single table `INDEX_PAKET` with columns: `ROW_ID` (PK), `ID_PAKET`, `JENIS_PAKET`, `KATEGORI_TAHUN_ANGGARAN`, `STATUS` (0=pending, 1=done), `DETAIL` (JSON blob). Four indexes on `KATEGORI_TAHUN_ANGGARAN`, `ID_PAKET`, `JENIS_PAKET`, `STATUS`.

### Configuration

No config file system. All configuration via CLI argparse arguments with hardcoded defaults. API-layer constants (base URL, User-Agent, retry params) are hardcoded in `lpse.py`.

---

## 3. Layer Boundary Assessment

### Good Existing Boundaries

- **`Lpse` class is self-contained.** It owns its `requests.Session`, handles auth, requests, and response parsing internally. It can be used from Python code without the CLI.
- **`exceptions.py` is properly separated.** Custom exceptions are in their own module.
- **`text.py` isolates UI strings.** Help text and error messages are not scattered through logic.
- **Parser classes follow a clean pattern.** `BaseLpseDetilParser` defines the interface; subclasses override `detil_path` and `parse_detil()`.

### Boundary Violations

| # | Violation | Location | Impact |
|---|-----------|----------|--------|
| 1 | CLI calls `pyproc.utils.download_host()` and `download_host_json()` directly, bypassing the `Lpse` class. These functions make raw `requests.get()` calls. | `cli.py:777-786`, `utils.py:23-85` | API-layer HTTP logic is duplicated outside the client class. |
| 2 | CLI accesses `pyproc.JenisPengadaan` by string name lookup. | `cli.py:110-114` | CLI couples to specific enum names in the API layer. |
| 3 | `utils.py` imports and uses `requests` directly for `get_all_host()` and `download_host_json()`. | `utils.py:24, 73` | HTTP transport leaks into a utility module. |
| 4 | `check_new_version()` in CLI makes a raw `requests.get()` to PyPI. | `cli.py:36` | HTTP call in CLI layer with no error handling. |
| 5 | SQLite schema definition, connection management, and queries are embedded in CLI classes (`IndexDownloader`, `DetailDownloader`, `Exporter`, `QualityAssurance`). | `cli.py:210-621` | Cache internals are inseparable from download orchestration. |
| 6 | `print()` calls for progress output are inside `DetailDownloader.start()`. | `cli.py:496-507` | Progress display is coupled to download logic. |
| 7 | `exit()` calls in `main()` and interactive menu. | `cli.py:643, 780, 787` | Process exit is scattered rather than centralized. |
| 8 | `disable_warnings(InsecureRequestWarning)` is called at module import time in `cli.py`. | `cli.py:19` | Side effect on import; should be in the API layer or configurable. |

### Duplicated Logic

- **Host URL construction:** `Lpse.__init__` builds `https://spse.inaproc.id/{instansi}`, but `utils.py` independently fetches host lists from a different API (`satudata.inaproc.id`).
- **HTTP request patterns:** Both `Lpse` and `utils.py` use `requests` with different timeout values, different error handling, and different session management.

### Import Direction

Import direction is correct: `cli.py` imports from `pyproc` (the API layer). There are no circular imports. However, `text.py` imports from `pyproc` (`__version__`), creating a mild coupling between UI strings and package metadata.

---

## 4. Key Findings

### Finding 1: Monolithic CLI Module

**Area:** Code Structure  
**Severity:** High

**Current Problem:**  
`cli.py` is 808 lines containing 10 classes and the `main()` function. It handles argument parsing, SQLite schema, index downloading, detail downloading with threading, CSV/JSON export, quality assurance checks, signal handling, version checking, progress display, and interactive menus — all in one file.

**Why It Matters:**  
Changes to any one concern (e.g., SQLite schema) risk affecting unrelated concerns (e.g., export formatting). The file is difficult to navigate, test in isolation, or extend. New contributors face a high cognitive load.

**Recommended Direction:**  
Split into focused modules: `cache.py` (SQLite logic), `export.py` (CSV/JSON export), `downloader.py` (download orchestration), and keep `cli.py` as the thin entry point with argument parsing and `main()`.

**Files/Modules Involved:**  
`pyproc/cli.py`

**Risk Level:** Medium — requires careful import management to avoid breaking the public entry point.

---

### Finding 2: SQLite Cache Embedded in CLI Classes

**Area:** SQLite Cache  
**Severity:** High

**Current Problem:**  
SQLite table creation (`CREATE TABLE INDEX_PAKET`), connection management, query execution, and row-to-object mapping are spread across `IndexDownloader`, `DetailDownloader`, `Exporter`, and `QualityAssurance`. The schema is defined as a string literal inside `get_index_db()`. Connection lifecycle is managed via `__del__` (garbage collection dependent).

**Why It Matters:**  
The cache cannot be tested independently. Schema changes require modifying the download orchestration code. The `__del__`-based cleanup is unreliable — Python does not guarantee `__del__` is called, and reference cycles can prevent it.

**Recommended Direction:**  
Extract a `CacheStore` class in a dedicated `cache.py` module that owns: connection lifecycle (context manager), schema creation, CRUD operations, and the row-to-`LpseIndex` factory. CLI classes should call `CacheStore` methods, not execute raw SQL.

**Files/Modules Involved:**  
`pyproc/cli.py` (lines 210-407, 510-621)

**Risk Level:** Medium — schema must remain backward-compatible for `--resume` to work with existing `.idx` files.

---

### Finding 3: All Tests Are Live Integration Tests

**Area:** Testing  
**Severity:** High

**Current Problem:**  
Every test in `test_lpse.py` and `test_downloader.py` makes live HTTP requests to real SPSE servers. There are no mocked HTTP responses, no temporary SQLite databases, and no test fixtures for API responses.

**Why It Matters:**  
Tests fail when servers are down, slow, or change behavior. Tests cannot run in CI without network access. Test execution is slow. Edge cases (error responses, timeouts, malformed HTML) cannot be reliably tested.

**Recommended Direction:**  
Add a parallel set of unit tests using `unittest.mock` to patch `requests.Session.get/post`. Create fixture files with real HTML/JSON responses captured from the live API. Keep existing integration tests but mark them with a `@pytest.mark.integration` decorator so they can be skipped in fast CI runs.

**Files/Modules Involved:**  
`tests/test_lpse.py`, `tests/test_downloader.py`, new `tests/fixtures/` directory

**Risk Level:** Low — adding tests does not change production code.

---

### Finding 4: Hardcoded Worker Count

**Area:** CLI Wrapper  
**Severity:** Medium

**Current Problem:**  
`DownloaderContext.__init__` sets `self.workers = 1` at line 99, ignoring the parsed `args.workers` value. The `--workers` CLI argument (default 8) is accepted by argparse but never used.

**Why It Matters:**  
Users believe they can control parallelism but cannot. The `--workers` help text is misleading. The threading infrastructure in `DetailDownloader` is built for multi-worker operation but is artificially constrained.

**Recommended Direction:**  
Either re-enable the workers argument (fix the thread safety issues first — see Finding 7) or remove the `--workers` argument from argparse to avoid confusion. If re-enabling, ensure SQLite reads in `get_index()` are thread-safe.

**Files/Modules Involved:**  
`pyproc/cli.py` (lines 99, 466, 692)

**Risk Level:** Low — changing the default or removing the flag is a safe CLI behavior change.

---

### Finding 5: Inconsistent Error Return Types

**Area:** API Wrapper  
**Severity:** Medium

**Current Problem:**  
`LpseIndex.parse_detail()` returns `{}` on `TypeError` (when `detail` is `None`) but returns `None` for any other exception. Parser methods like `LpseDetilPemenangParser.parse_detil()` can return `None` (via bare `return` on `AttributeError`), a `list`, or `None` again at the end.

**Why It Matters:**  
Downstream code must handle both `dict` and `None` for the same field, leading to defensive checks scattered throughout. The `Exporter.to_csv()` method calls `item.get('pengumuman')` which fails if `item` is `None`.

**Recommended Direction:**  
Standardize return types: parsers should return `None` consistently on failure (never `{}`), and callers should check for `None` explicitly. Alternatively, return empty collections (`[]` for list parsers, `{}` for dict parsers) consistently.

**Files/Modules Involved:**  
`pyproc/lpse.py` (parser classes), `pyproc/cli.py` (LpseIndex, Exporter)

**Risk Level:** Medium — changing return types may break downstream code that depends on current behavior.

---

### Finding 6: `skip_spse_check` Test Attribute Does Not Exist

**Area:** Testing  
**Severity:** Medium

**Current Problem:**  
In `test_lpse.py` line 202: `self.lpse.skip_spse_check = True` — this attribute does not exist on the `Lpse` class. The test `TestPaketNonTender.setUp()` sets a non-existent attribute, which silently succeeds in Python (dynamic attribute assignment) but has no effect.

**Why It Matters:**  
The test may be passing by accident. If the attribute was supposed to control behavior (e.g., skip a version/health check), that behavior is not being tested. If it was removed from `Lpse`, the test should have been updated.

**Recommended Direction:**  
Investigate whether `skip_spse_check` ever existed. If it was removed, remove the line from the test. If it was intended to control behavior, implement it properly or document why it's unnecessary.

**Files/Modules Involved:**  
`tests/test_lpse.py` (line 202)

**Risk Level:** Low — test-only change.

---

### Finding 7: Thread Safety Concern with SQLite

**Area:** Reliability  
**Severity:** Medium

**Current Problem:**  
`DetailDownloader` uses `check_same_thread=False` on the SQLite connection and a `threading.Lock` for writes (`update_detail`), but reads in `get_index()` are not locked. If workers were re-enabled (>1), concurrent reads during writes could cause `sqlite3.OperationalError: database is locked`.

**Why It Matters:**  
The multi-worker path is broken by design. Even with `workers=1`, the `check_same_thread=False` flag is unnecessary and masks potential issues.

**Recommended Direction:**  
For now, keep `workers=1` and remove `check_same_thread=False`. If multi-worker support is desired later, either use WAL mode with proper locking, or use a connection-per-thread pattern.

**Files/Modules Involved:**  
`pyproc/cli.py` (lines 257, 448-455, 379-387)

**Risk Level:** Low — removing `check_same_thread=False` with `workers=1` is safe.

---

### Finding 8: `utils.py` Makes Raw HTTP Calls

**Area:** API Wrapper  
**Severity:** Medium

**Current Problem:**  
`utils.py` contains `get_all_host()` and `download_host_json()` which make direct `requests.get()` calls to external APIs (`satudata.inaproc.id` and GitHub Gist). These bypass the `Lpse` class entirely and have no retry logic, no session management, and minimal error handling.

**Why It Matters:**  
HTTP transport is scattered across modules. Error handling is inconsistent (some functions raise, others silently fail). The `download_host()` function takes a `logging` module as a parameter instead of using the standard `logging.getLogger()` pattern.

**Recommended Direction:**  
Either: (a) move these HTTP calls into a proper client class with consistent retry/error handling, or (b) keep them as standalone utilities but add consistent error handling and use `logging.getLogger(__name__)` instead of passing `logging` as a parameter.

**Files/Modules Involved:**  
`pyproc/utils.py`

**Risk Level:** Low — these are auxiliary functions, not core API.

---

### Finding 9: No Type Hints

**Area:** Code Structure  
**Severity:** Low

**Current Problem:**  
The entire codebase has no type hints. Function signatures, return types, and data structures are documented only in docstrings (and many functions lack docstrings entirely).

**Why It Matters:**  
IDE autocomplete is limited. Static analysis tools cannot catch type errors. New contributors must read implementation to understand data shapes.

**Recommended Direction:**  
Add type hints incrementally, starting with the public API (`Lpse` methods, `BaseLpseDetil` attributes) and CLI entry points. Use `from __future__ import annotations` for Python 3.9 compatibility.

**Files/Modules Involved:**  
All `.py` files

**Risk Level:** Low — type hints are additive and do not change runtime behavior.

---

### Finding 10: `__del__`-Based Resource Cleanup

**Area:** Reliability  
**Severity:** Medium

**Current Problem:**  
Both `Lpse.__del__()` (line 237) and `IndexDownloader.__del__()` (line 396) rely on garbage collection to close resources (HTTP session, SQLite connection). Python does not guarantee `__del__` is called, and reference cycles can prevent it entirely.

**Why It Matters:**  
SQLite connections may leak. HTTP sessions may not be closed properly. In long-running processes or when exceptions occur, resources may accumulate.

**Recommended Direction:**  
Implement context managers (`__enter__`/`__exit__`) for both `Lpse` and `IndexDownloader`. Keep `__del__` as a safety net but do not rely on it. Use `with` statements in the CLI.

**Files/Modules Involved:**  
`pyproc/lpse.py` (Lpse class), `pyproc/cli.py` (IndexDownloader class)

**Risk Level:** Low — adding context managers is backward-compatible.

---

### Finding 11: `main()` Handles Subcommands with Raw sys.argv

**Area:** CLI Wrapper  
**Severity:** Low

**Current Problem:**  
`main()` checks `sys.argv[1]` directly for `daftarlpse` and `daftarhost` subcommands before falling through to argparse. The subcommands bypass argparse entirely, meaning they don't support `--help`, have no argument validation, and `daftarhost` parses `sys.argv[2]` manually.

**Why It Matters:**  
Subcommand behavior is inconsistent with the main command. Users cannot get help for subcommands. Adding new subcommands requires modifying the raw argv parsing.

**Recommended Direction:**  
Convert to argparse subparsers: `pyproc download [args]`, `pyproc daftarlpse`, `pyproc daftarhost [dir]`. This unifies argument handling and enables `pyproc daftarhost --help`.

**Files/Modules Involved:**  
`pyproc/cli.py` (main function, lines 769-807)

**Risk Level:** Medium — changes CLI invocation syntax. Must preserve backward compatibility (e.g., default to `download` when no subcommand is given).

---

### Finding 12: Disabled SSL Verification

**Area:** Reliability  
**Severity:** Low

**Current Problem:**  
`Lpse.__init__` sets `self.session.verify = False` and `cli.py` suppresses `InsecureRequestWarning` at import time. This disables SSL certificate verification for all requests.

**Why It Matters:**  
This is likely necessary because the SPSE server may have misconfigured certificates. However, it should be documented and ideally configurable rather than silently disabled.

**Recommended Direction:**  
Add a `verify` parameter to `Lpse.__init__` defaulting to `False` (preserving current behavior), with a comment explaining why. Move the warning suppression into the API layer.

**Files/Modules Involved:**  
`pyproc/lpse.py` (line 38), `pyproc/cli.py` (lines 16-19)

**Risk Level:** Low — additive parameter with backward-compatible default.

---

### Finding 13: pyproject.toml Classifiers Mismatch

**Area:** DevEx  
**Severity:** Low

**Current Problem:**  
The `pyproject.toml` lists `Programming Language :: Python :: 3.7` in classifiers but `requires-python = ">=3.9"`. The classifier is stale.

**Why It Matters:**  
Users may be confused about supported Python versions. PyPI displays the classifier prominently.

**Recommended Direction:**  
Update classifiers to match `requires-python`. Add `3.9`, `3.10`, `3.11`, `3.12` classifiers.

**Files/Modules Involved:**  
`pyproject.toml`

**Risk Level:** Low — metadata-only change.

---

## 5. Optimization Roadmap

### Phase 0 — Safety and Baseline

**Goal:** Establish a safety net before any refactoring.

- Document current `Lpse` public API signatures and return types
- Document current CLI commands, arguments, and exit codes
- Capture sample SPSE HTML responses as test fixtures
- Add mocked unit tests for `Lpse.get_paket()` and `Lpse.get_auth_token()`
- Add mocked unit tests for `IndexDownloader` with a temporary SQLite file
- Add mocked unit tests for `Exporter` CSV/JSON output
- Identify and fix the `skip_spse_check` test issue
- Verify all existing tests still pass

### Phase 1 — Layer Boundary Cleanup

**Goal:** Ensure CLI only calls public API wrapper methods; no direct HTTP or raw SQL from the wrong layer.

- Move `disable_warnings(InsecureRequestWarning)` into `Lpse.__init__` or a transport config
- Replace `pyproc.utils.download_host()` and `download_host_json()` calls in `main()` with calls through a proper client method or keep them as utilities with consistent error handling
- Replace `exit()` calls in `main()` with `sys.exit()` and centralize exit points
- Ensure `DownloaderContext.kategori` uses a safe lookup that does not depend on exact enum names
- Remove `print()` from `DetailDownloader.start()` and use `logging` consistently
- Move `check_new_version()` error handling to catch network failures gracefully

### Phase 2 — SQLite Cache Extraction

**Goal:** Separate SQLite logic from download orchestration.

- Create `pyproc/cache.py` with a `CacheStore` class
- Move schema creation, connection management, CRUD operations into `CacheStore`
- Implement context manager for connection lifecycle
- Keep the same `INDEX_PAKET` schema for backward compatibility
- Update `IndexDownloader`, `DetailDownloader`, `Exporter`, `QualityAssurance` to use `CacheStore`
- Add unit tests for `CacheStore` using temporary SQLite files

### Phase 3 — CLI Module Split

**Goal:** Break `cli.py` into focused modules without changing public behavior.

- Create `pyproc/downloader.py` for `IndexDownloader`, `DetailDownloader`, `LpseIndex`, `LpseHost`, `DownloaderContext`
- Create `pyproc/export.py` for `Exporter`
- Keep `cli.py` as the thin entry point: `main()`, `Downloader`, argument parsing, signal handling
- Preserve the `pyproc.cli:main` entry point
- Update imports throughout

### Phase 4 — Low-Level API Wrapper Improvement

**Goal:** Improve the `Lpse` class for independent Python use.

- Add `verify` parameter to `Lpse.__init__` (default `False`, documented)
- Add context manager support to `Lpse`
- Standardize parser return types (consistent `None` or empty collection on failure)
- Add type hints to public API methods
- Consolidate retry configuration into a class-level constant or parameter
- Document the public API in docstrings

### Phase 5 — CLI Experience Improvement

**Goal:** Improve usability without breaking existing commands.

- Convert `main()` to use argparse subparsers (with backward-compatible default)
- Fix or remove `--workers` argument
- Standardize exit codes (0=success, 1=error, 2=usage error)
- Add `--no-ssl-verify` flag (defaulting to current behavior of no verification)
- Improve error messages for common failures (host not found, network timeout)

### Phase 6 — Packaging and Developer Experience

**Goal:** Clean up project metadata and developer workflow.

- Fix `pyproject.toml` Python version classifiers
- Add `[project.optional-dependencies]` for dev/test dependencies (`pytest`, `responses` or `requests-mock`)
- Add `conftest.py` with shared fixtures
- Update Makefile test targets
- Add brief README sections for: Python API usage, CLI usage, development setup

---

## 6. Implementation Tasks for Small Agents

### Task 1: Capture SPSE Response Fixtures

**Goal:** Create test fixture files with real SPSE HTML/JSON responses for mocked testing.

**Context:** All current tests hit live servers. We need fixture files to enable offline unit tests.

**Scope:** New `tests/fixtures/` directory, no production code changes.

**Implementation Instructions:**
1. Create `tests/fixtures/` directory
2. Run each API call once and capture the response:
   - `GET /{instansi}/lelang` — HTML page with auth token
   - `POST /dt/lelang` — JSON DataTables response
   - `GET /lelang/{id}/pengumumanlelang` — HTML detail page
   - `GET /lelang/{id}/peserta` — HTML participants page
   - `GET /evaluasi/{id}/hasil` — HTML evaluation results page
   - `GET /evaluasi/{id}/pemenang` — HTML winner page
   - `GET /lelang/{id}/jadwal` — HTML schedule page
3. Save each as a `.html` or `.json` file in `tests/fixtures/`
4. Add a `README.md` in fixtures explaining how to refresh them

**Do Not Change:** Production code, existing tests.

**Acceptance Criteria:**
- [ ] Fixture directory exists with at least 7 response files
- [ ] Each file contains valid HTML or JSON
- [ ] Fixture README explains refresh procedure

**Suggested Tests:** N/A (this is test infrastructure).

**Risk:** Low

**Dependencies:** None

---

### Task 2: Add Mocked Unit Tests for Lpse API

**Goal:** Add unit tests for `Lpse` that do not require network access.

**Context:** Current tests are all live integration tests. Mocked tests enable safe refactoring.

**Scope:** New `tests/test_lpse_unit.py`, no production code changes.

**Implementation Instructions:**
1. Create `tests/test_lpse_unit.py`
2. Use `unittest.mock.patch` to mock `requests.Session.get` and `requests.Session.post`
3. Load fixture files from `tests/fixtures/`
4. Test cases:
   - `test_get_auth_token_from_cookies` — mock response with `SPSE_SESSION` cookie containing `___AT=xxx&`
   - `test_get_auth_token_from_page` — mock response without cookie, verify JS parsing fallback
   - `test_get_paket_returns_dict` — mock POST response with JSON, verify dict return
   - `test_get_paket_data_only_returns_list` — verify `data_only=True` returns list
   - `test_get_paket_error_raises` — mock 404 response, verify `LpseServerExceptions`
   - `test_get_paket_spse_error_text` — mock 200 with error text in body, verify exception
   - `test_detil_paket_tender_returns_lpse_detil` — verify return type
   - `test_parser_pengumuman` — feed fixture HTML, verify parsed dict structure
   - `test_parser_peserta` — feed fixture HTML, verify list of dicts
   - `test_parser_pemenang_empty_table` — verify `None` return on missing table

**Do Not Change:** Production code.

**Acceptance Criteria:**
- [ ] All tests pass without network access
- [ ] Tests cover auth token, search, detail parsing, and error paths
- [ ] Tests use fixture files, not live HTTP

**Suggested Tests:** Run with `pytest tests/test_lpse_unit.py -v`

**Risk:** Low

**Dependencies:** Task 1

---

### Task 3: Add Mocked Unit Tests for CLI Components

**Goal:** Add unit tests for CLI argument parsing, context creation, and export that do not require network access.

**Context:** Current CLI tests hit live servers. Need offline tests for safe refactoring.

**Scope:** New `tests/test_cli_unit.py`, no production code changes.

**Implementation Instructions:**
1. Create `tests/test_cli_unit.py`
2. Test `DownloaderContext` creation with various argument combinations
3. Test `LpseHost` parsing (valid, invalid, with filename, without filename)
4. Test `DownloaderContext.parse_tahun_anggaran()` edge cases (single, range, comma-separated, "all", invalid)
5. Test `Exporter.to_csv()` and `Exporter.to_json()` with mock data in a temporary SQLite DB
6. Test `QualityAssurance.check()` with mock data
7. Test `LpseIndex` creation and `parse_detail()` with `None`, valid JSON, and invalid input

**Do Not Change:** Production code.

**Acceptance Criteria:**
- [ ] All tests pass without network access
- [ ] Tests cover argument parsing, host parsing, year parsing, export, and QA
- [ ] Tests use temporary SQLite databases, not live ones

**Suggested Tests:** Run with `pytest tests/test_cli_unit.py -v`

**Risk:** Low

**Dependencies:** None

---

### Task 4: Fix Known Bugs and Inconsistencies

**Goal:** Fix the `skip_spse_check` test attribute, inconsistent `parse_detail()` return type, and stale pyproject.toml classifiers.

**Context:** These are small bugs that should be fixed before refactoring to establish a clean baseline.

**Scope:** `tests/test_lpse.py`, `pyproc/lpse.py` (LpseIndex), `pyproject.toml`

**Implementation Instructions:**
1. In `tests/test_lpse.py` line 202: remove `self.lpse.skip_spse_check = True` (the attribute has no effect)
2. In `pyproc/cli.py` `LpseIndex.parse_detail()`: change the `TypeError` handler to return `None` instead of `{}`, making it consistent with the general exception path. Update any code that assumes `{}` (check `Exporter` and `DetailDownloader`).
3. In `pyproject.toml`: update classifiers to replace `Programming Language :: Python :: 3.7` with `3.9`, `3.10`, `3.11`, `3.12`

**Do Not Change:** Public API behavior, CLI commands, `Lpse` class interface.

**Acceptance Criteria:**
- [ ] `self.lpse.skip_spse_check = True` removed from test
- [ ] `LpseIndex.parse_detail()` returns `None` consistently on error
- [ ] `pyproject.toml` classifiers match `requires-python = ">=3.9"`
- [ ] Existing tests still pass

**Suggested Tests:** Run full test suite.

**Risk:** Low

**Dependencies:** None

---

### Task 5: Extract SQLite Cache into `pyproc/cache.py`

**Goal:** Create a `CacheStore` class that owns all SQLite operations, separate from download orchestration.

**Context:** SQLite logic is currently embedded in `IndexDownloader`, `DetailDownloader`, `Exporter`, and `QualityAssurance`. Extracting it enables independent testing and cleaner refactoring.

**Scope:** New `pyproc/cache.py`, modify `pyproc/cli.py`

**Implementation Instructions:**
1. Create `pyproc/cache.py` with class `CacheStore`
2. `CacheStore.__init__(self, db_path: Path)` — stores path
3. `CacheStore.__enter__` / `__exit__` — open/close connection
4. `CacheStore.create_schema()` — execute CREATE TABLE and CREATE INDEX statements
5. `CacheStore.drop_schema()` — execute DROP TABLE IF EXISTS
6. `CacheStore.insert_rows(rows)` — executemany INSERT OR IGNORE
7. `CacheStore.get_pending()` — SELECT WHERE STATUS=0, yield `LpseIndex` objects
8. `CacheStore.update_detail(row_id, detail_json)` — UPDATE SET DETAIL=?, STATUS=1
9. `CacheStore.get_completed()` — SELECT WHERE STATUS=1
10. `CacheStore.count_by_status()` — returns `{0: fail_count, 1: success_count}`
11. `CacheStore.has_rows()` — returns bool (for resume check)
12. Move `index_factory` static method into `CacheStore` or keep it on `LpseIndex`
13. Update `IndexDownloader`, `DetailDownloader`, `Exporter`, `QualityAssurance` to accept a `CacheStore` instance
14. Remove raw SQL from CLI classes

**Do Not Change:** SQLite schema (table name, columns, indexes must remain identical for `--resume` compatibility), public CLI behavior, `Lpse` class.

**Acceptance Criteria:**
- [ ] `pyproc/cache.py` exists with `CacheStore` class
- [ ] `CacheStore` uses context manager for connection lifecycle
- [ ] No raw SQL remains in `IndexDownloader`, `DetailDownloader`, `Exporter`, or `QualityAssurance`
- [ ] Existing `.idx` files work with `--resume`
- [ ] All existing tests pass

**Suggested Tests:**
- `test_cache_create_schema` — verify table and indexes created
- `test_cache_insert_and_get_pending` — insert rows, verify pending retrieval
- `test_cache_update_detail` — update row, verify status change
- `test_cache_count_by_status` — verify counts
- `test_cache_context_manager` — verify connection cleanup

**Risk:** Medium — must preserve schema compatibility for `--resume`.

**Dependencies:** Task 3 (mocked CLI tests provide safety net)

---

### Task 6: Move `disable_warnings` and SSL Config to API Layer

**Goal:** Consolidate SSL-related configuration in the API layer.

**Context:** `cli.py` suppresses `InsecureRequestWarning` at import time. This should be in the API layer where SSL is actually disabled.

**Scope:** `pyproc/lpse.py`, `pyproc/cli.py`

**Implementation Instructions:**
1. In `Lpse.__init__`, after setting `self.session.verify = False`:
   ```python
   from urllib3.exceptions import InsecureRequestWarning
   from urllib3 import disable_warnings
   disable_warnings(InsecureRequestWarning)
   ```
2. Remove the same imports and call from `cli.py` lines 16-19
3. Add a `verify` parameter to `Lpse.__init__` defaulting to `False`:
   ```python
   def __init__(self, instansi, timeout=10, verify=False):
       self.session = requests.session()
       self.session.verify = verify
   ```

**Do Not Change:** Default behavior (SSL verification stays disabled by default).

**Acceptance Criteria:**
- [ ] `InsecureRequestWarning` suppression is in `lpse.py`, not `cli.py`
- [ ] `Lpse` accepts `verify` parameter
- [ ] Default behavior unchanged (no verification)
- [ ] Tests pass

**Suggested Tests:** `test_lpse_verify_parameter_default_false`

**Risk:** Low

**Dependencies:** None

---

### Task 7: Add Context Manager to `Lpse` and `IndexDownloader`

**Goal:** Enable `with` statement usage for proper resource cleanup.

**Context:** Both classes rely on `__del__` for cleanup, which is unreliable.

**Scope:** `pyproc/lpse.py`, `pyproc/cli.py`

**Implementation Instructions:**
1. Add to `Lpse`:
   ```python
   def __enter__(self):
       return self

   def __exit__(self, exc_type, exc_val, exc_tb):
       self.session.close()
       return False
   ```
2. Add to `IndexDownloader`:
   ```python
   def __enter__(self):
       return self

   def __exit__(self, exc_type, exc_val, exc_tb):
       if self.db:
           self.db.close()
       return False
   ```
3. Keep existing `__del__` methods as safety nets
4. Update `Downloader.start()` to use `with IndexDownloader(...)` if practical

**Do Not Change:** Public API behavior, CLI behavior.

**Acceptance Criteria:**
- [ ] `Lpse` and `IndexDownloader` support `with` statement
- [ ] `__del__` still exists as fallback
- [ ] Tests pass

**Suggested Tests:** `test_lpse_context_manager`, `test_index_downloader_context_manager`

**Risk:** Low

**Dependencies:** None

---

### Task 8: Convert `main()` to Argparse Subparsers

**Goal:** Unify argument handling for all subcommands under argparse.

**Context:** `daftarlpse` and `daftarhost` subcommands bypass argparse, making them inconsistent and lacking `--help` support.

**Scope:** `pyproc/cli.py` (main function)

**Implementation Instructions:**
1. Restructure argparse to use subparsers:
   - `pyproc download [args]` — current default behavior
   - `pyproc daftarlpse` — export host list as CSV
   - `pyproc daftarhost [directory]` — export host list as JSON
2. For backward compatibility: if no recognized subcommand is given, treat all args as `download` args (detect by checking if first arg starts with `-` or is a known host pattern)
3. Add `--help` support for each subcommand
4. Replace `exit(0)` with `sys.exit(0)`

**Do Not Change:** Existing CLI behavior when invoked without subcommands (backward compatible).

**Acceptance Criteria:**
- [ ] `pyproc download --help` works
- [ ] `pyproc daftarlpse` works
- [ ] `pyproc daftarhost --help` works
- [ ] `pyproc kemenkeu --tahun-anggaran 2025` still works (backward compatible)
- [ ] Tests pass

**Suggested Tests:** `test_main_download_subcommand`, `test_main_daftarlpse_subcommand`, `test_main_backward_compat`

**Risk:** Medium — must preserve backward compatibility for existing users.

**Dependencies:** None

---

### Task 9: Fix or Remove `--workers` Argument

**Goal:** Resolve the discrepancy between the `--workers` CLI argument (default 8) and the hardcoded `self.workers = 1`.

**Context:** The argument is accepted but ignored, misleading users.

**Scope:** `pyproc/cli.py`

**Implementation Instructions:**
1. Option A (recommended): Remove `--workers` from argparse and remove the `workers` attribute from `DownloaderContext`. Keep `workers=1` as a constant. This avoids the thread safety issues.
2. Option B: Re-enable workers by changing `self.workers = 1` to `self.workers = args.workers`, but then fix thread safety: add locking to `get_index()` reads, or use WAL mode, or use a connection-per-thread pattern.

**Do Not Change:** Detail download behavior (single-threaded remains default).

**Acceptance Criteria:**
- [ ] `--workers` argument either works correctly or is removed
- [ ] No misleading CLI help text
- [ ] Tests pass

**Suggested Tests:** If removing: `test_workers_argument_not_in_help`. If fixing: `test_multi_worker_download`.

**Risk:** Low (removing) or Medium (fixing).

**Dependencies:** Task 5 (cache extraction makes thread safety easier to reason about)

---

### Task 10: Standardize Error Handling in `utils.py`

**Goal:** Make `utils.py` functions use consistent error handling and logging patterns.

**Context:** `download_host()` takes `logging` as a parameter (anti-pattern). `get_all_host()` has no error handling. `download_host_json()` raises on HTTP error but `get_all_host()` does not.

**Scope:** `pyproc/utils.py`

**Implementation Instructions:**
1. Replace `def download_host(logging, ...)` with `def download_host(...)` using `logger = logging.getLogger(__name__)` at module level
2. Same for `download_host_json()`
3. Add try/except around `get_all_host()` HTTP call with a meaningful error message
4. Add timeout to `get_all_host()` (already has `timeout=10`, verify it's present)
5. Add retry logic to `download_host_json()` or document that it has no retries

**Do Not Change:** Function signatures (except removing `logging` parameter — this is a breaking change for direct callers, but these are internal functions).

**Acceptance Criteria:**
- [ ] `utils.py` uses `logging.getLogger(__name__)` instead of passed `logging` parameter
- [ ] HTTP calls have consistent error handling
- [ ] Tests pass (update `test_downloader.py` and `test_lpse.py` if they call these functions)

**Suggested Tests:** `test_download_host_json_error_handling`, `test_get_all_host_timeout`

**Risk:** Medium — removing `logging` parameter is a breaking change for any external callers.

**Dependencies:** None

---

### Task 11: Add Type Hints to Public API

**Goal:** Add type hints to `Lpse` public methods and `BaseLpseDetil` attributes.

**Context:** No type hints exist in the codebase. Adding them to the public API improves IDE support and documentation.

**Scope:** `pyproc/lpse.py`, `pyproc/exceptions.py`

**Implementation Instructions:**
1. Add `from __future__ import annotations` at the top of `lpse.py`
2. Add type hints to `Lpse.__init__`, `get_auth_token`, `get_paket`, `get_paket_tender`, `get_paket_non_tender`, `detil_paket_tender`, `detil_paket_non_tender`
3. Add type hints to `BaseLpseDetil` attributes and `get_all_detil`, `todict`
4. Add type hints to `BaseLpseDetilParser.get_detil` and `parse_detil`
5. Add type hints to exception classes (they have no methods, so this is just ensuring `__init__` signatures are typed)

**Do Not Change:** Runtime behavior.

**Acceptance Criteria:**
- [ ] All public `Lpse` methods have type hints
- [ ] `BaseLpseDetil` attributes have type hints
- [ ] `from __future__ import annotations` is used for Python 3.9 compatibility
- [ ] Tests pass

**Suggested Tests:** N/A (type hints don't change behavior; run existing tests to verify no syntax errors).

**Risk:** Low

**Dependencies:** None

---

### Task 12: Update pyproject.toml and Dev Dependencies

**Goal:** Fix classifiers and declare dev dependencies properly.

**Context:** Classifiers list Python 3.7 but `requires-python` is `>=3.9`. Dev dependencies are not declared.

**Scope:** `pyproject.toml`, `Makefile`

**Implementation Instructions:**
1. Update classifiers to remove `3.7`, add `3.9`, `3.10`, `3.11`, `3.12`
2. Add `[project.optional-dependencies]` section:
   ```toml
   [project.optional-dependencies]
   test = ["pytest"]
   ```
3. Update Makefile `install` target to use `pip install -e ".[test]"`

**Do Not Change:** Runtime dependencies, package behavior.

**Acceptance Criteria:**
- [ ] Classifiers match `requires-python`
- [ ] `pip install -e ".[test]"` installs pytest
- [ ] Makefile works

**Suggested Tests:** N/A

**Risk:** Low

**Dependencies:** None

---

## 7. Proposed Lightweight Project Structure

### Current Structure

```
pyproc/
    __init__.py
    lpse.py              # API wrapper + all parsers (758 lines)
    cli.py               # Everything else (808 lines)
    utils.py
    exceptions.py
    text.py
```

### Proposed Structure

```
pyproc/
    __init__.py          # Exports Lpse, JenisPengadaan, __version__ (unchanged)
    lpse.py              # API wrapper + parsers (unchanged for now)
    cache.py             # NEW — CacheStore class for SQLite operations
    cli.py               # Slimmed down — main(), Downloader, argparse only
    downloader.py        # NEW — IndexDownloader, DetailDownloader, LpseIndex, LpseHost, DownloaderContext
    export.py            # NEW — Exporter class
    utils.py             # Token parsing, host list download (cleaned up)
    exceptions.py        # Unchanged
    text.py              # Unchanged

tests/
    conftest.py          # NEW — shared fixtures
    fixtures/            # NEW — captured HTML/JSON responses
    test_lpse.py         # Existing integration tests (unchanged)
    test_downloader.py   # Existing integration tests (unchanged)
    test_lpse_unit.py    # NEW — mocked API tests
    test_cli_unit.py     # NEW — mocked CLI tests
    test_cache.py        # NEW — CacheStore tests
```

### What Moves Where

| Current Location | New Location | Reason |
|---|---|---|
| `IndexDownloader` class | `pyproc/downloader.py` | Download orchestration, not CLI entry point |
| `DetailDownloader` class | `pyproc/downloader.py` | Download orchestration |
| `LpseIndex` class | `pyproc/downloader.py` | Data class used by downloaders |
| `LpseHost` class | `pyproc/downloader.py` | Host parsing used by downloaders |
| `DownloaderContext` class | `pyproc/downloader.py` | Context used by downloaders |
| `Exporter` class | `pyproc/export.py` | Export logic, independent of download |
| `QualityAssurance` class | `pyproc/downloader.py` or `pyproc/export.py` | QA is part of export pipeline |
| SQLite schema/queries | `pyproc/cache.py` | Data access layer |
| `Downloader` class | `pyproc/cli.py` (stays) | CLI orchestration |
| `main()` function | `pyproc/cli.py` (stays) | Entry point |
| `IWillFindYouAndIWillKillYou` | `pyproc/cli.py` (stays) | Signal handling is CLI concern |
| `set_up_log()` | `pyproc/cli.py` (stays) | Logging config is CLI concern |
| `check_new_version()` | `pyproc/cli.py` (stays) | Version check is CLI concern |

### Migration Steps

1. **Add tests first** (Tasks 1-3) — safety net
2. **Fix bugs** (Task 4) — clean baseline
3. **Extract `cache.py`** (Task 5) — biggest structural win
4. **Extract `downloader.py`** — move classes, update imports in `cli.py`
5. **Extract `export.py`** — move `Exporter`, update imports
6. **Verify** — run all tests after each extraction

### How to Avoid Breaking Imports

- Keep `pyproc.cli:main` as the entry point
- If external code imports from `pyproc.cli` (e.g., `from pyproc.cli import IndexDownloader`), add re-exports in `cli.py`:
  ```python
  from .downloader import IndexDownloader, DetailDownloader  # backward compat
  ```
- The `tests/test_downloader.py` uses `from pyproc.cli import *` — this will need updating after the split.

### What Should NOT Be Abstracted Yet

- Do not create abstract base classes for the downloaders
- Do not introduce dependency injection for `Lpse` (the current direct instantiation is fine)
- Do not split `lpse.py` further (parsers are tightly coupled to the API class)
- Do not create a configuration file system (CLI args are sufficient)

---

## 8. Low-Level API Wrapper Plan

### Public API Design

The current `Lpse` API is reasonable. Improvements:

1. **Add `verify` parameter** to `__init__` (default `False`) — documented, configurable
2. **Add context manager** — `__enter__`/`__exit__` for session cleanup
3. **Standardize return types** — parsers return `None` on failure (not mixed `{}`/`None`)
4. **Add type hints** to all public methods

### Request/Response Handling

Current handling is adequate:
- `requests.Session` with persistent cookies — correct for SPSE's CSRF token flow
- `check_error()` static method checks status codes and error text — good
- DataTables-style POST parameters are constructed correctly

Improvements:
- Move the User-Agent string to a class constant
- Document why SSL verification is disabled

### Error Model

Current exceptions in `exceptions.py`:
- `LpseVersionException` — unused in current code
- `LpseHostExceptions` — unused in current code
- `LpseServerExceptions` — used for API errors
- `LpseAuthTokenNotFound` — unused in current code
- `DownloaderContextException` — CLI-specific, should move to CLI layer

Improvements:
- Remove unused exceptions or document their intended use
- Move `DownloaderContextException` to the CLI/downloader module
- Consider adding `LpseConnectionError` for network failures (wrapping `requests.exceptions.ConnectionError`)

### Retry/Timeout/Rate-Limit Behavior

Current: `backoff.on_exception` with Fibonacci backoff, `max_tries=3`, `jitter=None`, applied via decorators.

This is adequate for the SPSE API. Improvements:
- Make retry parameters configurable on `Lpse.__init__` (optional — only if users request it)
- Add `on_backoff` callback for logging retry attempts

### Backward Compatibility Notes

- `Lpse(instansi, timeout=10)` signature must not change
- `get_paket()` return shape (dict with `data`, `recordsTotal`, `recordsFiltered`) must not change
- `detil_paket_tender()` / `detil_paket_non_tender()` must continue returning `LpseDetil` / `LpseDetilNonTender`
- `BaseLpseDetil.todict()` must continue returning a dict without `_lpse`
- `By` and `JenisPengadaan` enums must not change values

---

## 9. CLI Wrapper Plan

### Command Structure

Current: `pyproc [lpse_host] [options]` with special-case `daftarlpse` and `daftarhost`.

Proposed (with backward compatibility):
```
pyproc [lpse_host] [options]          # backward compatible default (treated as "download")
pyproc download [lpse_host] [options] # explicit download subcommand
pyproc daftarlpse                     # export host list CSV
pyproc daftarhost [directory]         # export host list JSON
```

### Argument Naming Consistency

Current arguments are consistent. Minor improvements:
- `--sep` alias for `--separator` is already present (good)
- Consider adding `--output` or `-o` as alias for `--output-format` (already `-o`)
- `--tahun-anggaran` vs `--tahun` — the test at line 238 uses `--tahun` but argparse defines `--tahun-anggaran`. Verify if `--tahun` works as an abbreviation.

### Output Formatting

Current: CSV and JSON output via `Exporter`. Progress via `print()` in `DetailDownloader`.

Improvements:
- Move progress display to use `logging.info()` consistently (already partially done)
- Ensure JSON output is valid (current implementation writes `[` then items then seeks back — this is fragile; use `json.dump(list)` instead)

### Exit Code Strategy

Current: `exit(0)` for success, `exit(1)` for signal handler.

Proposed:
- `0` — success
- `1` — runtime error (network failure, API error)
- `2` — usage error (invalid arguments)

### Verbose/Debug Behavior

Current: `--log` flag with choices `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`.

This is adequate. Improvement: add `-v` as shorthand for `--log DEBUG`.

---

## 10. SQLite Cache Optimization Plan

### Current Schema Assessment

The schema is simple and functional:
```sql
CREATE TABLE INDEX_PAKET (
    ROW_ID varchar(100) unique primary key,
    ID_PAKET VARCHAR(50),
    JENIS_PAKET VARCHAR(32),
    KATEGORI_TAHUN_ANGGARAN varchar(100),
    STATUS int default 0,
    DETAIL text
);
```

This is adequate for the use case. No changes needed to the schema itself.

### Cache Key Strategy

`ROW_ID = "{tender|nontender}-{id_paket}"` is a good composite key. No changes needed.

### Suggested Indexes

Current indexes are appropriate:
- `KATEGORI_TAHUN_ANGGARAN` — used for year filtering
- `ID_PAKET` — used for lookups
- `JENIS_PAKET` — used for type filtering
- `STATUS` — used for pending/completed queries

No additional indexes needed.

### TTL/Expiration Strategy

There is no TTL. The cache is a download-progress database, not a response cache. TTL is not applicable — the `--resume` feature relies on persistence.

No TTL should be added.

### Cache Invalidation Strategy

Current: `DROP TABLE IF EXISTS` on non-resume runs. This is correct — the cache is disposable per-download.

No changes needed.

### Connection Management

Current: `sqlite3.connect()` in `IndexDownloader.__init__`, closed in `__del__`.

Proposed: Context manager pattern in `CacheStore` (see Task 5).

### Migration Strategy

No schema migration needed. The schema is stable and simple.

For `--resume` compatibility: the `CacheStore.create_schema()` method must produce the exact same table and index names. Existing `.idx` files must continue to work.

### Testing with Temporary SQLite Files

Use `tempfile.NamedTemporaryFile(suffix='.idx')` in tests:
```python
with tempfile.NamedTemporaryFile(suffix='.idx', delete=False) as f:
    db_path = Path(f.name)
    with CacheStore(db_path) as store:
        store.create_schema()
        # ... test operations
```

---

## 11. Testing Strategy

### Tests Needed Before Refactor (Phase 0)

| Test | Type | Purpose |
|------|------|---------|
| Mocked `Lpse.get_paket()` success | Unit | Verify JSON parsing, `data_only` flag |
| Mocked `Lpse.get_paket()` error | Unit | Verify exception on 400+ and error text |
| Mocked `Lpse.get_auth_token()` | Unit | Verify cookie and JS parsing paths |
| Mocked parser `parse_detil()` | Unit | Verify HTML parsing with fixture files |
| `DownloaderContext` argument parsing | Unit | Verify all argument combinations |
| `LpseHost` parsing | Unit | Verify URL/filename extraction |
| `parse_tahun_anggaran()` | Unit | Verify single, range, comma, "all", invalid |
| `Exporter.to_csv()` with temp DB | Unit | Verify CSV output format |
| `Exporter.to_json()` with temp DB | Unit | Verify JSON output format |
| `CacheStore` CRUD operations | Unit | Verify insert, update, query with temp DB |

### Tests Needed After Refactor

| Test | Type | Purpose |
|------|------|---------|
| `CacheStore` context manager cleanup | Unit | Verify connection closed on normal and exception paths |
| CLI subcommand routing | Unit | Verify `download`, `daftarlpse`, `daftarhost` dispatch |
| Backward-compatible argument parsing | Unit | Verify old invocation style still works |
| `--resume` with existing `.idx` file | Integration | Verify schema compatibility |
| Full pipeline with mocked HTTP | Integration | Verify IndexDownloader → DetailDownloader → Exporter |

### Test Infrastructure

- `conftest.py` with shared fixtures: mock `Lpse` instance, temporary SQLite path, fixture HTML/JSON loading helpers
- Mark integration tests with `@pytest.mark.integration`
- Default `pytest` runs unit tests only; `pytest -m integration` runs live tests

---

## 12. Risk Register

| Risk | Area | Severity | Mitigation |
|---|---|---|---|
| Breaking `--resume` for existing `.idx` files | SQLite Cache | High | Preserve exact schema in `CacheStore`; test with existing `.idx` files before and after |
| Breaking `from pyproc.cli import *` in tests | Code Structure | Medium | Add re-exports in `cli.py` after splitting modules |
| Breaking external code that imports from `pyproc.cli` | Code Structure | Medium | Keep re-exports; document any moved classes |
| `utils.download_host()` `logging` parameter removal | API Wrapper | Medium | Document breaking change; update all callers |
| Argparse subparser backward compatibility | CLI Wrapper | Medium | Default to `download` when no subcommand given; test old invocation patterns |
| Thread safety if workers re-enabled | Reliability | Medium | Keep `workers=1` by default; add proper locking if re-enabling |
| Test fixture staleness | Testing | Low | Document refresh procedure; fixtures are for unit tests only |
| Type hint syntax errors on Python 3.9 | Code Structure | Low | Use `from __future__ import annotations`; test on 3.9 |

---

## 13. Recommended Execution Order

1. **Task 1** (Capture fixtures) — no code changes, enables all subsequent testing
2. **Task 2** (Mocked API tests) — safety net for API layer
3. **Task 3** (Mocked CLI tests) — safety net for CLI layer
4. **Task 4** (Fix bugs) — clean baseline before refactoring
5. **Task 6** (Move SSL config) — small, safe boundary cleanup
6. **Task 7** (Context managers) — small, safe reliability improvement
7. **Task 5** (Extract cache) — biggest structural improvement; depends on Task 3 for safety
8. **Task 11** (Type hints) — additive, no risk, improves subsequent work
9. **Task 10** (Clean up utils.py) — small boundary cleanup
10. **Task 9** (Fix workers argument) — small CLI cleanup
11. **Task 8** (Subparsers) — CLI improvement; depends on Tasks 3, 5 for safety
12. **Task 12** (pyproject.toml) — metadata cleanup, no code risk

---

## 14. Out of Scope

The following should NOT be done unless explicitly requested:

- Replacing SQLite with PostgreSQL, Redis, or any other database
- Adding a web framework or REST API layer
- Full rewrite of `lpse.py` or `cli.py`
- Async rewrite (the project uses synchronous `requests` and threading; async would be a major rewrite)
- ORM adoption (SQLAlchemy, etc.) — raw sqlite3 is appropriate for this use case
- Breaking CLI command redesign (preserving existing invocation patterns)
- Breaking public Python API redesign (preserving `Lpse` class interface)
- Adding configuration file support (e.g., `~/.pyproc/config.toml`)
- Adding authentication beyond the current CSRF token approach
- Supporting multiple SPSE servers (the base URL is hardcoded to `spse.inaproc.id`)
- Adding pagination auto-detection or streaming
- Containerization (Docker)
- Adding a plugin system or extension mechanism
