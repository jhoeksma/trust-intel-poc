# Changelog

## 0.10.0 - 2026-10-20

- Explorer trend view: for any measure with three or more periods, choose "Trend over time" and 6/12/24 months. Shows the group median, middle half and 10th to 90th percentile band, a faint line per organisation, a highlighted trust, and lists of biggest movers either way (direction-aware where polarity is known). `GET /api/benchmark/metric/trend?code=&group=&subtype=&months=`.
- Financial position trend is not yet available: held NOF finance measures have one period (Q1 2026/27). Needs earlier NOF quarters; see docs/DECISIONS.md D-037.
- Tests: 63 passing.

## 0.9.0 - 2026-10-20

- RTT history: the 23 monthly Full CSV extracts from September 2024 to July 2026 are seeded by URL (`RTT_HISTORY` in the source registry), giving 24 months with August 2026. The addresses carry hashed names, so they were read from NHS England's RTT pages (2024-25, 2025-26, 2026-27) through Chrome; revised files are used where NHS England published one. Railway downloads them at load time; none are committed.
- Trend: `GET /api/benchmark/trust/{ods}/trend?code=&scope=&months=` returns a trust's value by period with the median, middle half and rank of its comparison group in each period. The trust dashboard shows "trend over N periods" on any measure with three or more periods, as a line against the group's median band. Metric catalogue entries now carry `periods`.
- Tests: 62 passing.

## 0.8.0 - 2026-10-20

- NOF trust subtype (Acute - Teaching, Large, Medium, Multi-Service, Small, Specialist; Community; Mental Health and Learning Disability; Care Trust; Ambulance) loaded as `nof:peer_subtype` from each file's Trust_subtype. LOADER_VERSION 8 forces the NOF files to reload.
- Filtering by trust type or subtype: Dashboard list (new Type column and filter; strain counts follow the filter), Explorer ("Show" now offers each type and subtype with counts) and `GET /api/benchmark/metric?subtype=`. New `GET /api/benchmark/groups` for filter options; `GET /api/trusts` now carries `peer_group` and `subtype`.
- Trust dashboard compares with the trust's subtype by default (new scope `subtype`), widening to the trust type and then to all organisations whenever fewer than 5 organisations have a value; each row says which pool it used.
- Tests: 61 passing.

## 0.7.0 - 2026-10-20

- Benchmarking API: `GET /api/benchmark/metrics` (comparable measures, direction, core flag), `GET /api/benchmark/metric?code=&group=` (one measure across every organisation, ranked, with distribution statistics) and `GET /api/benchmark/trust/{ods}?codes=&scope=peers|national` (rank, share beaten, quartile and gap to median per chosen measure). Logic in `app/benchmark.py`.
- Explorer tab: pick one measure, see every organisation as a dot (continuous measures) or as count bars (segments, ratings, flags), highlight any trust, filter to a peer group, and read the full ranking underneath.
- Trust dashboard (replaces the Trust tab): core fields by default, any other measure added or removed from a searchable picker (choice remembered in the browser), each shown with value, rank, share of peers beaten, quartile and a range bar. The old full value table is kept in a collapsible section.
- Reference: successors RNK to G6V2S, RVJ to RA7, RY2 to RWW added to `code_successors.csv`; RY3 added to `trusts_ods.csv` (no FHI id yet). Source: Jon, 20 Oct 2026, quoting NHS Digital's ODS mergers page. To verify against ODS.
- NOF loader emits `nof:peer_group` (1 acute, 2 mental health and community, 3 ambulance) from each file's Trust_type; benchmarking uses it for peer groups. LOADER_VERSION 7 forces the NOF files to reload. Found on the live data: the first inference misfiled RY3 as acute.
- A merged code's dashboard shows a banner pointing to its successor.
- `scripts/bench_check.py`: read-only view of what the benchmarking layer sees in the live database.
- Tests: 57 passing.

## 0.6.0 - 2026-10-20
- New source `cqc`: CQC "Latest ratings" workbook (monthly .ods, OGL v3; CQC acknowledged as source). Provider-level overall rating, the five key questions, Use of Resources and combined quality rating, plus counts of core services rated below Good. Discovered automatically from CQC's "Using CQC data" page (reachable from Railway); seed URL is the October 2026 file.
- Ratings stored 1 Inadequate, 2 Requires improvement, 3 Good, 4 Outstanding; "Not rated" is not stored. A rating's period is its publication month, which can be years old. Trusts under CQC's new approach record the overall rating as Well-led / Overall; the more recently published of old and new wins.
- Only about 30 of 200 NHS providers carry an ODS code in the file, so the rest are matched by normalised name against known organisations (unique matches only, `quality_flag = name_match`). Unmatched providers are listed in the file profile; manual fixes go in `data/reference/cqc_overrides.csv`.
- New `app/sources/ods.py`: standard-library streaming reader for .ods (the workbook is 27MB, 327k location rows).
- `SourceSpec.snapshot`: a snapshot source keeps one row per (org, metric, period) across monthly files, so unchanged ratings are not duplicated.
- Dashboard: CQC rating column; trust page shows rating names. Scripts: `review.py` (completeness and coherence checks), `probe_urls.py`, `profile_file.py`, `explore_cqc*.py` (diagnostics).
- Join order for CQC: hand override, the Provider ODS Code column, the Provider ID (NHS providers use their ODS code as ID, exact), then unique normalised name. Conflicts between ID and name are listed in the file profile. Snapshot month parsed from the underscored file name (it had come out as unknown). `LOADER_VERSION` 6.
- 49 tests.

## Notes - 2026-10-20
- Strain score scale and v0 limits documented in `docs/STRAIN_SCORE.md`; v1 parked (D-025).

## 0.5.0 - 2026-10-20
- RTT August 2026 full extract (supplied by Jon) committed as a seed: `data/manual/RTT - Aug 2026 - Full CSV data file.zip`. 532 providers, one month.
- **Bug fixed in `load_rtt`**: the part filter matched `part_2a` (patients with unknown clock start) as well as `part_2` (incomplete pathways), inflating the waiting list from 7.19m to 8.38m and understating within-18-weeks (63.1% instead of 65.2%). Now exact part codes; unknown-clock-start pathways are kept as their own metric.
- New RTT metrics per provider: over 52 weeks (count and share), median and 92nd percentile wait (interpolated within week buckets, approximate), unknown clock starts, completed pathways admitted and non-admitted.
- The Excel "Waiting Times by Hospital Trust" report was reviewed and not loaded: it is NHS England's interactive report over the same provider-by-specialty counts as the full CSV, and its summary cells hold no cached values.
- Seed files supplied by hand are no longer capped at 3 per run (the cap hid the three NOF league tables; discovered files stay capped). `LOADER_VERSION` 4.
- Refresh takes a Postgres advisory lock, so overlapping runs (a deploy-time run while another deploy was being replaced) queue instead of loading the same file twice. The first RTT/NOF load did exactly that and left 21,771 duplicate keys; `LOADER_VERSION` 5 forces a clean reload that replaces them.
- 39 tests.

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
