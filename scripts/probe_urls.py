"""Diagnostic: can this host reach a page, and which downloadable files does it link to?

    python -m scripts.probe_urls <page-url> [<page-url> ...]

Prints status, size and every link ending in a data-file extension. Used to find out
whether a publisher (e.g. CQC) is reachable from Railway before building a loader.
"""
import re
import sys

import requests

HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
           "Accept": "text/html,application/xhtml+xml,*/*", "Accept-Language": "en-GB,en;q=0.9"}

for url in sys.argv[1:]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        links = sorted(set(re.findall(r'href="([^"]+\.(?:ods|csv|xlsx|xls|zip|json))"', r.text, flags=re.I)))
        print(f"PROBE {url} -> {r.status_code}, {len(r.content)} bytes, {len(links)} data links")
        for l in links[:40]:
            print("PROBE   link", l)
    except Exception as e:  # noqa: BLE001
        print(f"PROBE {url} -> ERROR {type(e).__name__}: {str(e)[:160]}")
