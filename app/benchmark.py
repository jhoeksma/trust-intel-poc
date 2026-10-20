"""Benchmarking: one metric across every organisation, and where one organisation sits.

Rules, kept deliberately simple so a number on screen can always be explained:

* A metric's value for an organisation is its latest value (highest period_sort). Periods can differ
  between organisations for slow-moving sources (CQC ratings carry their publication month); the
  period shown with each value is its own.
* Peer groups come from the NHS Oversight Framework: ambulance, mental health and community, acute.
  The NOF trust type is not kept on the organisation row, so it is inferred from which NOF measures
  an organisation reports (the same inference scripts/review.py uses). Organisations with no NOF
  data fall into "other" and are only ever compared nationally.
* Rank 1 is best when we know which direction is good (POLARITY below), otherwise rank 1 is the
  highest value and nothing is coloured good or bad. Ties share the better rank.
* better_than_pct is the share of the other organisations in the comparison that this one beats
  (polarity known) or sits above (polarity unknown).
"""
import math
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.indicators import SEGMENT_CODE
from app.models import Metric, Org

GROUP_LABELS = {"acute": "Acute trusts", "mhc": "Mental health and community trusts", "ambulance": "Ambulance trusts",
                "other": "Other organisations"}
SOURCE_LABELS = {"nof": "Oversight Framework", "rtt": "Waiting times (RTT)", "cqc": "CQC quality ratings",
                 "workforce": "Workforce", "eric": "Estates (ERIC, trust)", "eric_site": "Estates (ERIC, sites)",
                 "hes": "Hospital activity (HES)"}

# Direction in which a metric is "good". Anything not listed is neutral: ranked highest first, never coloured.
HIGHER_BETTER = {"cqc:overall", "cqc:safe", "cqc:effective", "cqc:caring", "cqc:responsive", "cqc:well_led",
                 "cqc:use_of_resources", "cqc:combined_quality", "rtt:pct_within_18_weeks"}
LOWER_BETTER = {"nof:of5200", "nof:of5202", "nof:of5203", "nof:of5204", "nof:league_rank",
                "rtt:incomplete_over_18_weeks", "rtt:incomplete_over_52_weeks", "rtt:pct_over_52_weeks",
                "rtt:incomplete_median_wait_weeks", "rtt:incomplete_p92_wait_weeks",
                "cqc:core_services_below_good", "cqc:core_services_below_good_pct"}
LOWER_BETTER_SUFFIX = {"backlog_total", "backlog_high_significant", "backlog_high_significant_share", "backlog_per_sqm",
                       "unsuitable_share", "empty_share", "energy_cost_per_sqm", "energy_kwh_per_sqm"}
LOWER_BETTER_NOF = [(4200, 4209), (4300, 4309)]  # domain average scores and domain segments (1 = best)

# Fields shown on every trust dashboard until the user changes them. An entry is an exact metric code or a
# bare suffix (matched against the part after the colon, so the ERIC derived fields resolve whatever the source key).
CORE_FIELDS = ["nof:of5200", "nof:of5202", "nof:league_rank", "cqc:overall", "rtt:pct_within_18_weeks",
               "rtt:pct_over_52_weeks", "rtt:incomplete_median_wait_weeks", "rtt:incomplete_pathways_total",
               "cqc:core_services_below_good_pct", "backlog_per_sqm"]

MIN_ORGS = 10
_cache: dict = {}


def polarity(code: str) -> str | None:
    """'higher' or 'lower' is better, or None when we do not claim a direction."""
    if code in HIGHER_BETTER:
        return "higher"
    if code in LOWER_BETTER or code.split(":", 1)[-1] in LOWER_BETTER_SUFFIX:
        return "lower"
    if code.startswith("nof:of") and code[6:].isdigit():
        n = int(code[6:])
        if any(lo <= n <= hi for lo, hi in LOWER_BETTER_NOF):
            return "lower"
    return None


def _companion(code: str) -> bool:
    """Rank and likely-range columns describe another metric; they are not comparable measures themselves."""
    return code.endswith(":rank") or code.endswith("_low") or code.endswith("_high")


def catalogue(db: Session) -> list[dict]:
    """Comparable metrics: at least MIN_ORGS organisations, companion columns removed."""
    stamp = db.scalar(select(func.max(Metric.id))) or 0
    hit = _cache.get("catalogue")
    if hit and hit[0] == stamp:
        return hit[1]
    rows = db.execute(
        select(Metric.metric_code, Metric.source_key, Metric.unit, func.max(Metric.metric_label),
               func.count(func.distinct(Metric.ods_code)), func.max(Metric.period_sort))
        .where(Metric.value.is_not(None)).group_by(Metric.metric_code, Metric.source_key, Metric.unit)
    ).all()
    out = []
    for code, source, unit, label, n, ps in rows:
        if n < MIN_ORGS or _companion(code):
            continue
        out.append({"metric_code": code, "label": label or code, "source": source,
                    "source_label": SOURCE_LABELS.get(source, source), "unit": unit, "orgs": n,
                    "latest_period_sort": ps, "polarity": polarity(code), "core": False, "core_rank": None})
    out.sort(key=lambda r: (r["source"], r["metric_code"]))
    by_code = {r["metric_code"]: r for r in out}
    for rank, want in enumerate(CORE_FIELDS):
        hit_code = want if want in by_code else next(
            (r["metric_code"] for r in out if r["metric_code"].split(":", 1)[-1] == want), None)
        if hit_code:
            by_code[hit_code]["core"], by_code[hit_code]["core_rank"] = True, rank
    _cache["catalogue"] = (stamp, out)
    return out


def core_codes(db: Session) -> list[str]:
    return [r["metric_code"] for r in sorted((r for r in catalogue(db) if r["core"]), key=lambda r: r["core_rank"])]


def latest_values(db: Session, code: str) -> dict[str, dict]:
    """ods_code -> {value, period} using each organisation's latest period."""
    out: dict[str, dict] = {}
    rows = db.execute(
        select(Metric.ods_code, Metric.value, Metric.period, Metric.period_sort)
        .where(Metric.metric_code == code, Metric.value.is_not(None)).order_by(Metric.period_sort.desc())
    )
    for ods, value, period, _ in rows:
        if ods not in out and value is not None and not math.isnan(value):
            out[ods] = {"value": float(value), "period": period}
    return out


def peer_groups(db: Session) -> dict[str, str]:
    """ods_code -> acute | mhc | ambulance | other (see module docstring)."""
    stamp = db.scalar(select(func.max(Metric.id))) or 0
    hit = _cache.get("groups")
    if hit and hit[0] == stamp:
        return hit[1]

    def has(*codes):
        return {o for (o,) in db.execute(select(Metric.ods_code).where(Metric.metric_code.in_(codes)).distinct())}
    amb, mhc, nof = has("nof:of0004"), has("nof:of0029", "nof:of0043"), has(SEGMENT_CODE)
    groups = {}
    for o in nof:
        groups[o] = "ambulance" if o in amb else "mhc" if o in mhc else "acute"
    _cache["groups"] = (stamp, groups)
    return groups


def group_of(groups: dict, ods: str) -> str:
    return groups.get(ods, "other")


def _pct(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return float("nan")
    k = (len(sorted_vals) - 1) * p
    lo, hi = math.floor(k), math.ceil(k)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


def stats(values: list[float]) -> dict:
    s = sorted(values)
    if not s:
        return {"n": 0}
    return {"n": len(s), "min": s[0], "p10": _pct(s, .1), "p25": _pct(s, .25), "median": _pct(s, .5),
            "p75": _pct(s, .75), "p90": _pct(s, .9), "max": s[-1], "mean": sum(s) / len(s),
            "distinct": len({round(v, 9) for v in s})}


def position(values: list[float], mine: float, pol: str | None) -> dict:
    """Rank (1 = best, or highest when no direction), share beaten and quartile, among `values` (which include mine)."""
    n = len(values)
    if pol == "lower":
        ahead = sum(1 for v in values if v < mine)
        behind = sum(1 for v in values if v > mine)
    else:  # higher is better, or neutral: highest first
        ahead = sum(1 for v in values if v > mine)
        behind = sum(1 for v in values if v < mine)
    others = max(n - 1, 1)
    beaten = round(100 * behind / others, 1)
    out = {"rank": ahead + 1, "n": n, "better_than_pct": beaten, "quartile": None}
    if pol:
        out["quartile"] = 1 if beaten >= 75 else 2 if beaten >= 50 else 3 if beaten >= 25 else 4
    return out


def metric_view(db: Session, code: str, group: str | None = None) -> dict | None:
    """Every organisation's latest value for one metric, with distribution stats; optionally one peer group."""
    meta = next((r for r in catalogue(db) if r["metric_code"] == code), None)
    if meta is None:
        return None
    vals = latest_values(db, code)
    groups = peer_groups(db)
    names = {o: n for o, n in db.execute(select(Org.ods_code, Org.name))}
    strain = latest_values(db, SEGMENT_CODE)
    pts = []
    for ods, v in vals.items():
        g = group_of(groups, ods)
        if group and g != group:
            continue
        pts.append({"ods_code": ods, "name": names.get(ods), "value": v["value"], "period": v["period"], "group": g,
                    "strain": int(strain[ods]["value"]) if ods in strain else None})
    pol = meta["polarity"]
    pts.sort(key=lambda p: (p["value"] if pol == "lower" else -p["value"], p["ods_code"]))
    return {**meta, "group": group, "groups": GROUP_LABELS, "stats": stats([p["value"] for p in pts]),
            "points": pts, "ranking": "best first" if pol else "highest first"}


def trust_benchmark(db: Session, ods: str, codes: list[str], scope: str = "peers") -> dict:
    """For each metric: this organisation's value and where it sits among peers (or nationally)."""
    groups = peer_groups(db)
    mine_group = group_of(groups, ods)
    cat = {r["metric_code"]: r for r in catalogue(db)}
    rows = []
    for code in codes:
        meta = cat.get(code)
        if meta is None:
            continue
        vals = latest_values(db, code)
        national = {o: v["value"] for o, v in vals.items()}
        peers = {o: v for o, v in national.items() if group_of(groups, o) == mine_group} if mine_group != "other" else {}
        use_peers = scope == "peers" and len(peers) >= 5 and ods in peers
        pool = peers if use_peers else national
        row = {**meta, "scope_used": "peers" if use_peers else "national", "peer_group": mine_group if use_peers else None,
               "value": None, "period": None, "stats": stats(list(pool.values())), "national_median": stats(list(national.values())).get("median")}
        if ods in vals:
            row["value"], row["period"] = vals[ods]["value"], vals[ods]["period"]
            if ods in pool:
                row.update(position(list(pool.values()), vals[ods]["value"], meta["polarity"]))
                med = row["stats"]["median"]
                row["vs_median"] = round(vals[ods]["value"] - med, 6)
        rows.append(row)
    return {"ods_code": ods, "peer_group": mine_group, "peer_group_label": GROUP_LABELS[mine_group],
            "scope": scope, "metrics": rows}
