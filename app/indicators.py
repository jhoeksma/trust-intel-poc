"""Derived views over the metric store: latest values, scorecard, strain score.

Strain score (1 = low, 5 = high) v0
-----------------------------------
Jon asked for a 1-5 strain indicator on the dashboard. Until the first live run
has shown which financial fields exist, v0 uses the NHS Oversight Framework
segment as a proxy (segment 1 = strong ... 4/5 = needing most support), clamped
to 1-5. `inputs` records exactly what drove the score so it is never a black box.
Financial inputs (deficit, agency spend, estates backlog) are added once the
field inventory is reviewed; see docs/DECISIONS.md D-006.
"""
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.models import Metric, Org, TrustSystem

SEGMENT_CODE = "nof:of5200"  # NOF "Adjusted segment" (OF5200); OF5203 is the unadjusted one


def latest_by_metric(db: Session, ods: str) -> list[dict]:
    """Latest and previous value for each metric of one trust."""
    codes = [ods] + [c for (c,) in db.execute(select(Org.ods_code).where(Org.current_code == ods))]
    rows = db.execute(
        select(Metric).where(Metric.ods_code.in_(codes), Metric.value.is_not(None))
        .order_by(Metric.metric_code, Metric.period_sort.desc())
    ).scalars().all()
    out: dict[str, dict] = {}
    for m in rows:
        d = out.setdefault(m.metric_code, {
            "metric_code": m.metric_code, "label": m.metric_label, "source": m.source_key, "unit": m.unit,
            "period": m.period, "value": m.value, "previous_period": None, "previous_value": None,
        })
        if d["period"] != m.period and d["previous_period"] is None:
            d["previous_period"], d["previous_value"] = m.period, m.value
    return sorted(out.values(), key=lambda d: (d["source"], d["metric_code"]))


def strain_from_metrics(metrics: list[dict]) -> dict:
    """Return {score, label, inputs, basis}. score is None when nothing usable exists."""
    seg = None
    for m in metrics:
        if m["metric_code"] == SEGMENT_CODE and m["value"] is not None and 1 <= m["value"] <= 5:
            seg = m
            break
    if seg is None:
        return {"score": None, "label": "No data", "inputs": [], "basis": "NOF segment not found"}
    score = int(round(seg["value"]))
    score = max(1, min(5, score))
    return {
        "score": score,
        "label": {1: "Low", 2: "Moderate-low", 3: "Moderate", 4: "High", 5: "Very high"}[score],
        "basis": "v0: NHS Oversight Framework segment used as proxy",
        "inputs": [{"metric": seg["metric_code"], "period": seg["period"], "value": seg["value"]}],
    }


def trust_list(db: Session) -> list[dict]:
    """One row per organisation with a strain score and headline numbers."""
    orgs = db.execute(select(Org).order_by(Org.name)).scalars().all()
    if not orgs:
        return []
    # one query for latest value of the few headline metrics, not a per-trust loop
    heads = {"rtt:pct_within_18_weeks": "rtt_pct_18w", "rtt:incomplete_pathways_total": "rtt_waiting"}
    latest = {}
    sub = (select(Metric.ods_code, Metric.metric_code, func.max(Metric.period_sort).label("ps"))
           .where(Metric.metric_code.in_(list(heads))).group_by(Metric.ods_code, Metric.metric_code).subquery())
    for m in db.execute(select(Metric).join(sub, and_(
            Metric.ods_code == sub.c.ods_code, Metric.metric_code == sub.c.metric_code, Metric.period_sort == sub.c.ps))).scalars():
        latest[(m.ods_code, m.metric_code)] = m.value
    seg_rows = db.execute(select(Metric).where(Metric.metric_code == SEGMENT_CODE, Metric.value.is_not(None))
                          .order_by(Metric.period_sort.desc())).scalars().all()
    segs: dict[str, dict] = {}
    for m in seg_rows:  # newest first, so the first seen per trust is the latest
        segs.setdefault(m.ods_code, {"metric_code": m.metric_code, "label": m.metric_label, "source": "nof",
                                     "value": m.value, "period": m.period})
    suppliers = {}
    for ods, sup in db.execute(select(TrustSystem.ods_code, TrustSystem.supplier)):
        suppliers.setdefault(ods, set()).add(sup)
    out = []
    for o in orgs:
        s = strain_from_metrics([segs[o.ods_code]]) if o.ods_code in segs else {"score": None, "label": "No data"}
        out.append({
            "ods_code": o.ods_code, "name": o.name, "org_type": o.org_type,
            "strain": s["score"], "strain_label": s["label"],
            "rtt_pct_18w": latest.get((o.ods_code, "rtt:pct_within_18_weeks")),
            "rtt_waiting": latest.get((o.ods_code, "rtt:incomplete_pathways_total")),
            "suppliers": sorted(x for x in suppliers.get(o.ods_code, set()) if x),
        })
    return out


def scorecard(db: Session, ods: str) -> dict | None:
    org = db.get(Org, ods)
    if org is None:
        return None
    metrics = latest_by_metric(db, ods)
    systems = db.execute(select(TrustSystem).where(TrustSystem.ods_code == ods)).scalars().all()
    return {
        "ods_code": ods, "name": org.name, "org_type": org.org_type,
        "strain": strain_from_metrics(metrics),
        "metrics": metrics,
        "systems": [{"category": s.category, "supplier": s.supplier, "product": s.product,
                     "contract_end": s.contract_end.isoformat() if s.contract_end else None, "note": s.note}
                    for s in systems],
    }
