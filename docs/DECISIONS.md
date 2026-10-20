# Decisions

| ID | Date | Decision | Why |
|---|---|---|---|
| D-001 | 2026-10-20 | Separate repo, database and Railway project from the client API | Bhoomi is finishing that API; the spike must not touch it |
| D-002 | 2026-10-20 | Long-format metric store keyed on ODS code | New sources add metric codes, not schema |
| D-003 | 2026-10-20 | Deployed service fetches data itself | Sandbox cannot reach NHS hosts (403) |
| D-004 | 2026-10-20 | Audience: internal team first, then key supplier clients to test concepts (Jon) | Prove value before packaging |
| D-005 | 2026-10-20 | Pricing model undecided: extra product or inside existing subscription (Jon) | Agnostic at this stage |
| D-006 | 2026-10-20 | Strain flag shown on dashboard as 1-5 (Jon); v0 derived from NOF segment | Financial inputs need the field inventory first |
| D-007 | 2026-10-20 | Installed-systems data: Bhoomi supplies a trust-to-supplier table; where the master lives is for Jon to advise | Spike uses a CSV upload, held in the database only |
| D-008 | 2026-10-20 | Pass criterion: reliably join datasets and give clients insights they cannot get elsewhere (Jon) | Measured by join rate and a list of new cross-source findings |
| D-009 | 2026-10-20 | Option E (buy or partner) market scan requested (Jon) | Informs build-versus-buy before Phase 2 |
| D-010 | 2026-10-20 | Basic auth for the PoC | Matches earlier projects; proprietary data lands here |
| D-011 | 2026-10-20 | Use FHI's trust ODS code file (project files) as the organisation spine | Jon supplied it; anchors names and codes for joins |
| D-012 | 2026-10-20 | Sum additive measures across dimension rows instead of storing each row | One value per org, metric and period; otherwise scorecards show an arbitrary row |
| D-013 | 2026-10-20 | File URLs can be supplied by hand through `SEED_URLS_<SOURCE>` | NHS index pages return 403 or empty pages to Railway; stable manual seeds are the dependable route |
| D-014 | 2026-10-20 | Reload files when `LOADER_VERSION` changes, even if the file hash is unchanged | Loader fixes must reach data already loaded |
| D-015 | 2026-10-20 | Hand-maintained successor-code map; scorecards merge predecessor history | Mergers change ODS codes (RBZ to RH8) |
| D-016 | 2026-10-20 | Commit Jon's ERIC site data (converted from Numbers) to the repo as a seed file | Public OGL data; NHS sites block our fetcher; lets us load immediately. Replace with the official CSV when we have the link |
| D-017 | 2026-10-20 | Sum site rows to trust level; percentages weighted by floor area; Not Applicable treated as missing | Sites are additive; zero would misstate |
| D-018 | 2026-10-20 | Dedicated NOF loader; strain v0 reads OF5200 (adjusted segment) | Generic loader would drop rank, unit and the per-metric reporting window, and picking "any segment" risks the unadjusted or a domain segment |
| D-019 | 2026-10-20 | Load only league-table fields the trust data lacks (rank, likely ranges) | Segment, score and deficit flag matched the trust data for 202 of 202; duplicating them adds noise |
| D-020 | 2026-10-20 | Commit Jon's NOF Q1 2026/27 files (converted from Numbers) as seeds | Same reasoning as D-016; replace with official CSV links via `SEED_URLS_NOF` |
| D-021 | 2026-10-20 | Load RTT from the full CSV; do not load the Excel trust report | Same counts, no cached summary values, and the CSV allows the same percentiles to be computed and tested |
| D-022 | 2026-10-20 | Exact RTT part codes; unknown clock start (Part_2A) kept separate | Mixing them overstated the waiting list by 1.19m and distorted the 18-week share |
| D-023 | 2026-10-20 | Hand-supplied seed URLs are not capped per run | The cap is for newest-first discovery lists; seeds are an explicit finite list |
| D-024 | 2026-10-20 | Serialise refreshes with a Postgres advisory lock | Overlapping deploys each ran the start-up refresh and double-loaded new files |
| D-025 | 2026-10-20 | Strain score stays at v0 (NOF adjusted segment); blended v1 parked at Jon's request | See docs/STRAIN_SCORE.md. Revisit when Jon asks |
