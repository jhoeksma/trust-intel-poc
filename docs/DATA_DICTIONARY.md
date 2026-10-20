# Data dictionary

- **orgs**: ods_code (key), name, org_type, current_code (successor, once known), first_seen_source.
- **source_files**: one row per file attempted. status, mapper_status (ok, generic, needs_review), sha256, url, row and metric counts, profile (columns, detected roles, sample rows, periods), error, licence.
- **metrics**: ods_code, source_key, metric_code (`<source>:<slug>`), label, period (display), period_sort (YYYYMM of period start; financial years start in April), period_type, value, unit, source_file_id, quality_flag.
- **trust_systems**: FHI overlay: ods_code, category, supplier, product, contract_end, note. Proprietary.
- **refresh_runs**: status, trigger, summary, log.

## Metric codes
`<source>:<column>` for single tables; `<source>:<table>:<column>` for multi-table releases (workforce `core_8`). Aggregated totals carry the label "(total)"; breakdowns add `:<value>` to the code, e.g. `workforce:core_8:fte:nurses_health_visitors`. Wide tables are summed across dimension rows; averages and rates must not be summed, so check the profile before relying on a column.

## ERIC site metrics (`eric_site:*`)
Raw questions keep ERIC codes in lower case (`eric_site:s03_10` = cost to eradicate moderate risk backlog, £), summed over a trust's sites. Percentages are floor-area weighted. Derived: `backlog_total`, `backlog_high_significant`, `backlog_high_significant_share`, `backlog_per_sqm`, `energy_cost_total`, `energy_cost_per_sqm`, `energy_kwh_total`, `energy_kwh_per_sqm`, `estates_cost_total` (S25 lines 05 to 19 excluding S25_11 and S25_22; check against the ERIC guidance before publishing), `unsuitable_share`, `empty_share`, `sites_total`, `sites:<type>`. Text and select columns are skipped and listed in the file profile.

## NOF metrics (`nof:*`)
`nof:of0xxx` underlying measures (unit in `unit`); `nof:of2xxx` metric scores; `nof:of4200..4209` domain scores and `of4300..4309` domain segments; `nof:of5200` adjusted segment (1 best, 4 worst); `of5203` unadjusted segment; `of5202` average metric score; `of5204` financial override flag. A `:rank` suffix is the trust's rank among its trust type for that metric (rank direction follows the publisher: check before comparing across metrics). `nof:league_rank`, `league_score_low/high` and `league_rank_low/high` come from the league tables. All periods are the publication quarter; the metric's own reporting window is in the label.

## Derived metrics
| Code | Definition |
|---|---|
| rtt:incomplete_pathways_total | Incomplete pathways (Part_2 only), all specialties, summed across commissioners |
| rtt:incomplete_over_18_weeks | Those waiting 18 weeks or more (buckets starting at 18+) |
| rtt:pct_within_18_weeks | (total - over 18) / total x 100 |
| rtt:incomplete_over_52_weeks, rtt:pct_over_52_weeks | Waiting over 52 weeks (count, share) |
| rtt:incomplete_median_wait_weeks, rtt:incomplete_p92_wait_weeks | Median and 92nd percentile wait of incomplete pathways, interpolated within week buckets (approximate) |
| rtt:unknown_clock_start | Part_2A: pathways with no clock start date; not in the waiting list or distribution |
| rtt:completed_admitted, rtt:completed_non_admitted | Completed pathways in the month (Part_1A, Part_1B) |

## Cautions
HES counts episodes, not patients. NOF 2026/27 is not comparable with 2025/26. Organisation mergers change ODS codes; `current_code` holds the successor code where known (see `data/reference/code_successors.csv`).
