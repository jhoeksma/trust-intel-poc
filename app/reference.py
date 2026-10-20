"""FHI's organisation reference list (data/reference/trusts_ods.csv).

Source: Jon's "NHS_Trusts with ods code.xlsx" in the project files (20 Oct 2026),
de-duplicated on ODS code (first row wins; later rows were ICS aliases) and with
rows lacking a valid code dropped. `kind` is Trust or ICB, inferred from the name.
It anchors names for the join: a public-data code missing from this list, or a
listed code with no public data, is reported as a join gap.
"""
import csv
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Org

REF = Path(__file__).resolve().parent.parent / "data" / "reference" / "trusts_ods.csv"
SUCCESSORS = REF.with_name("code_successors.csv")


def load_reference(path: Path = REF) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_successors(path: Path = SUCCESSORS) -> dict[str, str]:
    """Old ODS code -> current code, for mergers. Hand-maintained; each row needs checking against ODS."""
    if not path.exists():
        return {}
    with open(path, newline="", encoding="utf-8") as f:
        return {r["old_code"]: r["current_code"] for r in csv.DictReader(f)}


def seed_orgs(db: Session) -> int:
    """Insert reference organisations; FHI's name wins over names from public files."""
    existing = {o.ods_code: o for o in db.execute(select(Org)).scalars()}
    n = 0
    for r in load_reference():
        o = existing.get(r["ods_code"])
        if o is None:
            db.add(Org(ods_code=r["ods_code"], name=r["name"], org_type=r["kind"], first_seen_source="fhi_reference"))
            n += 1
        else:
            o.name = r["name"]
            o.org_type = r["kind"] if o.org_type in (None, "") else o.org_type
    for old, new in load_successors().items():
        o = existing.get(old) or db.get(Org, old)
        if o is not None:
            o.current_code = new
    db.commit()
    return n
