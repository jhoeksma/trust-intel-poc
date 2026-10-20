# Sources

All public, Open Government Licence v3.0 unless a publication page says otherwise. Checked 20 October 2026.

| Key | Dataset | Owner | Cadence | Loader | Notes |
|---|---|---|---|---|---|
| nof | NHS Oversight Framework trust data and league tables, Q1 2026/27 | NHS England | Quarterly | nof | Committed files (file:// seeds, from Jon's Numbers exports); override with SEED_URLS_NOF. OF5200 = adjusted segment, OF5203 unadjusted, OF5202 average score, OF5204 financial override. 2026/27 framework changed method; not comparable with 2025/26. Covers 202 trusts (134 acute, 10 ambulance, 58 mental health and community). |
| rtt | Referral to treatment waiting times, full CSV | NHS England | Monthly | rtt | Incomplete pathways (exactly Part_2), all specialties (C_999), summed across commissioners. August 2026 extract committed as a seed (one month; add earlier months for trend). |
| workforce | NHS Workforce Statistics, trusts and core organisations CSVs | NHS England | Monthly | generic | Zip of many CSVs; each with an organisation code is loaded. |
| eric | Estates Returns Information Collection, trust data | NHS England | Annual | generic (wide) | 2024/25 published October 2025. Some fields flagged unreliable by publisher. |
| eric_site | ERIC site-level return 2025/26, rolled up to trust | NHS England | Annual | eric_site | Committed file (file:// seed); override with SEED_URLS_ERIC_SITE. Holds the backlog, energy and estates cost fields the trust-level file lacks. |
| hes | Hospital Episode Statistics, admitted patient care, provider level | NHS England | Annual | generic | Counts episodes, not patients. Publisher notes a data error at RMC (Bolton) in 2024-25. |

Plus the FHI trust ODS code list (Jon, project files, 20 October 2026): the reference spine for organisation names and codes.

## Deferred
Trust accounts (TAC; list stops at 2023/24), National Cost Collection, SCMD prescribing (Phase 2), DM01 diagnostics, acute provider table.

## Out of scope
Record-level HES (needs DARS approval). Anything behind a login (including the full Model Health System). There is no NHS "claims" data.

## Adding a source
1. Add a `SourceSpec` in `app/sources/registry.py`.
2. Use the generic loader; write a specialised one in `loaders.py` only if needed, with a test.
3. Run a refresh, review the profile in the Sources tab, adjust.
4. Add a row here and a line in CHANGELOG.
