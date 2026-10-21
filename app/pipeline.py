"""Refresh pipeline: discover -> download -> load -> record.

Every file attempted leaves a `source_files` row, success or not, so the Sources
tab is an honest account of what worked. A file whose sha256 matches the last
successful load is skipped. Re-loading a changed file replaces that file's
metrics (matched on source_key + file_name), never duplicates them.
"""
import logging
import threading
import traceback
from urllib.parse import quote, unquote
from datetime import datetime, timezone

from sqlalchemy import delete, func, insert, select, text
from sqlalchemy.orm import Session

from app.db import SessionLocal, engine
from app.models import Metric, Org, RefreshRun, SourceFile
from app.reference import seed_orgs
from app.sources import fetch
from app.sources.discover import discover
from app.sources.loaders import LOADER_VERSION, LoadResult, get_loader, overrides_fingerprint
from app.sources.registry import SOURCES, SourceSpec

log = logging.getLogger("pipeline")
_lock = threading.Lock()
CHUNK = 5000


def _now():
    return datetime.now(timezone.utc)


def _store(db: Session, spec: SourceSpec, sf: SourceFile, res: LoadResult) -> None:
    old_ids = [r for (r,) in db.execute(
        select(SourceFile.id).where(SourceFile.source_key == spec.key, SourceFile.file_name.in_({sf.file_name, quote(sf.file_name), unquote(sf.file_name)}), SourceFile.id != sf.id)
    )]
    if old_ids:
        db.execute(delete(Metric).where(Metric.source_file_id.in_(old_ids)))
    for code, (name, org_type) in res.orgs.items():
        org = db.get(Org, code)
        if org is None:
            db.add(Org(ods_code=code, name=name, org_type=org_type, first_seen_source=spec.key))
        else:
            if name and not org.name:
                org.name = name
            if org_type and not org.org_type:
                org.org_type = org_type
    db.flush()
    if spec.snapshot and res.metrics:
        # a snapshot repeats unchanged facts every release; keep one row per (org, metric, period), the newest file's
        fresh = {(m["ods_code"], m["metric_code"], m["period"]) for m in res.metrics}
        stale = [i for i, o, c, p in db.execute(select(Metric.id, Metric.ods_code, Metric.metric_code, Metric.period).where(
            Metric.source_key == spec.key, Metric.source_file_id != sf.id)) if (o, c, p) in fresh]
        for i in range(0, len(stale), CHUNK):
            db.execute(delete(Metric).where(Metric.id.in_(stale[i:i + CHUNK])))
    rows = [dict(m, source_file_id=sf.id) for m in res.metrics]
    for i in range(0, len(rows), CHUNK):
        db.execute(insert(Metric), rows[i:i + CHUNK])
    sf.row_count = res.row_count
    sf.metric_rows = len(rows)
    sf.profile = res.profile
    sf.mapper_status = res.mapper_status
    sf.status = "loaded"


def _members(spec: SourceSpec, url: str, data: bytes) -> list[tuple[str, bytes]]:
    if spec.kind == "zip_csv" or url.lower().split("?")[0].endswith(".zip"):
        return fetch.csv_members(data)
    name = unquote(url.rsplit("/", 1)[-1])
    return [(name[:-3] if name.endswith(".gz") else name, data)]


def run_source(db: Session, key: str) -> dict:
    spec = SOURCES[key]
    summary = {"source": key, "files": 0, "loaded": 0, "unchanged": 0, "failed": 0, "notes": []}
    found = discover(spec)
    summary["notes"] = found.notes
    if not found.files:
        db.add(SourceFile(source_key=key, status="discovery_failed", licence=spec.licence,
                          error="; ".join(found.notes) or "no files found",
                          profile={"links_seen": found.links_seen[:80]}))
        db.commit()
        summary["failed"] += 1
        return summary

    loader = get_loader(spec.loader)
    # newest-first lists from discovery are capped per run; hand-supplied seed files are an explicit, finite list
    files = found.files if all(f.via == "seed_url" for f in found.files) else found.files[:3]
    for f in files:
        summary["files"] += 1
        try:
            data = fetch.download(f.url)
        except Exception as exc:  # noqa: BLE001
            db.add(SourceFile(source_key=key, page_url=f.page_url, file_url=f.url, status="download_failed",
                              error=str(exc)[:2000], licence=spec.licence))
            db.commit()
            summary["failed"] += 1
            continue
        digest = fetch.sha256(data)
        try:
            members = _members(spec, f.url, data)
        except Exception as exc:  # noqa: BLE001
            db.add(SourceFile(source_key=key, page_url=f.page_url, file_url=f.url, sha256=digest, size_bytes=len(data),
                              status="parse_failed", error=f"unzip: {exc}", licence=spec.licence))
            db.commit()
            summary["failed"] += 1
            continue
        for name, blob in members:
            prior = [p for (p,) in db.execute(select(SourceFile.profile).where(
                SourceFile.source_key == key, SourceFile.file_name.in_({name, quote(name)}),
                SourceFile.sha256 == fetch.sha256(blob), SourceFile.status == "loaded"))
                if (p or {}).get("loader_version") == LOADER_VERSION and (p or {}).get("overrides_sha") == overrides_fingerprint(key)]
            if prior:
                summary["unchanged"] += 1
                continue
            sf = SourceFile(source_key=key, page_url=f.page_url, file_url=f.url, file_name=name,
                            sha256=fetch.sha256(blob), size_bytes=len(blob), status=f.via, licence=spec.licence)
            db.add(sf)
            db.flush()
            try:
                res = loader(key, name, blob, spec.default_period)
                _store(db, spec, sf, res)
                summary["loaded"] += 1
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                sf = SourceFile(source_key=key, page_url=f.page_url, file_url=f.url, file_name=name,
                                sha256=fetch.sha256(blob), size_bytes=len(blob), status="parse_failed",
                                error=traceback.format_exc()[-2000:], licence=spec.licence)
                db.add(sf)
                summary["failed"] += 1
            db.commit()
    return summary


class _db_lock:
    """Cross-process lock (Postgres advisory lock, held on its own connection).

    Two refreshes overlapping, for example a cron run and a deploy-time run, both loaded
    the same new file and left duplicate rows. A second refresh now waits for the first,
    then sees the file as unchanged. A no-op on SQLite (tests).
    """
    KEY = 72401190

    def __enter__(self):
        self.conn = None
        if engine.dialect.name == "postgresql":
            self.conn = engine.connect()
            self.conn.execute(text("select pg_advisory_lock(:k)"), {"k": self.KEY})
        return self

    def __exit__(self, *exc):
        if self.conn is not None:
            try:
                self.conn.execute(text("select pg_advisory_unlock(:k)"), {"k": self.KEY})
            finally:
                self.conn.close()


def refresh(keys: list[str] | None = None, trigger: str = "manual") -> int:
    """Run the pipeline for the given sources (default all). Returns the RefreshRun id."""
    keys = keys or list(SOURCES)
    with _lock, _db_lock():
        db = SessionLocal()
        try:
            run = RefreshRun(trigger=trigger, status="running")
            db.add(run)
            db.commit()
            seed_orgs(db)
            results, failed, lines = [], 0, []
            for k in keys:
                try:
                    s = run_source(db, k)
                except Exception:  # noqa: BLE001 - one source failing must not stop the others
                    db.rollback()
                    s = {"source": k, "error": traceback.format_exc()[-1500:], "failed": 1}
                results.append(s)
                failed += 1 if s.get("failed") else 0
                lines.append(f"{k}: {({a: b for a, b in s.items() if a != 'notes'})}")
            run.finished_at = _now()
            run.status = "ok" if not failed else ("failed" if failed == len(keys) else "partial")
            run.summary = {"sources": results}
            run.log = "\n".join(lines)
            db.commit()
            log.info("refresh %s: %s", run.id, run.status)
            return run.id
        finally:
            db.close()


def refresh_in_background(keys: list[str] | None, trigger: str) -> None:
    threading.Thread(target=refresh, args=(keys, trigger), daemon=True).start()


def run_report(db: Session) -> str:
    """Plain-text summary of what is in the store: coverage per source, join rate, headline checks."""
    from sqlalchemy import func
    from app.reference import load_reference, load_successors
    lines = ["== coverage by source =="]
    for src, n, orgs, ps in db.execute(select(Metric.source_key, func.count(), func.count(func.distinct(Metric.ods_code)),
                                              func.max(Metric.period_sort)).group_by(Metric.source_key).order_by(Metric.source_key)):
        codes = db.scalar(select(func.count(func.distinct(Metric.metric_code))).where(Metric.source_key == src))
        lines.append(f"{src}: {n} rows, {codes} metric codes, {orgs} orgs, latest period key {ps}")
    ref = {r["ods_code"]: r for r in load_reference()}
    succ = load_successors()
    have = {c for (c,) in db.execute(select(Metric.ods_code).distinct())}
    matched = {c for c in ref if c in have or succ.get(c) in have}
    lines.append(f"== join == reference {len(ref)}, matched {len(matched)} ({100 * len(matched) / len(ref):.1f}%)")
    per_src = {}
    for src, ods in db.execute(select(Metric.source_key, Metric.ods_code).distinct()):
        per_src.setdefault(src, set()).add(ods)
    trusts = {c for c, r in ref.items() if r["kind"] == "Trust"}
    for src, orgs in sorted(per_src.items()):
        lines.append(f"  {src}: {len(orgs & set(ref))} of {len(ref)} reference orgs, {len(orgs - set(ref))} codes not in reference")
    allsrc = set.intersection(*per_src.values()) if per_src else set()
    lines.append(f"  trusts present in every loaded source: {len(allsrc & trusts)}")
    lines.append("== headline checks ==")
    for code in ("eric_site:backlog_total", "eric_site:backlog_high_significant", "eric_site:s02_01", "eric_site:energy_cost_total"):
        v, n = db.execute(select(func.sum(Metric.value), func.count()).where(Metric.metric_code == code)).one()
        lines.append(f"{code}: sum {v}, {n} trusts")
    from app.indicators import SEGMENT_CODE
    seg = dict(db.execute(select(Metric.value, func.count(func.distinct(Metric.ods_code))).where(Metric.metric_code == SEGMENT_CODE).group_by(Metric.value)).all())
    in_ref = db.scalar(select(func.count(func.distinct(Metric.ods_code))).where(Metric.metric_code == SEGMENT_CODE, Metric.ods_code.in_(list(ref))))
    lines.append(f"strain (NOF adjusted segment): {sum(seg.values())} trusts, {in_ref} in the FHI reference list; segments {dict(sorted(seg.items()))}")
    dup = db.scalar(select(func.count()).select_from(
        select(Metric.ods_code, Metric.metric_code, Metric.period).group_by(Metric.ods_code, Metric.metric_code, Metric.period)
        .having(func.count() > 1).subquery()))
    lines.append(f"duplicate (org, metric, period) keys: {dup}")
    unk = db.scalar(select(func.count()).where(Metric.period == "unknown"))
    lines.append(f"rows with unknown period: {unk}")
    fails = db.execute(select(SourceFile.source_key, SourceFile.status, SourceFile.error).where(
        SourceFile.status.in_(("discovery_failed", "download_failed", "parse_failed"))).order_by(SourceFile.id.desc()).limit(6)).all()
    for src, st, err in fails:
        lines.append(f"issue {src} {st}: {(err or '')[:160]}")
    return "\n".join(lines)
