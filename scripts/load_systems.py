"""Load FHI's master installations CSV into the database: python -m scripts.load_systems path/to/master.csv

The file is proprietary and must never be committed. Same code path as POST /api/systems/upload.
"""
import json
import sys

from app.db import SessionLocal
from app.systems import parse_master, replace_all

if __name__ == "__main__":
    rows, report = parse_master(open(sys.argv[1], "rb").read())
    with SessionLocal() as db:
        report.update(replace_all(db, rows))
    print(json.dumps(report, indent=1))
