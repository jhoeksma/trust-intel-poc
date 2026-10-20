"""Diagnostic: how does CQC's Latest ratings file represent NHS trust ratings?  Prints EXPLORE lines."""
import sys
from collections import Counter

import requests

from app.sources.ods import iter_ods

URL = sys.argv[1]
data = requests.get(URL, headers={"User-Agent": "Mozilla/5.0 Chrome/124"}, timeout=180).content
P = lambda *a: print("EXPLORE", *a, flush=True)
for sheet, row in iter_ods(data, only_sheet="README"):
    P("README:", " | ".join(str(c) for c in row)[:900].replace("\n", " / "))
hdr, rows = None, []
for sheet, row in iter_ods(data, only_sheet="Providers"):
    if hdr is None:
        hdr = row
        continue
    rows.append(dict(zip(hdr, row)))
P("provider rows", len(rows))
for col in ("Provider Type", "Report Type", "Domain", "Latest Rating", "Inherited Rating (Y/N)"):
    P(col, dict(Counter(r.get(col) for r in rows).most_common(12)))
nhs = [r for r in rows if "nhs" in str(r.get("Provider Type", "")).lower()]
P("NHS-type rows", len(nhs), "distinct providers", len({r["Provider ID"] for r in nhs}))
P("NHS Service/Population Group values", dict(Counter(r.get("Service / Population Group") for r in nhs).most_common(8)))
P("NHS Report Type", dict(Counter(r.get("Report Type") for r in nhs)))
for code in ("RJ1", "R0A", "RYJ", "RX1"):
    for r in [r for r in rows if r.get("Provider ODS Code") == code][:14]:
        P(code, r.get("Provider Name"), "|", r.get("Service / Population Group"), "|", r.get("Domain"), "|", r.get("Latest Rating"), "|", str(r.get("Publication Date"))[:10], "|", r.get("Report Type"), "|", r.get("Inherited Rating (Y/N)"))
ods = Counter(r.get("Provider ODS Code") for r in nhs if r.get("Provider ODS Code"))
P("NHS providers with an ODS code", len(ods), "sample", list(ods)[:15])
loc_hdr, n, nhs_loc = None, 0, Counter()
for sheet, row in iter_ods(data, only_sheet="Locations"):
    if loc_hdr is None:
        loc_hdr = row
        continue
    n += 1
    d = dict(zip(loc_hdr, row))
    if d.get("Location ODS Code", "")[:3] in ("RJ1", "R0A") and d.get("Domain") == "Overall" and d.get("Service / Population Group") == "Overall":
        nhs_loc[d["Location ODS Code"]] = (d["Location Name"][:30], d["Latest Rating"])
P("location rows", n, "sample NHS locations Overall/Overall", dict(list(nhs_loc.items())[:12]))
