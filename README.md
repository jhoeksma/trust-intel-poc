# FHI Trust Intelligence PoC

Phase 1 spike for Future Health Intelligence: join public NHS trust data (oversight framework, waiting times, workforce, estates, hospital activity) on ODS code, give every trust a 1-5 strain score, and overlay FHI's own trust-to-supplier data. Internal first, then selected supplier clients to test concepts.

**Status:** spike. Deliberately separate from the client API Bhoomi is building (own repo, database and Railway project). Nothing here touches that work.

**Pass criterion (Jon, 20 Oct 2026):** we can join the datasets reliably and give clients insights they cannot get elsewhere. Measured by the join rate reported when the supplier table is imported, plus a short list of cross-source findings the team judges new.

## Run locally
```bash
pip install -r requirements.txt
alembic upgrade head          # SQLite by default; set DATABASE_URL for Postgres
python -m scripts.refresh nof rtt   # or no args for all sources
uvicorn app.main:app --reload
python -m pytest -q
```
Note: NHS and GOV.UK hosts may be unreachable from some sandboxes. The deployed Railway service fetches the data itself.

## Layout
| Path | Purpose |
|---|---|
| `app/sources/registry.py` | Where each dataset lives. Add a source here. |
| `app/sources/discover.py` | Finds the latest file by reading index pages |
| `app/sources/loaders.py` | Generic CSV loader (auto-detects columns) and RTT aggregator |
| `app/pipeline.py` | Discover, download, load, record provenance |
| `app/indicators.py` | Scorecard and strain score |
| `app/main.py`, `app/static/index.html` | API and single-page UI |
| `docs/` | Architecture, sources, decisions, runbook, data dictionary, changelog |

## Documentation
Start with `docs/ARCHITECTURE.md`. Decisions are in `docs/DECISIONS.md`; operations in `docs/RUNBOOK.md`. Update the changelog with every change.

## Data and licence
Public data is under the Open Government Licence v3.0 (confirm per publication). FHI installed-systems data is proprietary: it is uploaded to the database through the UI and must never be committed.
