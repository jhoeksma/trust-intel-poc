"""NHS England Digital Maturity Assessment (DMA) 2024 and 2025 -> trust digital maturity scores.

Source: NHS England "Digital Maturity Assessment: data report 2024 and 2025 results" (published 30 March 2026),
results data file v2 (.xlsx). Scores are on a 1-5 scale, a self-assessment against the What Good Looks Like framework.

Layout (sheets used):
* "SC - 2025 Pillar Summary": one row per provider and care setting with the seven 2025 pillar scores
  (Well Led, Ensure Smart Foundations, Safe Practice, Support Workforce, Empower People, Improve Care, Healthy Populations).
* "SC - 24 vs 25 Overall DMA": the overall score for 2025 and 2024, "for comparable domains only", so it can differ from
  the stand-alone 2025 score the publisher quotes elsewhere. There is no 2024 pillar breakdown in the file.
* ICB sheets are not loaded (ICBs are not trusts).

The file has NO ODS codes, only upper-case provider names, so rows are joined to organisations by normalised name
(unique matches only; hand fixes in data/reference/dma_overrides.csv: provider_name, ods_code). Unmatched names are
listed in the file profile, never guessed.

Care settings: multi-service trusts submit one entry per care setting (Acute, Community, Mental Health, Ambulance), so
there are 285 rows for 204 trusts. A trust's headline score uses its PRIMARY setting (Acute, then Ambulance, then Mental
Health, then Community) under the plain codes `dma:overall` and `dma:pillar_*`. The other settings are kept only as
`dma:overall_<setting>` so nothing is thrown away. The publisher advises comparing within one care setting.
"""
import csv
import io
import re
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import unquote

from app.periods import Period
from app.sources.cqc import _known_from_db, norm_name
from app.sources.loaders import LOADER_VERSION, LoadResult, _metric

OVERRIDES = Path(__file__).resolve().parents[2] / "data" / "reference" / "dma_overrides.csv"
SCALE = "1-5 scale, higher is more mature"
PILLARS = {
    "Well Led": ("well_led", "Well led"),
    "Ensure Smart Foundations": ("smart_foundations", "Smart foundations"),
    "Safe Practice": ("safe_practice", "Safe practice"),
    "Support Workforce": ("support_workforce", "Support workforce"),
    "Empower People": ("empower_people", "Empower people"),
    "Improve Care": ("improve_care", "Improve care"),
    "Healthy Populations": ("healthy_populations", "Healthy populations"),
}
PRIMARY_ORDER = ["Acute", "Ambulance", "Mental Health", "Community"]  # first present wins
SETTING_KEY = {"Acute": "acute", "Ambulance": "ambulance", "Mental Health": "mental_health", "Community": "community"}
Y2025, Y2024 = Period("2025", 202504, "year"), Period("2024", 202404, "year")  # DMA rounds run in the financial year


def _overrides() -> dict:
    if not OVERRIDES.exists():
        return {}
    with OVERRIDES.open(newline="", encoding="utf-8") as fh:
        return {norm_name(r["provider_name"]): r["ods_code"].strip() for r in csv.DictReader(fh) if r.get("provider_name") and r.get("ods_code")}


def _sheet_rows(wb, prefix: str):
    """Data rows of the first sheet whose title starts with prefix: header found by the 'Provider' cell."""
    for ws in wb.worksheets:
        if ws.title.strip().startswith(prefix):
            hdr, out = None, []
            for row in ws.iter_rows(values_only=True):
                cells = [str(c).strip() if c is not None else "" for c in row]
                if hdr is None:
                    if "Provider" in cells and "Care Setting" in cells:
                        hdr = cells
                    continue
                d = dict(zip(hdr, row))
                if d.get("Provider") and d.get("Care Setting"):
                    out.append(d)
            return hdr, out
    return None, []


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if 0 < f <= 5 else None


def load_dma(source_key: str, file_name: str, data: bytes, default_period: str | None = None,
             known_orgs: dict | None = None, overrides: dict | None = None) -> LoadResult:
    import openpyxl
    result = LoadResult()
    profile = {"file": unquote(file_name), "shape": "dma_workbook", "loader_version": LOADER_VERSION, "notes": []}
    result.profile = profile
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    _, pillar_rows = _sheet_rows(wb, "SC - 2025 Pillar")
    _, overall_rows = _sheet_rows(wb, "SC - 24 vs 25")
    if not pillar_rows and not overall_rows:
        profile["notes"] = ["no 'SC - 2025 Pillar Summary' or 'SC - 24 vs 25 Overall DMA' sheet found; nothing loaded"]
        result.mapper_status = "needs_review"
        return result

    known = known_orgs if known_orgs is not None else _known_from_db()
    overrides = overrides if overrides is not None else _overrides()
    names: dict[str, list] = defaultdict(list)
    for code, nm in known.items():
        if nm:
            names[norm_name(nm)].append(code)

    match: dict[str, str] = {}
    ambiguous, unmatched = [], []
    providers = {str(r["Provider"]).strip() for r in pillar_rows + overall_rows}
    for prov in sorted(providers):
        n = norm_name(prov)
        if n in overrides:
            if overrides[n] in known:
                match[prov] = overrides[n]
            else:
                unmatched.append(f"{prov} (override {overrides[n]} is not a known organisation)")
        elif len(names.get(n, [])) == 1:
            match[prov] = names[n][0]
        elif names.get(n):
            ambiguous.append(f"{prov}: {','.join(names[n])}")
        else:
            unmatched.append(prov)

    # one entry per (provider, setting)
    by_prov: dict[str, dict[str, dict]] = defaultdict(lambda: defaultdict(dict))
    for r in pillar_rows:
        prov, cs = str(r["Provider"]).strip(), str(r["Care Setting"]).strip()
        by_prov[prov][cs]["pillars"] = {k: _num(r.get(k)) for k in PILLARS}
    for r in overall_rows:
        prov, cs = str(r["Provider"]).strip(), str(r["Care Setting"]).strip()
        by_prov[prov][cs]["o25"], by_prov[prov][cs]["o24"] = _num(r.get("2025 Average")), _num(r.get("2024 Average"))

    claimed: dict[str, str] = {}
    primary_count = Counter()
    for prov, settings_ in by_prov.items():
        ods = match.get(prov)
        if not ods:
            continue
        if ods in claimed:
            profile["notes"].append(f"{ods} claimed by two DMA providers ({claimed[ods]}, {prov}); kept the first")
            continue
        claimed[ods] = prov
        primary = next((s for s in PRIMARY_ORDER if s in settings_), next(iter(settings_)))
        primary_count[primary] += 1
        flag = None if len(settings_) == 1 else f"primary_of_{len(settings_)}_settings"
        for cs, d in settings_.items():
            is_primary = cs == primary
            suffix = "" if is_primary else "_" + SETTING_KEY.get(cs, re.sub(r"\W+", "_", cs.lower()))
            for per, key in ((Y2025, "o25"), (Y2024, "o24")):
                if d.get(key) is not None:
                    m = _metric(f"dma:overall{suffix}", f"Digital maturity overall score, comparable domains ({SCALE})"
                                + ("" if is_primary else f", {cs} entry"), ods, per, d[key], source_key, "score")
                    m["quality_flag"] = flag
                    result.metrics.append(m)
            if is_primary:
                for col, (code, label) in PILLARS.items():
                    v = d.get("pillars", {}).get(col)
                    if v is not None:
                        m = _metric(f"dma:pillar_{code}", f"Digital maturity pillar: {label} ({SCALE})", ods, Y2025, v, source_key, "score")
                        m["quality_flag"] = flag
                        result.metrics.append(m)
                result.metrics.append(_metric("dma:care_setting", "Digital maturity: care setting of headline score (1 Acute, 2 Ambulance, 3 Mental Health, 4 Community)",
                                              ods, Y2025, PRIMARY_ORDER.index(primary) + 1, source_key, "code"))
        result.orgs.setdefault(ods, (None, None))

    result.row_count = len(pillar_rows) + len(overall_rows)
    profile.update({
        "provider_rows": len(pillar_rows), "overall_rows": len(overall_rows), "providers": len(providers),
        "matched_providers": len(match), "orgs": len(result.orgs), "metrics_loaded": len(result.metrics),
        "primary_settings": dict(primary_count), "unmatched_providers": unmatched, "ambiguous_names": ambiguous,
        "notes": profile["notes"] + ["Overall score covers comparable domains only, so it can differ from the stand-alone 2025 DMA score. "
                                     "Pillar scores are 2025 only (rounded to one decimal in the file)."],
    })
    result.mapper_status = "ok" if result.metrics and not unmatched else "needs_review" if not result.metrics else "ok"
    return result
