# Migration Matrix

This new project references the older LitWatch implementation at `fa81340` selectively. It does not copy the old repository or its Git history. Phase 2 search, Phase 3 persistence, and Phase 4 BYOK analysis capabilities are migrated. Phase 4.5 acoustic-journal search is additive and is currently under review on its feature branch.

| Older capability | New phase | Decision |
| --- | --- | --- |
| OpenAlex | Phase 2 | Migrated |
| arXiv | Phase 2 | Migrated |
| Crossref | Phase 2 | Migrated |
| Search core | Phase 2 | Migrated |
| SQLite persistence | Phase 3 | Migrated |
| scan_id | Phase 3 | Migrated |
| stable paper_id | Phase 3 | Migrated |
| persistent deduplication | Phase 3 | Migrated |
| PaperAnalysisService | Phase 4 | Migrated |
| BYOK OpenAI-compatible gateway | Phase 4 | Migrated |
| Journal registry | Phase 4.5 | In review |
| Acoustic relevance/filtering | Phase 4.5 | In review |
| Abstract analysis eligibility | Phase 4.5 | In review |
| Scheduler | — | Omitted |
| Email | — | Omitted |
| Radar | — | Omitted |
| Dify | — | Omitted |
| Prompt Library | — | Omitted |
| Windows Task | — | Omitted |

See [NOTICE.md](../NOTICE.md) for source attribution and license obligations if substantial source is adapted in a later commit.

## Phase 4.5 persistence compatibility

Phase 4.5 adds journal identity, acoustic relevance, abstract status, and analysis eligibility to the existing `Paper` JSON payload. It does not add, drop, or rebuild SQLite tables. Existing payloads that lack the additive fields continue to deserialize with safe defaults; `abstract_status` and `analysis_eligible` are always derived from the stored abstract. A later scan can enrich an existing stable `paper_id` with Phase 4.5 metadata without changing scan links, aliases, redirects, or saved analyses.
