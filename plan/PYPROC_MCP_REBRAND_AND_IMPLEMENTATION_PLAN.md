# PyProc MCP Rebrand and Implementation Plan

## 1. Executive Summary

### What PyProc Is Today
PyProc (Python Procurement) is a Python API wrapper for SPSE/Inaproc — Indonesia's national e-procurement system. It provides:
- A Python library (`from pyproc import Lpse`) that talks to SPSE/Inaproc DataTables endpoints and scrapes HTML procurement detail pages
- A CLI tool (`pyproc`) for bulk-downloading procurement data with local SQLite caching and CSV/JSON export
- Support for filtering by keyword, budget year, procurement category, provider name, LPSE host, tender/non-tender mode
- Retry/backoff logic, conservative defaults, and responsible-use disclaimers

### What It Should Become
An MCP-compatible tool server so LLM agents can access real-time or near real-time Indonesian public procurement data. The MCP server layer sits beside the existing CLI, calling the same library layer directly. The project is repositioned as MCP-first while preserving full backward compatibility for existing library and CLI users.

### What Must Remain Backward-Compatible
- `from pyproc import Lpse` and `from pyproc import JenisPengadaan`
- All `Lpse` class methods and their signatures
- `pyproc` CLI entry point (`pyproc = "pyproc.cli:main"`)
- All CLI arguments, output formats (CSV/JSON), and the `.idx` SQLite cache schema
- Package name `pyproc` on PyPI
- MIT license

### Recommended Implementation Approach
Add an MCP adapter layer (`pyproc/mcp/`) as a new module that imports from the existing `pyproc.lpse` library. Add a new CLI entry point `pyproc-mcp` for the MCP server. The MCP layer is additive — no existing code paths are modified. The README is rewritten to position MCP as the primary use case while preserving library/CLI documentation.

---

## 2. Current Repository Assessment

### 2.1 Repository Structure

```
pyproc/
    __init__.py          # Exports: Lpse, JenisPengadaan, __version__, __all__
    lpse.py              # 774 lines — Lpse class + 10 HTML parser classes + enums
    cli.py               # 767 lines — CLI downloader pipeline + argument parsing + main()
    cache.py             # 146 lines — CacheStore class for SQLite operations
    utils.py             # 95 lines — Token parsing, host list download, version parsing
    exceptions.py        # 18 lines — 5 exception classes
    text.py              # 44 lines — CLI UI strings, help text, banner

tests/
    __init__.py
    test_lpse.py         # 421 lines — Live integration tests (hits real SPSE servers)
    test_lpse_unit.py    # 493 lines — Mocked unit tests with HTML/JSON fixtures
    test_cli_unit.py     # 526 lines — Mocked CLI component tests with temp SQLite
    test_cache.py        # 200 lines — CacheStore unit tests with temp SQLite
    test_downloader.py   # 295 lines — Live integration tests (hits real SPSE servers)
    fixtures/            # Captured HTML/JSON responses for mocked tests
        pengumuman_lelang.html, peserta.html, hasil_evaluasi.html,
        pemenang.html, jadwal.html, lelang_page.html, error_page.html,
        not_found_page.html, dt_lelang.json, dt_lelang_data_only.json
    supporting_files/     # Test input files
        list-host.txt, list-host-with-filename.txt

pyproject.toml           # Hatchling build, version 0.2, 4 core dependencies
README.md                # Indonesian-language, library/CLI-focused
CHANGELOG.md, LICENSE, Makefile, .gitignore
```

### 2.2 Public Python API

Exported from `pyproc/__init__.py`:
- `Lpse` — Main client class. Constructs URL `https://spse.inaproc.id/{instansi}`, manages `requests.Session`, handles CSRF auth tokens
- `JenisPengadaan` — Enum with 6 procurement categories (PENGADAAN_BARANG through JASA_KONSULTANSI_BADAN_USAHA_KONSTRUKSI)
- `utils` — Module reference (token parsing, host list download)
- `exceptions` — Module reference (error classes)

Key `Lpse` methods:
| Method | Returns | Description |
|---|---|---|
| `get_paket(jenis_paket, start, length, ...)` | `dict` or `list` | Generic package search via DataTables endpoint |
| `get_paket_tender(start, length, ...)` | `dict` or `list` | Tender package search wrapper |
| `get_paket_non_tender(start, length, ...)` | `dict` or `list` | Non-tender package search wrapper |
| `detil_paket_tender(id_paket)` | `LpseDetil` | Create detail fetcher for a tender package |
| `detil_paket_non_tender(id_paket)` | `LpseDetilNonTender` | Create detail fetcher for a non-tender package |
| `get_auth_token()` | `str` or `None` | Extract CSRF token from cookies or page JS |
| `check_error(resp)` | `None` (raises) | Static method, checks HTTP/SPSE error conditions |

Key `BaseLpseDetil` methods (inherited by `LpseDetil` and `LpseDetilNonTender`):
| Method | Sets Attribute | Description |
|---|---|---|
| `get_pengumuman()` | `self.pengumuman: dict` | Parse announcement page |
| `get_peserta()` | `self.peserta: list` | Parse participants page |
| `get_hasil_evaluasi()` | `self.hasil: list` | Parse evaluation results page |
| `get_pemenang(all, key)` | `self.pemenang: list` | Parse winner page |
| `get_pemenang_berkontrak()` | `self.pemenang_berkontrak: list` | Parse contracted winner page |
| `get_jadwal()` | `self.jadwal: list` | Parse schedule page |
| `get_all_detil()` | `dict` (error info) | Fetch all details, catch errors per section |
| `todict()` | `dict` | Serialize to dict (excludes `_lpse` ref) |

### 2.3 CLI Entry Point

Defined in `pyproject.toml`: `pyproc = "pyproc.cli:main"`

`main()` supports three paths:
1. **Default (download)**: `pyproc [LPSE_HOST] [options]` — Downloads index, fetches detail, exports CSV/JSON
2. **`pyproc daftarlpse`**: Downloads LPSE host list as CSV
3. **`pyproc daftarhost [directory]`**: Downloads LPSE host list as JSON from GitHub Gist

CLI arguments (via argparse):
| Flag | Type | Default | Description |
|---|---|---|---|
| `lpse_host` | str (positional) | required | LPSE host or file of hosts |
| `-k, --keyword` | str | `""` | Search keyword filter |
| `-t, --tahun-anggaran` | str | current year | Budget year filter |
| `--kategori` | choice | None | Procurement category filter |
| `--nama-penyedia` | str | None | Provider name filter |
| `-c, --chunk-size` | int | 100 | Records per page |
| `-w, --workers` | int (suppressed) | 8 (unused) | Worker count (hardcoded to 1) |
| `-x, --timeout` | int | 30 | Request timeout in seconds |
| `-n, --non-tender` | flag | False | Download non-tender data |
| `-d, --index-download-delay` | int | 1 | Delay between index page requests |
| `-o, --output-format` | choice | csv | Output format: csv or json |
| `--keep-index` | flag | False | Keep SQLite index file |
| `-r, --resume` | flag | False | Resume failed download |
| `-s, --separator` | str | `;` | CSV delimiter |
| `--log` | choice | INFO | Log level |

### 2.4 Dependencies (from pyproject.toml)

- **requests** — HTTP client
- **beautifulsoup4** — HTML parsing
- **html5lib** — HTML5 parser for BeautifulSoup
- **backoff** — Retry/backoff decorators
- **pytest** (test optional) — Testing framework

### 2.5 Current Architecture Assessment

**Strengths:**
- Clean separation between `Lpse` (transport + parsing) and CLI (orchestration)
- `CacheStore` already extracted into dedicated module with context manager support
- Parser classes follow a consistent `BaseLpseDetilParser` → subclass pattern
- Retry/backoff decorators on all network-facing methods
- Error checking centralized in `Lpse.check_error()`
- Existing unit tests with mocked HTTP responses and fixture files

**Areas for MCP adaptation:**
- `lpse.py` mixes transport (HTTP), parsing (BeautifulSoup), data modeling (enums), and public API (Lpse class) — acceptable for current scale
- Parsers return dicts and lists (suitable for MCP JSON serialization)
- No async support — MCP stdio transport works fine with synchronous code
- Exception hierarchy is simple but adequate — 5 exception classes
- Cache is CLI-focused (download progress DB, not a response cache) — MCP tools will call `Lpse` directly without the CLI cache

---

## 3. Existing Feature Compatibility Contract

### 3.1 Must Not Break

**Public imports:**
- `from pyproc import Lpse` — must continue working
- `from pyproc import JenisPengadaan` — must continue working
- `from pyproc.lpse import By` — must continue working
- `from pyproc.exceptions import LpseServerExceptions` — must continue working

**Public classes:**
- `Lpse(instansi, timeout=10)` — constructor signature must not change
- All `Lpse` methods — signatures and return types must not change
- `LpseDetil` and `LpseDetilNonTender` — interface must not change
- `By` and `JenisPengadaan` enums — values must not change
- All parser classes — behavior must not change

**CLI entry point:**
- `pyproc` command must work as before
- All CLI arguments must be accepted
- `pyproc daftarlpse` and `pyproc daftarhost` must work
- CSV/JSON output format must not change
- SQLite `.idx` file schema must remain compatible

**Packaging:**
- Package name `pyproc` on PyPI must not change
- Version must continue from `0.2` forward
- MIT license must not change

### 3.2 Mitigation Strategy for Each Risk

| Risk | Mitigation |
|---|---|
| Breaking imports | MCP code lives in new `pyproc/mcp/` package; `__init__.py` unchanged |
| Breaking CLI | New entry point `pyproc-mcp` added; `pyproc` entry point untouched |
| Breaking library API | MCP layer calls library methods, never modifies them |
| Breaking cache schema | MCP layer does not use CLI cache; no changes to `cache.py` |
| Confusing existing users | README clearly documents MCP as an additional interface |

---

## 4. Target Architecture

```text
External SPSE/Inaproc endpoints (spse.inaproc.id, satudata.inaproc.id)
        ↓
pyproc library core (lpse.py, utils.py)
  - Lpse class: HTTP transport, CSRF auth, DataTables API
  - HTML parsers: BeautifulSoup/html5lib detail page scraping
  - Backoff/retry decorators, error checking
        ↓
shared modules:
  - cache.py: SQLite CacheStore (CLI download progress, not a response cache)
  - exceptions.py: LpseServerExceptions and 4 other exception classes
  - text.py: UI strings and help text
  - utils.py: Token parsing, host list download
        ↓
adapter layers:
  ├── CLI (cli.py): Downloader pipeline, argparse, CSV/JSON export
  └── MCP server (mcp/): MCP tools, resources, prompts — calls Lpse directly
```

### What's Immediate
- Add `pyproc/mcp/` package with `server.py`, `tools.py`, `schemas.py`, `resources.py`, `prompts.py`
- Add `pyproc-mcp` entry point in `pyproject.toml`
- Add `mcp` Python SDK as an optional dependency

### What's Future Refactor (Phase 5, not in MVP scope)
- Further split `lpse.py` if it grows beyond manageable size
- Add async transport option if MCP streaming transport is needed
- Improve type hints across the codebase
- Extract a lightweight response normalization layer shared by CLI and MCP

---

## 5. Key Findings

### Finding 1: Library API Is MCP-Ready

**Area:** Library  
**Severity:** Low (positive finding)  

**Current State:**  
The `Lpse` class provides clean methods (`get_paket_tender()`, `detil_paket_tender()`, etc.) that return dicts and lists — naturally JSON-serializable for MCP tool output. The `todict()` method on detail objects produces flat dicts suitable for LLM consumption.

**Why It Matters:**  
MCP tools can be thin wrappers around existing library methods. No library refactoring is required for MVP.

**Recommended Direction:**  
Create MCP tool handlers that call `Lpse` methods, normalize output, and add LLM-friendly descriptions.

**Files/Modules Involved:** `pyproc/lpse.py`

**Backward Compatibility Risk:** Low — no changes to library code.

**Implementation Risk:** Low.

---

### Finding 2: README Is Indonesian-Only, Library/CLI-Focused

**Area:** Docs  
**Severity:** Medium  

**Current Problem:**  
The README is written entirely in Indonesian, positioned as a Python library and CLI tool for Indonesian users. There is no mention of MCP, LLM, or AI agent use cases.

**Why It Matters:**  
The MCP rebrand requires a bilingual or English-first README that positions MCP as the primary use case while keeping Indonesian disclaimers for local users.

**Recommended Direction:**  
Rewrite README in English with an Indonesian responsible-use disclaimer section. The MCP use case should be the hero section.

**Files/Modules Involved:** `README.md`

**Backward Compatibility Risk:** Low — documentation-only change.

**Implementation Risk:** Low.

---

### Finding 3: No MCP Dependency Currently

**Area:** MCP  
**Severity:** Low (expected)  

**Current State:**  
The project has no MCP SDK dependency. The `pyproject.toml` lists only `requests`, `beautifulsoup4`, `html5lib`, and `backoff`.

**Why It Matters:**  
The MCP SDK must be added. The official `mcp` Python package (from Anthropic/modelcontextprotocol) is the recommended choice — it's lightweight, supports stdio transport, and is well-documented.

**Recommended Direction:**  
Add `mcp` as an optional dependency: `mcp = ["mcp"]`. The MCP server uses stdio transport (no additional network dependencies).

**Files/Modules Involved:** `pyproject.toml`

**Backward Compatibility Risk:** Low — optional dependency.

**Implementation Risk:** Low.

---

### Finding 4: Parser Output Contains Raw HTML Text

**Area:** Security  
**Severity:** Medium  

**Current State:**  
BeautifulSoup parsers extract text from HTML elements but do not sanitize it. The raw text from SPSE pages could contain unexpected content (user-generated provider names, package descriptions) that might include problematic text for LLM consumption.

**Why It Matters:**  
When MCP tools return procurement data to LLMs, any raw text from SPSE pages becomes part of the LLM context. This is a prompt injection vector — malicious SPSE data could theoretically influence LLM behavior.

**Recommended Direction:**  
Add lightweight output sanitization in the MCP layer: truncate long text fields, strip control characters, and note in tool descriptions that data comes from public SPSE pages. The risk is low because SPSE is a government system with controlled data entry, but it should be documented.

**Files/Modules Involved:** `pyproc/mcp/tools.py`, `pyproc/mcp/schemas.py`

**Backward Compatibility Risk:** Low — sanitization only in MCP layer.

**Implementation Risk:** Low.

---

### Finding 5: Exception Hierarchy Is Adequate but Could Be Improved for MCP

**Area:** Library / MCP  
**Severity:** Low  

**Current State:**  
Five exception classes exist: `LpseVersionException`, `LpseHostExceptions`, `LpseServerExceptions`, `LpseAuthTokenNotFound`, `DownloaderContextException`. The first two and the auth token exception are unused in current code. Only `LpseServerExceptions` is actively raised.

**Why It Matters:**  
MCP tools need to map Python exceptions to MCP error responses. Having a clear, well-defined exception hierarchy makes this mapping clean.

**Recommended Direction:**  
Keep existing exceptions as-is. In the MCP layer, create an error mapper that catches `LpseServerExceptions` (and `requests` exceptions) and converts them to MCP error responses with user-friendly messages. Do not remove unused exceptions — they may be used in future.

**Files/Modules Involved:** `pyproc/exceptions.py`, `pyproc/mcp/errors.py`

**Backward Compatibility Risk:** Low — no changes to exceptions.

**Implementation Risk:** Low.

---

### Finding 6: No Rate Limiting at the Library Level

**Area:** Library / MCP  
**Severity:** Medium  

**Current State:**  
Rate limiting exists only in the CLI layer (`index_download_delay`). The `Lpse` class itself has no built-in rate limiting — it relies on `backoff` for retries on failure, not for proactive throttling.

**Why It Matters:**  
MCP tools called by LLM agents could trigger rapid successive requests if an LLM loops or makes concurrent tool calls. The MCP layer should add conservative throttling to avoid overwhelming SPSE servers.

**Recommended Direction:**  
Add a simple inter-request delay in the MCP tool layer (e.g., 1 second minimum between calls to the same `Lpse` instance). Use `time.sleep()` or a simple token bucket. Document the rate limiting in tool descriptions so LLMs understand the constraint.

**Files/Modules Involved:** `pyproc/mcp/tools.py`, `pyproc/mcp/server.py`

**Backward Compatibility Risk:** Low — throttling only in MCP layer.

**Implementation Risk:** Low.

---

### Finding 7: `verify=False` Is Default — Security Consideration

**Area:** Security  
**Severity:** Medium  

**Current State:**  
`Lpse.__init__` sets `self.session.verify = False`, disabling SSL certificate verification. This is likely necessary because SPSE servers may have misconfigured certificates. The `InsecureRequestWarning` is suppressed.

**Why It Matters:**  
MCP tools will inherit this behavior. The risk is low (public procurement data, not sensitive credentials), but it should be clearly documented so MCP users understand the security trade-off.

**Recommended Direction:**  
Document in README and MCP tool descriptions that SSL verification is disabled by default. The `verify` parameter on `Lpse.__init__` is already configurable for users who want to enable it. No code changes needed.

**Files/Modules Involved:** `pyproc/lpse.py` (no changes), README, MCP resource docs

**Backward Compatibility Risk:** Low — documentation only.

**Implementation Risk:** Low.

---

### Finding 8: CLI `--workers` Is Hardcoded to 1

**Area:** CLI  
**Severity:** Low  

**Current State:**  
`DownloaderContext.__init__` sets `self.workers = 1` (hardcoded), ignoring the `--workers` argument. The `--workers` flag is suppressed from help output.

**Why It Matters:**  
Does not directly affect MCP work but represents technical debt. Not urgent for MCP MVP.

**Recommended Direction:**  
Leave as-is for MCP MVP. Address in a future CLI cleanup phase if needed.

**Files/Modules Involved:** `pyproc/cli.py`

**Backward Compatibility Risk:** Low.

**Implementation Risk:** Low.

---

## 6. MCP Server Design

### 6.1 Proposed Module Structure

```
pyproc/mcp/
    __init__.py        # Package marker, version export
    server.py          # MCP server entry point, transport setup
    tools.py           # Tool registration and handler functions
    schemas.py         # Tool input/output schemas (JSON Schema or typed dicts)
    resources.py       # MCP resource definitions
    prompts.py         # MCP prompt definitions (future phase)
    errors.py          # Error mapping: Python exceptions → MCP errors
```

### 6.2 MCP Server Entry Point

Added to `pyproject.toml`:
```toml
[project.scripts]
pyproc = "pyproc.cli:main"
pyproc-mcp = "pyproc.mcp.server:main"
```

The `pyproc-mcp` command starts an MCP server on stdio. Example:
```bash
pyproc-mcp
# or via Python:
python -m pyproc.mcp.server
```

### 6.3 SDK/Dependency Approach

Use the official `mcp` Python package (from `modelcontextprotocol` on PyPI):
```toml
[project.optional-dependencies]
test = ["pytest"]
mcp = ["mcp"]
```

Users install with: `pip install pyproc[mcp]`

The `mcp` SDK provides:
- `mcp.server.Server` — MCP server class
- `mcp.server.stdio.stdio_server()` — stdio transport
- `@server.list_tools()` — tool listing decorator
- `@server.call_tool()` — tool call handler decorator
- `@server.list_resources()` — resource listing decorator
- `@server.read_resource()` — resource read handler decorator
- `@server.list_prompts()` — prompt listing decorator
- `@server.get_prompt()` — prompt get handler decorator
- `mcp.types` — type definitions (Tool, TextContent, etc.)

### 6.4 Transport Mode

**Primary: stdio** — The MCP server runs as a subprocess, communicating with the MCP client via stdin/stdout JSON-RPC. This is the standard MCP transport and works with all major MCP clients (Claude Desktop, Continue, Cursor, etc.).

**Future: HTTP/SSE** — If requested, add an optional HTTP+SSE transport using `mcp.server.sse` or a lightweight ASGI wrapper. Not in MVP scope.

### 6.5 Configuration Approach

MCP server configuration via environment variables (no config file for MVP):

| Variable | Default | Description |
|---|---|---|
| `PYPROC_TIMEOUT` | `30` | HTTP request timeout in seconds |
| `PYPROC_RATE_LIMIT_DELAY` | `1.0` | Minimum seconds between requests |
| `PYPROC_LOG_LEVEL` | `INFO` | Logging level |
| `PYPROC_USER_AGENT` | `PyProc/{version}` | User-Agent header override |

MCP client configuration example:
```json
{
  "mcpServers": {
    "pyproc": {
      "command": "pyproc-mcp",
      "args": [],
      "env": {
        "PYPROC_TIMEOUT": "30"
      }
    }
  }
}
```

### 6.6 Logging Approach

- MCP server logs to stderr (stdio transport reserves stdout for JSON-RPC)
- Use Python's `logging` module with configurable level
- Log tool invocations (tool name, LPSE host, package ID) at INFO level
- Log HTTP errors and retries at WARNING level
- Never log full HTML page content or auth tokens

### 6.7 Error Handling Approach

Create an error mapper in `pyproc/mcp/errors.py`:

```python
def map_exception_to_mcp_error(exc: Exception) -> dict:
    """Map Python exceptions to MCP error responses."""
```

| Exception | MCP Error | User Message |
|---|---|---|
| `LpseServerExceptions` | Server error | "SPSE server returned an error: {details}" |
| `LpseHostExceptions` | Invalid params | "Invalid LPSE host: {host}" |
| `requests.exceptions.Timeout` | Timeout | "Request to SPSE timed out after {n}s" |
| `requests.exceptions.ConnectionError` | Connection error | "Could not connect to SPSE server" |
| `ValueError`, `TypeError` | Invalid params | "Invalid parameter: {details}" |
| Any other exception | Internal error | "An unexpected error occurred" |

### 6.8 Rate-Limit and Timeout Approach

- **Timeout**: Default 30s per HTTP request (configurable via env var, inherited from `Lpse` timeout)
- **Inter-request delay**: Minimum 1 second between tool invocations on the same `Lpse` instance
- **Retry**: The existing `backoff.on_exception` decorators on `Lpse.get_paket()` and detail methods already provide retry with Fibonacci backoff (max 3 tries)
- **No concurrent tool calls**: MCP stdio processes requests sequentially by default
- **Document in tool descriptions**: Each tool description notes approximate latency and rate limits

### 6.9 Cache Behavior

The MCP server does NOT use the CLI's SQLite cache (`CacheStore`). The CLI cache is a download-progress database, not a response cache.

For MCP:
- No persistent caching in MVP — each tool call makes a fresh HTTP request
- Future improvement: Add optional short-lived in-memory cache (TTL 60s) for identical requests within a session
- Document that data freshness depends on SPSE/Inaproc source availability

### 6.10 Tool Naming Convention

Use `snake_case` with a verb-noun pattern, consistent with MCP conventions:

```
search_tender_packages
search_non_tender_packages
get_tender_detail
get_non_tender_detail
get_tender_winner
get_non_tender_winner
get_tender_participants
get_non_tender_participants
get_tender_schedule
get_non_tender_schedule
get_procurement_categories
validate_lpse_host
```

### 6.11 Tool Description Style

Each tool description follows this pattern:
1. **What it does** — one sentence summary
2. **Inputs** — brief description of required parameters
3. **Outputs** — what data is returned
4. **Rate limits** — expected latency and throttling
5. **Data source note** — "Data sourced from public SPSE/Inaproc system"

Example:
```python
"""
Search for tender procurement packages on an LPSE host.

Searches the SPSE/Inaproc DataTables endpoint for tender packages matching
the given criteria (keyword, year, category). Returns a list of matching
packages with basic metadata (code, name, institution, status, HPS value).

Args:
    lpse_host: LPSE host identifier (e.g., 'kemenkeu', 'jakarta', 'sumbarprov')
    keyword: Search keyword to filter packages by name
    tahun_anggaran: Budget year filter (e.g., 2025)
    kategori: Procurement category filter
    start: Pagination offset (default 0)
    length: Number of results (default 20, max 100)

Returns:
    JSON object with packages list and total record count.

Rate limits: Minimum 1 second between requests. Each call takes 2-5 seconds.
Data sourced from public SPSE/Inaproc system. Not affiliated with LKPP or any government institution.
"""
```

---

## 7. MCP Tool Plan

| # | Tool Name | Purpose | Existing Method | Inputs | Output | MVP? | Notes |
|---|---|---|---|---|---|---|---|
| 1 | `search_tender_packages` | Search tender procurement packages | `Lpse.get_paket_tender()` | lpse_host, keyword?, tahun_anggaran?, kategori?, start?, length? | `{packages: [...], total: int}` | **Yes** | Core capability. Limit length to 100 max. |
| 2 | `search_non_tender_packages` | Search non-tender/direct procurement packages | `Lpse.get_paket_non_tender()` | lpse_host, keyword?, tahun_anggaran?, kategori?, start?, length? | `{packages: [...], total: int}` | **Yes** | Mirror of tender search for non-tender. |
| 3 | `get_tender_detail` | Get full tender package detail | `LpseDetil.get_all_detil()` + `todict()` | lpse_host, package_id | `{pengumuman, peserta, hasil, pemenang, jadwal, ...}` | **Yes** | Returns all detail sections. Most data-rich tool. |
| 4 | `get_non_tender_detail` | Get full non-tender package detail | `LpseDetilNonTender.get_all_detil()` + `todict()` | lpse_host, package_id | `{pengumuman, peserta, hasil, pemenang, jadwal, ...}` | **Yes** | Mirror of tender detail for non-tender. |
| 5 | `get_tender_winner` | Get tender winner information | `LpseDetil.get_pemenang()` | lpse_host, package_id | `{winners: [{nama, alamat, npwp, harga}]}` | **Phase 3** | Focused winner-only query. Useful for vendor analysis. |
| 6 | `get_non_tender_winner` | Get non-tender winner | `LpseDetilNonTender.get_pemenang()` | lpse_host, package_id | `{winners: [{nama, alamat, npwp, harga}]}` | **Phase 3** | Mirror for non-tender. |
| 7 | `get_tender_participants` | Get tender participants list | `LpseDetil.get_peserta()` | lpse_host, package_id | `{participants: [{nama, ...}]}` | **Phase 3** | Useful for competitive analysis. |
| 8 | `get_non_tender_participants` | Get non-tender participants | `LpseDetilNonTender.get_peserta()` | lpse_host, package_id | `{participants: [{nama, ...}]}` | **Phase 3** | Mirror for non-tender. |
| 9 | `get_tender_schedule` | Get tender timeline/schedule | `LpseDetil.get_jadwal()` | lpse_host, package_id | `{schedule: [{tahap, mulai, sampai}]}` | **Phase 3** | Timeline analysis for vendors. |
| 10 | `get_non_tender_schedule` | Get non-tender timeline | `LpseDetilNonTender.get_jadwal()` | lpse_host, package_id | `{schedule: [{tahap, mulai, sampai}]}` | **Phase 3** | Mirror for non-tender. |
| 11 | `get_procurement_categories` | List supported procurement categories | `JenisPengadaan` enum | none | `{categories: [{name, value}]}` | **MVP** | Static resource-like tool. No network call. |
| 12 | `validate_lpse_host` | Check if LPSE host is accessible | `Lpse.get_auth_token()` | lpse_host | `{valid: bool, url: str, message: str}` | **MVP** | Lightweight connectivity check. |
| 13 | `get_lpse_host_list` | Get known LPSE host list | `utils.download_host_json()` | none | `{hosts: [{name, url, ...}]}` | **Phase 3** | Useful for discovering available hosts. |

### 7.1 MVP Tool Details

**Tool 1: `search_tender_packages`**
- Required: `lpse_host` (str)
- Optional: `keyword` (str), `tahun_anggaran` (int), `kategori` (str enum), `start` (int, default 0), `length` (int, default 20, max 100), `nama_penyedia` (str)
- Validation: `lpse_host` must be non-empty, `kategori` must be valid enum member name, `length` clamped to 1-100
- Rate limit: 1s minimum delay
- Errors: Invalid host, SPSE server error, timeout, empty results (not an error, just empty list)
- Output shape:
```json
{
  "packages": [
    {
      "id_paket": "10080116000",
      "nama_paket": "Pengadaan Barang...",
      "instansi": "KEMENTERIAN KEUANGAN",
      "tahap": "Tender Sudah Selesai",
      "hps": 950000000.0,
      "tahun_anggaran": "2025"
    }
  ],
  "total": 150,
  "lpse_host": "kemenkeu",
  "lpse_url": "https://spse.inaproc.id/kemenkeu"
}
```

**Tool 2: `search_non_tender_packages`**
- Same as Tool 1 but calls `get_paket_non_tender()`
- Excludes `nama_penyedia` parameter (not supported by non-tender endpoint)

**Tool 3: `get_tender_detail`**
- Required: `lpse_host` (str), `package_id` (str/int)
- Validation: `lpse_host` non-empty, `package_id` numeric
- Rate limit: 2s minimum delay (detail pages are heavier to scrape)
- Errors: Package not found, SPSE error, timeout
- Output shape:
```json
{
  "package_id": "10080116000",
  "pengumuman": {
    "kode_tender": "10080116000",
    "nama_tender": "...",
    "instansi": "...",
    "nilai_pagu_paket": 1000000000.0,
    "nilai_hps_paket": 950000000.0,
    "tahun_anggaran": "2025",
    "lokasi_pekerjaan": ["Jakarta"],
    "label_paket": ["Pengadaan Barang"]
  },
  "peserta": [...],
  "hasil_evaluasi": [...],
  "pemenang": [...],
  "pemenang_berkontrak": [...],
  "jadwal": [...]
}
```

**Tool 4: `get_non_tender_detail`**
- Same as Tool 3 but calls `detil_paket_non_tender()`

**Tool 11: `get_procurement_categories`**
- No parameters
- No rate limit (static data)
- Output shape:
```json
{
  "categories": [
    {"name": "PENGADAAN_BARANG", "value": 0, "description": "Pengadaan Barang"},
    {"name": "JASA_KONSULTANSI_BADAN_USAHA_NON_KONSTRUKSI", "value": 1},
    ...
  ]
}
```

**Tool 12: `validate_lpse_host`**
- Required: `lpse_host` (str)
- Validation: Non-empty string
- Tries to fetch auth token from the host — if successful, host is valid
- Output shape:
```json
{
  "valid": true,
  "host": "kemenkeu",
  "url": "https://spse.inaproc.id/kemenkeu",
  "message": "LPSE host is accessible"
}
```

---

## 8. MCP Resources and Prompts Plan

### 8.1 Resources

| # | Resource Name | URI Pattern | Purpose | Content Type | MVP? |
|---|---|---|---|---|---|
| 1 | Procurement Categories | `pyproc://categories` | List all procurement category enums | JSON | **Yes** |
| 2 | Tool Usage Guide | `pyproc://docs/tools` | Markdown description of all tools | text/markdown | **Yes** |
| 3 | Output Schema Reference | `pyproc://docs/schemas` | JSON Schema for tool outputs | application/json | Phase 3 |
| 4 | LPSE Host Format Guide | `pyproc://docs/host-format` | How to construct LPSE host identifiers | text/markdown | Phase 3 |
| 5 | Responsible Use Policy | `pyproc://docs/responsible-use` | Usage guidelines and disclaimers | text/markdown | **Yes** |
| 6 | Cache Behavior | `pyproc://docs/cache` | Explanation of MCP cache behavior | text/markdown | Phase 3 |

### 8.2 Prompts

| # | Prompt Name | Purpose | Arguments | MVP? |
|---|---|---|---|---|
| 1 | `analyze_procurement_opportunity` | Guide LLM to analyze a tender for a vendor | `package_id`, `lpse_host` | Phase 3 |
| 2 | `summarize_tender_package` | Summarize a tender package for quick review | `package_id`, `lpse_host` | Phase 3 |
| 3 | `compare_tender_packages` | Compare multiple tenders by value, schedule, requirements | `package_ids` (list), `lpse_host` | Phase 3 |
| 4 | `vendor_research_checklist` | Generate a checklist for vendor bid preparation | `package_id`, `lpse_host` | Phase 3 |

Prompts are lower priority than tools. MVP focuses on tools only. Prompts are added in Phase 3 after the core tools are stable.

---

## 9. Rebranding Plan

### 9.1 Recommended Product/Display Name

Keep `pyproc` as the package name. Add a display/product name for MCP positioning:

**Product name:** `PyProc MCP`

**Tagline candidates (final selection in README rewrite):**
1. "Real-time Indonesian procurement data for LLM agents"
2. "Turn public SPSE/Inaproc data into MCP tools for AI agents"
3. "Connect AI agents to Indonesian procurement opportunities through MCP"

### 9.2 Package Name

**Keep `pyproc`.** The package name is established on PyPI, has existing users, and is referenced in documentation. Renaming would break existing installs and imports.

### 9.3 CLI Commands

| Command | Status | Notes |
|---|---|---|
| `pyproc` | **Keep** | Existing CLI entry point, unchanged |
| `pyproc-mcp` | **Add** | New MCP server entry point |

### 9.4 PyPI Metadata Changes

Update `pyproject.toml`:
```toml
[project]
name = "pyproc"  # unchanged
version = "0.3"  # bump to 0.3 for MCP release
description = "MCP tools for real-time Indonesian public procurement data from SPSE/Inaproc"
classifiers = [
    # Add:
    'Topic :: Scientific/Engineering :: Artificial Intelligence',
    'Framework :: MCP',
    # Keep existing classifiers
]
keywords = ["mcp", "procurement", "indonesia", "spse", "inaproc", "lpse", "llm", "ai-agent"]
```

### 9.5 Documentation Changes

| File | Action |
|---|---|
| `README.md` | Full rewrite: MCP-first positioning, English language |
| `docs/mcp.md` | New: Detailed MCP usage guide |
| `docs/examples.md` | New: LLM workflow examples |
| `docs/assets/README_ASSET_PROMPTS.md` | New: Image generation prompts for branding |
| `CHANGELOG.md` | Add v0.3 entry with MCP support |

### 9.6 Migration Message for Existing Users

No migration needed. Existing library and CLI behavior is unchanged. The `pyproc-mcp` command is additive. The only visible change is the README rewrite.

### 9.7 Versioning Recommendation

Bump to `0.3` for the MCP release. This is a minor version bump per semantic versioning (new feature, backward-compatible). After MCP stabilization, consider `1.0` when the API surface is considered stable.

---

## 10. README Rebrand and Marketing Plan

### 10.1 New Positioning

> **PyProc MCP** — MCP tools for LLM agents to access real-time or near real-time public procurement data in Indonesia.

PyProc MCP turns public SPSE/Inaproc procurement data into MCP tools that can be used by LLM clients (Claude Desktop, Continue, Cursor), AI agents, automation workflows, Python scripts, and command-line users.

### 10.2 Recommended Tagline

> **Give your LLM real-time access to Indonesian procurement data.**

### 10.3 Hero Section Copy

```markdown
## Real-time Indonesian procurement data for LLM agents

PyProc MCP connects AI agents to Indonesia's public e-procurement system (SPSE/Inaproc)
through the Model Context Protocol (MCP). Search tender and non-tender packages, fetch
detailed procurement data, retrieve winners and participants, and analyze procurement
opportunities — all through MCP-compatible LLM clients.

**Why PyProc MCP?**
- **LLM-native access** — MCP tools let AI agents search and analyze procurement data directly
- **Real-time data** — Fetches live data from SPSE/Inaproc, not stale snapshots
- **Comprehensive** — Full package details: announcements, participants, evaluation results, winners, schedules
- **Lightweight** — Single command: `pyproc-mcp`. Works with Claude Desktop, Continue, Cursor, and any MCP client
- **Multi-interface** — Use as MCP server, Python library, or CLI tool — same codebase, no lock-in
- **Respectful defaults** — Conservative rate limiting, caching guidance, responsible-use policy built in
```

### 10.4 README Structure

```markdown
# PyProc MCP

<p align="center">
  <img src="docs/assets/pyproc-mcp-banner.png" alt="PyProc MCP banner" width="800">
</p>

<p align="center">
  <strong>Real-time Indonesian procurement data for LLM agents</strong>
</p>

[Badges: PyPI version, Python versions, License, MCP compatible]

---

## Why PyProc MCP?
[Value proposition paragraphs]

## What You Can Do
[Marketing-oriented capability bullets]

## Quick Start
[Install, run MCP server, configure MCP client — 3 steps]

## Usage Modes

### 1. MCP Server for LLM Clients (Recommended)
- Installation: `pip install pyproc[mcp]`
- Running: `pyproc-mcp`
- MCP client configuration example (JSON)

### 2. Python Library
- Import: `from pyproc import Lpse`
- Code examples (search, detail)

### 3. CLI Tool
- Command: `pyproc kemenkeu --keyword "mobil dinas" --output json`
- Full argument reference

## MCP Tools
[Table of all tools with descriptions]

## Example LLM Workflows
[3-4 concrete examples]

## Installation
[All installation methods]

## Configuration
[Environment variables, defaults]

## Cache and Rate Limiting
[Transparent about behavior]

## Responsible Use and Disclaimer
[Non-affiliation, respectful use, data accuracy caveats]

## Development
[Setup, test commands, contributing]

## Roadmap
[What's next]

## License
[MIT]
```

### 10.5 MCP-First Documentation Section

```markdown
## MCP Server for LLM Clients

### What is MCP?

The [Model Context Protocol (MCP)](https://modelcontextprotocol.io) lets LLM applications
discover and use external tools through a standardized interface. PyProc MCP exposes
Indonesian procurement data as MCP tools.

### Quick Start

```bash
pip install pyproc[mcp]
pyproc-mcp
```

### MCP Client Configuration

Add to your MCP client's configuration file:

```json
{
  "mcpServers": {
    "pyproc": {
      "command": "pyproc-mcp",
      "args": [],
      "env": {
        "PYPROC_TIMEOUT": "30"
      }
    }
  }
}
```

Restart your MCP client. PyProc MCP tools will appear in the tool list.
```

### 10.6 Marketing-Oriented Capability List

```markdown
## Procurement Intelligence Capabilities

- **Discover opportunities** — Search tender and non-tender packages across any LPSE host
- **Deep-dive analysis** — Retrieve full package details: requirements, HPS value, location, schedule
- **Competitive intelligence** — See who's bidding, who's winning, and at what price
- **Timeline tracking** — Monitor procurement schedules from announcement to contract
- **Vendor research** — Find which companies win which types of contracts where
- **AI-powered insights** — Let LLMs analyze procurement patterns, compare packages, and generate reports
- **Export and automate** — Use the Python library or CLI to build automated procurement monitoring pipelines
```

### 10.7 Responsible-Use Disclaimer

```markdown
## Responsible Use and Disclaimer

**This project is not affiliated with LKPP, LPSE, SPSE, Inaproc, or any Indonesian government institution.**

PyProc MCP accesses publicly available procurement data from SPSE/Inaproc systems. Users are responsible for:

- **Respectful usage** — Do not overwhelm SPSE servers with excessive requests. The tool includes built-in rate limiting.
- **Data accuracy** — Procurement data may be incomplete, delayed, or changed by source systems. LLM-generated analysis should be verified against official sources at [spse.inaproc.id](https://spse.inaproc.id).
- **Compliance** — Ensure your use complies with applicable laws and regulations in Indonesia.
- **No disruption** — Do not use this tool to disrupt public e-procurement services.

> PyProc ada karena SPSE ada, jadi gunakanlah dengan bijak dan secukupnya.
> *(PyProc exists because SPSE exists — use it wisely and sparingly.)*
```

### 10.8 Logo and Header Illustration Concept

**Logo concept:**
A minimal geometric mark combining:
- A document/page icon (representing procurement packages)
- Small connected nodes (representing MCP tools / AI agent access)
- A subtle red-and-white accent (Indonesia flag colors, used sparingly as a thin line or dot)
- Clean sans-serif typography

**Banner concept:**
- Wide GitHub README header (3:1 or 4:1 aspect ratio)
- Left side: Logo mark
- Center: "PyProc MCP" in bold modern type
- Right side: Abstract data-flow lines connecting document icons to tool nodes
- Color palette: Deep navy/slate (#1a2332) background, electric blue (#3b82f6) accents, red (#ce1126) and white (#ffffff) subtle Indonesia accent

**Visual constraints:**
- No government emblems, seals, official-looking marks, or garuda symbols
- No Indonesian coat of arms
- No text implying "official" or "government"
- No fake UI screenshots with real government data
- No LKPP/LPSE/SPSE/Inaproc logos

### 10.9 Exact Image Generation Prompts

**Banner prompt (to include in `docs/assets/README_ASSET_PROMPTS.md`):**

```
Create a modern open-source software banner for "PyProc MCP", an MCP tool server
for Indonesian public procurement data.

Visual concept:
A clean AI-tooling dashboard symbol combined with procurement/search/data elements.
Include abstract nodes representing LLM tools, a subtle document/package icon, and a
small Indonesian-inspired red-white accent. The visual should feel trustworthy,
technical, transparent, and modern.

Style:
Modern developer-tool branding, minimal, professional, open-source, clean vector/3D
hybrid, suitable for a GitHub README header. Avoid government emblems, official seals,
or anything that implies affiliation with LKPP/LPSE/SPSE/Inaproc or any government
institution.

Colors:
Deep navy or slate base (#1a2332), electric blue accents (#3b82f6) for AI/tooling,
red (#ce1126) and white (#ffffff) accent inspired by Indonesia, soft neutral backgrounds.

Composition:
Wide README banner, centered logo mark and "PyProc MCP" product name, with abstract
data-flow lines connecting procurement documents to LLM/MCP tool nodes.

Text: "PyProc MCP" in clean sans-serif, with optional small tagline
"Real-time Indonesian procurement data for LLM agents"

Output specifications:
- File: docs/assets/pyproc-mcp-banner.png
- Aspect ratio 3:1 or 4:1
- High resolution (2400x800 or similar)
- Clean readable at GitHub README width (~800px)
- No fake UI text with specific data
- No official government symbols or emblems
```

**Logo prompt:**

```
Create a square logo icon for "PyProc MCP".

Visual concept:
A minimal procurement document/search icon connected to small MCP-style tool nodes,
suggesting AI agents accessing public procurement data. Include a subtle Indonesia
red-white accent without using official government symbols.

Style:
Modern open-source developer tool logo, simple geometric mark, clean, professional,
scalable, works as GitHub avatar and package icon.

Colors:
Deep navy/slate, blue AI accent, small red-white Indonesia accent.
Transparent background.

Output specifications:
- File: docs/assets/logo.png
- Aspect ratio 1:1
- Transparent background
- High resolution (1024x1024 or similar)
- No text inside the logo mark
- No government emblems
```

### 10.10 Asset File Paths

```
docs/assets/
    README_ASSET_PROMPTS.md   # The prompts above, documented for future regeneration
    logo.png                  # Square logo (generated later from prompt)
    pyproc-mcp-banner.png     # Wide README banner (generated later from prompt)
```

### 10.11 README Language Recommendation

**English-first with bilingual disclaimers.** The primary audience for MCP tools is the global LLM/AI developer community, which operates in English. However, since the data is Indonesian and many users are Indonesian, include:

- English README for all technical documentation
- Indonesian responsible-use disclaimer (preserving the original `DISCLAIMER` message)
- Bilingual tool descriptions in the MCP tools themselves (the SPSE data is in Indonesian, so tool output fields should preserve Indonesian names with English descriptions)

---

## 11. Security and Responsible-Use Plan

### 11.1 Rate Limiting

- **Inter-request delay**: Minimum 1 second between consecutive tool invocations on the same Lpse instance
- **Detail requests**: 2 second delay for detail page scraping (heavier operations)
- **No concurrent requests**: MCP stdio processes sequentially by default
- **Document limits**: Tool descriptions note rate limits so LLMs can plan accordingly

### 11.2 Conservative Defaults

- `timeout=30` seconds (inherited from Lpse, matching CLI default)
- `length` default 20, max 100 for search tools
- No auto-pagination — LLM must explicitly request next page

### 11.3 Cache Usage

- No persistent cache in MCP MVP
- Future: Optional short-lived in-memory cache (60s TTL) for identical requests
- Document that the CLI's SQLite cache is unrelated to MCP operation

### 11.4 Disclaimer

- Emphatic non-affiliation statement in README, MCP resource `pyproc://docs/responsible-use`, and every tool description
- "Not affiliated with LKPP, LPSE, SPSE, Inaproc, or any Indonesian government institution"
- "Data sourced from public SPSE/Inaproc system"

### 11.5 Prompt Injection Risk

- SPSE HTML pages contain user-generated content (provider names, package descriptions) that could theoretically contain malicious text
- MCP tools return parsed/extracted text fields, not raw HTML
- Risk is low (SPSE is a controlled government system) but documented
- MCP tool descriptions note: "Data sourced from public SPSE pages. Verify analysis against official sources."

### 11.6 Output Sanitization

- Truncate text fields longer than 1000 characters in MCP output
- Strip null bytes and control characters from string fields
- Redact NPWP (tax ID) values where they appear (replace middle digits with asterisks, matching existing test fixture patterns like `0*.6**.8**.*-*27.**0`)

### 11.7 Safe Logging

- Log to stderr only (stdio transport)
- Log tool name, LPSE host, package ID at INFO level
- Never log auth tokens, full HTML content, or NPWP values
- Use `logging` module with configurable level via `PYPROC_LOG_LEVEL` env var

### 11.8 Safe Error Messages

- Error messages describe what went wrong without exposing internal state
- SPSE server error codes are included (they are not sensitive)
- Stack traces are logged at DEBUG level only, never returned to MCP client

### 11.9 Read-Only Behavior

- All MCP tools are read-only
- No tool modifies SPSE data or submits forms
- No tool requires authentication beyond the public CSRF token exchange
- `clear_or_refresh_cache` tool is NOT included in MVP (no persistent cache to clear)

---

## 12. Implementation Roadmap

### Phase 0 — Safety Baseline (pre-MCP, can be done now)

**Goal:** Ensure existing behavior is well-tested before adding MCP layer.

**Tasks:**
- Run existing test suite, verify all tests pass
- Verify `from pyproc import Lpse` works
- Verify `pyproc --help` works
- Verify `pyproc daftarlpse` and `pyproc daftarhost` work
- Document current test coverage gaps

**No code changes.** This is a verification phase.

### Phase 1 — Minimal Structure Preparation

**Goal:** Add MCP dependency and module scaffolding without touching existing code.

**Tasks:**
- Add `mcp` optional dependency to `pyproject.toml`
- Create `pyproc/mcp/` package with `__init__.py`
- Create empty module files: `server.py`, `tools.py`, `schemas.py`, `resources.py`, `errors.py`
- Add `pyproc-mcp` entry point to `pyproject.toml`
- Verify `pip install -e ".[mcp]"` works
- Verify existing `pyproc` CLI entry point still works
- Verify existing imports still work

### Phase 2 — MCP MVP

**Goal:** Working MCP server with core tools.

**Tasks:**
1. Implement `pyproc/mcp/server.py` — MCP server setup with stdio transport
2. Implement `pyproc/mcp/schemas.py` — Input/output type definitions for MVP tools
3. Implement `pyproc/mcp/tools.py` — MVP tool handlers (tools 1-4, 11-12 from Section 7)
4. Implement `pyproc/mcp/errors.py` — Exception-to-MCP-error mapping
5. Implement `pyproc/mcp/resources.py` — MVP resources (categories, docs, responsible-use)
6. Add tests for MCP server startup and tool registration
7. Add tests with mocked HTTP responses for each MVP tool
8. Test manually with a real MCP client (Claude Desktop or mcp-cli)

### Phase 3 — MCP Tool Expansion

**Goal:** Add winner, participant, schedule tools, and prompts.

**Tasks:**
1. Add tools 5-10 (winner, participant, schedule for both tender and non-tender)
2. Add tool 13 (LPSE host list)
3. Add output schema reference resource
4. Add LPSE host format guide resource
5. Implement prompts (`analyze_procurement_opportunity`, etc.)
6. Add tests for new tools and prompts

### Phase 4 — README Rebrand, Marketing, and Documentation

**Goal:** Complete project rebrand with MCP-first positioning.

**Tasks:**
1. Rewrite `README.md` with MCP-first structure
2. Create `docs/assets/README_ASSET_PROMPTS.md` with image generation prompts
3. Create `docs/mcp.md` with detailed MCP usage guide
4. Create `docs/examples.md` with LLM workflow examples
5. Update `pyproject.toml` metadata (description, classifiers, keywords)
6. Update `CHANGELOG.md` with v0.3 entry
7. Remove or update old `plan/API_AND_CLI_WRAPPER_OPTIMIZATION_PLAN.md` (or keep as historical reference)

### Phase 5 — Optional Internal Refactor

**Goal:** Improve codebase structure after MCP MVP is stable.

**Tasks (only if justified):**
- Split `lpse.py` if it grows with MCP-related additions
- Add more type hints
- Improve transport abstraction
- Extract shared response normalization

**Do not do this before Phase 2-4 are complete.**

---

## 13. Implementation Tasks for Small Agents

### Task 1: Add MCP SDK Dependency and Module Scaffolding

**Goal:** Add the MCP SDK as an optional dependency and create the empty MCP package structure.

**Context:** The MCP layer needs a home. This task creates the package scaffolding without implementing any MCP logic. Existing behavior must remain unchanged.

**Scope:** `pyproject.toml`, new `pyproc/mcp/` directory with empty `__init__.py`

**Implementation Instructions:**
1. Add `mcp` to `[project.optional-dependencies]` in `pyproject.toml`:
   ```toml
   [project.optional-dependencies]
   test = ["pytest"]
   mcp = ["mcp"]
   ```
2. Create `pyproc/mcp/__init__.py` with a docstring and version reference
3. Create empty placeholder files: `pyproc/mcp/server.py`, `pyproc/mcp/tools.py`, `pyproc/mcp/schemas.py`, `pyproc/mcp/resources.py`, `pyproc/mcp/errors.py`
4. Add `pyproc-mcp` entry point to `[project.scripts]`:
   ```toml
   pyproc-mcp = "pyproc.mcp.server:main"
   ```
5. Update `pyproject.toml` description and classifiers for MCP positioning:
   - description: "MCP tools for real-time Indonesian public procurement data from SPSE/Inaproc"
   - Add classifier: `'Framework :: MCP'`
   - Add keywords: `["mcp", "procurement", "indonesia", "spse", "inaproc", "lpse", "llm"]`
6. Version bump to `0.3`

**Do Not Change:**
- `pyproc/__init__.py` public exports
- `pyproc/lpse.py`, `pyproc/cli.py`, or any existing module
- `pyproc` CLI entry point
- Test files

**Acceptance Criteria:**
- [ ] `pip install -e ".[mcp]"` works and installs `mcp` package
- [ ] `pip install -e ".[test]"` still installs pytest
- [ ] `pip install -e .` does NOT install mcp (it's optional)
- [ ] `pyproc` CLI entry point still works: `pyproc --help`
- [ ] `from pyproc import Lpse` still works
- [ ] `pyproc/mcp/` directory exists with all placeholder files
- [ ] All existing tests pass

**Suggested Tests:** Run existing test suite: `python -m pytest tests/`

**Risk:** Low

**Dependencies:** None

---

### Task 2: Implement MCP Server Core (Entry Point and Transport)

**Goal:** Create a working MCP server that starts up, registers tools, and communicates via stdio.

**Context:** The MCP server must use the official `mcp` Python package and stdio transport. This task sets up the server framework without implementing actual tool logic.

**Scope:** `pyproc/mcp/server.py`, `pyproc/mcp/errors.py`

**Implementation Instructions:**
1. Implement `pyproc/mcp/server.py`:
   - Create an MCP `Server` instance with name "pyproc"
   - Configure stdio transport using `stdio_server()`
   - Set up tool listing handler (`@server.list_tools()`)
   - Set up tool call handler (`@server.call_tool()`)
   - Set up resource listing handler (`@server.list_resources()`)
   - Set up resource read handler (`@server.read_resource()`)
   - Create a `main()` function that reads env vars for config and runs the server
   - Log startup info and configuration to stderr
2. Implement `pyproc/mcp/errors.py`:
   - `map_exception_to_mcp_error()` function
   - Handle: `LpseServerExceptions`, `requests.exceptions.Timeout`, `requests.exceptions.ConnectionError`, `ValueError`, generic fallback
   - Each returns an MCP-compatible error message string
3. Register one placeholder tool (e.g., `get_procurement_categories`) to verify the wiring works

**Do Not Change:**
- Any existing module outside `pyproc/mcp/`
- `pyproc` CLI entry point
- `Lpse` class

**Acceptance Criteria:**
- [ ] `pyproc-mcp` command starts the server (can test by piping a JSON-RPC init message)
- [ ] Server responds to `initialize` and `tools/list` requests
- [ ] At least one tool is registered and callable
- [ ] Server logs to stderr
- [ ] Server exits cleanly on EOF (stdin close)

**Suggested Tests:**
- `test_mcp_server_startup` — verify server instance creation
- `test_mcp_tool_listing` — verify tools/list returns expected tools
- `test_mcp_tool_call_placeholder` — verify placeholder tool returns expected response
- `test_mcp_error_mapping` — verify exception-to-error conversion

**Risk:** Medium

**Dependencies:** Task 1

---

### Task 3: Implement MCP Tool Schemas

**Goal:** Define input validation and output normalization schemas for all MVP MCP tools.

**Context:** MCP tools need clean input validation and consistent output formatting. This task defines the schemas without implementing tool handlers.

**Scope:** `pyproc/mcp/schemas.py`

**Implementation Instructions:**
1. Define input validation functions for each MVP tool (tools 1-4, 11-12):
   - `validate_search_params(lpse_host, keyword, tahun_anggaran, kategori, start, length)` — validates search tool inputs, clamps length to 1-100
   - `validate_detail_params(lpse_host, package_id)` — validates detail tool inputs
   - `validate_host_param(lpse_host)` — validates host-only inputs
2. Define output normalization functions:
   - `normalize_search_results(raw_data, lpse_host)` — transforms raw DataTables response into structured output with descriptive field names
   - `normalize_detail_results(detail_dict)` — transforms `todict()` output into MCP-friendly format
   - `normalize_categories()` — transforms `JenisPengadaan` enum into list of dicts
   - `normalize_host_validation(is_valid, host, url)` — formats validation result
3. Define field name mappings (SPSE field names → human-readable field names)
4. Add sanitization: truncate long fields, strip control characters

**Do Not Change:**
- Any existing module
- Library return types

**Acceptance Criteria:**
- [ ] All validation functions reject invalid inputs with clear error messages
- [ ] All normalization functions produce consistent JSON-serializable output
- [ ] Search `length` is clamped to 1-100
- [ ] Category validation matches `JenisPengadaan` enum members
- [ ] Long text fields are truncated at 1000 characters

**Suggested Tests:**
- `test_validate_search_params_valid` — valid params pass
- `test_validate_search_params_invalid_host` — empty host rejected
- `test_validate_search_params_length_clamped` — length > 100 → 100
- `test_validate_search_params_invalid_kategori` — bad category name rejected
- `test_normalize_search_results` — raw data → structured output
- `test_normalize_detail_results` — todict output → MCP format
- `test_normalize_categories` — enum → list of dicts
- `test_sanitize_long_text` — long fields truncated

**Risk:** Low

**Dependencies:** Task 1

---

### Task 4: Implement MVP MCP Tools (Search and Detail)

**Goal:** Implement MCP tool handlers for search and detail retrieval — the core MVP tools.

**Context:** These are the most important tools. They call `Lpse` methods directly and normalize output via the schemas from Task 3.

**Scope:** `pyproc/mcp/tools.py`, `pyproc/mcp/server.py` (tool registration updates)

**Implementation Instructions:**
1. Implement `handle_search_tender_packages(params)`:
   - Create `Lpse(lpse_host, timeout=...)` instance
   - Call `lpse.get_paket_tender()` with validated params
   - Normalize output via `normalize_search_results()`
   - Return as MCP `TextContent` with JSON
2. Implement `handle_search_non_tender_packages(params)`:
   - Same pattern, calls `lpse.get_paket_non_tender()`
3. Implement `handle_get_tender_detail(params)`:
   - Create `Lpse(lpse_host)` instance
   - Call `lpse.detil_paket_tender(package_id).get_all_detil()`
   - Call `.todict()` and normalize
   - Return structured detail JSON
4. Implement `handle_get_non_tender_detail(params)`:
   - Same pattern, calls `detil_paket_non_tender()`
5. Implement `handle_get_procurement_categories()`:
   - Return `JenisPengadaan` enum as list of dicts
6. Implement `handle_validate_lpse_host(params)`:
   - Try `Lpse(lpse_host).get_auth_token()`
   - Return validation result
7. Add rate limiting: `time.sleep(1)` minimum between tool calls (track last call time)
8. Add error handling: wrap each handler in try/except, map exceptions via `map_exception_to_mcp_error()`
9. Register all tools in `server.py`'s tool listing handler

**Do Not Change:**
- `pyproc/lpse.py` — only call its public methods
- `pyproc/cli.py`
- `pyproc/cache.py`
- Any existing public API

**Acceptance Criteria:**
- [ ] All 6 MVP tools are registered and callable
- [ ] `search_tender_packages` returns structured package list
- [ ] `search_non_tender_packages` returns structured package list
- [ ] `get_tender_detail` returns full detail JSON
- [ ] `get_non_tender_detail` returns full detail JSON
- [ ] `get_procurement_categories` returns category list (no network)
- [ ] `validate_lpse_host` returns validation result
- [ ] Rate limiting enforces minimum 1s delay
- [ ] Errors return user-friendly messages
- [ ] Tests use mocked HTTP responses, never live SPSE

**Suggested Tests:**
- `test_search_tender_packages_mocked` — mock Lpse, verify output structure
- `test_search_non_tender_packages_mocked` — mock Lpse, verify output
- `test_get_tender_detail_mocked` — mock detail fetch, verify normalized output
- `test_get_non_tender_detail_mocked` — mock detail fetch, verify normalized output
- `test_get_procurement_categories` — verify all 6 categories returned
- `test_validate_lpse_host_valid` — mock successful auth token
- `test_validate_lpse_host_invalid` — mock connection error
- `test_tool_error_handling` — verify errors mapped correctly
- `test_tool_rate_limiting` — verify delay enforced

**Risk:** Medium

**Dependencies:** Tasks 2, 3

---

### Task 5: Implement MVP MCP Resources

**Goal:** Add MCP resources for procurement categories, tool docs, and responsible-use policy.

**Context:** Resources provide read-only reference data to LLM clients. These are simple and require no network access.

**Scope:** `pyproc/mcp/resources.py`

**Implementation Instructions:**
1. Implement `get_categories_resource()`:
   - URI: `pyproc://categories`
   - Returns `JenisPengadaan` enum as JSON with descriptions
2. Implement `get_tool_docs_resource()`:
   - URI: `pyproc://docs/tools`
   - Returns markdown description of all available MCP tools
3. Implement `get_responsible_use_resource()`:
   - URI: `pyproc://docs/responsible-use`
   - Returns markdown text with non-affiliation disclaimer and usage guidelines
4. Register all resources in `server.py`'s resource listing handler

**Do Not Change:** Any existing module.

**Acceptance Criteria:**
- [ ] 3 resources are registered
- [ ] Resources return correct content types (JSON or text/markdown)
- [ ] Responsible-use resource includes non-affiliation disclaimer
- [ ] Tool docs resource lists all MVP tools with descriptions

**Suggested Tests:**
- `test_list_resources` — verify 3 resources listed
- `test_read_categories_resource` — verify JSON structure
- `test_read_tool_docs_resource` — verify markdown content
- `test_read_responsible_use_resource` — verify disclaimer text

**Risk:** Low

**Dependencies:** Task 2, 4

---

### Task 6: Rewrite README as MCP-First Project Page

**Goal:** Rewrite `README.md` so PyProc is positioned primarily as an MCP tool server for LLM access to Indonesian procurement data while preserving documentation for existing Python library and CLI users.

**Context:** The project is being rebranded from a Python/CLI SPSE wrapper into an MCP-first procurement intelligence tool for LLM agents. Existing users must still find library and CLI documentation.

**Scope:** `README.md`, optional `docs/mcp.md`, optional `docs/examples.md`

**Implementation Instructions:**
1. Read the current `README.md` thoroughly
2. Preserve important installation, CLI, library usage, and disclaimer information
3. Rewrite the top section with MCP-first positioning (use hero copy from Section 10.3)
4. Add MCP server usage instructions (install, run, configure client)
5. Add MCP client configuration example (JSON)
6. Add MCP tools table with descriptions
7. Add example LLM workflows (3-4 concrete examples)
8. Preserve existing Python library usage section (update code examples if needed)
9. Preserve existing CLI usage section (update if needed)
10. Add responsible-use and non-affiliation disclaimer (use text from Section 10.7)
11. Add "Usage Modes" section clearly showing MCP, Python library, and CLI as three options
12. Ensure all claims are accurate and not overstated
13. Keep existing Indonesian disclaimer text alongside English version

**Do Not Change:**
- Existing Python package behavior
- Existing CLI behavior
- Existing public API
- Existing license

**Acceptance Criteria:**
- [ ] README clearly presents PyProc as MCP-first
- [ ] Existing library and CLI usage remain documented
- [ ] README includes responsible-use disclaimer in English and Indonesian
- [ ] README includes MCP quick start (3 steps)
- [ ] README includes example MCP client config (JSON)
- [ ] README includes marketing-quality hero copy
- [ ] README does not imply official affiliation with LKPP, LPSE, SPSE, Inaproc, or any government institution
- [ ] All commands in README match actual entry points
- [ ] Links are valid

**Suggested Tests:**
- Verify `pyproc-mcp` command referenced in README exists
- Verify MCP client config JSON is valid
- Verify markdown renders correctly (check with a markdown previewer)
- Verify all links are valid

**Risk:** Medium

**Dependencies:** Tasks 1-5 should be planned/completed before finalizing command examples in README

---

### Task 7: Create README Branding Asset Prompts

**Goal:** Create a clear plan and prompts for README logo/header assets.

**Context:** The project needs visual branding. This task creates the prompts and documentation — it does NOT generate the actual images.

**Scope:** New files: `docs/assets/README_ASSET_PROMPTS.md`, `docs/assets/` directory

**Implementation Instructions:**
1. Create `docs/assets/` directory
2. Create `docs/assets/README_ASSET_PROMPTS.md` with:
   - Banner generation prompt (use prompt from Section 10.9)
   - Square logo generation prompt (use prompt from Section 10.9)
   - Recommended file names: `pyproc-mcp-banner.png`, `logo.png`
   - Aspect ratios: banner 3:1 or 4:1, logo 1:1
   - Transparency requirements: logo needs transparent background, banner does not
   - Visual constraints: no government emblems, no official seals, no garuda
   - Instructions for how to reference assets from README
   - Note that images should be generated separately using an image generation tool
3. Add placeholder references in README (commented out or with "coming soon" alt text)

**Do Not Change:**
- README image references (add references, don't break existing ones)
- Project package code
- CLI or library behavior

**Acceptance Criteria:**
- [ ] `docs/assets/README_ASSET_PROMPTS.md` exists with both prompts
- [ ] File paths are documented
- [ ] Visual constraints include explicit prohibition of government symbols
- [ ] Aspect ratios and transparency requirements are specified
- [ ] Prompts are ready to use with image generation tools

**Suggested Tests:**
- Verify markdown renders correctly
- Verify asset file paths are consistent with README references

**Risk:** Low

**Dependencies:** None

---

### Task 8: Write MCP-Specific Tests

**Goal:** Comprehensive test coverage for all MCP components.

**Context:** The MCP layer needs tests that verify correct behavior without hitting real SPSE endpoints.

**Scope:** New test files: `tests/test_mcp_tools.py`, `tests/test_mcp_server.py`, `tests/test_mcp_schemas.py`

**Implementation Instructions:**
1. Create `tests/test_mcp_schemas.py`:
   - Test all validation functions with valid and invalid inputs
   - Test all normalization functions with fixture data
   - Test sanitization functions
2. Create `tests/test_mcp_tools.py`:
   - Mock `Lpse` class methods using `unittest.mock.patch`
   - Test each tool handler with mocked responses
   - Test error cases (SPSE error, timeout, connection error)
   - Test rate limiting behavior
   - Use existing fixtures from `tests/fixtures/` where applicable
3. Create `tests/test_mcp_server.py`:
   - Test server startup and tool/resource registration
   - Test tool listing returns correct tools
   - Test resource listing returns correct resources
   - Test that server can handle a tool call end-to-end (mocked HTTP)

**Do Not Change:**
- Existing test files
- Production code (tests only)

**Acceptance Criteria:**
- [ ] All MCP tests pass without network access
- [ ] Tests cover all 6 MVP tools
- [ ] Tests cover error handling for each tool
- [ ] Tests cover schema validation
- [ ] Tests use mocked HTTP responses
- [ ] `python -m pytest tests/ -v` passes all tests (unit + MCP)

**Suggested Tests:** Run with `python -m pytest tests/test_mcp_*.py -v`

**Risk:** Low

**Dependencies:** Tasks 2, 3, 4, 5

---

## 14. Proposed File Structure

### Target Structure After MCP Implementation

```text
pyproc/
    __init__.py                # Existing — exports Lpse, JenisPengadaan, __version__
    lpse.py                    # Existing — unchanged, Lpse class and HTML parsers
    cli.py                     # Existing — unchanged, CLI downloader and main()
    cache.py                   # Existing — unchanged, CacheStore for SQLite
    utils.py                   # Existing — unchanged, token parsing, host list
    exceptions.py              # Existing — unchanged, exception classes
    text.py                    # Existing — unchanged, CLI UI strings

    mcp/                       # NEW — MCP server adapter layer
        __init__.py            # Package marker
        server.py              # MCP server entry point, transport setup
        tools.py               # Tool handler functions
        schemas.py             # Input validation and output normalization
        resources.py           # MCP resource definitions
        prompts.py             # MCP prompt definitions (Phase 3)
        errors.py              # Exception-to-MCP-error mapping

docs/
    mcp.md                     # NEW — Detailed MCP usage guide
    examples.md                # NEW — LLM workflow examples
    assets/
        README_ASSET_PROMPTS.md  # NEW — Image generation prompts
        logo.png               # Future — Generated from prompt
        pyproc-mcp-banner.png  # Future — Generated from prompt

tests/
    __init__.py
    test_lpse.py               # Existing — live integration tests
    test_lpse_unit.py          # Existing — mocked unit tests
    test_cli_unit.py           # Existing — mocked CLI tests
    test_cache.py              # Existing — CacheStore tests
    test_downloader.py         # Existing — live integration tests
    test_mcp_server.py         # NEW — MCP server tests
    test_mcp_tools.py          # NEW — MCP tool tests
    test_mcp_schemas.py        # NEW — Schema validation tests
    fixtures/                  # Existing — HTML/JSON response fixtures
    supporting_files/          # Existing — test input files

pyproject.toml                 # Updated — MCP dependency, pyproc-mcp entry point
README.md                      # Rewritten — MCP-first positioning
CHANGELOG.md                   # Updated — v0.3 MCP entry
```

### What Should Be Added Now
- `pyproc/mcp/` package and all its modules
- New test files for MCP
- New documentation files

### What Should NOT Be Moved Yet
- Do not split `lpse.py` — it works fine as-is and MCP tools call it as a client
- Do not split `cli.py` — it's the CLI adapter, separate from MCP
- Do not move `cache.py` — it's stable and used only by CLI
- Do not rename any existing module

### How to Avoid Breaking Imports
- `pyproc/__init__.py` continues to export `Lpse` and `JenisPengadaan` from `lpse.py`
- MCP modules import from `pyproc.lpse`, never the reverse
- CLI modules import from `pyproc` as before
- No circular imports possible because MCP is a leaf module

---

## 15. Testing Plan

### 15.1 Unit Tests

| Test File | What It Tests | Mock Strategy |
|---|---|---|
| `test_mcp_schemas.py` | Input validation, output normalization, sanitization | No network — pure logic |
| `test_mcp_server.py` | Server startup, tool registration, resource registration | Mock MCP transport |
| `test_mcp_tools.py` | Tool handlers with mocked Lpse responses | `unittest.mock.patch` on `Lpse` methods |
| `test_lpse_unit.py` | (Existing) Lpse API with mocked HTTP | `unittest.mock.patch` on `requests.Session` |
| `test_cli_unit.py` | (Existing) CLI components | Temp SQLite files |
| `test_cache.py` | (Existing) CacheStore CRUD | Temp SQLite files |

### 15.2 Integration Tests (Optional, Network-Dependent)

| Test File | What It Tests | Notes |
|---|---|---|
| `test_lpse.py` | (Existing) Live Lpse API calls | Mark with `@pytest.mark.integration` |
| `test_downloader.py` | (Existing) Live download pipeline | Mark with `@pytest.mark.integration` |

### 15.3 Commands to Run Tests

```bash
# Run all unit tests (no network required)
python -m pytest tests/ --ignore=tests/test_lpse.py --ignore=tests/test_downloader.py -v

# Run only MCP tests
python -m pytest tests/test_mcp_*.py -v

# Run all tests including integration (requires network)
python -m pytest tests/ -v

# Run with coverage
python -m pytest tests/ --ignore=tests/test_lpse.py --ignore=tests/test_downloader.py --cov=pyproc -v
```

---

## 16. Packaging and Entry Point Plan

### 16.1 `pyproject.toml` Changes

```toml
[project]
name = "pyproc"
version = "0.3"
description = "MCP tools for real-time Indonesian public procurement data from SPSE/Inaproc"
keywords = ["mcp", "procurement", "indonesia", "spse", "inaproc", "lpse", "llm", "ai-agent"]
classifiers = [
    # Keep existing classifiers, add:
    'Framework :: MCP',
    'Topic :: Scientific/Engineering :: Artificial Intelligence',
]

[project.optional-dependencies]
test = ["pytest"]
mcp = ["mcp"]

[project.scripts]
pyproc = "pyproc.cli:main"
pyproc-mcp = "pyproc.mcp.server:main"
```

### 16.2 Dependency Changes

| Dependency | Type | Notes |
|---|---|---|
| `mcp` | Optional (`[mcp]`) | Official MCP Python SDK |
| All existing deps | Required (unchanged) | requests, beautifulsoup4, html5lib, backoff |

### 16.3 Entry Points

| Command | Module | Status |
|---|---|---|
| `pyproc` | `pyproc.cli:main` | Unchanged |
| `pyproc-mcp` | `pyproc.mcp.server:main` | New |

### 16.4 Versioning

- Current: `0.2`
- After MCP MVP: `0.3`
- Future stable MCP: `0.4+` or `1.0`

---

## 17. Documentation Plan

| Document | Purpose | Status |
|---|---|---|
| `README.md` | Primary project page — MCP-first | Rewrite |
| `docs/mcp.md` | Detailed MCP server usage, configuration, troubleshooting | New |
| `docs/examples.md` | LLM workflow examples, sample queries | New |
| `docs/assets/README_ASSET_PROMPTS.md` | Image generation prompts for branding | New |
| `CHANGELOG.md` | Version history — add v0.3 entry | Update |
| `pyproject.toml` | Package metadata — update description, classifiers, keywords | Update |

---

## 18. Risk Register

| # | Risk | Area | Severity | Mitigation |
|---|---|---|---|---|
| 1 | MCP SDK API changes before stable release | MCP | Medium | Pin `mcp` version; test against specific version |
| 2 | SPSE/Inaproc endpoint changes break parser | Library | Medium | Existing tests catch breaking changes; MCP tools surface errors clearly |
| 3 | MCP tool descriptions enable abuse (scraping) | Security | Low | Rate limiting built in; responsible-use docs; read-only tools |
| 4 | LLM misinterprets procurement data as financial advice | Safety | Low | Tool descriptions and responsible-use resource warn about data accuracy |
| 5 | Breaking existing user workflows | Compatibility | High | All existing API, CLI, imports preserved; MCP is additive |
| 6 | `mcp` dependency conflicts with other packages | Packaging | Low | Optional dependency; users install `pyproc[mcp]` explicitly |
| 7 | Raw HTML text injection via SPSE data | Security | Low | Sanitization in MCP layer; risk is low (SPSE is controlled system) |
| 8 | README overstates MCP readiness before tools are tested | Docs | Medium | Clearly mark tool status (MVP, planned, experimental) |

---

## 19. Recommended Execution Order

1. **Task 1** — Add MCP dependency and module scaffolding. No logic, just structure. Enables everything else.
2. **Task 2** — Implement MCP server core. The server must start and register tools before anything else can be tested end-to-end.
3. **Task 3** — Implement schemas. Input validation and output normalization must be done before tool handlers to ensure consistency.
4. **Task 4** — Implement MVP MCP tools. The core value proposition — search and detail tools.
5. **Task 5** — Implement MCP resources. Static resources add documentation value with low risk.
6. **Task 8** — Write MCP-specific tests. Tests should follow implementation closely.
7. **Task 6** — Rewrite README. The rebrand comes after the MCP server works, so the README can reference real commands and configurations.
8. **Task 7** — Create branding asset prompts. Documentation-only task that can be done at any time.

---

## 20. Out of Scope

The following items are explicitly out of scope for this plan unless separately approved:

1. **Full rewrite** of `lpse.py`, `cli.py`, or any existing module
2. **Breaking existing CLI** commands, arguments, or output formats
3. **Breaking existing Python imports** (`from pyproc import Lpse`)
4. **Replacing all parsers** — the BeautifulSoup/html5lib approach works for current needs
5. **Replacing SQLite** with PostgreSQL, Redis, or any other database
6. **Adding authentication features** not supported by existing public SPSE endpoints
7. **Building a hosted SaaS service** — PyProc remains a local tool
8. **Aggressive scraping or concurrency** — rate limiting and conservative defaults are deliberate
9. **Async rewrite** — synchronous `requests` is appropriate for MCP stdio transport
10. **Claiming official affiliation** with LKPP, LPSE, SPSE, Inaproc, or any Indonesian government institution
11. **Guaranteeing data completeness or legal/financial correctness** — data is "as-is" from public sources
12. **Generating final logo/image files** — this plan provides prompts; actual image generation is a separate step
13. **Adding `clear_or_refresh_cache` MCP tool** — MCP MVP has no persistent cache
14. **HTTP/SSE MCP transport** — stdio first; HTTP transport is future work
