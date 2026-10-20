# Architecture

```
registry.py --> discover.py --> fetch.py --> loaders.py --> pipeline.py --> Postgres
 (where)        (latest URL)    (download)   (rows+profile)   (provenance)    orgs / metrics / source_files
                                                                                 |
                                         indicators.py (scorecard, strain 1-5) <-+-- trust_systems (FHI overlay)
                                                 |
                                       main.py (API) + static/index.html
```

## Principles
1. **Everything keys on ODS code.** The join is the product; the join rate is the success measure.
2. **Long-format metric store.** One `metrics` table (ods_code, metric_code, period, value). A new source adds metric codes, not tables.
3. **Provenance on every row.** `metrics.source_file_id` points to `source_files` (URL, sha256, retrieved_at, status, licence).
4. **Discover, never guess URLs.** NHS file URLs include random suffixes. Index pages are scraped; hand-confirmed `seed_urls` are a fallback and are flagged.
5. **Schema-discovering ingestion.** Real column layouts were not inspectable when this was built. The loader detects roles (organisation code, period, long vs wide) and stores a per-file profile. The first live run is the field inventory.
6. **Honest failure.** Every attempted file leaves a `source_files` row (`discovery_failed`, `download_failed`, `parse_failed`, `loaded`). Unchanged files (same sha256) are skipped; changed files replace their metrics.

## Isolation
Own GitHub repo, Railway project and Postgres. Later, scorecard endpoints can be lifted into Bhoomi's API using its conventions.

## Security
Basic auth on everything except `/health` when `APP_ENV=production` (503 if credentials unset). The installed-systems overlay is proprietary and stored only in the database.

## Strain score (v0)
1 (low) to 5 (high), shown on the dashboard. v0 maps the NHS Oversight Framework segment to the score and records its inputs. Financial inputs are added after the field inventory. See DECISIONS D-006.
