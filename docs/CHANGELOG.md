# Changelog

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
