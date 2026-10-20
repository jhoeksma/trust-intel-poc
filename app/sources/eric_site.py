"""ERIC site-level return -> trust-level metrics.

The file has one row per site (about 2,900 sites, 230 columns) under two header
rows: row 1 holds the ERIC question code (S03_10), row 2 the description with its
unit in brackets, e.g. "Cost to eradicate moderate risk backlog (£)". Per trust we
sum additive measures (money, floor area, energy, waste, counts), take a floor-area
weighted average of percentages, and compute a few derived headline measures.
Text and select columns are skipped. "Not Applicable" and blanks are not zeros.
"""
import re

from app.periods import parse_period
from app.sources.loaders import (LOADER_VERSION, LoadResult, _metric, detect_encoding, iter_rows, slug, to_float)

FIRST_DATA_COL = 15  # columns before this describe the site (code, name, type, tenure ...)
GIA = "S02_01"  # gross internal floor area, m2
OCCUPIED = "S02_03"

UNITS = {"£": "gbp", "m²": "sqm", "m³": "m3", "kwh": "kwh", "kw": "kw", "kva": "kva", "tonnes": "tonnes",
         "hrs": "hours", "wte": "wte", "no.": "count", "no": "count", "hectares": "hectares", "%": "pct"}
_UNIT_RE = re.compile(r"\(([^()]*)\)\s*$")

BACKLOG = ["S03_08", "S03_09", "S03_10", "S03_11"]  # high, significant, moderate, low risk (£)
ENERGY_COST = ["S05_22", "S05_34", "S05_36", "S05_38", "S05_40", "S05_51", "S05_53", "S05_19", "S05_20", "S05_24", "S05_25"]
ENERGY_KWH = ["S05_14", "S05_35", "S05_37", "S05_39", "S05_41", "S05_52", "S05_54", "S05_11", "S05_12", "S22_06"]
ESTATES_COST = ["S25_12", "S25_13", "S25_14", "S25_15", "S25_16", "S25_17", "S25_05", "S25_06", "S25_07", "S25_08", "S25_10", "S25_19"]


def _unit(desc: str):
    m = _UNIT_RE.search(desc)
    if not m:
        return None
    return UNITS.get(m.group(1).strip().lower())


def load_eric_site(source_key: str, file_name: str, data: bytes, default_period: str | None = None) -> LoadResult:
    enc = detect_encoding(data)
    it = iter_rows(data, enc)
    codes = next(it)
    descs = next(it)
    period = parse_period(file_name) or parse_period(default_period)
    result = LoadResult()
    if period is None:
        result.mapper_status = "needs_review"
        result.profile = {"file": file_name, "error": "no period found in file name or default"}
        return result

    cols = {}  # index -> (qcode, description, unit)
    skipped = []
    for i in range(FIRST_DATA_COL, min(len(codes), len(descs))):
        q, d = codes[i].strip(), descs[i].strip()
        u = _unit(d)
        if q and u:
            cols[i] = (q, re.sub(r"\s*\([^()]*\)\s*$", "", d), u)
        elif q:
            skipped.append(f"{q}: {d[:60]}")
    gia_idx = next((i for i, c in cols.items() if c[0] == GIA), None)

    sums: dict = {}
    wsum: dict = {}
    wtot: dict = {}
    sites: dict = {}
    site_types: dict = {}
    names: dict = {}
    rows = 0
    for r in it:
        if len(r) < FIRST_DATA_COL or not r[0].strip():
            continue
        rows += 1
        org = r[0].strip().upper()
        names.setdefault(org, r[1].strip() or None)
        sites[org] = sites.get(org, 0) + 1
        st = r[10].strip() if len(r) > 10 else ""
        if st:
            site_types[(org, st)] = site_types.get((org, st), 0) + 1
        gia = to_float(r[gia_idx]) if gia_idx is not None and gia_idx < len(r) else None
        for i, (q, d, u) in cols.items():
            if i >= len(r):
                continue
            v = to_float(r[i])
            if v is None:
                continue
            if u == "pct":
                if gia and gia > 0:
                    wsum[(org, q)] = wsum.get((org, q), 0.0) + v * gia
                    wtot[(org, q)] = wtot.get((org, q), 0.0) + gia
            else:
                sums[(org, q)] = sums.get((org, q), 0.0) + v

    label = {q: (d, u) for (q, d, u) in cols.values()}
    for (org, q), v in sums.items():
        d, u = label[q]
        result.metrics.append(_metric(f"{source_key}:{q.lower()}", d, org, period, round(v, 4), source_key, u))
    for (org, q), v in wsum.items():
        d, u = label[q]
        result.metrics.append(_metric(f"{source_key}:{q.lower()}", f"{d} (floor-area weighted)", org, period,
                                      round(v / wtot[(org, q)], 2), source_key, u))
    for org, n in sites.items():
        result.metrics.append(_metric(f"{source_key}:sites_total", "Number of sites", org, period, n, source_key, "count"))
    for (org, st), n in site_types.items():
        result.metrics.append(_metric(f"{source_key}:sites:{slug(st)}", f"Sites: {st}", org, period, n, source_key, "count"))

    def total(org, qs):
        vals = [sums[(org, q)] for q in qs if (org, q) in sums]
        return sum(vals) if vals else None

    for org in sites:
        gia_t = sums.get((org, GIA))
        occ = sums.get((org, OCCUPIED))
        derived = []
        bl = total(org, BACKLOG)
        hs = total(org, BACKLOG[:2])
        if bl is not None:
            derived.append(("backlog_total", "Backlog maintenance, total cost to eradicate (all risk levels)", bl, "gbp"))
            if hs is not None:
                derived.append(("backlog_high_significant", "Backlog maintenance, high and significant risk", hs, "gbp"))
                if bl > 0:
                    derived.append(("backlog_high_significant_share", "Share of backlog rated high or significant risk", 100 * hs / bl, "pct"))
            if gia_t:
                derived.append(("backlog_per_sqm", "Backlog maintenance per m² of floor area", bl / gia_t, "gbp_per_sqm"))
        ec, ek = total(org, ENERGY_COST), total(org, ENERGY_KWH)
        if ec is not None:
            derived.append(("energy_cost_total", "Energy cost, all sources", ec, "gbp"))
            if gia_t:
                derived.append(("energy_cost_per_sqm", "Energy cost per m² of floor area", ec / gia_t, "gbp_per_sqm"))
        if ek is not None:
            derived.append(("energy_kwh_total", "Energy consumed, all sources", ek, "kwh"))
            if gia_t:
                derived.append(("energy_kwh_per_sqm", "Energy consumed per m² of floor area", ek / gia_t, "kwh_per_sqm"))
        ex = total(org, ESTATES_COST)
        if ex is not None:
            derived.append(("estates_cost_total", "Estates and facilities cost lines, summed (S25_05-19)", ex, "gbp"))
            if gia_t:
                derived.append(("estates_cost_per_sqm", "Estates and facilities cost per m²", ex / gia_t, "gbp_per_sqm"))
        uns = sums.get((org, "S01_17"))
        if uns is not None and occ:
            derived.append(("unsuitable_share", "Share of occupied floor area not functionally suitable", 100 * uns / occ, "pct"))
        emp = sums.get((org, "S01_19"))
        if emp is not None and gia_t:
            derived.append(("empty_share", "Share of floor area empty", 100 * emp / gia_t, "pct"))
        for code, lab, val, unit in derived:
            result.metrics.append(_metric(f"{source_key}:{code}", lab, org, period, round(val, 4), source_key, unit))

    for org, name in names.items():
        result.orgs[org] = (name, None)
    result.row_count = rows
    result.mapper_status = "ok" if result.metrics else "needs_review"
    result.profile = {
        "file": file_name, "shape": "site-level, rolled up to trust", "file_period": period.label,
        "rows_read": rows, "orgs": len(names), "metrics_loaded": len(result.metrics),
        "numeric_columns": len(cols), "skipped_text_columns": skipped[:80], "periods": [period.label],
        "loader_version": LOADER_VERSION,
        "notes": ["additive measures summed over sites; percentages floor-area weighted; Not Applicable and blanks ignored. "
                  "Derived: backlog (S03_08-11), energy (S05_*), estates cost lines (S25_*, excluding S25_11 and S25_22)."],
    }
    return result
