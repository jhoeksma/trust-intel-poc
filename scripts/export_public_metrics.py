"""Export public-source metrics and the organisation reference to CSV for offline analysis.

Usage (from a machine that can reach the database):
    railway run python -m scripts.export_public_metrics out_dir

Excludes proprietary FHI sources (IT spend, installed systems): public data only.
"""
import csv
import sys
from pathlib import Path

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Metric, Org

PROPRIETARY = {"itspend"}  # TrustSystem (installed systems) is a separate table and is not exported

if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "export")
    out.mkdir(parents=True, exist_ok=True)
    with SessionLocal() as db:
        with open(out / "metrics.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["ods_code", "source_key", "metric_code", "metric_label", "period", "period_sort", "period_type", "value", "unit", "quality_flag"])
            n = 0
            for m in db.execute(select(Metric).where(Metric.source_key.notin_(PROPRIETARY))).scalars().yield_per(5000):
                w.writerow([m.ods_code, m.source_key, m.metric_code, m.metric_label, m.period, m.period_sort, m.period_type, m.value, m.unit, m.quality_flag]); n += 1
        cols = [c.name for c in Org.__table__.columns]
        with open(out / "organisations.csv", "w", newline="") as f:
            w = csv.writer(f); w.writerow(cols)
            for o in db.execute(select(Org)).scalars():
                w.writerow([getattr(o, c) for c in cols])
    print(f"wrote {n} metric rows to {out}")
