"""LPSE host discovery helpers for MCP tools."""

from __future__ import annotations

import re
import time
import requests

from pyproc import utils

HOST_CACHE_TTL_SECONDS = 6 * 60 * 60
NATIONAL_HOST = {
    "host": "nasional",
    "name": "Nasional",
    "url": "https://spse.inaproc.id/nasional",
    "source": "builtin",
    "aliases": [
        "nasional",
        "national",
        "national wide",
        "nationwide",
        "seluruh indonesia",
        "semua instansi",
        "lintas instansi",
    ],
    "executor_scope": "national",
}

_host_cache: dict[str, object] = {
    "loaded_at": 0.0,
    "hosts": None,
}


class HostMetadataError(RuntimeError):
    """Raised when LPSE host metadata cannot be loaded."""


def _normalize_text(value: object) -> str:
    """Normalize Indonesian institution text for simple fuzzy matching."""
    text = str(value or "").lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def normalize_host_record(item: dict) -> dict | None:
    """Normalize one Gist host record into MCP output shape."""
    host = str(item.get("newUrlPath") or "").strip().lower()
    if not host:
        return None

    name = str(item.get("name") or "").strip()
    aliases = {
        _normalize_text(host),
        _normalize_text(name),
    }
    for part in name.split(">"):
        aliases.add(_normalize_text(part))

    aliases = sorted(alias for alias in aliases if alias)
    canonical_url = f"https://spse.inaproc.id/{host}"

    return {
        "host": host,
        "name": name or host,
        "url": canonical_url,
        "source": "gist",
        "aliases": aliases,
    }


def _load_hosts(refresh: bool = False) -> list[dict]:
    now = time.monotonic()
    cached_hosts = _host_cache.get("hosts")
    loaded_at = float(_host_cache.get("loaded_at") or 0.0)

    if (
        not refresh
        and isinstance(cached_hosts, list)
        and now - loaded_at < HOST_CACHE_TTL_SECONDS
    ):
        return cached_hosts

    try:
        raw_hosts = utils.get_host_metadata()
    except requests.exceptions.Timeout as exc:
        raise HostMetadataError(
            "Host metadata source timed out while loading LPSE host aliases."
        ) from exc
    except requests.exceptions.RequestException as exc:
        raise HostMetadataError(
            f"Host metadata source could not be loaded: {exc}"
        ) from exc
    normalized = [dict(NATIONAL_HOST)]
    seen = {NATIONAL_HOST["host"]}
    for item in raw_hosts:
        if not isinstance(item, dict):
            continue
        host = normalize_host_record(item)
        if not host or host["host"] in seen:
            continue
        seen.add(host["host"])
        normalized.append(host)

    _host_cache["hosts"] = normalized
    _host_cache["loaded_at"] = now
    return normalized


def reset_host_cache() -> None:
    """Reset host cache. Intended for tests."""
    _host_cache["hosts"] = None
    _host_cache["loaded_at"] = 0.0


def _score_host(query: str, host: dict) -> tuple[float, str]:
    normalized_query = _normalize_text(query)
    if not normalized_query:
        return 0.0, "Empty query"

    query_tokens = set(normalized_query.split())
    best_score = 0.0
    best_reason = "No match"

    searchable = [host["host"], host["name"], *host.get("aliases", [])]
    for value in searchable:
        normalized_value = _normalize_text(value)
        if not normalized_value:
            continue

        value_tokens = set(normalized_value.split())
        if normalized_query == normalized_value:
            score = 1.0
            reason = f"Exact match for '{value}'"
        elif normalized_query in normalized_value:
            score = 0.9
            reason = f"Query is contained in '{value}'"
        elif normalized_value in normalized_query:
            score = 0.85
            reason = f"Host alias '{value}' is contained in query"
        else:
            overlap = len(query_tokens & value_tokens)
            score = overlap / max(len(query_tokens), len(value_tokens), 1)
            reason = f"Token overlap with '{value}'"

        if score > best_score:
            best_score = score
            best_reason = reason

    return best_score, best_reason


def search_lpse_hosts(query: str, limit: int = 5, refresh: bool = False) -> dict:
    """Search known LPSE hosts by free-text institution or host query."""
    query = str(query or "").strip()
    if not query:
        raise ValueError("Host search query must not be empty")

    limit = max(1, min(int(limit or 5), 20))
    hosts = _load_hosts(refresh=refresh)

    matches = []
    for host in hosts:
        score, reason = _score_host(query, host)
        if score <= 0:
            continue
        item = dict(host)
        item["match_score"] = round(score, 4)
        item["match_reason"] = reason
        matches.append(item)

    matches.sort(key=lambda item: (-item["match_score"], item["name"], item["host"]))
    matches = matches[:limit]

    return {
        "query": query,
        "count": len(matches),
        "hosts": matches,
        "usage_hint": (
            "Use the selected 'host' value as the lpse_host argument for "
            "package search and detail tools. Procurement data can be scoped "
            "to a specific agency host such as 'kemenkeu' or to the national "
            "host 'nasional' for nationwide pencatatan data."
        ),
    }


def get_lpse_host_detail(lpse_host: str, refresh: bool = False) -> dict:
    """Return metadata for one LPSE host slug."""
    host_query = _normalize_text(lpse_host)
    if not host_query:
        raise ValueError("LPSE host must not be empty")

    hosts = _load_hosts(refresh=refresh)
    for host in hosts:
        if host["host"] == host_query:
            return {
                **host,
                "usage_hint": (
                    f"Use lpse_host='{host['host']}' when calling package "
                    "search or detail tools."
                ),
            }

    raise ValueError(f"LPSE host '{lpse_host}' was not found in the known host list")
