"""CQC "Latest ratings" workbook -> provider-level quality ratings per organisation.

Source: https://www.cqc.org.uk/about-us/transparency/using-cqc-data (monthly .ods, OGL v3;
CQC must be acknowledged as the data source). The "Providers" sheet holds one row per
provider, rating domain and service group:

* Report Type "Provider": the provider-level (whole trust) rating. Service/Population
  Group "Overall" with Domain Safe / Effective / Caring / Responsive / Well-led / Overall,
  plus Use of Resources and Combined Quality Rating for some acute trusts. Trusts assessed
  under CQC's new approach record the overall rating as Group "Well-led", Domain "Overall"
  (stated in the file's README); when both exist the more recently published wins.
* Report Type "CoreService": ratings for each core service (maternity, urgent care ...).

Ratings are stored as numbers: 1 Inadequate, 2 Requires improvement, 3 Good, 4 Outstanding.
"Not rated" and "Insufficient evidence to rate" are not stored. A metric's period is the
month its rating was published, which may be years old; the snapshot month is used only
for core-service counts.

Joining to ODS codes: in order, a hand override, the Provider ODS Code column (only about 30 of 200
NHS providers fill it), the Provider ID itself (NHS providers use their ODS code as ID), and finally
normalised organisation name against the organisations already held
(unique matches only, flagged quality_flag="name_match"). Hand fixes go in
data/reference/cqc_overrides.csv (provider_id, ods_code, note). Unmatched NHS providers are
listed in the file profile. Load this source after the others so the names exist.

ICBs are not rated by CQC at provider level; independent and social-care providers are
loaded only when their ODS code is already a known organisation.
"""
import csv
import re
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import unquote

from app.periods import Period, parse_period
from app.sources.loaders import LOADER_VERSION, overrides_fingerprint, UNKNOWN_PERIOD, LoadResult, _metric
from app.sources.ods import iter_ods

OVERRIDES = Path(__file__).resolve().parents[2] / "data" / "reference" / "cqc_overrides.csv"
RATING = {"inadequate": 1, "requires improvement": 2, "good": 3, "outstanding": 4}
RATING_NAME = {v: k.capitalize() for k, v in RATING.items()}
SCALE = "1 Inadequate, 2 Requires improvement, 3 Good, 4 Outstanding"
KEY_QUESTIONS = {"safe": "Safe", "effective": "Effective", "caring": "Caring", "responsive": "Responsive", "well-led": "Well-led"}
EXTRA = {"use of resources": ("use_of_resources", "Use of Resources"), "combined quality rating": ("combined_quality", "Combined quality and resources rating")}
_ODS_LIKE = re.compile(r"^[A-Z0-9]{3,5}$")  # NHS providers use their ODS code as the CQC provider ID (independents use 1-nnnnnnnn)
_STOP = re.compile(r"\b(the|nhs|foundation|trust)\b")


def norm_name(name: str) -> str:
    s = (name or "").lower().replace("&", " and ").replace("’", "'")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = _STOP.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def _known_from_db() -> dict:
    from sqlalchemy import select
    from app.db import SessionLocal
    from app.models import Org
    with SessionLocal() as db:
        return {o.ods_code: o.name for o in db.scalars(select(Org))}


def _overrides() -> dict:
    if not OVERRIDES.exists():
        return {}
    with OVERRIDES.open(newline="", encoding="utf-8") as fh:
        return {r["provider_id"].strip(): r["ods_code"].strip() for r in csv.DictReader(fh) if r.get("provider_id") and r.get("ods_code")}


def _period(date_text) -> Period | None:
    m = re.match(r"(20\d{2})-(\d{2})", str(date_text or ""))
    if not m:
        return None
    y, mo = int(m.group(1)), int(m.group(2))
    return Period(f"{y}-{mo:02d}", y * 100 + mo, "month")


def _pick(rows: list[dict]):
    """Latest published rating among rows for one provider/group/domain; ties go to the lowest, flagged."""
    rated = [r for r in rows if str(r.get("Latest Rating", "")).strip().lower() in RATING]
    if not rated:
        return None
    newest = max(str(r.get("Publication Date", ""))[:10] for r in rated)
    cand = [r for r in rated if str(r.get("Publication Date", ""))[:10] == newest]
    cand.sort(key=lambda r: RATING[r["Latest Rating"].strip().lower()])
    return cand[0], len(cand) > 1 and len({c["Latest Rating"] for c in cand}) > 1


def load_cqc(source_key: str, file_name: str, data: bytes, default_period: str | None = None,
             known_orgs: dict | None = None, overrides: dict | None = None) -> LoadResult:
    known = known_orgs if known_orgs is not None else _known_from_db()
    overrides = overrides if overrides is not None else _overrides()
    result = LoadResult()
    hdr, rows = None, []
    for _, row in iter_ods(data, only_sheet="Providers"):
        if hdr is None:
            if "Provider ID" in row:
                hdr = row
            continue
        rows.append(dict(zip(hdr, row)))
    profile = {"file": unquote(file_name), "shape": "cqc_ratings", "loader_version": LOADER_VERSION, "notes": [], "provider_rows": len(rows)}
    result.profile = profile
    profile["overrides_sha"] = overrides_fingerprint("cqc")
    if not rows:
        profile["notes"] = ["no 'Providers' sheet or no rows; nothing loaded"]
        result.mapper_status = "needs_review"
        return result
    snapshot = parse_period(unquote(file_name).replace("_", " ")) or parse_period(default_period) or UNKNOWN_PERIOD

    by_prov: dict[str, list[dict]] = defaultdict(list)
    meta: dict[str, dict] = {}
    for r in rows:
        pid = str(r.get("Provider ID", "")).strip()
        if pid:
            by_prov[pid].append(r)
            meta.setdefault(pid, r)

    names: dict[str, list] = defaultdict(list)
    for code, nm in known.items():
        if nm:
            names[norm_name(nm)].append(code)

    method: dict[str, tuple[str, str]] = {}  # provider id -> (ods, how)
    ambiguous, unmatched_nhs, ods_unknown, conflicts = [], [], 0, []
    for pid, r in meta.items():
        is_nhs = r.get("Provider Type") == "NHS Healthcare Organisation"
        explicit = str(r.get("Provider ODS Code", "") or "").strip().upper()
        cands = names.get(norm_name(r.get("Provider Name", "")), []) if is_nhs else []
        if pid in overrides:
            method[pid] = (overrides[pid], "override")
        elif explicit and explicit in known:
            method[pid] = (explicit, "ods_code")
        elif _ODS_LIKE.match(pid) and pid in known:
            method[pid] = (pid, "provider_id")
            if cands and pid not in cands:
                conflicts.append(f"{pid} {r.get('Provider Name')}: name suggests {','.join(cands)}")
        elif is_nhs:
            if len(cands) == 1:
                method[pid] = (cands[0], "name_match")
            elif len(cands) > 1:
                ambiguous.append(f"{r.get('Provider Name')}: {','.join(cands)}")
            else:
                unmatched_nhs.append(f"{pid} {r.get('Provider Name')}" + (f" [{explicit}]" if explicit else ""))
        elif explicit:
            ods_unknown += 1

    # two providers pointing at one ODS code would collide; keep the one with an explicit code
    seen: dict[str, str] = {}
    for pid, (ods, how) in sorted(method.items(), key=lambda kv: kv[1][1] != "ods_code"):
        if ods in seen:
            profile["notes"].append(f"{ods} claimed by two CQC providers ({seen[ods]}, {pid}); kept the first")
            del method[pid]
        else:
            seen[ods] = pid

    overall_dist = Counter()
    for pid, (ods, how) in method.items():
        flag = "name_match" if how == "name_match" else None  # provider_id and ods_code joins are exact
        prov = [r for r in by_prov[pid] if r.get("Report Type") == "Provider"]
        grp = lambda g, d: [r for r in prov if r.get("Service / Population Group") == g and r.get("Domain") == d]

        def emit(code, label, pick, dup=False):
            if pick is None:
                return
            row, tie = pick
            per = _period(row.get("Publication Date")) or snapshot
            m = _metric(f"cqc:{code}", f"{label} ({SCALE})", ods, per, RATING[row["Latest Rating"].strip().lower()], source_key, "rating")
            m["quality_flag"] = "multiple_ratings" if tie else flag
            result.metrics.append(m)

        old, new = _pick(grp("Overall", "Overall")), _pick(grp("Well-led", "Overall"))
        chosen = old
        if new and (not old or str(new[0].get("Publication Date"))[:10] >= str(old[0].get("Publication Date"))[:10]):
            chosen = new
        emit("overall", "CQC overall rating", chosen)
        if chosen:
            overall_dist[chosen[0]["Latest Rating"].strip()] += 1
        for dom, label in KEY_QUESTIONS.items():
            emit(dom.replace("-", "_"), f"CQC {label} rating", _pick([r for r in grp("Overall", label)]))
        for dom, (code, label) in EXTRA.items():
            emit(code, f"CQC {label}", _pick([r for r in prov if r.get("Service / Population Group") == "Overall"
                                              and str(r.get("Domain", "")).lower() == dom]))

        # core services: latest Overall-domain rating for each service group
        svc: dict[str, list] = defaultdict(list)
        for r in by_prov[pid]:
            if r.get("Report Type") == "CoreService" and r.get("Domain") == "Overall":
                svc[r.get("Service / Population Group")].append(r)
        picked = [p[0] for p in (_pick(v) for v in svc.values()) if p]
        if picked:
            below = sum(1 for r in picked if RATING[r["Latest Rating"].strip().lower()] <= 2)
            for code, label, val, unit in (
                ("core_services_rated", "CQC core services with a published rating", len(picked), "count"),
                ("core_services_below_good", "CQC core services rated Requires improvement or Inadequate", below, "count"),
                ("core_services_below_good_pct", "CQC share of rated core services below Good", round(100 * below / len(picked), 1), "pct"),
            ):
                result.metrics.append(_metric(f"cqc:{code}", label, ods, snapshot, val, source_key, unit))
        result.orgs.setdefault(ods, (None, None))

    result.row_count = len(rows)
    profile.update({
        "providers": len(meta), "nhs_providers": sum(1 for r in meta.values() if r.get("Provider Type") == "NHS Healthcare Organisation"),
        "matched": dict(Counter(h for _, h in method.values())), "orgs": len(result.orgs), "metrics_loaded": len(result.metrics),
        "overall_ratings": dict(overall_dist), "snapshot": snapshot.label,
        "unmatched_nhs_providers": unmatched_nhs[:80], "unmatched_nhs_count": len(unmatched_nhs),
        "ambiguous_names": ambiguous[:20], "provider_id_vs_name_conflicts": conflicts[:40], "providers_with_ods_not_in_our_orgs": ods_unknown,
        "match_list": {pid: f"{o} ({h})" for pid, (o, h) in list(method.items())[:400]},
    })
    result.mapper_status = "ok" if result.metrics else "needs_review"
    return result
