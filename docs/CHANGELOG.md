# Changelog

## 0.4.0 - 2026-10-20
- New dedicated NOF loader `app/sources/nof.py` for the Q1 2026/27 NHS Oversight Framework files supplied by Jon (Numbers, converted to CSV and committed under `data/manual/`): trust data for acute (134 trusts), ambulance (10) and mental health and community (58), plus the three league tables. 202 trusts, 177 metric codes.
- Trust data loads every metric with its unit and peer rank (`nof:<metric>` and `nof:<metric>:rank`). League tables add `nof:league_rank` and the likely ranges for score and rank (`league_score_low/high`, `league_rank_low/high`). Segment, score and deficit flag in the league tables are identical to OF5200, OF5202 and OF5204 for all 202 trusts, so are not reloaded.
- Strain score v0 now reads the adjusted segment `nof:of5200` explicitly. The earlier hint (`of5000`, any label containing "segment") was wrong and could have picked the unadjusted or a domain segment.
- Every row takes the file's Quarter as its period (Reporting_date varies per metric); "Q1 26/27" is normalised to "Q1 2026/27". Float noise removed (1.7000000000000002 becomes 1.7). `LOADER_VERSION` 3.
- 38 tests.

## 0.3.1 - 2026-10-20
- Refresh prints a run report (coverage per source, join rates, headline checks, duplicates, unknown periods, recent failures) to the logs.
- Profile-only files (no organisation column) now carry a loader version, so they are no longer reloaded every run.
- 34 tests.

## 0.3.0 - 2026-10-20
- New source `eric_site`: ERIC 2025/26 site-level return (2,923 sites, 195 numeric measures) rolled up to 205 trusts. Supplied by Jon as a Numbers file, converted to CSV, committed as `data/manual/ERIC - 2025_26 - Site data.csv.gz` (public data, OGL). Dedicated loader `app/sources/eric_site.py`.
- Derived trust measures: backlog (total, high and significant, share, per m²), energy cost and consumption (total, per m²), estates cost lines, unsuitable and empty floor area shares, site counts by type.
- `file://` seed URLs for committed data files (repo-relative, .gz decompressed).
- Coverage report now follows the successor map and reports English trusts separately.
- Migration 0001: metrics.id portable to SQLite for local runs (no effect on Postgres).
- 33 tests.

## 0.2.0 - 2026-10-20
Fixes from the first live load review (docs/REVIEW-2026-10-20-first-load.md):
- Wide tables that repeat an organisation across dimension rows (workforce) are now summed to one value per organisation, period and metric, plus a breakdown by the main categorical column (e.g. staff group). Metric codes for multi-table releases carry the table (`workforce:core_8:fte`).
- File names are URL-decoded before period detection (fixes ERIC period "unknown").
- HES: suppressed values counted in the file profile; labels include the measure type.
- `SEED_URLS_<SOURCE>` environment variable (comma separated) overrides discovery. Needed because NHS pages block our fetcher from Railway.
- Discovery sends browser-like headers and reports pages that return no links.
- `LOADER_VERSION` in each profile: a loader change forces unchanged files to reload.
- Successor-code map (`data/reference/code_successors.csv`, RBZ to RH8 to verify); scorecards include history from predecessor codes.
- 31 tests.

## Review - 2026-10-20
- First live load reviewed: see docs/REVIEW-2026-10-20-first-load.md. No code changes.

## 0.1.1 - 2026-10-20
- Fix: add python-multipart to requirements (first Railway deploy crashed on the CSV upload endpoint; local tests had it installed globally).

## 0.1.0 - 2026-10-20
- Scaffold: config, models, Alembic migration 0001.
- Source registry, index-page discovery, download with size cap, generic and RTT loaders.
- Pipeline with provenance, unchanged-file skipping, failure recording.
- Strain score v0 (NOF segment, 1-5), scorecard, compare, sources inventory.
- API, single-page UI (Dashboard, Trust, Compare, Sources), installed-systems CSV import with join rate.
- FHI reference list (274 codes: 238 trusts, 36 ICBs) seeded as the organisation spine; Sources tab reports join coverage.
- 23 tests; GitHub Actions gate.
