"""FastAPI app: JSON API plus the single-page frontend.

Isolated from the main FHI client API on purpose (separate repo, database and
Railway project). Later, endpoints here can be lifted into that API using its
conventions. All /api routes and the page sit behind basic auth in production.
"""
import csv
import io
from datetime import date
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy import delete, desc, func, select
from sqlalchemy.orm import Session

from app import accounts, benchmark, dma_analysis, indicators, itspend, systems
from app.config import settings
from app.db import get_db
from app.accounts import Principal, principal, require_admin, require_auth
from app.models import Metric, Org, RefreshRun, SourceFile, TrustSystem, User
from app.pipeline import refresh
from app.reference import load_reference
from app.sources.registry import SOURCES

app = FastAPI(title="FHI Trust Intelligence PoC", version="0.1.0")
STATIC = Path(__file__).parent / "static"


@app.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(select(1))
    return {"status": "ok", "env": settings.app_env}


@app.get("/")
def index(p: Principal | None = Depends(principal)):
    page = "index.html" if p else "login.html"  # the sign-in page is the only thing served without a session
    return FileResponse(STATIC / page, headers={"Cache-Control": "no-store"})


class RegisterIn(BaseModel):
    email: str
    name: str = ""
    password: str


class LoginIn(BaseModel):
    email: str
    password: str


@app.post("/api/auth/register")
def auth_register(body: RegisterIn, db: Session = Depends(get_db)):
    accounts.register(db, body.email, body.name, body.password)
    return {"ok": True, "message": "Thanks. An FHI admin needs to approve your account before you can sign in."}


@app.post("/api/auth/login")
def auth_login(body: LoginIn, db: Session = Depends(get_db)):
    uid, name = accounts.login(db, body.email, body.password)
    resp = JSONResponse({"ok": True, "name": name})
    resp.set_cookie(accounts.COOKIE, accounts.make_token(uid), max_age=settings.session_days * 86400, httponly=True,
                    samesite="lax", secure=settings.app_env == "production", path="/")
    return resp


@app.post("/api/auth/logout")
def auth_logout(response: Response):
    response.delete_cookie(accounts.COOKIE, path="/")
    return {"ok": True}


@app.get("/api/auth/me")
def auth_me(p: Principal = Depends(require_auth)):
    return {"email": p.email, "name": p.name, "is_admin": p.is_admin}


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str


@app.post("/api/auth/change_password")
def auth_change_password(body: ChangePasswordIn, p: Principal = Depends(require_auth), db: Session = Depends(get_db)):
    u = db.execute(select(User).where(User.email == p.email)).scalar_one_or_none() if p.via == "session" else None
    if u is None:
        raise HTTPException(409, "This sign-in has no stored password. The admin password is the BASIC_AUTH_PASSWORD variable on Railway.")
    accounts.change_password(db, u, body.current_password, body.new_password)
    return {"ok": True}


def _user_row(u: User) -> dict:
    return {"id": u.id, "email": u.email, "name": u.name, "status": u.status, "is_admin": u.is_admin,
            "created_at": u.created_at.isoformat() if u.created_at else None, "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None}


@app.get("/api/admin/users", dependencies=[Depends(require_admin)])
def admin_users(db: Session = Depends(get_db)):
    order = {"pending": 0, "approved": 1, "disabled": 2}
    us = db.execute(select(User)).scalars().all()
    return sorted((_user_row(u) for u in us), key=lambda r: (order.get(r["status"], 3), r["email"]))


@app.post("/api/admin/users/{uid}/{action}")
def admin_user_action(uid: int, action: str, p: Principal = Depends(require_admin), db: Session = Depends(get_db)):
    """approve | disable | make_admin | remove_admin | reset_password. An admin cannot disable or demote their own account.
    reset_password returns a one-off temporary password in the response; it is not stored anywhere readable."""
    u = db.get(User, uid)
    if u is None:
        raise HTTPException(404, "No such user")
    if action not in ("approve", "disable", "make_admin", "remove_admin", "reset_password"):
        raise HTTPException(422, "action must be approve, disable, make_admin, remove_admin or reset_password")
    if u.email == p.email and action in ("disable", "remove_admin"):
        raise HTTPException(409, "You cannot do that to your own account")
    if action == "approve":
        u.status = "approved"
    elif action == "disable":
        u.status = "disabled"
    elif action == "make_admin":
        u.is_admin, u.status = True, "approved"
    elif action == "reset_password":
        return {**_user_row(u), "temporary_password": accounts.reset_password(db, u)}
    else:
        u.is_admin = False
    db.commit()
    return _user_row(u)


@app.get("/api/trusts", dependencies=[Depends(require_auth)])
def trusts(db: Session = Depends(get_db)):
    rows = indicators.trust_list(db)
    groups, subs = benchmark.peer_groups(db), benchmark.subtypes(db)
    for r in rows:
        r["peer_group"] = benchmark.group_of(groups, r["ods_code"])
        r["subtype"] = subs.get(r["ods_code"])
    return rows


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


@app.get("/api/benchmark/groups", dependencies=[Depends(require_auth)])
def benchmark_groups(db: Session = Depends(get_db)):
    """Trust types and subtypes (with organisation counts) for filters."""
    return benchmark.group_options(db)


@app.get("/api/benchmark/metric", dependencies=[Depends(require_auth)])
def benchmark_metric(code: str, group: str | None = None, subtype: str | None = None, db: Session = Depends(get_db)):
    """One metric across every organisation (optionally one trust type or subtype), ranked, with distribution statistics."""
    if subtype is not None and subtype not in benchmark.SUBTYPE_LABELS:
        raise HTTPException(422, "subtype must be one of " + ", ".join(benchmark.SUBTYPE_LABELS))
    if group is not None and group not in benchmark.GROUP_LABELS:
        raise HTTPException(422, "group must be one of " + ", ".join(benchmark.GROUP_LABELS))
    view = benchmark.metric_view(db, code, group, subtype)
    if view is None:
        raise HTTPException(404, "Unknown or too sparse metric (needs at least 10 organisations)")
    return view


@app.get("/api/benchmark/metric/trend", dependencies=[Depends(require_auth)])
def benchmark_metric_trend(code: str, group: str | None = None, subtype: str | None = None, months: int = 24,
                           db: Session = Depends(get_db)):
    """One measure over time for a trust type or subtype: spread per period and every member's series."""
    if group is not None and group not in benchmark.GROUP_LABELS:
        raise HTTPException(422, "group must be one of " + ", ".join(benchmark.GROUP_LABELS))
    if subtype is not None and subtype not in benchmark.SUBTYPE_LABELS:
        raise HTTPException(422, "subtype must be one of " + ", ".join(benchmark.SUBTYPE_LABELS))
    out = benchmark.metric_trend(db, code, group, subtype, max(1, min(months, 60)))
    if out is None:
        raise HTTPException(404, "Unknown or too sparse metric (needs at least 10 organisations)")
    return out


@app.get("/api/dma/correlation", dependencies=[Depends(require_auth)])
def dma_correlation(group: str | None = None, subtype: str | None = None, category: str | None = None,
                    supplier: str | None = None, db: Session = Depends(get_db)):
    """Do more digitally mature trusts perform better? DMA scores against NOF, CQC and finance, with rank correlations and quartiles."""
    if group is not None and group not in benchmark.GROUP_LABELS:
        raise HTTPException(422, "group must be one of " + ", ".join(benchmark.GROUP_LABELS))
    if subtype is not None and subtype not in benchmark.SUBTYPE_LABELS:
        raise HTTPException(422, "subtype must be one of " + ", ".join(benchmark.SUBTYPE_LABELS))
    return dma_analysis.analyse(db, group, subtype, category or None, supplier or None)


@app.get("/api/benchmark/trust/{ods}", dependencies=[Depends(require_auth)])
def benchmark_trust(ods: str, codes: str = "", scope: str = "subtype", db: Session = Depends(get_db)):
    """Where one organisation sits on each chosen metric. No codes given means the core fields."""
    if scope not in ("subtype", "peers", "national"):
        raise HTTPException(422, "scope must be subtype, peers or national")
    ods = ods.upper()
    if db.get(Org, ods) is None:
        raise HTTPException(404, "Unknown organisation code")
    wanted = [c.strip() for c in codes.split(",") if c.strip()][:60]
    if not wanted:
        wanted = benchmark.core_codes(db)
    return benchmark.trust_benchmark(db, ods, wanted, scope)


@app.get("/api/benchmark/trust/{ods}/trend", dependencies=[Depends(require_auth)])
def benchmark_trend(ods: str, code: str, scope: str = "subtype", months: int = 24, db: Session = Depends(get_db)):
    """One measure over time for one organisation, against the median and middle half of its comparison group."""
    if scope not in ("subtype", "peers", "national"):
        raise HTTPException(422, "scope must be subtype, peers or national")
    ods = ods.upper()
    if db.get(Org, ods) is None:
        raise HTTPException(404, "Unknown organisation code")
    out = benchmark.trust_trend(db, ods, code, scope, max(2, min(months, 60)))
    if out is None:
        raise HTTPException(404, "Unknown or too sparse metric")
    return out


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


@app.post("/api/refresh", dependencies=[Depends(require_admin)])
def trigger_refresh(bg: BackgroundTasks, source: str | None = None):
    if source and source not in SOURCES:
        raise HTTPException(404, f"Unknown source {source}")
    bg.add_task(refresh, [source] if source else None, "api")
    return {"started": True, "source": source or "all"}


@app.post("/api/itspend/import", dependencies=[Depends(require_admin)])
async def import_itspend(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Load FHI's IT-spend workbook (FOI survey). Proprietary: database only. Replaces the previous itspend load."""
    raw = await file.read()
    try:
        res = itspend.load_itspend(raw)
    except (KeyError, ValueError, StopIteration) as e:
        raise HTTPException(400, f"Not the IT-spend workbook layout: {e!r}")
    if not res.metrics:
        raise HTTPException(400, "No IT spend rows found")
    itspend.store(db, file.filename or "FHI_IT_spend.xlsx", raw, res)
    return {"metric_rows": len(res.metrics), **res.profile}


@app.get("/api/systems/options")
def systems_options(db: Session = Depends(get_db)):
    """Categories (EPR first) with trust counts, and suppliers per category. loaded=false until the master file is uploaded."""
    return systems.options(db)


@app.post("/api/systems/import", dependencies=[Depends(require_admin)])
async def import_systems(file: UploadFile = File(...), replace: bool = True, db: Session = Depends(get_db)):
    """Load the trust-to-supplier overlay from CSV.

    Columns (header names case-insensitive, extras ignored): ods_code, category,
    supplier, product, contract_end (YYYY-MM-DD or DD/MM/YYYY), note.
    Proprietary data: lives in the database only, never in git.
    """
    raw = await file.read()
    text = raw.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(400, "Empty CSV")
    if {"Trust_ID", "DepartmentName", "SupplierName"} <= set(reader.fieldnames):
        # FHI master installations layout: full snapshot, mapped to ODS via fhi_trust_id
        try:
            mrows, report = systems.parse_master(raw)
        except ValueError as e:
            raise HTTPException(400, str(e))
        report.update(systems.replace_all(db, mrows))
        report["format"] = "master"
        return report
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
