"""Do more digitally mature trusts perform better? DMA scores set against NOF, CQC and finance outcomes.

Method (kept deliberately simple, so it can be defended in a sales conversation):

* Rank correlation (Spearman), not Pearson: DMA scores are a 1-5 self-assessment, CQC ratings are 1-4 and NOF segments
  are 1-4, none of which are interval data. Every correlation is signed so that POSITIVE always means "more digitally
  mature trusts do better" (outcomes where lower is better are flipped). 95% interval from the Fisher transformation.
* Quartile comparison: trusts are ranked by overall DMA score and cut into four equal groups; each outcome is averaged
  within each group, with the share doing well where that is meaningful (CQC Good or better, NOF segment 1 or 2).
* One headline DMA score per trust (its primary care setting), compared within a trust type by default because both the
  DMA and the NOF are designed to be read within like-for-like groups.
* This is association, not cause: bigger, better-funded trusts may do better on both. The API says so in `caveats`.
"""
import math

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import benchmark
from app.models import Metric, Org

OUTCOMES = [
    # key, label, metric code, better direction, share-doing-well test (label, fn) or None, group for the UI
    ("nof_score", "Oversight Framework average score", "nof:of5202", "lower", None, "NHS Oversight Framework"),
    ("nof_segment", "Oversight Framework segment", "nof:of5200", "lower", ("segment 1 or 2", lambda v: v <= 2), "NHS Oversight Framework"),
    ("nof_rank", "Oversight Framework league table rank", "nof:league_rank", "lower", None, "NHS Oversight Framework"),
    ("cqc_overall", "CQC overall rating", "cqc:overall", "higher", ("Good or Outstanding", lambda v: v >= 3), "CQC rating"),
    ("cqc_well_led", "CQC well-led rating", "cqc:well_led", "higher", ("Good or Outstanding", lambda v: v >= 3), "CQC rating"),
    ("fin_domain", "Finance, productivity and innovation domain score", "nof:of4203", "lower", None, "Financial position (Q1 2026/27 snapshot)"),
    ("fin_planned", "Planned surplus/deficit (% of income)", "nof:of0079", "higher", None, "Financial position (Q1 2026/27 snapshot)"),
    ("fin_variance", "Variance to plan year-to-date (%)", "nof:of0081", "higher", None, "Financial position (Q1 2026/27 snapshot)"),
    ("fin_override", "Financial override applied (1 = yes)", "nof:of5204", "lower", ("no override", lambda v: v == 0), "Financial position (Q1 2026/27 snapshot)"),
    ("rtt_18w", "RTT pathways within 18 weeks (%)", "rtt:pct_within_18_weeks", "higher", None, "Waiting times (acute only)"),
]
PILLARS = [("well_led", "Well led"), ("smart_foundations", "Smart foundations"), ("safe_practice", "Safe practice"),
           ("support_workforce", "Support workforce"), ("empower_people", "Empower people"), ("improve_care", "Improve care"),
           ("healthy_populations", "Healthy populations")]
DMA_MEASURES = [("overall", "Overall DMA score (2025)"), ("change", "Change in overall score, 2024 to 2025")] + \
               [("p_" + k, "Pillar: " + v) for k, v in PILLARS]
SETTINGS = {1: "Acute", 2: "Ambulance", 3: "Mental Health", 4: "Community"}
MIN_N = 12  # below this a correlation is shown as too few to read
CAVEATS = [
    "Association, not cause: larger, better-funded and teaching trusts may score higher on both digital maturity and performance.",
    "The DMA is a self-assessment (validated by NHS England, with a 100% return) on a 1-5 scale; scores are rounded to one decimal.",
    "The overall score is for comparable domains only, so it can differ from the stand-alone 2025 score NHS England quotes.",
    "Financial measures are a single snapshot (Q1 2026/27), not a trend, and the 2026/27 framework changed method.",
    "Multi-service trusts submit one DMA entry per care setting; each trust's headline is its primary setting (acute first).",
]


def _ranks(xs: list[float]) -> list[float]:
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def spearman(x: list[float], y: list[float]) -> dict | None:
    n = len(x)
    if n < MIN_N or len(set(x)) < 2 or len(set(y)) < 2:
        return None
    rx, ry = _ranks(x), _ranks(y)
    mx, my = sum(rx) / n, sum(ry) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    sxx, syy = sum((a - mx) ** 2 for a in rx), sum((b - my) ** 2 for b in ry)
    if sxx == 0 or syy == 0:
        return None
    r = max(-0.9999, min(0.9999, sxy / math.sqrt(sxx * syy)))
    z, se = math.atanh(r), 1 / math.sqrt(n - 3)
    return {"rho": round(r, 3), "lo": round(math.tanh(z - 1.96 * se), 3), "hi": round(math.tanh(z + 1.96 * se), 3), "n": n}


def _median(v: list[float]) -> float:
    s = sorted(v)
    m = len(s) // 2
    return s[m] if len(s) % 2 else (s[m - 1] + s[m]) / 2


def _all_periods(db: Session, code: str) -> dict[str, dict[int, float]]:
    out: dict[str, dict[int, float]] = {}
    for ods, ps, v in db.execute(select(Metric.ods_code, Metric.period_sort, Metric.value).where(Metric.metric_code == code, Metric.value.is_not(None))):
        out.setdefault(ods, {})[ps] = float(v)
    return out


def analyse(db: Session, group: str | None = None, subtype: str | None = None) -> dict:
    groups, subs = benchmark.peer_groups(db), benchmark.subtypes(db)
    names = {o: n for o, n in db.execute(select(Org.ods_code, Org.name))}
    overall = _all_periods(db, "dma:overall")
    setting = benchmark.latest_values(db, "dma:care_setting")
    pillars = {k: benchmark.latest_values(db, "dma:pillar_" + k) for k, _ in PILLARS}
    outs = {key: benchmark.latest_values(db, code) for key, _, code, *_ in OUTCOMES}

    trusts = []
    for ods, per in overall.items():
        g = benchmark.group_of(groups, ods)
        if group and g != group:
            continue
        if subtype and subs.get(ods) != subtype:
            continue
        latest_ps = max(per)
        prev = [p for p in per if p < latest_ps]
        dma = {"overall": per[latest_ps], "overall_period": latest_ps // 100,
               "change": round(per[latest_ps] - per[max(prev)], 3) if prev else None}
        for k, _ in PILLARS:
            dma["p_" + k] = pillars[k].get(ods, {}).get("value")
        trusts.append({
            "ods_code": ods, "name": names.get(ods), "group": g, "subtype": subs.get(ods), "subtype_label": benchmark.SUBTYPE_LABELS.get(subs.get(ods)),
            "care_setting": SETTINGS.get(int(setting[ods]["value"])) if ods in setting else None,
            "dma": dma, "outcomes": {k: outs[k][ods]["value"] for k in outs if ods in outs[k]},
        })
    trusts.sort(key=lambda t: -t["dma"]["overall"])

    corr: dict[str, dict] = {}
    for dkey, _ in DMA_MEASURES:
        corr[dkey] = {}
        for okey, _, _, better, *_ in OUTCOMES:
            pairs = [(t["dma"][dkey], t["outcomes"][okey]) for t in trusts if t["dma"].get(dkey) is not None and okey in t["outcomes"]]
            res = spearman([p[0] for p in pairs], [p[1] for p in pairs])
            if res and better == "lower":  # flip so positive always means "more mature does better"
                res = {**res, "rho": -res["rho"], "lo": -res["hi"], "hi": -res["lo"]}
            corr[dkey][okey] = res

    quartiles: dict[str, list] = {}
    ranked = [t for t in trusts]  # already highest DMA first
    cuts = []
    if len(ranked) >= 8:
        size = len(ranked) / 4
        # quartile 4 = most mature
        cuts = [ranked[round(i * size):round((i + 1) * size)] for i in range(4)][::-1]  # [Q1 lowest .. Q4 highest]
    for okey, label, _, better, good, _ in OUTCOMES:
        rows = []
        for qi, grp in enumerate(cuts, start=1):
            vals = [t["outcomes"][okey] for t in grp if okey in t["outcomes"]]
            if not vals:
                continue
            row = {"q": qi, "n": len(vals), "mean": round(sum(vals) / len(vals), 3), "median": round(_median(vals), 3),
                   "dma_min": min(t["dma"]["overall"] for t in grp), "dma_max": max(t["dma"]["overall"] for t in grp)}
            if good:
                row["good_pct"] = round(100 * sum(1 for v in vals if good[1](v)) / len(vals), 1)
            rows.append(row)
        quartiles[okey] = rows

    return {
        "group": group, "subtype": subtype, "n_trusts": len(trusts), "min_n": MIN_N,
        "dma_measures": [{"key": k, "label": l} for k, l in DMA_MEASURES],
        "outcomes": [{"key": k, "label": l, "code": c, "better": b, "group": gr, "good_label": g[0] if g else None}
                     for k, l, c, b, g, gr in OUTCOMES],
        "correlations": corr, "quartiles": quartiles, "trusts": trusts, "caveats": CAVEATS,
        "groups": benchmark.GROUP_LABELS, "subtype_labels": benchmark.SUBTYPE_LABELS,
    }
