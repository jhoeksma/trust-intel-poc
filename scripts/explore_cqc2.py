"""Diagnostic 2: provider-level rating rows, and how to map CQC providers to NHS trust ODS codes."""
import sys
from collections import Counter, defaultdict

import requests
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Metric
from app.sources.ods import iter_ods

data = requests.get(sys.argv[1], headers={"User-Agent": "Mozilla/5.0 Chrome/124"}, timeout=180).content
P = lambda *a: print("EXPLORE2", *a, flush=True)
hdr, prov = None, []
for _, row in iter_ods(data, only_sheet="Providers"):
    if hdr is None:
        hdr = row
        continue
    prov.append(dict(zip(hdr, row)))
nhs = [r for r in prov if r.get("Provider Type") == "NHS Healthcare Organisation"]
pl = [r for r in nhs if r.get("Report Type") == "Provider"]
P("NHS Provider-level rows", len(pl), "providers", len({r["Provider ID"] for r in pl}))
P("provider-level (group|domain)", dict(Counter((r["Service / Population Group"], r["Domain"]) for r in pl).most_common(14)))
P("provider-level rating values", dict(Counter(r["Latest Rating"] for r in pl)))
shown = 0
for r in pl:
    if r.get("Provider ODS Code") in ("R0A", "RJ1", "RYJ", "RX1", "RTH", "RRK") and shown < 40:
        shown += 1
        P("ROW", r["Provider ODS Code"], r["Provider Name"][:34], "|", r["Service / Population Group"], "|", r["Domain"], "|", r["Latest Rating"], "|", str(r["Publication Date"])[:10])
named = {r["Provider ID"] for r in nhs if r.get("Provider ODS Code")}
P("NHS providers with ODS on Providers sheet", len(named), "of", len({r["Provider ID"] for r in nhs}))
# derive ODS from location site codes
nhs_ids = {r["Provider ID"] for r in nhs}
pref = defaultdict(Counter)
lh = None
loc_types = Counter()
for _, row in iter_ods(data, only_sheet="Locations"):
    if lh is None:
        lh = row
        continue
    d = dict(zip(lh, row))
    if d.get("Provider ID") in nhs_ids and d.get("Location ODS Code"):
        pref[d["Provider ID"]][d["Location ODS Code"][:3]] += 1
        loc_types[d.get("Location Type")] += 1
P("NHS providers with at least one located site ODS code", len(pref), "location types", dict(loc_types))
with SessionLocal() as db:
    nof = {c for (c,) in db.execute(select(Metric.ods_code).where(Metric.source_key == "nof").distinct())}
    nm = {}
    from app.models import Org
    for o in db.scalars(select(Org)):
        nm[o.ods_code] = o.name
by_pid = {r["Provider ID"]: r for r in nhs}
explicit = {r["Provider ID"]: r["Provider ODS Code"] for r in nhs if r.get("Provider ODS Code")}
hit_exp = {c for c in explicit.values() if c in nof}
hit_der, amb = set(), 0
for pid, cnt in pref.items():
    top, n = cnt.most_common(1)[0]
    if top in nof:
        hit_der.add(top)
    if len(cnt) > 1 and n / sum(cnt.values()) < 0.8:
        amb += 1
P("NOF trusts matched by explicit provider ODS", len(hit_exp), "by derived site prefix", len(hit_der), "union", len(hit_exp | hit_der), "of", len(nof), "; providers with mixed prefixes", amb)
miss = sorted(nof - hit_exp - hit_der)
P("NOF trusts with no CQC match", len(miss), [f"{c} {nm.get(c, '')[:26]}" for c in miss[:30]])
unm = [by_pid[p]["Provider Name"][:40] for p in nhs_ids if p not in explicit and (p not in pref or pref[p].most_common(1)[0][0] not in nof)]
P("NHS CQC providers not matched to a NOF trust", len(unm), sorted(unm)[:30])
