"""Diagnostic: download a data file and print its structure.

    python -m scripts.profile_file <url> [max_rows_per_sheet]

For .ods prints each sheet's row count and first rows; for .csv/.zip the header and
first rows. Used to inspect a publisher's real layout before writing a loader.
"""
import io
import sys
import zipfile
from collections import defaultdict

import requests

from app.sources.loaders import detect_encoding, iter_rows
from app.sources.ods import iter_ods

H = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
url = sys.argv[1]
n_show = int(sys.argv[2]) if len(sys.argv) > 2 else 6
r = requests.get(url, headers=H, timeout=180)
data = r.content
print(f"PROFILE {url} -> {r.status_code}, {len(data)} bytes")
cut = lambda row: [str(c)[:40] for c in row[:30]]
if url.lower().endswith(".ods"):
    counts, shown = defaultdict(int), defaultdict(int)
    for sheet, row in iter_ods(data):
        counts[sheet] += 1
        if shown[sheet] < n_show:
            shown[sheet] += 1
            print(f"PROFILE [{sheet}] row {counts[sheet]} ({len(row)} cols): {cut(row)}")
    for s, n in counts.items():
        print(f"PROFILE sheet '{s}': {n} rows")
else:
    if url.lower().endswith(".zip"):
        z = zipfile.ZipFile(io.BytesIO(data))
        for name in z.namelist():
            print("PROFILE zip member", name)
        name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        data = z.read(name)
    enc = detect_encoding(data)
    for i, row in enumerate(iter_rows(data, enc)):
        if i < n_show:
            print(f"PROFILE row {i}: {cut(row)}")
    print("PROFILE rows total", i + 1)
