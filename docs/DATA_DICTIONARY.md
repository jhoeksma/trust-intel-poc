# Data dictionary

- **orgs**: ods_code (key), name, org_type, current_code (successor, once known), first_seen_source.
- **source_files**: one row per file attempted. status, mapper_status (ok, generic, needs_review), sha256, url, row and metric counts, profile (columns, detected roles, sample rows, periods), error, licence.
- **metrics**: ods_code, source_key, metric_code (`<source>:<slug>`), label, period (display), period_sort (YYYYMM of period start; financial years start in April), period_type, value, unit, source_file_id, quality_flag.
- **trust_systems**: FHI overlay: ods_code, category, supplier, product, contract_end, note. Proprietary.
- **refresh_runs**: status, trigger, summary, log.

## Derived metrics
| Code | Definition |
|---|---|
| rtt:incomplete_pathways_total | Incomplete pathways, all specialties, summed across commissioners |
| rtt:incomplete_over_18_weeks | Those waiting 18 weeks or more (buckets starting at 18+) |
| rtt:pct_within_18_weeks | (total - over 18) / total x 100 |

## Cautions
HES counts episodes, not patients. NOF 2026/27 is not comparable with 2025/26. Organisation mergers change ODS codes; `current_code` is reserved for successor mapping (not yet populated).
