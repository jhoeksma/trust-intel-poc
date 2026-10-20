# Data review: completeness and coherence, 20 October 2026

Run with `python -m scripts.review` against the live database after the CQC load. Result: 29 pass, 10 warn, 0 fail, 1 skipped. Sources loaded: NOF (Q1 2026/27), RTT (August 2026), ERIC trust (2024/25), ERIC site (2025/26), HES (2024/25), workforce (July 2026), CQC (October 2026 file).

## Completeness
| Source | Organisations | FHI trusts covered (of 238) |
|---|---|---|
| CQC | 200 | 199 (84%) |
| NOF | 202 | 200 |
| ERIC trust / site | 207 / 205 | 201 / 201 |
| Workforce | 237 | 200 |
| HES | 583 | 152 |
| RTT | 532 | 145 |

- Trusts present in every source: 127 of 238. The 37 FHI "trusts" with no data at all are not English NHS provider trusts: Welsh health boards (7A1 to 7A7), commissioning support units and regional bodies (0AR, 0CX, 0DE, 0DF), plus K0N6A, QRV, RQF, RT4 (to identify). All 36 ICBs have some data (workforce/HES), but are not rated by CQC or in NOF.
- Domain segments: Access domain segment missing for RBV, REN, RPY; Effectiveness domain segment missing for RY3, RY6, RY7, RYX (community trusts). Genuine gaps in the published file.
- NOF covers acute, ambulance, mental health and community trusts only; RTT includes independent providers (about 390 of 532 are outside the FHI list).
- CQC: 200 of 200 NHS providers matched (29 by ODS code column, 171 by Provider ID, which is the ODS code; 0 conflicts with name matching). 153 trusts have a published overall rating: 70 Good, 71 Requires improvement, 10 Outstanding, 2 Inadequate.
- Still missing from the FHI list but present in three or more sources: RY3 (Norfolk Community), RVJ (North Bristol).

## Validity
No NaN or infinite values; no percentages outside 0-100 (signed measures such as surplus/deficit excluded); no duplicate keys; no unknown periods; every metric row has a source file.
- Two negative estates cost values (ERIC S25_13 at RRK and RTG, -£5.96m and -£2.08m): published as negatives, likely credits; our `estates_cost_total` sums S25 lines, so treat those two trusts with care.
- One ERIC metric is zero everywhere (deaths from fires) and one site-type count is constant: genuine.

## Internal coherence (all pass)
- NOF: mean average score rises with segment (1.79, 2.14, 2.46, 2.89); league rank agrees with average score (rank correlation 0.99 acute, 0.95 mental health and community, 0.99 ambulance); every rank and score sits inside its published likely range; financial override flagged for 99 trusts, none in segments 1 or 2; the adjusted segment differs from the unadjusted for 21 trusts.
- RTT: over-18 <= total; over-52 <= over-18; stored percentage matches the counts; median <= 92nd percentile; national 7.19m waiting, 65.2% within 18 weeks.
- ERIC: high+significant backlog <= total; implied energy price median £0.12/kWh (range 0.03 to 0.23), plausible.

## Cross-source coherence (independent sources agree)
- NOF elective 18-week measure vs RTT within 18 weeks: r = 0.96 across 126 acute trusts. (An earlier check used a community-services measure and showed 0.15; the metric choice, not the data, was wrong.)
- Acute trusts' mean RTT % within 18 weeks falls as NOF segment worsens: 75.7 (segment 1), 67.7, 65.9, 60.5 (segment 4).
- Size measures move together: workforce FTE vs ERIC floor area r = 0.92 (201 trusts); HES episodes vs RTT completed admitted pathways r = 0.90 (400 providers).
- Weaker, as expected, where unlike organisations are mixed: RTT waiting list vs floor area 0.56 and vs FTE 0.50 before restricting to acute trusts.

## Warnings that remain
1. Mixed periods: HES and ERIC annual (2024/25, 2025/26), NOF quarterly, RTT/workforce/CQC monthly. Ratios across sources mix periods; label them.
2. Unverified against publications: ERIC national backlog £17.35bn with 56% rated high or significant; NOF values such as 6.39% on one acute trust's community 18-week measure and ambulance response times of 1 to 5 minutes. Check against the published workbooks before external use.
3. 141 organisations have no name from their source (workforce/HES carry codes only); the FHI list names those it covers.
4. RTT is one month; no trend until earlier months load.
5. Old `discovery_failed` rows for NOF and RTT remain in the file history (superseded by the seeded loads).
6. CQC ratings carry their own publication dates, some years old (Use of Resources 2019); show the date beside the rating.

## Fixes made during the review
RTT loader counted unknown-clock-start pathways; two start-up refreshes double-loaded files (now serialised); NOF segment code corrected (OF5200); review checks themselves corrected (community vs elective measure, mixed trust types in rank correlation).
