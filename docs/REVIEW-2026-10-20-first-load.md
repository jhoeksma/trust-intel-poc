# First load review, 20 October 2026

Run 1 (manual, 09:57 UTC) on Railway. Status: partial.

## Scorecard
| Source | Result | Metric rows | Orgs | Verdict |
|---|---|---|---|---|
| nof | discovery failed (page returned no links) | 0 | 0 | Not loaded. Blocks the strain score. |
| rtt | discovery failed (page returned no links) | 0 | 0 | Not loaded |
| workforce | 17 CSVs loaded via seed URL (index page 403) | 635,699 | 237 | Loaded but not analytically usable yet (dimensions collapsed) |
| eric | 1 CSV loaded via seed URL (index page 403) | 8,938 | 207 | Loaded; period lost; trust file lacks cost and backlog fields |
| hes | 1 CSV loaded via seed URL (index page 403) | 58,623 | 583 | Loaded; labels are codes; suppressed values dropped |

Join to the FHI reference list: 236 of 274 (86.1%). The 38 unmatched are mostly not trusts: NHS England region codes (7A1 to 7A7), central bodies, dummy codes (SA999 to SZ999, ZT001 to ZT005, XDH, W01, T1520). Likely genuine misses: RBZ (believed to be Northern Devon Healthcare, merged into Royal Devon in 2022, so a stale code), RQF, RT4, QRV, 0AR, 0CX, 0DE, 0DF, K0N6A: to check. 100 public codes are not in the reference list (13Q, GP and ICB-level codes such as ACG12, ADP02). Expected, since the public files cover more than trusts.

## Defects found
1. **Discovery is blocked from Railway.** NHS Digital index pages return 403 to our fetcher; england.nhs.uk pages return nothing parseable (empty link list, no error). Only files.digital.nhs.uk downloads work. The seed URLs saved the three loaded sources. NOF and RTT have no seed URLs, so they failed.
2. **Dimensions collapsed (workforce, Core 3/5/8/10/14/15/17).** Rows are org by staff group by role by area; the loader emits one metric (`workforce:fte`) per row, so one org has hundreds of values for the same org, metric and period. The scorecard shows an arbitrary one. Fix: sum additive measures per org (total FTE, headcount) and per main staff group.
3. **ERIC period unknown.** The file name is URL-encoded (`ERIC%20-%202024_25...`), so the financial-year pattern fails. Fix: decode file names before parsing periods. Affects 8,938 rows.
4. **ERIC trust file is thin on money.** 56 columns; no backlog maintenance, energy cost or PFI fields visible. Those sit in the separate site-level ERIC file, which needs adding and aggregating to trust level.
5. **HES labels are codes** (`FAE_SUM`, etc.) and suppressed values (`*`) are dropped silently. Fix: add a measure glossary and record suppression counts as quality flags.
6. **England, region and ICS-level workforce tables** (Core 1, 2, 4, 6, 7, 9, 11, 12, 13, 16) were profiled only (no organisation code). Correct behaviour, but there are useful national benchmarks in them.
7. **Strain score is blank** for every trust until NOF loads.

## What worked
Provenance, failure recording, seed fallback, schema detection on 19 files without human mapping, 86% join to the FHI list on the first pass, and the clean 403 diagnostics.

## Next fixes (in order)
1. Seed URLs for NOF and RTT (and make discovery fall back to a browser-like fetch or a stored URL list).
2. Aggregation in the wide loader and URL-decoded names.
3. ERIC site file; HES glossary.
4. Stale-code map (current_code) starting with RBZ.

---

# Second load (11:41 UTC, after fixes 0.2.0 to 0.3.1)

| Source | Rows | Metric codes | Orgs | Period | Change |
|---|---|---|---|---|---|
| workforce | 11,285 (was 635,699) | 62 | 237 | 2026-07 | One value per org, metric and period; staff-group breakdowns |
| eric (trust) | 8,938 | 44 | 207 | 2024/25 (was unknown) | Period fixed |
| eric_site (new) | 37,257 | 220 | 205 | 2025/26 | 2,923 sites rolled up |
| hes | 58,623 | 189 | 583 | 2024/25 | Unchanged; suppressed values now counted |
| nof, rtt | 0 | 0 | 0 | | Still blocked: england.nhs.uk returns a 1,999-byte page with no links to Railway |

Integrity: 0 duplicate (org, metric, period) keys; 0 rows with unknown period.

Join to FHI reference (274): 237 matched (86.5%) with the successor map. Per source: workforce 235, eric 200, eric_site 200, hes 151. Trusts present in all loaded sources: 151 (HES is the limit; it covers acute providers). The unmatched remainder is mostly non-English or non-trust bodies. Codes in public data but missing from the FHI list include RNK (Tavistock and Portman), RVJ (North Bristol), RY2 (Bridgewater Community), RY3 (Norfolk Community and Health Care): the FHI list should be extended.

ERIC site checks (2025/26): backlog £17.35bn across 203 trusts, of which £9.74bn rated high or significant risk; 27.9m m² gross internal floor area; £1.19bn energy cost; largest backlog Imperial College Healthcare (£992m). Verify these against the published ERIC national summary before any external use.

Open: NOF and RTT need hand-supplied URLs (`SEED_URLS_NOF`, `SEED_URLS_RTT`); the strain score stays blank until NOF loads. Cron schedule is daily 05:00 UTC; the first cron run has not been observed yet (the 11:34 test schedule did not fire, so scheduled execution is still unproven).

---

# Third load (12:20 UTC): NOF and RTT in

- nof: 202 trusts (134 acute, 10 ambulance, 58 mental health and community), 177 metric codes, Q1 2026/27. League tables agree with the trust data on segment, score and deficit flag for 202 of 202.
- Adjusted segment (OF5200) across 202 trusts: segment 1: 28, 2: 43, 3: 109, 4: 22. Strain score now populated for all 202 (199 in the FHI reference list).
- rtt: August 2026, 532 providers (144 in the FHI reference list; the rest are independent providers and non-trust organisations). National: 7.19m waiting, 65.2% within 18 weeks, 113k over 52 weeks.
- Defects found and fixed during this load: RTT part filter included Part_2A (unknown clock start), inflating the waiting list by 1.19m; seed files were capped at 3 per run; overlapping start-up refreshes double-loaded files (21,771 duplicate keys), now serialised by an advisory lock and cleaned by a forced reload. Duplicate keys after reload: 0.
- Open: the NOF reporting windows differ by metric (Jun-26, 2025, 12 months to June 2026); some values look odd (for example an acute trust with 6.39% on the 18-week community measure, ambulance response times of 1 to 5 minutes) and need checking against the published workbook before external use. RTT is one month only.
