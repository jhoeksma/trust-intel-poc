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
