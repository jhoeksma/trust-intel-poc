"""python -m scripts.load_itspend path/to/FHI_IT_spend.xlsx  (proprietary: never commit the workbook)"""
import json
import sys

from app import itspend
from app.db import SessionLocal

if __name__ == "__main__":
    raw = open(sys.argv[1], "rb").read()
    res = itspend.load_itspend(raw)
    with SessionLocal() as db:
        itspend.store(db, sys.argv[1].split("/")[-1], raw, res)
    print(len(res.metrics), "metric rows")
    print(json.dumps(res.profile, indent=1))
