"""Turn a downloaded CSV into metric rows, and record what the file looks like.

We have not been able to inspect the live files before writing this, so the
generic loader works out the shape of each file itself (which column is the
organisation code, whether the table is long or wide, which columns are numeric)
and records that in the file's `profile`. The profile is the field inventory
called for in the Phase 1 scope: read it at /api/sources after the first run and
tighten the mappings where the guesses are wrong.
"""
import codecs
from urllib.parse import unquote
import csv
import io
import re
from dataclasses import dataclass, field

from app.config import settings
from app.periods import Period, parse_period

LOADER_VERSION = 3  # bump when loader output changes, so unchanged files are reloaded
ODS_RE = re.compile(r"^[A-Z0-9]{3,5}$")
UNKNOWN_PERIOD = Period("unknown", 0, "unknown")


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(text).lower()).strip("_")


def to_float(raw) -> float | None:
    if raw is None:
        return None
    s = str(raw).strip().replace(",", "").replace("£", "").replace("%", "")
    if s in ("", "-", "*", "..", "n/a", "N/A", "NA", ":", "x"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def detect_encoding(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252"):
        try:
            codecs.getincrementaldecoder(enc)().decode(data[:200000], final=False)
            return enc
        except UnicodeDecodeError:
            continue
    return "latin-1"


def iter_rows(data: bytes, enc: str):
    text = io.TextIOWrapper(io.BytesIO(data), encoding=enc, newline="", errors="replace")
    for row in csv.reader(text):
        if row and any(cell.strip() for cell in row):
            yield row


def unique_header(header: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    out = []
    for h in header:
        h = h.strip() or "unnamed"
        n = seen.get(h, 0)
        seen[h] = n + 1
        out.append(h if n == 0 else f"{h}.{n}")
    return out


@dataclass
class Roles:
    org_code: int | None = None
    org_name: int | None = None
    period: int | None = None
    metric_id: int | None = None
    metric_name: int | None = None
    value: int | None = None
    score: int | None = None
    shape: str = "wide"  # long | wide
    numeric: list = field(default_factory=list)


_ORG_GOOD = ("org_code", "organisation_code", "organization_code", "provider_code", "trust_code", "ods_code", "provider_org_code", "org_id", "organisation_id")
_ORG_BAD = ("parent", "commissioner", "icb", "region", "site", "specialty", "treatment", "function", "cpv", "metric", "stp", "ccg", "sub_icb")
_PERIOD_TOKENS = ("period", "quarter", "reporting_month", "month", "financial_year", "fy", "date", "year")
_METRIC_ID = ("metric_id", "metric_code", "measure_id", "indicator_id", "metric", "measure", "indicator")
_METRIC_NAME = ("metric_name", "measure_name", "indicator_name", "metric_description", "measure_description", "metric_label")
_VALUE = ("metric_value", "value", "measure_value", "figure", "result", "count", "indicator_value")
_NOT_METRIC = ("code", "id", "name", "postcode", "phone", "address", "ods")


def _col(sample: list[list[str]], i: int) -> list[str]:
    return [r[i].strip() for r in sample if i < len(r) and r[i].strip()]


def _share(values: list[str], pred) -> float:
    return (sum(1 for v in values if pred(v)) / len(values)) if values else 0.0


def detect_roles(header: list[str], sample: list[list[str]]) -> Roles:
    slugs = [slug(h) for h in header]
    roles = Roles()

    best, best_score = None, 0
    for i, s in enumerate(slugs):
        score = 0
        if any(t in s for t in _ORG_GOOD):
            score += 3
        elif s.endswith("code") or s == "ods" or "ods" in s.split("_"):
            score += 1
        if any(b in s for b in _ORG_BAD):
            score -= 3
        if score > best_score and _share(_col(sample, i), lambda v: bool(ODS_RE.match(v))) >= 0.6:
            best, best_score = i, score
    roles.org_code = best

    if best is not None:
        wanted = slugs[best].replace("code", "name")
        if wanted in slugs and wanted != slugs[best]:
            roles.org_name = slugs.index(wanted)
        else:
            for i, s in enumerate(slugs):
                if "name" in s and any(t in s for t in ("trust", "provider", "org")) and not any(b in s for b in ("parent", "commissioner", "site", "metric")):
                    roles.org_name = i
                    break

    for i, s in enumerate(slugs):
        if i == roles.org_code:
            continue
        if any(t == s or t in s.split("_") for t in _PERIOD_TOKENS) and not any(x in s for x in ("start", "end")):
            if _share(_col(sample, i), lambda v: parse_period(v) is not None) >= 0.6:
                roles.period = i
                break

    def find(options):
        for opt in options:
            if opt in slugs:
                return slugs.index(opt)
        return None

    roles.metric_id = find(_METRIC_ID)
    roles.metric_name = find(_METRIC_NAME)
    roles.value = find(_VALUE)
    roles.score = find(("metric_score", "score"))
    if (roles.metric_id is not None and roles.value is not None
            and _share(_col(sample, roles.value), lambda v: to_float(v) is not None) >= 0.5):
        roles.shape = "long"
        return roles

    skip = {roles.org_code, roles.org_name, roles.period}
    for i, s in enumerate(slugs):
        if i in skip or any(t in s.split("_") for t in _NOT_METRIC):
            continue
        vals = _col(sample, i)
        if len(vals) >= 3 and _share(vals, lambda v: to_float(v) is not None) >= 0.6:
            roles.numeric.append(i)
    roles.numeric = roles.numeric[:400]
    return roles


def infer_org_type(file_name: str) -> str | None:
    n = file_name.lower().replace("_", "-")
    if "non-acute" in n:
        return "Non-acute hospital"
    if "acute" in n:
        return "Acute"
    if "ambulance" in n:
        return "Ambulance"
    return None


_TABLE_RE = re.compile(r"(?i)^(core\s*\d+)")
_DIM_SKIP = ("region", "ics", "date", "month", "level", "code", "name", "classification_code")


def _table_prefix(source_key: str, file_name: str) -> str:
    """Metric code prefix. Multi-table releases (workforce 'Core 8. ...') get the table in the code."""
    m = _TABLE_RE.match(file_name.strip())
    return f"{source_key}:{slug(m.group(1))}:" if m else f"{source_key}:"


def _pick_breakdown(header, roles, rows, skip):
    """The categorical column to break totals down by: low cardinality, preferring 'group' columns."""
    best, best_rank = None, None
    for i, h in enumerate(header):
        s = slug(h)
        if i in skip or i in roles.numeric or any(t in s for t in _DIM_SKIP):
            continue
        vals = {r[i].strip() for r in rows[:50000] if i < len(r) and r[i].strip()}
        if not 2 <= len(vals) <= 15:
            continue
        rank = (0 if "group" in s else 1, len(vals))
        if best_rank is None or rank < best_rank:
            best, best_rank = i, rank
    return best


@dataclass
class LoadResult:
    metrics: list = field(default_factory=list)
    orgs: dict = field(default_factory=dict)  # code -> (name, type)
    profile: dict = field(default_factory=dict)
    mapper_status: str = "generic"  # ok | generic | needs_review
    row_count: int = 0
    truncated: bool = False


def _file_period(file_name: str, default_period: str | None) -> Period:
    return parse_period(unquote(file_name)) or parse_period(default_period) or UNKNOWN_PERIOD


def _metric(code, label, org, period: Period, value, source_key, unit=None):
    return {
        "ods_code": org, "source_key": source_key, "metric_code": code[:200], "metric_label": (label or code)[:400],
        "period": period.label, "period_sort": period.sort, "period_type": period.kind,
        "value": value, "unit": unit, "quality_flag": None,
    }


def load_generic(source_key: str, file_name: str, data: bytes, default_period: str | None = None) -> LoadResult:
    enc = detect_encoding(data)
    rows = iter_rows(data, enc)
    try:
        header = unique_header(next(rows))
    except StopIteration:
        return LoadResult(profile={"file": file_name, "error": "empty file"}, mapper_status="needs_review")

    sample = []
    for r in rows:
        sample.append(r)
        if len(sample) >= 500:
            break
    roles = detect_roles(header, sample)
    fperiod = _file_period(file_name, default_period)
    org_type = infer_org_type(file_name)
    result = LoadResult()
    profile = {
        "file": file_name, "encoding": enc, "columns": header, "shape": roles.shape,
        "roles": {k: (header[v] if isinstance(v, int) else v) for k, v in vars(roles).items()
                  if k not in ("numeric", "shape") and v is not None},
        "file_period": fperiod.label,
        "sample": [dict(zip(header, r)) for r in sample[:3]],
    }
    result.profile = profile

    if roles.org_code is None:
        profile["notes"] = ["no organisation code column detected; nothing loaded (profile only)"]
        profile["loader_version"] = LOADER_VERSION
        result.mapper_status = "needs_review"
        result.row_count = len(sample)
        return result

    cap = settings.max_metric_rows_per_file
    period_cache: dict[str, Period] = {}
    periods_seen: set = set()
    all_rows = sample + list(rows)
    prefix = _table_prefix(source_key, file_name)
    skip_dims = {roles.org_code, roles.org_name, roles.period}
    org_rows = [r[roles.org_code].strip() for r in all_rows if roles.org_code < len(r)]
    repeats = len(org_rows) > 1.2 * max(1, len(set(org_rows)))  # organisations repeat across dimension rows
    breakdown = _pick_breakdown(header, roles, all_rows, skip_dims) if roles.shape == "wide" and repeats else None
    profile["breakdown_column"] = header[breakdown] if breakdown is not None else None

    def period_of(r):
        if roles.period is None or roles.period >= len(r):
            return fperiod
        raw = r[roles.period].strip()
        if raw not in period_cache:
            period_cache[raw] = parse_period(raw) or fperiod
        return period_cache[raw]

    # wide tables repeat an organisation across dimension rows (staff group, role, area ...):
    # additive measures are summed so each (org, period, metric) has exactly one value.
    sums: dict = {}
    dup_rows = 0
    suppressed = 0
    seen_keys: set = set()
    measure_type_col = next((i for i, h in enumerate(header) if slug(h) == "measure_type"), None)
    total = 0
    for r in all_rows:
        total += 1
        if roles.org_code >= len(r):
            continue
        org = r[roles.org_code].strip()
        if not ODS_RE.match(org):
            continue
        result.orgs.setdefault(org, ((r[roles.org_name].strip() or None) if roles.org_name is not None and roles.org_name < len(r) else None, org_type))
        period = period_of(r)
        periods_seen.add(period.label)

        if roles.shape == "long":
            mid = r[roles.metric_id].strip() if roles.metric_id < len(r) else ""
            if not mid:
                continue
            label = r[roles.metric_name].strip() if roles.metric_name is not None and roles.metric_name < len(r) else mid
            if measure_type_col is not None and measure_type_col < len(r) and r[measure_type_col].strip():
                label = f"{label} [{r[measure_type_col].strip()}]"
            code = f"{prefix}{slug(mid)}"
            raw_val = r[roles.value] if roles.value < len(r) else None
            val = to_float(raw_val)
            if val is None:
                if raw_val is not None and raw_val.strip() in ("*", "-", ".."):
                    suppressed += 1
                continue
            key = (org, period.label, code)
            if key in seen_keys:
                dup_rows += 1
            seen_keys.add(key)
            result.metrics.append(_metric(code, label, org, period, val, source_key))
            if roles.score is not None and roles.score < len(r):
                sc = to_float(r[roles.score])
                if sc is not None:
                    result.metrics.append(_metric(code + ":score", f"{label} (score)", org, period, sc, source_key))
        else:
            bval = r[breakdown].strip() if breakdown is not None and breakdown < len(r) else None
            for i in roles.numeric:
                if i >= len(r):
                    continue
                val = to_float(r[i])
                if val is None:
                    continue
                col = slug(header[i])
                tk = (org, period, f"{prefix}{col}", f"{header[i]} (total)")
                sums[tk] = sums.get(tk, 0.0) + val
                if bval:
                    bk = (org, period, f"{prefix}{col}:{slug(bval)}", f"{header[i]}: {bval}")
                    sums[bk] = sums.get(bk, 0.0) + val
        if len(result.metrics) + len(sums) >= cap:
            result.truncated = True
            break

    for (org, period, code, label), val in sums.items():
        unit = "fte" if "fte" in code else None
        result.metrics.append(_metric(code, label, org, period, round(val, 4), source_key, unit))

    result.row_count = total
    profile.update({
        "rows_read": total, "metrics_loaded": len(result.metrics), "orgs": len(result.orgs),
        "numeric_columns": len(roles.numeric), "periods": sorted(periods_seen)[:24], "truncated": result.truncated,
        "suppressed_values": suppressed, "duplicate_keys_in_long_file": dup_rows,
        "notes": ["wide table: additive measures summed per organisation" + (f" and by {header[breakdown]}" if breakdown is not None else "")]
        if roles.shape == "wide" else [],
    })
    profile["loader_version"] = LOADER_VERSION
    result.mapper_status = "generic" if result.metrics else "needs_review"
    return result


# ---------------------------------------------------------------- RTT


_BUCKET = re.compile(r"^gt_(\d+)(?:_to_(\d+))?_weeks")


def load_rtt(source_key: str, file_name: str, data: bytes, default_period: str | None = None) -> LoadResult:
    """RTT full CSV: aggregate incomplete pathways to one row per provider and month.

    Shape assumed from NHS England's published format: a Period column, provider
    org code and name, an 'RTT Part Type' (incomplete pathways are Part_2), a
    treatment function code (C_999 = all specialties) and week-bucket columns
    ('Gt 00 To 01 Weeks SUM 1' ... 'Gt 52 Weeks SUM 1') plus a total. If those
    columns are not there the loader falls back to the generic profile.
    """
    enc = detect_encoding(data)
    rows = iter_rows(data, enc)
    header = unique_header(next(rows))
    slugs = [slug(h) for h in header]

    def idx(*options):
        for o in options:
            if o in slugs:
                return slugs.index(o)
        return None

    i_org = idx("provider_org_code")
    i_name = idx("provider_org_name")
    i_period = idx("period")
    i_part = idx("rtt_part_type", "rtt_part_description")
    i_tfc = idx("treatment_function_code")
    i_total = idx("total_all", "total")
    buckets = [(i, int(m.group(1))) for i, s in enumerate(slugs) if (m := _BUCKET.match(s))]

    if None in (i_org, i_period, i_part, i_tfc, i_total) or not buckets:
        fallback = load_generic(source_key, file_name, data, default_period)
        fallback.mapper_status = "needs_review"
        fallback.profile["notes"] = ["RTT columns not as expected; fell back to generic loader"]
        return fallback

    result = LoadResult(mapper_status="ok")
    agg: dict = {}
    names: dict = {}
    total_rows = 0
    sample = []
    for r in rows:
        total_rows += 1
        if len(sample) < 3:
            sample.append(dict(zip(header, r)))
        if max(i_org, i_part, i_tfc, i_total) >= len(r):
            continue
        part = slug(r[i_part])
        if "part_2" not in part and "incomplete" not in part:
            continue
        if r[i_tfc].strip().upper() != "C_999":
            continue
        org = r[i_org].strip()
        if not ODS_RE.match(org):
            continue
        period = parse_period(r[i_period]) or _file_period(file_name, default_period)
        total = to_float(r[i_total]) or 0.0
        over18 = sum((to_float(r[i]) or 0.0) for i, lo in buckets if lo >= 18 and i < len(r))
        key = (org, period)
        a = agg.setdefault(key, [0.0, 0.0])
        a[0] += total
        a[1] += over18
        if i_name is not None and i_name < len(r):
            names.setdefault(org, r[i_name].strip() or None)

    for (org, period), (total, over18) in agg.items():
        if total <= 0:
            continue
        result.orgs.setdefault(org, (names.get(org), None))
        result.metrics.append(_metric("rtt:incomplete_pathways_total", "RTT incomplete pathways, all specialties", org, period, total, source_key, "count"))
        result.metrics.append(_metric("rtt:incomplete_over_18_weeks", "RTT incomplete pathways waiting over 18 weeks", org, period, over18, source_key, "count"))
        result.metrics.append(_metric("rtt:pct_within_18_weeks", "RTT share of incomplete pathways within 18 weeks", org, period, round(100 * (total - over18) / total, 2), source_key, "pct"))

    result.row_count = total_rows
    result.profile = {
        "file": file_name, "encoding": enc, "columns": header, "shape": "rtt", "sample": sample,
        "rows_read": total_rows, "metrics_loaded": len(result.metrics), "orgs": len(result.orgs),
        "periods": sorted({p.label for (_, p) in agg})[:24], "loader_version": LOADER_VERSION,
        "notes": ["Incomplete pathways (Part_2), all specialties (C_999), summed across commissioners. "
                  "pct_within_18_weeks = (total - waiting over 18 weeks) / total."],
    }
    return result


LOADERS = {"generic": load_generic, "rtt": load_rtt}


def get_loader(name: str):
    """Loader by name. eric_site is imported lazily: it imports helpers from this module."""
    if name == "eric_site":
        from app.sources.eric_site import load_eric_site
        return load_eric_site
    if name == "nof":
        from app.sources.nof import load_nof
        return load_nof
    return LOADERS.get(name, load_generic)
