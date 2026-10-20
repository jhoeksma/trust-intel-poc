"""FastAPI app: JSON API plus the single-page frontend.

Isolated from the main FHI client API on purpose (separate repo, database and
Railway project). Later, endpoints here can be lifted into that API using its
conventions. All /api routes and the page sit behind basic auth in production.
"""
import csv
import io
import secrets
from datetime import date
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy import delete, desc, func, select
from sqlalchemy.orm import Session

from app import benchmark, indicators
from app.config import settings
from app.db import get_db
from app.models import Metric, Org, RefreshRun, SourceFile, TrustSystem
from app.pipeline import refresh
from app.reference import load_reference
from app.sources.registry import SOURCES

security = HTTPBasic(auto_error=False)


def require_auth(creds: HTTPBasicCredentials | None = Depends(security)) -> None:
    if not settings.auth_required:
        return
    if not settings.basic_auth_user or not settings.basic_auth_password:
        raise HTTPException(503, "Auth is required but BASIC_AUTH_USER / BASIC_AUTH_PASSWORD are not set")
    ok = creds is not None and secrets.compare_digest(creds.username, settings.basic_auth_user) \
        and secrets.compare_digest(creds.password, settings.basic_auth_password)
    if not ok:
        raise HTTPException(401, "Authentication required", headers={"WWW-Authenticate": "Basic"})


app = FastAPI(title="FHI Trust Intelligence PoC", version="0.1.0")
STATIC = Path(__file__).parent / "static"


@app.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(select(1))
    return {"status": "ok", "env": settings.app_env}


@app.get("/", dependencies=[Depends(require_auth)])
def index():
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-store"})


@app.get("/api/trusts", dependencies=[Depends(require_auth)])
def trusts(db: Session = Depends(get_db)):
    return indicators.trust_list(db)


@app.get("/api/trusts/{ods}", dependencies=[Depends(require_auth)])
def trust(ods: str, db: Session = Depends(get_db)):
    card = indicators.scorecard(db, ods.upper())
    if card is None:
        raise HTTPException(404, "Unknown organisation code")
    return card


@app.get("/api/compare", dependencies=[Depends(require_auth)])
def compare(codes: str, db: Session = Depends(get_db)):
    wanted = [c.strip().upper() for c in codes.split(",") if c.strip()][:5]
    cards = [c for c in (indicators.scorecard(db, w) for w in wanted) if c]
    shared = {}
    for card in cards:
        for m in card["metrics"]:
            shared.setdefault(m["metric_code"], {"metric_code": m["metric_code"], "label": m["label"],
                                                 "source": m["source"], "values": {}})["values"][card["ods_code"]] = \
                {"value": m["value"], "period": m["period"]}
    rows = sorted(shared.values(), key=lambda r: (r["source"], r["metric_code"]))
    return {"trusts": [{"ods_code": c["ods_code"], "name": c["name"], "strain": c["strain"]["score"]} for c in cards],
            "rows": rows}


@app.get("/api/benchmark/metrics", dependencies=[Depends(require_auth)])
def benchmark_metrics(db: Session = Depends(get_db)):
    """Comparable metrics (at least 10 organisations), with the direction in which each is good and the core flag."""
    return benchmark.catalogue(db)


@app.get("/api/benchmark/metric", dependencies=[Depends(require_auth)])
def benchmark_metric(code: str, group: str | None = None, db: Session = Depends(get_db)):
    """One metric across every organisation (optionally one peer group), ranked, with distribution statistics."""
    if group is not None and group not in benchmark.GROUP_LABELS:
        raise HTTPException(422, "group must be one of " + ", ".join(benchmark.GROUP_LABELS))
    view = benchmark.metric_view(db, code, group)
    if view is None:
        raise HTTPException(404, "Unknown or too sparse metric (needs at least 10 organisations)")
    return view


@app.get("/api/benchmark/trust/{ods}", dependencies=[Depends(require_auth)])
def benchmark_trust(ods: str, codes: str = "", scope: str = "peers", db: Session = Depends(get_db)):
    """Where one organisation sits on each chosen metric. No codes given means the core fields."""
    if scope not in ("peers", "national"):
        raise HTTPException(422, "scope must be peers or national")
    ods = ods.upper()
    if db.get(Org, ods) is None:
        raise HTTPException(404, "Unknown organisation code")
    wanted = [c.strip() for c in codes.split(",") if c.strip()][:60]
    if not wanted:
        wanted = benchmark.core_codes(db)
    return benchmark.trust_benchmark(db, ods, wanted, scope)


@app.get("/api/sources", dependencies=[Depends(require_auth)])
def sources(db: Session = Depends(get_db)):
    files = db.execute(select(SourceFile).order_by(desc(SourceFile.retrieved_at)).limit(200)).scalars().all()
    return {
        "registry": [{"key": s.key, "name": s.name, "owner": s.owner, "cadence": s.cadence, "note": s.note}
                     for s in SOURCES.values()],
        "files": [{
            "id": f.id, "source": f.source_key, "file_name": f.file_name, "file_url": f.file_url, "status": f.status,
            "mapper_status": f.mapper_status, "retrieved_at": f.retrieved_at.isoformat() if f.retrieved_at else None,
            "rows": f.row_count, "metric_rows": f.metric_rows, "error": f.error, "profile": f.profile,
        } for f in files],
        "reference_coverage": _reference_coverage(db),
        "coverage": [{"source": s, "metrics": n, "orgs": o, "latest_period_sort": p}
                     for s, n, o, p in db.execute(select(
                         Metric.source_key, func.count(), func.count(func.distinct(Metric.ods_code)), func.max(Metric.period_sort)
                     ).group_by(Metric.source_key))],
    }


def _reference_coverage(db: Session) -> dict:
    """Join check: FHI reference list against organisations present in public data.

    A reference code counts as matched if it, or its successor (data/reference/code_successors.csv),
    has data. England-only trusts are reported separately from ICBs and non-English bodies.
    """
    from app.reference import load_successors
    ref = {r["ods_code"]: r for r in load_reference()}
    succ = load_successors()
    with_data = {c for (c,) in db.execute(select(Metric.ods_code).distinct())}
    matched = {c for c in ref if c in with_data or succ.get(c) in with_data}
    covered_public = set(ref) | set(succ.values())
    trusts = {c for c, r in ref.items() if r["kind"] == "Trust"}
    non_english = {c for c in trusts if c[:1] in ("S", "Z") or c.startswith("7A") or c in ("W01", "XDH", "T1520", "K0N6A", "RQF", "RT4")
                   or c.startswith("0")}
    english = trusts - non_english
    return {
        "reference_orgs": len(ref), "with_public_data": len(matched),
        "join_rate": round(len(matched) / len(ref), 3) if ref else None,
        "english_trusts_in_reference": len(english), "english_trusts_with_data": len(english & matched),
        "english_trust_join_rate": round(len(english & matched) / len(english), 3) if english else None,
        "english_trusts_without_data": sorted(english - matched),
        "reference_without_data": sorted(set(ref) - matched)[:100],
        "public_data_not_in_reference": sorted(with_data - covered_public)[:100],
    }


@app.get("/api/metrics", dependencies=[Depends(require_auth)])
def metric_catalogue(q: str = "", source: str | None = None, db: Session = Depends(get_db)):
    stmt = select(Metric.metric_code, Metric.metric_label, Metric.source_key, func.count(func.distinct(Metric.ods_code))) \
        .group_by(Metric.metric_code, Metric.metric_label, Metric.source_key).order_by(Metric.source_key, Metric.metric_code).limit(500)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(func.lower(Metric.metric_code).like(like) | func.lower(Metric.metric_label).like(like))
    if source:
        stmt = stmt.where(Metric.source_key == source)
    return [{"metric_code": c, "label": l, "source": s, "orgs": n} for c, l, s, n in db.execute(stmt)]


@app.get("/api/runs", dependencies=[Depends(require_auth)])
def runs(db: Session = Depends(get_db)):
    rs = db.execute(select(RefreshRun).order_by(desc(RefreshRun.started_at)).limit(20)).scalars().all()
    return [{"id": r.id, "started_at": r.started_at.isoformat(), "status": r.status, "trigger": r.trigger,
             "summary": r.summary, "log": r.log} for r in rs]


@app.post("/api/refresh", dependencies=[Depends(require_auth)])
def trigger_refresh(bg: BackgroundTasks, source: str | None = None):
    if source and source not in SOURCES:
        raise HTTPException(404, f"Unknown source {source}")
    bg.add_task(refresh, [source] if source else None, "api")
    return {"started": True, "source": source or "all"}


@app.post("/api/systems/import", dependencies=[Depends(require_auth)])
async def import_systems(file: UploadFile = File(...), replace: bool = True, db: Session = Depends(get_db)):
    """Load the trust-to-supplier overlay from CSV.

    Columns (header names case-insensitive, extras ignored): ods_code, category,
    supplier, product, contract_end (YYYY-MM-DD or DD/MM/YYYY), note.
    Proprietary data: lives in the database only, never in git.
    """
    text = (await file.read()).decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(400, "Empty CSV")
    cols = {c.strip().lower().replace(" ", "_"): c for c in reader.fieldnames}
    if "ods_code" not in cols:
        raise HTTPException(400, f"Need an ods_code column; got {list(cols)}")

    def get(row, name):
        return (row.get(cols[name]) or "").strip() if name in cols else ""

    def parse_date(s):
        for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
            try:
                return date.fromisoformat(s) if fmt == "%Y-%m-%d" else date(*reversed([int(x) for x in s.split("/")]))
            except ValueError:
                continue
        return None

    rows, unknown = [], set()
    known = {c for (c,) in db.execute(select(Org.ods_code))}
    for r in reader:
        code = get(r, "ods_code").upper()
        if not code:
            continue
        if code not in known:
            unknown.add(code)
        rows.append(TrustSystem(ods_code=code, category=get(r, "category") or None, supplier=get(r, "supplier") or None,
                                product=get(r, "product") or None, contract_end=parse_date(get(r, "contract_end")) if get(r, "contract_end") else None,
                                note=get(r, "note") or None))
    if replace:
        db.execute(delete(TrustSystem))
    db.add_all(rows)
    db.commit()
    return {"imported": len(rows), "codes_not_in_public_data": sorted(unknown)[:50],
            "join_rate": round(1 - len(unknown) / max(1, len({r.ods_code for r in rows})), 3)}
