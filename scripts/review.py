"""Completeness and coherence review of whatever is in the database.

    python -m scripts.review

Prints PASS / WARN / FAIL lines grouped by theme. Read-only. Designed to run both on a
local SQLite database built from the committed seed files and on the live Postgres
(via a one-off start command), so the same checks judge both. Checks that need a
source that is not loaded are skipped, not failed.
"""
import math
import re
import statistics
from collections import Counter, defaultdict

from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import Metric, Org, SourceFile
from app.reference import load_reference, load_successors

OUT: list[str] = []
TALLY = Counter()


def say(level: str, text: str):
    TALLY[level] += 1
    OUT.append(f"{level:5} {text}")


def head(text: str):
    OUT.append(f"\n== {text} ==")


def pearson(xs, ys):
    n = len(xs)
    if n < 8:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return None if sx == 0 or sy == 0 else sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)


def ranks(vals):
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    r = [0.0] * len(vals)
    for pos, i in enumerate(order):
        r[i] = pos
    return r


def main():
    db = SessionLocal()
    ref = {r["ods_code"]: r for r in load_reference()}
    succ = load_successors()
    trusts = {c for c, r in ref.items() if r["kind"] == "Trust"}
    orgs = {o.ods_code: o for o in db.scalars(select(Org))}

    # latest value per (code, org): {metric_code: {org: value}} and period of that value
    latest: dict[str, dict[str, float]] = defaultdict(dict)
    latest_ps: dict[str, dict[str, int]] = defaultdict(dict)
    unit_of: dict[str, str | None] = {}
    label_of: dict[str, str] = {}
    src_of: dict[str, str] = {}
    for m in db.execute(select(Metric.ods_code, Metric.metric_code, Metric.metric_label, Metric.source_key, Metric.period_sort,
                               Metric.value, Metric.unit).where(Metric.value.is_not(None))).all():
        o, code, label, src, ps, v, unit = m
        if ps >= latest_ps[code].get(o, -1):
            latest[code][o] = v
            latest_ps[code][o] = ps
        unit_of[code], label_of[code], src_of[code] = unit, label, src
    sources = sorted(set(src_of.values()))
    org_by_source: dict[str, set] = defaultdict(set)
    for code, d in latest.items():
        org_by_source[src_of[code]] |= set(d)

    def nof_group(o):
        """NOF trust type is not kept on the org row (FHI type wins), so infer it from the metrics a trust reports."""
        if o in latest.get("nof:of0004", {}):
            return "ambulance"
        if o in latest.get("nof:of0029", {}) or o in latest.get("nof:of0043", {}):
            return "mental health and community"
        return "acute"

    def has(code):
        return code in latest and len(latest[code]) > 0

    # ---------------------------------------------------------------- 1 completeness
    head("1. Completeness")
    if not sources:
        say("FAIL", "no metrics in the database")
    for s in sources:
        got = org_by_source[s]
        matched_t = {c for c in trusts if c in got or succ.get(c) in got}
        rows = db.scalar(select(func.count()).where(Metric.source_key == s))
        pct = 100 * len(matched_t) / max(1, len(trusts))
        say("INFO", f"{s}: {rows} rows, {len(got)} orgs; {len(matched_t)} of {len(trusts)} FHI trusts ({pct:.0f}%)")
    if sources:
        every = set.intersection(*[org_by_source[s] for s in sources])
        say("INFO", f"FHI trusts present in every loaded source: {len(every & trusts)} of {len(trusts)}")
        anywhere = set().union(*org_by_source.values())
        none = sorted(c for c in trusts if c not in anywhere and succ.get(c) not in anywhere)
        say("PASS" if not none else "WARN", f"FHI trusts with no data at all: {len(none)}" + (f" ({', '.join(none[:15])})" if none else ""))
        for s in sources:
            miss = sorted(c for c in trusts if c not in org_by_source[s] and succ.get(c) not in org_by_source[s])
            if miss and len(miss) < len(trusts):
                names = "; ".join(f"{c} {ref[c]['name'][:28]}" for c in miss[:8])
                say("INFO", f"{s} lacks {len(miss)} FHI trusts, e.g. {names}")
        icb_hits = [c for c, r in ref.items() if r["kind"] == "ICB" and c in anywhere]
        say("INFO", f"ICBs in FHI list with any data: {len(icb_hits)} of {sum(1 for r in ref.values() if r['kind']=='ICB')} (trust-level sources are not expected to cover ICBs)")

    headline = ["nof:of5200", "nof:league_rank", "rtt:pct_within_18_weeks", "rtt:incomplete_median_wait_weeks",
                "eric_site:backlog_total", "eric_site:backlog_per_sqm", "eric_site:energy_cost_total"]
    for code in headline:
        if has(code):
            n_ref = len([c for c in trusts if c in latest[code]])
            say("PASS" if n_ref >= 0.75 * len(trusts) else "INFO", f"{code}: {len(latest[code])} orgs, {n_ref} FHI trusts")
    fills = [(c, len(d)) for c, d in latest.items() if src_of[c] == "workforce"]
    if fills:
        say("INFO", f"workforce: {len(fills)} metric codes; fewest orgs {min(n for _, n in fills)}, most {max(n for _, n in fills)}")

    # per-source file health
    for src, st, ms, n in db.execute(select(SourceFile.source_key, SourceFile.status, SourceFile.mapper_status, func.count()).group_by(
            SourceFile.source_key, SourceFile.status, SourceFile.mapper_status)):
        if st != "loaded" or ms in ("needs_review",):
            say("WARN", f"file status {src}: {st}/{ms} x{n}")

    # ---------------------------------------------------------------- 2 validity
    head("2. Validity of values")
    bad_pct, bad_neg, bad_nan = [], [], []
    for code, d in latest.items():
        u = unit_of[code]
        for o, v in d.items():
            if v is None or math.isnan(v) or math.isinf(v):
                bad_nan.append((code, o))
            elif u in ("pct",) and not (0 <= v <= 100.0001) and not any(
                    w in (label_of.get(code) or "").lower() for w in ("surplus", "deficit", "variance", "difference", "cost")):
                bad_pct.append((code, o, v))
            elif u in ("count", "gbp", "sqm", "kwh", "fte", "wte") and v < 0:
                bad_neg.append((code, o, v))
    say("PASS" if not bad_nan else "FAIL", f"NaN/inf values: {len(bad_nan)}")
    say("PASS" if not bad_pct else "WARN", f"percent-unit values outside 0-100: {len(bad_pct)}" + (f" e.g. {bad_pct[:4]}" if bad_pct else ""))
    say("PASS" if not bad_neg else "WARN", f"negative counts/money/areas: {len(bad_neg)}" + (f" e.g. {bad_neg[:4]}" if bad_neg else ""))
    zero_all = [c for c, d in latest.items() if len(d) >= 20 and all(v == 0 for v in d.values())]
    say("PASS" if not zero_all else "WARN", f"metrics that are zero for every org (20+ orgs): {len(zero_all)}" + (f" e.g. {zero_all[:5]}" if zero_all else ""))
    const = [c for c, d in latest.items() if len(d) >= 30 and len(set(d.values())) == 1 and not all(v == 0 for v in d.values())]
    say("PASS" if not const else "WARN", f"metrics with one constant value across 30+ orgs: {len(const)}" + (f" e.g. {const[:5]}" if const else ""))
    for code in ("rtt:pct_within_18_weeks", "eric_site:backlog_per_sqm", "eric_site:energy_cost_per_sqm", "rtt:incomplete_median_wait_weeks"):
        d = latest.get(code)
        if d and len(d) >= 20:
            vals = sorted(d.values())
            med = statistics.median(vals)
            mad = statistics.median([abs(v - med) for v in vals]) or 1e-9
            out = sorted(((abs(v - med) / (1.4826 * mad), o, v) for o, v in d.items()), reverse=True)[:3]
            say("INFO", f"{code}: median {med:.2f}, min {vals[0]:.2f}, max {vals[-1]:.2f}; most extreme "
                + ", ".join(f"{o} {orgs[o].name[:22] if o in orgs and orgs[o].name else ''} {v:.1f}" for _, o, v in out))

    # ---------------------------------------------------------------- 3 internal coherence
    head("3. Internal coherence (within a source)")
    if has("nof:of5200"):
        seg = latest["nof:of5200"]
        say("PASS" if set(seg.values()) <= {1, 2, 3, 4, 5} else "FAIL", f"NOF segments take values {sorted(set(seg.values()))}")
        if has("nof:of5202"):
            by = defaultdict(list)
            for o, s in seg.items():
                if o in latest["nof:of5202"]:
                    by[s].append(latest["nof:of5202"][o])
            means = {s: round(sum(v) / len(v), 2) for s, v in sorted(by.items())}
            mono = all(a < b for a, b in zip(list(means.values()), list(means.values())[1:]))
            say("PASS" if mono else "FAIL", f"mean NOF average score rises with segment: {means}")
            # adjusted segment may differ from score-implied segment, but never by more than 1 band on average
        if has("nof:of5204"):
            fo = latest["nof:of5204"]
            worse = [o for o, f in fo.items() if f == 1 and seg.get(o, 0) < 3]
            say("INFO", f"financial override flagged for {sum(1 for f in fo.values() if f == 1)} trusts; of those {len(worse)} sit in segment 1-2")
        if has("nof:of5203"):
            diff = sum(1 for o in seg if o in latest["nof:of5203"] and seg[o] != latest["nof:of5203"][o])
            say("INFO", f"adjusted segment differs from unadjusted for {diff} trusts")
        if has("nof:league_rank") and has("nof:of5202"):
            by_type = defaultdict(list)
            for o, r in latest["nof:league_rank"].items():
                if o in latest["nof:of5202"]:
                    by_type[nof_group(o)].append((r, latest["nof:of5202"][o]))
            for t, pairs in by_type.items():
                if len(pairs) >= 8:
                    rho = pearson(ranks([p[0] for p in pairs]), ranks([p[1] for p in pairs]))
                    say("PASS" if rho and rho > 0.95 else "WARN", f"league rank vs average score ({t}, n={len(pairs)}): rank correlation {rho:.3f}")
        for lo, mid, hi in (("nof:league_rank_low", "nof:league_rank", "nof:league_rank_high"),):
            if all(has(c) for c in (lo, mid, hi)):
                bad = [o for o, r in latest[mid].items() if o in latest[lo] and o in latest[hi] and not (latest[lo][o] <= r <= latest[hi][o])]
                say("PASS" if not bad else "FAIL", f"league rank lies inside its likely range for all trusts (violations {len(bad)})")
        if has("nof:league_score_low"):
            bad = [o for o, s in latest["nof:of5202"].items() if o in latest["nof:league_score_low"] and not (latest["nof:league_score_low"][o] - 0.02 <= s <= latest["nof:league_score_high"][o] + 0.02)]
            say("PASS" if not bad else "WARN", f"average score lies inside its likely range (violations {len(bad)})")
        domain = [c for c in latest if re.match(r"nof:of43\d\d$", c)]
        if domain:
            n = {c: len(latest[c]) for c in domain}
            say("PASS" if len(set(n.values())) == 1 else "WARN", f"six NOF domain segments cover the same trusts: {n}")
            if len(set(n.values())) > 1:
                allt = set().union(*[set(latest[c]) for c in domain])
                for c in domain:
                    gone = sorted(allt - set(latest[c]))
                    if gone:
                        say("INFO", f"  {c} ({label_of.get(c, '')[:40]}) missing for: {', '.join(gone)}")
    else:
        say("SKIP", "NOF not loaded")

    if has("rtt:incomplete_pathways_total"):
        T, O18, O52 = latest["rtt:incomplete_pathways_total"], latest.get("rtt:incomplete_over_18_weeks", {}), latest.get("rtt:incomplete_over_52_weeks", {})
        bad1 = [o for o in T if o in O18 and O18[o] > T[o] + 0.5]
        bad2 = [o for o in O18 if o in O52 and O52[o] > O18[o] + 0.5]
        bad3 = [o for o, p in latest["rtt:pct_within_18_weeks"].items() if o in O18 and abs(p - 100 * (T[o] - O18[o]) / T[o]) > 0.02]
        say("PASS" if not (bad1 or bad2 or bad3) else "FAIL", f"RTT arithmetic: over-18 <= total ({len(bad1)} bad), over-52 <= over-18 ({len(bad2)} bad), pct matches counts ({len(bad3)} bad)")
        if has("rtt:incomplete_median_wait_weeks") and has("rtt:incomplete_p92_wait_weeks"):
            bad = [o for o, m in latest["rtt:incomplete_median_wait_weeks"].items() if latest["rtt:incomplete_p92_wait_weeks"].get(o, 1e9) < m]
            say("PASS" if not bad else "FAIL", f"RTT median wait <= 92nd percentile wait everywhere (violations {len(bad)})")
        nat, nat18, nat52 = sum(T.values()), sum(O18.values()), sum(O52.values())
        say("INFO", f"RTT national (all providers): {nat:,.0f} waiting, {100*(nat-nat18)/nat:.1f}% within 18 weeks, {nat52:,.0f} over 52 weeks")
        small = sum(1 for v in T.values() if v < 100)
        say("INFO", f"RTT providers with fewer than 100 incomplete pathways: {small} of {len(T)} (percentages unstable)")
        per = Counter(m for (m,) in db.execute(select(Metric.period).where(Metric.metric_code == "rtt:incomplete_pathways_total").distinct()))
        say("INFO", f"RTT periods loaded: {sorted(per)} (trend needs 2+)")
    else:
        say("SKIP", "RTT not loaded")

    if has("eric_site:backlog_total"):
        B, H = latest["eric_site:backlog_total"], latest.get("eric_site:backlog_high_significant", {})
        bad = [o for o in H if H[o] > B.get(o, 0) + 1]
        say("PASS" if not bad else "FAIL", f"ERIC backlog: high+significant <= total (violations {len(bad)})")
        sh = latest.get("eric_site:backlog_high_significant_share", {})
        say("PASS" if all(0 <= v <= 100.0001 or 0 <= v <= 1.0001 for v in sh.values()) else "WARN", f"ERIC high+significant share within range ({len(sh)} trusts)")
        tot, hs = sum(B.values()), sum(H.values())
        say("INFO", f"ERIC site backlog national £{tot/1e9:.2f}bn, of which high+significant £{hs/1e9:.2f}bn ({100*hs/tot:.0f}%)")
        gia = latest.get("eric_site:s02_01", {})
        pos = sum(1 for o in B if gia.get(o, 0) > 0)
        say("PASS" if pos == len(B) else "WARN", f"ERIC trusts with backlog also have floor area > 0: {pos} of {len(B)}")
        ec, en = latest.get("eric_site:energy_cost_total", {}), latest.get("eric_site:energy_kwh_total", {})
        rates = sorted(ec[o] / en[o] for o in ec if en.get(o, 0) > 0)
        if rates:
            say("PASS" if 0.05 <= statistics.median(rates) <= 0.5 else "WARN", f"ERIC implied energy price £/kWh: median {statistics.median(rates):.3f}, range {rates[0]:.3f}-{rates[-1]:.3f}")
    else:
        say("SKIP", "ERIC site not loaded")

    # ---------------------------------------------------------------- 4 cross-source coherence
    head("4. Cross-source coherence (do independent sources agree?)")
    ok_types = lambda codes: [o for o in codes if o in orgs and (orgs[o].org_type or "").lower().startswith("acute")]
    # NOF elective 18-week metric vs RTT
    cands = [c for c in latest if c.startswith("nof:of0") and "18 weeks" in (label_of.get(c) or "") and unit_of.get(c) == "pct"
             and not c.endswith(":rank") and "community" not in (label_of.get(c) or "").lower() and "elective" in (label_of.get(c) or "").lower()]
    nof18 = max(cands, key=lambda c: len(latest[c]), default=None)
    if nof18 and has("rtt:pct_within_18_weeks"):
        both = [o for o in latest[nof18] if o in latest["rtt:pct_within_18_weeks"]]
        r = pearson([latest[nof18][o] for o in both], [latest["rtt:pct_within_18_weeks"][o] for o in both])
        say("PASS" if r and r > 0.7 else "WARN", f"NOF {nof18} ('{label_of[nof18][:60]}') vs RTT within-18-weeks: n={len(both)}, r={r if r is None else round(r,2)}")
        gaps = sorted(((abs(latest[nof18][o] - latest["rtt:pct_within_18_weeks"][o]), o) for o in both), reverse=True)[:4]
        say("INFO", "largest NOF-vs-RTT gaps: " + "; ".join(f"{o} {orgs[o].name[:24] if o in orgs and orgs[o].name else ''} NOF {latest[nof18][o]:.1f} vs RTT {latest['rtt:pct_within_18_weeks'][o]:.1f}" for _, o in gaps))
    else:
        say("SKIP", "NOF/RTT 18-week comparison needs both sources")

    # NOF strain vs RTT/ERIC: worse segment should carry worse waits on average
    if has("nof:of5200") and has("rtt:pct_within_18_weeks"):
        by = defaultdict(list)
        for o, s in latest["nof:of5200"].items():
            if o in latest["rtt:pct_within_18_weeks"] and nof_group(o) == "acute" and latest["rtt:incomplete_pathways_total"].get(o, 0) >= 1000:
                by[s].append(latest["rtt:pct_within_18_weeks"][o])
        means = {s: (round(sum(v) / len(v), 1), len(v)) for s, v in sorted(by.items()) if v}
        vals = [m for m, _ in means.values()]
        say("PASS" if all(a >= b for a, b in zip(vals, vals[1:])) else "WARN", f"acute trusts: mean RTT % within 18 weeks by NOF segment (mean, n): {means}")
    if has("nof:of5200") and has("eric_site:backlog_per_sqm"):
        by = defaultdict(list)
        for o, s in latest["nof:of5200"].items():
            if o in latest["eric_site:backlog_per_sqm"]:
                by[s].append(latest["eric_site:backlog_per_sqm"][o])
        say("INFO", "mean ERIC backlog £/m2 by NOF segment: " + str({s: round(sum(v) / len(v)) for s, v in sorted(by.items())}))

    # size coherence: independent size measures should move together
    def size_pair(a, b, label):
        if has(a) and has(b):
            both = [o for o in latest[a] if o in latest[b] and latest[a][o] > 0 and latest[b][o] > 0
                    and (not (a.startswith("rtt:") or b.startswith("rtt:")) or nof_group(o) == "acute")]
            label += " (acute trusts)" if (a.startswith("rtt:") or b.startswith("rtt:")) else ""
            r = pearson([math.log(latest[a][o]) for o in both], [math.log(latest[b][o]) for o in both])
            say("PASS" if r and r > 0.6 else "WARN", f"{label}: n={len(both)}, log-log r={r if r is None else round(r,2)}")
        else:
            say("SKIP", f"{label}: needs {a} and {b}")

    wf_total = next((c for c in latest if c.startswith("workforce:") and c.endswith(":fte") and len(latest[c]) >= 150), None)
    wf_total = wf_total or next((c for c in sorted(latest, key=lambda c: -len(latest[c])) if c.startswith("workforce:") and "fte" in c), None)
    if wf_total:
        say("INFO", f"workforce size metric used: {wf_total} ({label_of.get(wf_total)}), {len(latest[wf_total])} orgs, national total {sum(latest[wf_total].values()):,.0f}")
    size_pair("rtt:incomplete_pathways_total", "eric_site:s02_01", "RTT waiting list vs ERIC floor area")
    if wf_total:
        size_pair(wf_total, "rtt:incomplete_pathways_total", "workforce FTE vs RTT waiting list")
        size_pair(wf_total, "eric_site:s02_01", "workforce FTE vs ERIC floor area")
    hes_ep = next((c for c in sorted(latest, key=lambda c: -len(latest[c])) if src_of[c] == "hes" and "fae" in c and len(latest[c]) >= 100), None)
    if hes_ep:
        size_pair(hes_ep, "rtt:completed_admitted", f"HES {hes_ep} vs RTT completed admitted pathways")
    eric_gia = next((c for c in latest if src_of[c] == "eric" and "gross_internal_floor_area" in c.lower().replace(" ", "_") + (label_of.get(c) or "").lower().replace(" ", "_")), None)
    if eric_gia and has("eric_site:s02_01"):
        both = [o for o in latest[eric_gia] if o in latest["eric_site:s02_01"] and latest[eric_gia][o] > 0]
        ratios = sorted(latest["eric_site:s02_01"][o] / latest[eric_gia][o] for o in both)
        if ratios:
            near = sum(1 for r in ratios if 0.9 <= r <= 1.1)
            say("PASS" if near >= 0.7 * len(ratios) else "WARN", f"ERIC trust file ({eric_gia}) vs ERIC site roll-up floor area: {near} of {len(ratios)} within 10% (median ratio {statistics.median(ratios):.2f}; different years)")
    else:
        say("SKIP", "ERIC trust vs site floor-area comparison: no floor-area metric found in the trust file")

    # ---------------------------------------------------------------- 5 identity
    head("5. Identity and joins")
    unnamed = [o for o in orgs.values() if not o.name]
    by_src = Counter(o.first_seen_source for o in unnamed)
    in_ref = sum(1 for o in unnamed if o.ods_code in ref)
    say("PASS" if not unnamed else "INFO", f"orgs without a name: {len(unnamed)} (first seen in {dict(by_src)}); {in_ref} are in the FHI list, so named from it")
    def norm(n):
        return re.sub(r"[^a-z0-9]", "", re.sub(r"(?i)\b(nhs|foundation|trust|the)\b", "", n or "").lower())
    clash = [(c, ref[c]["name"], orgs[c].name) for c in ref if c in orgs and orgs[c].name and norm(orgs[c].name) != norm(ref[c]["name"])]
    say("INFO", f"FHI name differs from public name after normalising for {len(clash)} of {len([c for c in ref if c in orgs])}")
    for c, a, b in clash[:6]:
        say("INFO", f"  {c}: FHI '{a[:45]}' vs source '{b[:45]}'")
    seen_multi = Counter()
    for s, got in org_by_source.items():
        for o in got:
            seen_multi[o] += 1
    stray = sorted((c for c, n in seen_multi.items() if n >= 3 and c not in ref and not any(succ.get(r) == c for r in ref)),
                   key=lambda c: -seen_multi[c])
    say("PASS" if not stray else "WARN", f"codes in 3+ sources but missing from the FHI list: {len(stray)}"
        + ("; " + ", ".join(f"{c} {orgs[c].name[:26] if c in orgs and orgs[c].name else ''}" for c in stray[:10]) if stray else ""))
    stale = [c for c in ref if succ.get(c)]
    say("INFO", f"stale-to-current code mappings in use: {len(stale)} ({', '.join(f'{c}->{succ[c]}' for c in stale)})")
    dup = db.scalar(select(func.count()).select_from(select(Metric.ods_code, Metric.metric_code, Metric.period).group_by(
        Metric.ods_code, Metric.metric_code, Metric.period).having(func.count() > 1).subquery()))
    say("PASS" if not dup else "FAIL", f"duplicate (org, metric, period) keys: {dup}")
    unk = db.scalar(select(func.count()).where(Metric.period == "unknown"))
    say("PASS" if not unk else "FAIL", f"rows with unknown period: {unk}")
    orphan = db.scalar(select(func.count()).where(Metric.source_file_id.is_(None)))
    say("PASS" if not orphan else "WARN", f"metric rows with no source file (no provenance): {orphan}")

    # ---------------------------------------------------------------- 6 timeliness
    head("6. Timeliness and comparability")
    for s in sources:
        per = db.execute(select(Metric.period, Metric.period_sort).where(Metric.source_key == s).distinct().order_by(Metric.period_sort)).all()
        say("INFO", f"{s}: periods {', '.join(p for p, _ in per[-6:])}" + (f" (+{len(per)-6} earlier)" if len(per) > 6 else ""))
    spans = {s: max(ps for (ps,) in db.execute(select(Metric.period_sort).where(Metric.source_key == s).distinct())) for s in sources}
    if spans:
        say("INFO", "latest period key by source: " + ", ".join(f"{s} {v}" for s, v in sorted(spans.items())) + " (financial years are keyed on April)")
        say("WARN", "sources describe different times: HES/ERIC are annual, NOF quarterly, RTT/workforce monthly; cross-source ratios mix periods")

    print("\n".join(OUT))
    print(f"\nSUMMARY: {TALLY['PASS']} pass, {TALLY['WARN']} warn, {TALLY['FAIL']} fail, {TALLY['SKIP']} skipped, {TALLY['INFO']} info")
    db.close()


if __name__ == "__main__":
    main()
