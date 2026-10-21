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
| D-026 | 2026-10-20 | CQC provider-level ratings, not location-level, as the organisation rating | Matches how a trust is described ("rated Good"); the 327k location rows are a later layer |
| D-027 | 2026-10-20 | Join CQC to ODS by override, explicit code, Provider ID (NHS IDs are ODS codes), then unique normalised name | The code column is filled for only about 30 of 200 NHS providers; the ID is exact; name matches are flagged and unmatched ones listed, never guessed |
| D-028 | 2026-10-20 | Store CQC ratings as 1-4 numbers with the scale in the label | The metrics table holds numbers; the UI maps back to names |
| D-029 | 2026-10-20 | Snapshot sources keep one row per (org, metric, period) | A monthly file repeats unchanged ratings; without this every month would duplicate them |
| D-030 | 2026-10-20 | Merged trusts handled as successors (RNK, RVJ, RY2) and RY3 added as retained code | Jon confirmed all four are 2026 mergers. Successor rows pool the old code's history into the new trust's scorecard; benchmarks still use each code's own rows. Dates and codes are from Jon's NHS Digital citation: verify against ODS |
| D-031 | 2026-10-20 | Rank 1 is best only where the direction of good is known; otherwise highest first and never coloured | A curated list (`HIGHER_BETTER`, `LOWER_BETTER` in app/benchmark.py) covers CQC, RTT, NOF segment and scores, ERIC backlog and a few more. Volumes and most NOF underlying measures stay neutral rather than guess whether more is good |
| D-032 | 2026-10-20 | Peer groups are NOF's own trust type (acute, mental health and community, ambulance), written by the NOF loader as `nof:peer_group` (LOADER_VERSION 7); no NOF data means "other", compared nationally only | First version inferred the type from which measures a trust reports and misfiled RY3, a community trust, as acute (found on the live data). The files carry Trust_type, so use it; inference stays only as a fallback. A trust is compared with peers only when at least five exist. NOF also carries a subtype (Teaching, Large, Medium, Small, Specialist, Community, MH and LD): finer peer groups are a candidate next step |
| D-033 | 2026-10-20 | Charts are hand-written SVG in the single HTML page, no charting library | Keeps the spike to one file, works offline and in dark mode; revisit if interactions outgrow it |

| D-034 | 2026-10-20 | Trust dashboards compare with the NOF subtype by default, falling back to type then everyone below 5 peers | Jon: peer groups by subtype are what a supplier's client expects (a teaching hospital against teaching hospitals). Care Trust (2 trusts) and any small group would otherwise give meaningless ranks. Subtypes are stored as numeric codes (`nof:peer_subtype`); keys and labels live in app/benchmark.py |
| D-035 | 2026-10-20 | RTT history is seeded by URL, not committed and not scraped | NHS England file names carry hashes that cannot be guessed, its WordPress media API is disallowed by robots.txt so is not used, and Railway gets empty pages from the RTT index. The addresses were read from the public RTT pages in Chrome. Revised files win where one exists. Period comes from each file's own Period column |
| D-036 | 2026-10-20 | Trend compares a trust with a comparison group fixed from latest values | The group (subtype, then type, then everyone) is chosen once, so the median band does not jump as membership changes between months; rank is among members with a value that month |
| D-037 | 2026-10-20 | Explorer trends use the same fixed-pool rule as trust trends; finance trends wait for earlier NOF quarters | RTT has 24 months, finance measures only one quarter. The 2026/27 framework changed method, so older quarters need a comparability caveat before being joined |
| D-038 | 2026-10-21 | DMA joined by name, headline is the primary care setting | The DMA file carries no ODS codes. Names are matched uniquely after normalisation, with a reviewed override file; unmatched are reported not guessed. One headline per trust (acute first) because NHS England advises comparing within a care setting; other settings are kept as separate metrics |
| D-039 | 2026-10-21 | Digital maturity versus performance uses signed Spearman rank correlation plus quartiles, within trust type by default | DMA, CQC and NOF segments are ordinal, so no averages-of-ratings correlations. Signed so positive always means more mature does better. Intervals shown so a weak link is not oversold; association only, with caveats on the page. Finance is a single quarter until earlier NOF quarters are loaded |
