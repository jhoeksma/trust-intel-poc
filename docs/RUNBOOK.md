# Runbook

## Services (Railway)
Project `trust-intel-poc` (id ac109a62-a295-4396-8785-8b8f25df2cdf), environment production. Services: web (34862a51-063c-4676-aaa0-d41227c23d98), refresh (89d6b1c9-8796-4a46-83cb-989317c5113f), Postgres (0e332ac8-ae3d-4d1e-b690-88053ec08ac5). Web domain: web-production-b155ce4.up.railway.app. Basic-auth user `fhi`; password is a Railway variable on web (never in git).

- **web**: `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- **refresh** (cron, daily 05:00 UTC): `alembic upgrade head && python -m scripts.refresh`
- **Postgres**: `DATABASE_URL` shared with both.

Variables: `DATABASE_URL`, `APP_ENV=production`, `BASIC_AUTH_USER`, `BASIC_AUTH_PASSWORD`. Optional: `HTTP_TIMEOUT_SECONDS`, `MAX_DOWNLOAD_MB`.

## When NHS pages block discovery
NHS Digital index pages return 403 and some NHS England pages return no links when fetched from Railway. Open the page in a browser, right-click the file link, copy the address, and set it on the **refresh** and **web** services as `SEED_URLS_<SOURCE>` (sources: NOF, RTT, WORKFORCE, ERIC, HES; comma-separate several URLs). The override wins over scraping. File URLs include random suffixes, so refresh these when a new release is published.

## Committed data files
Seeds can be `file://` paths relative to the repo root (e.g. `file://data/manual/<name>.csv.gz`); `.gz` is decompressed. Only public data may be committed. Never commit installed-systems data.

## Deploy
Push to `main`; CI must pass. Trigger a deploy with a new `CACHE_BUST` variable value (redeploy reuses the old snapshot). After a migration, confirm `alembic_version` and the tables; do not rely on deployment status.

## First run
Open Sources and press Refresh, or run `python -m scripts.refresh`. Review each file's profile, then tighten mappers. `needs_review` means no usable mapping was found.

## Troubleshooting
- `discovery_failed`: NHS changed an index page. Open the profile for `links_seen`, adjust the regexes in the registry, or update `seed_urls`.
- `download_failed`: check host reachability from Railway and the size cap.
- Slow or timed-out request: read the Railway `http` log stream, not just `deploy`.
- Refresh in the web process is a background thread; the cron is the reliable path.

## Installed-systems overlay
Sources tab, Import. CSV columns: ods_code, category, supplier, product, contract_end, note. Import replaces the table. The response reports the join rate and unmatched codes. Never commit this data.

## Deployment log
- 2026-10-20: first deploy crashed (python-multipart missing from requirements). Fixed in 0.1.1. Migration 0001 verified by querying /api/sources (tables exist, reference list reads 274 orgs). Alembic logs at WARN, so a clean run prints nothing; verify through the API, not the logs.
