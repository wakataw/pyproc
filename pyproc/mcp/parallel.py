"""Shared concurrency utilities for MCP tool handlers.

Provides thread-safe rate limiting, per-worker Lpse session pools with
unique browser footprints, and parallel detail fetching — so the SPSE
server sees each worker as a distinct client even from the same IP.
"""

import logging
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from time import sleep

logger = logging.getLogger(__name__)


# ── Thread-Safe Rate Limiter ─────────────────────────────────────────────────

class ThreadSafeRateLimiter:
    """Thread-safe rate limiter with jitter for concurrent workers.

    Unlike the module-level ``_rate_limit()`` in ``tools.py`` (which uses a
    bare global float and is NOT safe for concurrent access), this class
    protects the timing state behind a ``threading.Lock`` and adds random
    jitter so workers that pile up on the lock don't fire in lockstep.
    """

    def __init__(self, min_delay: float = 1.0):
        self._min_delay = min_delay
        self._lock = threading.Lock()
        self._last_time: float = 0.0

    def wait(self) -> None:
        """Block until *min_delay* has elapsed since the previous ``wait()``.

        Safe to call concurrently from any number of threads.
        """
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_time
            if elapsed < self._min_delay:
                # Jitter prevents synchronised bursts when multiple threads
                # are queued on the lock simultaneously.
                jittered = (self._min_delay - elapsed) * random.uniform(0.5, 1.5)
                time.sleep(jittered)
            self._last_time = time.monotonic()


# ── Worker Lpse Pool ─────────────────────────────────────────────────────────

def create_worker_lpse_pool(host, count, timeout, verify):
    """Create *count* ``Lpse`` instances, each with a unique browser footprint.

    Uses ``pyproc.user_agents.create_session_headers()`` to assign a
    different User-Agent, Accept, and Accept-Language to every worker so
    the server sees concurrent requests as distinct clients.

    Args:
        host: LPSE host slug (e.g. ``"kemenkeu"``).
        count: Number of workers / Lpse instances to create.
        timeout: HTTP timeout in seconds.
        verify: SSL certificate verification flag.

    Returns:
        list of ``Lpse`` instances.
    """
    from pyproc.user_agents import create_session_headers
    from pyproc import Lpse

    pool = []
    for i in range(count):
        headers = create_session_headers(i)
        lpse = Lpse(
            host, timeout=timeout, verify=verify,
            user_agent=headers.pop('User-Agent'),
        )
        # Apply remaining profile headers (Accept, Accept-Language)
        lpse.session.headers.update(headers)
        pool.append(lpse)
    return pool


# ── Parallel Detail Fetch ────────────────────────────────────────────────────

def fetch_details_parallel(package_ids, lpse_pool, detail_method_name,
                           rate_limiter, continue_on_error=True):
    """Fetch full details for *package_ids* in parallel using stealth workers.

    Each worker thread gets its own ``Lpse`` instance from *lpse_pool*
    (cycled via modulo), giving every concurrent request a distinct HTTP
    footprint.  A thread-safe *rate_limiter* ensures the global request
    rate stays within bounds.

    This is a **synchronous** function designed to be offloaded from the
    MCP event loop via ``anyio.to_thread.run_sync()``.

    Args:
        package_ids: List of SPSE package IDs to fetch.
        lpse_pool: List of ``Lpse`` instances (one per worker).
        detail_method_name: Name of the detail method on ``Lpse``
            (e.g. ``"detil_paket_tender"``).
        rate_limiter: A ``ThreadSafeRateLimiter`` instance.
        continue_on_error: If ``False``, cancel remaining futures on the
            first failure.

    Returns:
        list of result dicts with keys ``package_id``, ``success``,
        ``detail``, and optionally ``error_messages`` or ``error``.
        Results are sorted to match the input *package_ids* order.
    """
    workers = len(lpse_pool)
    if workers < 1:
        raise ValueError("lpse_pool must contain at least one Lpse instance")

    results = []

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_pid = {}
        for i, pid in enumerate(package_ids):
            lpse = lpse_pool[i % workers]
            future = executor.submit(
                _fetch_one_detail,
                pid, lpse, detail_method_name, rate_limiter,
            )
            future_to_pid[future] = pid

        for future in as_completed(future_to_pid):
            pid = future_to_pid[future]
            try:
                result = future.result()
                results.append(result)
                if not result.get('success') and not continue_on_error:
                    _cancel_all(future_to_pid)
                    break
            except Exception as exc:
                results.append(_error_item(pid, exc))
                if not continue_on_error:
                    _cancel_all(future_to_pid)
                    break

    # Restore input order for deterministic output
    pid_order = {pid: i for i, pid in enumerate(package_ids)}
    results.sort(key=lambda r: pid_order.get(r.get('package_id'), 9999))
    return results


# ── Internal helpers ─────────────────────────────────────────────────────────

def _fetch_one_detail(package_id, lpse, detail_method_name, rate_limiter):
    """Fetch a single package detail.  Runs inside a worker thread."""
    rate_limiter.wait()
    method = getattr(lpse, detail_method_name)
    package_detail = method(package_id)
    info = package_detail.get_all_detil()
    detail_dict = package_detail.todict()

    item = {
        "package_id": package_id,
        "success": not bool(info.get("error")),
        "detail": detail_dict,
    }
    if info.get("error"):
        item["error_messages"] = info.get("error_message", [])

    # Small random delay so workers don't hammer the server in lockstep
    sleep(random.uniform(0.3, 1.5))
    return item


def _error_item(package_id, exc):
    """Build an error result dict for a package that raised an exception."""
    return {
        "package_id": package_id,
        "success": False,
        "error": str(exc),
    }


def _cancel_all(future_to_pid):
    """Cancel all pending futures in the map."""
    for f in future_to_pid:
        f.cancel()
