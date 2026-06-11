"""
Per-worker HTTP header rotation for stealth concurrent downloads.

Each worker gets a unique browser profile (User-Agent + Accept headers)
so the server sees parallel requests as distinct clients, even from the
same IP address.
"""

USER_AGENTS = [
    # Chrome 120 on Windows 10
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    # Chrome 120 on macOS Ventura
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    # Chrome 120 on Linux
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    # Chrome 121 on Windows 11
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    # Chrome 121 on macOS Sonoma
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_1) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    # Firefox 121 on Windows
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) '
    'Gecko/20100101 Firefox/121.0',
    # Firefox 121 on macOS
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) '
    'Gecko/20100101 Firefox/121.0',
    # Firefox 121 on Linux
    'Mozilla/5.0 (X11; Linux x86_64; rv:121.0) '
    'Gecko/20100101 Firefox/121.0',
    # Edge 120 on Windows
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 '
    'Edg/120.0.0.0',
    # Edge 121 on Windows
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 '
    'Edg/121.0.0.0',
    # Chrome 119 on Windows 10
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    # Chrome 119 on macOS
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    # Firefox 120 on Windows
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) '
    'Gecko/20100101 Firefox/120.0',
    # Firefox 120 on macOS
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:120.0) '
    'Gecko/20100101 Firefox/120.0',
    # Chrome 122 on Windows
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    # Chrome 122 on macOS
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    # Safari 17 on macOS
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_1) AppleWebKit/605.1.15 '
    '(KHTML, like Gecko) Version/17.1 Safari/605.1.15',
    # Firefox 122 on Windows
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) '
    'Gecko/20100101 Firefox/122.0',
    # Edge 122 on Windows
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 '
    'Edg/122.0.0.0',
    # Chrome 118 on Linux
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36',
]

HEADER_PROFILES = [
    {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,'
                  'image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    },
    {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,'
                  'image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    },
    {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,'
                  '*/*;q=0.8',
        'Accept-Language': 'en-GB,en;q=0.7,id;q=0.3',
    },
    {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,'
                  'image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7',
    },
    {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,'
                  'image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9,id;q=0.5',
    },
]


def create_session_headers(worker_id):
    """Return a dict of HTTP headers for a worker based on its ID.

    Different worker IDs produce different User-Agent, Accept, and
    Accept-Language combinations so the server sees each worker as
    a distinct browser/client.

    Args:
        worker_id: Integer worker identifier (0-based).

    Returns:
        dict with 'User-Agent', 'Accept', and 'Accept-Language' keys.
    """
    ua = USER_AGENTS[worker_id % len(USER_AGENTS)]
    profile = HEADER_PROFILES[worker_id % len(HEADER_PROFILES)]
    return {
        'User-Agent': ua,
        'Accept': profile['Accept'],
        'Accept-Language': profile['Accept-Language'],
    }
