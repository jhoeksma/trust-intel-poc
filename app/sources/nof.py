"""NHS Oversight Framework (NOF) files -> metrics.

Two published shapes, told apart by their header:

* Trust data (long): one row per trust and metric, with Metric_ID, Value, and the
  peer median, quartiles and rank. 17 columns. Metric OF5200 is the adjusted
  segment (1 best to 4 worst; 5 is reserved for the Recovery Support Programme),
  OF5203 the unadjusted segment, OF5202 the average metric score and OF5204 the
  financial override flag. OF4xxx are domain scores/segments; OF2xxx metric scores;
  OF0xxx the underlying measures.
* League table (one row per trust): average score, its likely range, segment,
  deficit flag, rank and likely rank range. Segment, score and deficit flag
  duplicate OF5200/OF5202/OF5204 (checked: 202 of 202 identical on Q1 2026/27), so
  only the fields the trust data lacks are loaded: rank and the two likely ranges.

Every trust-data row carries Trust_type, so one `nof:peer_group` metric (1 acute, 2 mental health and
community, 3 ambulance; unit "group") is emitted per trust. League tables do not repeat it.

Reporting_date in the trust data varies per metric ("Jun-26", "2025", "12 months to
June 2026"), so every row takes the file's Quarter as its period; the metric's own
reporting window is kept in the label.
"""
import re

from app.periods import parse_period
from app.sources.loaders import (LOADER_VERSION, ODS_RE, UNKNOWN_PERIOD, LoadResult, _metric, detect_encoding,
                                 iter_rows, slug, to_float)

_SHORT_QUARTER = re.compile(r"(?i)\bQ([1-4])\s*(\d{2})\s*/\s*(\d{2})\b")  # "Q1 26/27"
UNITS = {"%": "pct", "mins": "mins", "days": "days", "score": "score", "segment": "segment", "flag": "flag",
         "count": "count", "index": "index", "out of 10": "score10", "per 1,000 deliveries": "per1000"}
_RANGE = re.compile(r"^\s*([\d.]+)\s+to\s+([\d.]+)\s*$")


def peer_group_code(trust_type: str | None) -> int | None:
    """NOF's own trust type: 1 acute, 2 mental health and community, 3 ambulance. The peer group used for benchmarking."""
    t = (trust_type or "").lower()
    if "ambulance" in t:
        return 3
    if "mental health" in t or "community" in t:
        return 2
    if "acute" in t:
        return 1
    return None


def _quarter(text: str, default_period):
    s = str(text or "").strip()
    m = _SHORT_QUARTER.search(s)
    if m:
        s = f"Q{m.group(1)} 20{m.group(2)}/{m.group(3)}"
    return parse_period(s) or parse_period(default_period) or UNKNOWN_PERIOD


def _num(raw):
    v = to_float(raw)
    return None if v is None else round(v, 6)


def load_nof(source_key: str, file_name: str, data: bytes, default_period: str | None = None) -> LoadResult:
    enc = detect_encoding(data)
    it = iter_rows(data, enc)
    try:
        header = [h.strip() for h in next(it)]
    except StopIteration:
        return LoadResult(profile={"file": file_name, "error": "empty file"}, mapper_status="needs_review")
    idx = {slug(h): i for i, h in enumerate(header)}
    result = LoadResult()
    profile = {"file": file_name, "encoding": enc, "columns": header, "loader_version": LOADER_VERSION, "notes": []}
    result.profile = profile

    def need(*names):
        return all(n in idx for n in names)

    if need("trust_code", "metric_id", "value"):
        shape = "trust_data"
    elif need("trust_code", "average_score", "segment", "rank"):
        shape = "league_table"
    else:
        profile["notes"] = ["not a recognised NOF layout (needs Trust_code with Metric_ID/Value or Average_score/Rank); nothing loaded"]
        result.mapper_status = "needs_review"
        return result
    profile["shape"] = shape

    def get(r, name):
        i = idx.get(name)
        return r[i].strip() if i is not None and i < len(r) else ""

    total = 0
    grouped: set = set()
    periods: set = set()
    seen: set = set()
    dup = 0
    types: dict = {}
    for r in it:
        total += 1
        org = get(r, "trust_code")
        if not ODS_RE.match(org):
            continue
        period = _quarter(get(r, "quarter"), default_period)
        periods.add(period.label)
        org_type = get(r, "trust_type") or None
        result.orgs.setdefault(org, (get(r, "trust_name") or None, org_type))
        types[org_type] = types.get(org_type, 0) + 1

        if shape == "trust_data":
            grp = peer_group_code(org_type)
            if grp and (org, period.label) not in grouped:
                grouped.add((org, period.label))
                result.metrics.append(_metric(f"{source_key}:peer_group", "NOF trust type (1 Acute, 2 Mental health and community, 3 Ambulance)",
                                              org, period, float(grp), source_key, "group"))
            mid = get(r, "metric_id")
            val = _num(get(r, "value"))
            if not mid or val is None:
                continue
            key = (org, period.label, mid)
            if key in seen:
                dup += 1
                continue
            seen.add(key)
            code = f"{source_key}:{slug(mid)}"
            desc = get(r, "metric_description").replace("\xa0", " ").strip() or mid
            window = get(r, "reporting_date")
            label = f"{mid} {desc}" + (f" [{window}]" if window else "")
            unit = UNITS.get(get(r, "units").lower(), slug(get(r, "units")) or None)
            result.metrics.append(_metric(code, label, org, period, val, source_key, unit))
            rank = _num(get(r, "rank"))
            if rank is not None:
                result.metrics.append(_metric(f"{code}:rank", f"{label} (rank among {org_type or 'peers'})", org, period, rank, source_key, "rank"))
        else:
            for col, code, label, unit in (
                ("rank", "league_rank", "League table rank (within trust type)", "rank"),
            ):
                v = _num(get(r, col))
                if v is not None:
                    result.metrics.append(_metric(f"{source_key}:{code}", label, org, period, v, source_key, unit))
            for col, stem, label, unit in (
                ("likely_range_of_average_score", "league_score", "League table average score, likely range", "score"),
                ("likely_range_of_rank", "league_rank", "League table rank, likely range", "rank"),
            ):
                m = _RANGE.match(get(r, col))
                if m:
                    for end, v in (("low", m.group(1)), ("high", m.group(2))):
                        result.metrics.append(_metric(f"{source_key}:{stem}_{end}", f"{label} ({end})", org, period, float(v), source_key, unit))

    result.row_count = total
    profile.update({
        "rows_read": total, "metrics_loaded": len(result.metrics), "orgs": len(result.orgs),
        "periods": sorted(periods), "duplicate_keys": dup, "trust_types": {k or "unknown": v for k, v in types.items()},
    })
    if shape == "league_table":
        profile["notes"].append("segment, average score and deficit flag duplicate OF5200/OF5202/OF5204 in the trust data and are not reloaded")
    result.mapper_status = "ok" if result.metrics else "needs_review"
    return result
