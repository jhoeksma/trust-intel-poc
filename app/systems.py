"""FHI master installations file -> trust_systems (which system and supplier each trust runs, per department).

PROPRIETARY: this is FHI's own data. It is never committed (see .gitignore and CLAUDE.md); it is loaded into the
database only, through `POST /api/systems/upload` or `python -m scripts.load_systems <file.csv>`.

The master file (Numbers, exported to CSV) has one row per organisation, department and system, 39 columns, and
covers 459 organisations: English NHS trusts and ICBs, the other UK nations and private providers. `Trust_ID` is
FHI's own trust id, which `data/reference/trusts_ods.csv` (fhi_trust_id) maps to the ODS code; organisations outside
that list (devolved nations, private providers) are skipped and counted, not guessed.

Kept: rows with Has_System = Yes and a supplier, excluding Upd_Flag D (deleted). Columns: DepartmentName is the
category (EPR, PACS, Pharmacy ...), SupplierName the supplier, SystemName the product; the rest go into `detail`.
Suppliers are kept as FHI wrote them (trimmed); the source is already consistent for EPR.
"""
import csv
import io
import re
from collections import Counter
from datetime import date, datetime

from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from app.models import Org, TrustSystem
from app.reference import load_reference

DETAIL = {
    "Version": "version", "Date_Verified": "date_verified", "Contract_expiration_notes": "contract_expiry_notes",
    "Annual_renewal": "annual_renewal", "Plan_to_replace_system": "plan_to_replace", "Locally_Remotely_hosted": "hosting",
    "Remote_host_provider": "host_provider", "System_Outsourced": "outsourced", "Outsourcing_Company": "outsourcing_company",
    "Procurement_framework": "procurement_framework", "Contract_Status": "contract_status", "Total_Contract_Value": "contract_value_text",
    "Installed_notes": "installed_notes", "No_of_licenses": "licences", "Other_systems_integrated": "integrated_with",
    "LSP": "lsp", "Source": "source",
}
_DATES = ("%m/%d/%Y", "%d/%m/%Y", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S")


def _clean(v) -> str:
    return re.sub(r"\s+", " ", str(v or "").replace("\xa0", " ")).strip()


def _date(text: str) -> date | None:
    for f in _DATES:
        try:
            return datetime.strptime(text, f).date()
        except ValueError:
            continue
    return None


def fhi_to_ods() -> dict[str, str]:
    return {str(r["fhi_trust_id"]).strip(): r["ods_code"] for r in load_reference() if str(r.get("fhi_trust_id") or "").strip()}


def parse_master(data: bytes, mapping: dict[str, str] | None = None) -> tuple[list[dict], dict]:
    """CSV bytes -> (rows ready to insert, report). Rows are for known ODS codes only."""
    mapping = mapping if mapping is not None else fhi_to_ods()
    text = data.decode("utf-8-sig", errors="replace")
    rd = csv.DictReader(io.StringIO(text))
    need = {"Trust_ID", "DepartmentName", "SupplierName", "SystemName", "Has_System"}
    if not rd.fieldnames or not need <= set(rd.fieldnames):
        raise ValueError("not the master installations layout; needs columns " + ", ".join(sorted(need)))
    rows, skipped, unmapped = [], Counter(), {}
    total = 0
    for r in rd:
        total += 1
        if _clean(r.get("Upd_Flag")).upper() == "D":
            skipped["deleted_flag"] += 1
            continue
        if _clean(r.get("Has_System")).lower() != "yes" or not _clean(r.get("SupplierName")):
            skipped["no_system_or_supplier"] += 1
            continue
        raw = _clean(r.get("Trust_ID"))
        try:
            fid = str(int(float(raw)))
        except ValueError:
            skipped["no_trust_id"] += 1
            continue
        ods = mapping.get(fid)
        if not ods:
            skipped["not_in_reference"] += 1
            unmapped[fid] = (_clean(r.get("Foundation_Trust_Name")), _clean(r.get("Trust_Type")))
            continue
        detail = {new: _clean(r.get(old)) for old, new in DETAIL.items() if _clean(r.get(old)) not in ("", "None", "N/A", "#N/A")}
        detail["department_id"] = _clean(r.get("Department_ID"))
        end = _date(_clean(r.get("Contract_expiration_notes")))
        rows.append({
            "ods_code": ods, "category": _clean(r.get("DepartmentName"))[:80], "supplier": _clean(r.get("SupplierName"))[:200],
            "product": _clean(r.get("SystemName"))[:200] or None, "contract_end": end,
            "note": _clean(r.get("Notes")) or None, "detail": detail,
        })
    report = {
        "rows_read": total, "rows_loaded": len(rows), "organisations": len({r["ods_code"] for r in rows}),
        "skipped": dict(skipped), "unmapped_organisations": len(unmapped),
        "unmapped_sample": [f"{n} ({t})" for n, t in list(unmapped.values())[:15]],
        "categories": len({r["category"] for r in rows}),
    }
    return rows, report


def replace_all(db: Session, rows: list[dict]) -> dict:
    """Replace the whole table (the master file is a complete snapshot). Codes missing from `orgs` are added by name-less stub."""
    known = {c for (c,) in db.execute(select(Org.ods_code))}
    missing = sorted({r["ods_code"] for r in rows} - known)
    names = {r["ods_code"]: r["name"] for r in load_reference()}
    for code in missing:
        db.add(Org(ods_code=code, name=names.get(code), first_seen_source="systems"))
    db.flush()
    db.execute(delete(TrustSystem))
    now = datetime.now().astimezone()
    for i in range(0, len(rows), 1000):
        db.execute(insert(TrustSystem), [dict(r, loaded_at=now) for r in rows[i:i + 1000]])
    db.commit()
    return {"orgs_added": len(missing)}


def options(db: Session) -> dict:
    """Categories with the number of trusts using each, and per category the suppliers with trust counts."""
    cats: dict[str, set] = {}
    sups: dict[str, dict[str, set]] = {}
    for ods, cat, sup in db.execute(select(TrustSystem.ods_code, TrustSystem.category, TrustSystem.supplier)):
        if not cat or not sup:
            continue
        cats.setdefault(cat, set()).add(ods)
        sups.setdefault(cat, {}).setdefault(sup, set()).add(ods)
    return {
        "loaded": bool(cats),
        "categories": [{"category": c, "trusts": len(o)} for c, o in sorted(cats.items(), key=lambda kv: (kv[0] != "EPR", -len(kv[1]), kv[0]))],
        "suppliers": {c: [{"supplier": s, "trusts": len(o)} for s, o in sorted(d.items(), key=lambda kv: (-len(kv[1]), kv[0]))] for c, d in sups.items()},
    }
