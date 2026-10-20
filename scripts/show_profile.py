"""Print the latest loaded file profile for a source: python -m scripts.show_profile cqc [key ...]"""
import json
import sys

from sqlalchemy import select

from app.db import SessionLocal
from app.models import SourceFile

src, keys = sys.argv[1], sys.argv[2:]
with SessionLocal() as db:
    sf = db.scalars(select(SourceFile).where(SourceFile.source_key == src, SourceFile.status == "loaded").order_by(SourceFile.id.desc())).first()
    prof = (sf.profile or {}) if sf else {}
    print("PROFILE file", sf.file_name if sf else None)
    for k, v in prof.items():
        if keys and k not in keys:
            continue
        txt = json.dumps(v, ensure_ascii=False)
        print(f"PROFILE {k}: {txt[:1800]}")
