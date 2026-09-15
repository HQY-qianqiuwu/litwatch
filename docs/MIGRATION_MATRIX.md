# Migration Matrix

This new project references the older LitWatch implementation at `fa81340` selectively. It does not copy the old repository or its Git history. Phase 2 search and Phase 3 persistence capabilities are migrated; Phase 4 analysis is next.

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
| PaperAnalysisService | Phase 4 | Next |
| Scheduler | — | Omitted |
| Email | — | Omitted |
| Radar | — | Omitted |
| Dify | — | Omitted |
| Prompt Library | — | Omitted |
| Windows Task | — | Omitted |

See [NOTICE.md](../NOTICE.md) for source attribution and license obligations if substantial source is adapted in a later commit.
