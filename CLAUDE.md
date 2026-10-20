# Working notes for Claude

- British English. Jon is CEO of FHI and wants opinionated, direct answers.
- This is a spike, isolated from Bhoomi's client API. Do not import from or modify that codebase.
- Conventions follow the other FHI Railway projects: FastAPI, SQLAlchemy 2, Alembic, Postgres, pytest + GitHub Actions gate, single HTML frontend.
- Document as you go: update `docs/CHANGELOG.md` for every change, `docs/DECISIONS.md` for every choice, `docs/SOURCES.md` when a source changes.
- Never commit proprietary installed-systems data. Never scrape pages behind a login.
- Real file layouts are not guaranteed. The loaders detect columns and record a profile per file (Sources tab). Prefer fixing mappers from that inventory over guessing.
- After a deploy that includes a migration, verify the migration actually ran; a green deployment is not proof. Trigger deploys with a CACHE_BUST variable rather than redeploy.
- `app/static/index.html` is a plain file (not a Python string), so JS escaping is normal; still run `node --check` on the script block.
