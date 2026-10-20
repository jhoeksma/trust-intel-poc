"""Cron entry point: python -m scripts.refresh [source ...]

Runs migrations first (done in the start command), then refreshes the named
sources, or all of them. Exits non-zero only if every source failed.
"""
import logging
import sys

from app.db import SessionLocal
from app.models import RefreshRun
from app.pipeline import refresh

logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    keys = sys.argv[1:] or None
    run_id = refresh(keys, trigger="cron")
    with SessionLocal() as db:
        run = db.get(RefreshRun, run_id)
        print(run.log)
        print("status:", run.status)
        sys.exit(1 if run.status == "failed" else 0)
