"""Benchmarking: one metric across every organisation, and where one organisation sits.

Rules, kept deliberately simple so a number on screen can always be explained:

* A metric's value for an organisation is its latest value (highest period_sort). Periods can differ
  between organisations for slow-moving sources (CQC ratings carry their publication month); the
  period shown with each value is its own.
* Peer groups come from the NHS Oversight Framework: ambulance, mental health and community, acute.
  The NOF trust type comes from the Trust_type column of the NOF files (metric nof:peer_group); where that is
  missing it is inferred from which NOF measures an organisation reports (as scripts/review.py does). Organisations with no NOF
  data fall into "other" and are only ever compared nationally.
* Within a trust type NOF also publishes a subtype (Acute - Teaching, Large, Medium, Multi-Service, Small, Specialist;
  Community, Mental Health and Learning Disability, Care Trust; Ambulance), written by the loader as nof:peer_subtype.
  Dashboards compare with the subtype by default, falling back to the type and then to everyone when fewer than
  MIN_PEERS (5) members have a value.
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

PEER_GROUP_CODE = "nof:peer_group"  # written by the NOF loader from each file's Trust_type
SUBTYPE_CODE = "nof:peer_subtype"  # ... and from Trust_subtype (see app/sources/nof.py SUBTYPES)
_GROUP_BY_VALUE = {1: "acute", 2: "mhc", 3: "ambulance"}
# code -> (key, label, group). Codes are the loader's; keys appear in URLs and the UI.
SUBTYPES = {11: ("acute_teaching", "Acute - Teaching", "acute"), 12: ("acute_large", "Acute - Large", "acute"),
            13: ("acute_medium", "Acute - Medium", "acute"), 14: ("acute_multi_service", "Acute - Multi-Service", "acute"),
            15: ("acute_small", "Acute - Small", "acute"), 16: ("acute_specialist", "Acute - Specialist", "acute"),
            21: ("community", "Community", "mhc"), 22: ("mhld", "Mental Health and Learning Disability", "mhc"),
            23: ("care_trust", "Care Trust", "mhc"), 31: ("ambulance", "Ambulance", "ambulance")}
SUBTYPE_LABELS = {k: lbl for k, lbl, _ in SUBTYPES.values()}
MIN_PEERS = 5
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
    return code.endswith(":rank") or code.endswith("_low") or code.endswith("_high") or code in (PEER_GROUP_CODE, SUBTYPE_CODE)


def catalogue(db: Session) -> list[dict]:
    """Comparable metrics: at least MIN_ORGS organisations, companion columns removed."""
    stamp = db.scalar(select(func.max(Metric.id))) or 0
    hit = _cache.get("catalogue")
    if hit and hit[0] == stamp:
        return hit[1]
    rows = db.execute(
        select(Metric.metric_code, Metric.source_key, Metric.unit, func.max(Metric.metric_label),
               func.count(func.distinct(Metric.ods_code)), func.max(Metric.period_sort), func.count(func.distinct(Metric.period_sort)))
        .where(Metric.value.is_not(None)).group_by(Metric.metric_code, Metric.source_key, Metric.unit)
    ).all()
    out = []
    for code, source, unit, label, n, ps, nper in rows:
        if n < MIN_ORGS or _companion(code):
            continue
        out.append({"metric_code": code, "label": label or code, "source": source,
                    "source_label": SOURCE_LABELS.get(source, source), "unit": unit, "orgs": n,
                    "latest_period_sort": ps, "periods": nper, "polarity": polarity(code), "core": False, "core_rank": None})
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
    for o in nof:  # fallback inference for NOF organisations whose files predate the peer_group metric
        groups[o] = "ambulance" if o in amb else "mhc" if o in mhc else "acute"
    for o, v in latest_values(db, PEER_GROUP_CODE).items():  # the publisher's own trust type wins
        if int(v["value"]) in _GROUP_BY_VALUE:
            groups[o] = _GROUP_BY_VALUE[int(v["value"])]
    _cache["groups"] = (stamp, groups)
    return groups


def group_of(groups: dict, ods: str) -> str:
    return groups.get(ods, "other")


def subtypes(db: Session) -> dict[str, str]:
    """ods_code -> subtype key (e.g. acute_teaching), from NOF's Trust_subtype. Organisations without one are absent."""
    stamp = db.scalar(select(func.max(Metric.id))) or 0
    hit = _cache.get("subtypes")
    if hit and hit[0] == stamp:
        return hit[1]
    out = {o: SUBTYPES[int(v["value"])][0] for o, v in latest_values(db, SUBTYPE_CODE).items() if int(v["value"]) in SUBTYPES}
    _cache["subtypes"] = (stamp, out)
    return out


def group_options(db: Session) -> dict:
    """Filter options with counts: trust types and subtypes among organisations NOF classifies."""
    groups, subs = peer_groups(db), subtypes(db)
    gc = {k: 0 for k in GROUP_LABELS}
    for o in set(groups) | set(subs):
        gc[group_of(groups, o)] += 1
    sc = {}
    for k in subs.values():
        sc[k] = sc.get(k, 0) + 1
    return {"groups": [{"key": k, "label": GROUP_LABELS[k], "n": n} for k, n in gc.items() if n],
            "subtypes": [{"key": k, "label": lbl, "group": g, "n": sc[k]} for _, (k, lbl, g) in sorted(SUBTYPES.items()) if k in sc]}


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


def metric_view(db: Session, code: str, group: str | None = None, subtype: str | None = None) -> dict | None:
    """Every organisation's latest value for one metric, with distribution stats; optionally one trust type or subtype."""
    meta = next((r for r in catalogue(db) if r["metric_code"] == code), None)
    if meta is None:
        return None
    vals = latest_values(db, code)
    groups, subs = peer_groups(db), subtypes(db)
    names = {o: n for o, n in db.execute(select(Org.ods_code, Org.name))}
    strain = latest_values(db, SEGMENT_CODE)
    pts = []
    for ods, v in vals.items():
        g = group_of(groups, ods)
        if group and g != group:
            continue
        if subtype and subs.get(ods) != subtype:
            continue
        pts.append({"ods_code": ods, "name": names.get(ods), "value": v["value"], "period": v["period"], "group": g,
                    "subtype": subs.get(ods), "subtype_label": SUBTYPE_LABELS.get(subs.get(ods)),
                    "strain": int(strain[ods]["value"]) if ods in strain else None})
    pol = meta["polarity"]
    pts.sort(key=lambda p: (p["value"] if pol == "lower" else -p["value"], p["ods_code"]))
    return {**meta, "group": group, "subtype": subtype, "groups": GROUP_LABELS, "subtype_labels": SUBTYPE_LABELS, "stats": stats([p["value"] for p in pts]),
            "points": pts, "ranking": "best first" if pol else "highest first"}


def metric_trend(db: Session, code: str, group: str | None = None, subtype: str | None = None, months: int = 24) -> dict | None:
    """One measure over time for a whole group: per-period spread, plus every member's series.

    Membership is by trust type/subtype only (not by having a value), so a series simply has gaps where an
    organisation did not report that month. periods[i] and every series' values[i] line up.
    """
    meta = next((r for r in catalogue(db) if r["metric_code"] == code), None)
    if meta is None:
        return None
    groups, subs = peer_groups(db), subtypes(db)
    by_org: dict[str, dict[int, float]] = {}
    labels: dict[int, str] = {}
    for o, per, ps, v in db.execute(select(Metric.ods_code, Metric.period, Metric.period_sort, Metric.value)
                                    .where(Metric.metric_code == code, Metric.value.is_not(None))):
        if math.isnan(v) or (group and group_of(groups, o) != group) or (subtype and subs.get(o) != subtype):
            continue
        by_org.setdefault(o, {})[ps] = float(v)
        labels[ps] = per
    keep = sorted(labels)[-months:]
    periods = []
    for ps in keep:
        st = stats([vals[ps] for vals in by_org.values() if ps in vals])
        periods.append({"period": labels[ps], "period_sort": ps, **{k: st.get(k) for k in ("n", "p10", "p25", "median", "p75", "p90")}})
    names = {o: n for o, n in db.execute(select(Org.ods_code, Org.name))}
    series = [{"ods_code": o, "name": names.get(o), "values": [round(vals[ps], 4) if ps in vals else None for ps in keep]}
              for o, vals in sorted(by_org.items()) if any(ps in vals for ps in keep)]
    return {**meta, "group": group, "subtype": subtype, "groups": GROUP_LABELS, "subtype_labels": SUBTYPE_LABELS,
            "periods_shown": len(keep), "periods": periods, "series": series}


def choose_pool(national: dict, ods: str, groups: dict, subs: dict, scope: str):
    """(kind, label, {ods: value}): the narrowest requested group with at least MIN_PEERS values that includes `ods`."""
    mine_group, mine_sub = group_of(groups, ods), subs.get(ods)
    pools = []
    if scope == "subtype" and mine_sub:
        pools.append(("subtype", SUBTYPE_LABELS[mine_sub], {o: v for o, v in national.items() if subs.get(o) == mine_sub}))
    if scope in ("subtype", "peers") and mine_group != "other":
        pools.append(("peers", GROUP_LABELS[mine_group], {o: v for o, v in national.items() if group_of(groups, o) == mine_group}))
    for kind, lbl, p in pools:
        if len(p) >= MIN_PEERS and ods in p:
            return kind, lbl, p
    return "national", "all organisations", national


def trust_trend(db: Session, ods: str, code: str, scope: str = "subtype", months: int = 24) -> dict | None:
    """One organisation's value by period against the median and middle half of its comparison group in that period.

    The group is chosen once, from latest values (as in trust_benchmark), then its members' values are read
    period by period; rank is among the group members that have a value in that period.
    """
    meta = next((r for r in catalogue(db) if r["metric_code"] == code), None)
    if meta is None:
        return None
    by_period: dict[int, dict[str, float]] = {}
    labels: dict[int, str] = {}
    latest: dict[str, tuple[int, float]] = {}
    for o, per, ps, v in db.execute(select(Metric.ods_code, Metric.period, Metric.period_sort, Metric.value)
                                    .where(Metric.metric_code == code, Metric.value.is_not(None))):
        if math.isnan(v):
            continue
        by_period.setdefault(ps, {})[o] = float(v)
        labels[ps] = per
        if o not in latest or ps > latest[o][0]:
            latest[o] = (ps, float(v))
    used, label, pool = choose_pool({o: v for o, (ps, v) in latest.items()}, ods, peer_groups(db), subtypes(db), scope)
    points = []
    for ps in sorted(by_period)[-months:]:
        here = by_period[ps]
        vals = [here[o] for o in pool if o in here]
        mine = here.get(ods)
        pt = {"period": labels[ps], "period_sort": ps, "value": mine, "n": len(vals)}
        if vals:
            st = stats(vals)
            pt.update({"median": st["median"], "p25": st["p25"], "p75": st["p75"]})
            if mine is not None:
                pt.update(position(vals if ods in pool else vals + [mine], mine, meta["polarity"]))
        points.append(pt)
    return {**meta, "ods_code": ods, "scope": scope, "scope_used": used, "peer_label": label, "points": points}


def trust_benchmark(db: Session, ods: str, codes: list[str], scope: str = "subtype") -> dict:
    """For each metric: this organisation's value and where it sits among its subtype, trust type or everyone.

    scope "subtype" falls back to the trust type, then to all organisations, whenever the narrower group has fewer
    than MIN_PEERS members with a value; scope "peers" starts at the trust type. Each row says which pool it used.
    """
    groups, subs = peer_groups(db), subtypes(db)
    mine_group, mine_sub = group_of(groups, ods), subs.get(ods)
    cat = {r["metric_code"]: r for r in catalogue(db)}
    rows = []
    for code in codes:
        meta = cat.get(code)
        if meta is None:
            continue
        vals = latest_values(db, code)
        national = {o: v["value"] for o, v in vals.items()}
        used, label, pool = choose_pool(national, ods, groups, subs, scope)
        row = {**meta, "scope_used": used, "peer_label": label, "peer_group": mine_group if used != "national" else None,
               "value": None, "period": None, "stats": stats(list(pool.values())), "national_median": stats(list(national.values())).get("median")}
        if ods in vals:
            row["value"], row["period"] = vals[ods]["value"], vals[ods]["period"]
            if ods in pool:
                row.update(position(list(pool.values()), vals[ods]["value"], meta["polarity"]))
                row["vs_median"] = round(vals[ods]["value"] - row["stats"]["median"], 6)
        rows.append(row)
    from app.reference import load_successors
    merged = load_successors().get(ods)
    merged_name = db.scalar(select(Org.name).where(Org.ods_code == merged)) if merged else None
    return {"ods_code": ods, "merged_into": merged, "merged_into_name": merged_name, "peer_group": mine_group,
            "peer_group_label": GROUP_LABELS[mine_group], "subtype": mine_sub, "subtype_label": SUBTYPE_LABELS.get(mine_sub),
            "scope": scope, "metrics": rows}
