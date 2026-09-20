# Phase 4.5 Acoustic Journal Search Implementation Plan

> **For Codex:** Execute this plan task-by-task using `superpowers:test-driven-development`. Each behavior change starts with a failing test, then the minimum implementation, then focused and full verification. Do not merge `main`.

**Goal:** Add backward-compatible, optional acoustic journal filtering and ranking to the shared LitWatch search pipeline while preserving stable paper identity, persistence, and Phase 4 analysis isolation.

**Architecture:** A central journal registry and deterministic acoustic scorer enrich normalized `Paper` values after global deduplication. `SearchService` remains the only search orchestrator, accepts optional criteria, over-fetches candidates for locally filtered requests, and persists only the final normalized results through the existing API repository boundary. Analysis continues to load a persisted paper and refuses papers without usable abstracts.

**Tech Stack:** Python 3.12, Pydantic 2, FastAPI, httpx, SQLite, pytest, Ruff, uv.

---

## Task 1: Add the journal registry and exact identity resolution

**Files:**

- Create: `src/litwatch/journals/__init__.py`
- Create: `src/litwatch/journals/registry.py`
- Create: `tests/test_journal_registry.py`

**Step 1: Write failing registry tests**

Test canonical IDs, canonical names, abbreviations, case/punctuation-normalized exact aliases, ISSN/eISSN resolution, verified provider-source resolution, precedence under conflicting names, and rejection of fuzzy substrings.

**Step 2: Run the focused test and confirm RED**

```powershell
uv run pytest tests/test_journal_registry.py -q
```

Expected: import or assertion failure because the registry does not exist.

**Step 3: Implement the minimal registry**

Add immutable `JournalDefinition` values and `JournalRegistry` methods:

```python
def get(journal_id: str) -> JournalDefinition | None: ...
def resolve_requested(value: str) -> JournalDefinition | None: ...
def resolve_identity(
    *,
    issns: Iterable[str] = (),
    provider_source_ids: Mapping[str, str] | None = None,
    internal_id: str | None = None,
    name: str | None = None,
) -> JournalDefinition | None: ...
```

Populate only verified ISSN/eISSN and provider identifiers. Normalize ISSNs and exact names without substring matching.

**Step 4: Run focused tests and Ruff**

```powershell
uv run pytest tests/test_journal_registry.py -q
uv run ruff check src/litwatch/journals tests/test_journal_registry.py
```

**Step 5: Commit**

```powershell
git add src/litwatch/journals tests/test_journal_registry.py
git commit -m "feat: add acoustic journal registry"
```

## Task 2: Carry journal metadata through every provider

**Files:**

- Modify: `src/litwatch/core/models.py`
- Modify: `src/litwatch/providers/openalex.py`
- Modify: `src/litwatch/providers/crossref.py`
- Modify: `src/litwatch/providers/arxiv.py`
- Modify: `src/litwatch/search/deduplication.py`
- Modify: `tests/test_providers.py`
- Modify: `tests/test_search_models.py`
- Modify: `tests/test_search_processing.py`

**Step 1: Write failing normalization and merge tests**

Add fixtures proving each provider extracts its available journal name, ISSNs, and source ID. Add a merge test proving complementary provider metadata survives global DOI-based deduplication and conflicting DOI records still do not merge by title.

**Step 2: Run focused tests and confirm RED**

```powershell
uv run pytest tests/test_providers.py tests/test_search_models.py tests/test_search_processing.py -q
```

**Step 3: Extend `Paper` additively**

Add backward-compatible defaults for:

```python
journal: str | None = None
journal_id: str | None = None
journal_issns: list[str] = []
journal_source_ids: dict[str, str] = {}
acoustic_relevance: float = 0.0
is_priority_journal: bool = False
```

Implement `abstract_status` and `analysis_eligible` as derived properties/computed fields based only on the normalized abstract.

**Step 4: Normalize and merge metadata**

Extract OpenAlex primary-location source data, Crossref container-title/ISSN data, and arXiv journal references. Merge lists/maps deterministically in deduplication.

**Step 5: Run focused tests and Ruff**

```powershell
uv run pytest tests/test_providers.py tests/test_search_models.py tests/test_search_processing.py -q
uv run ruff check src tests
```

**Step 6: Commit**

```powershell
git add src/litwatch/core src/litwatch/providers src/litwatch/search/deduplication.py tests
git commit -m "feat: normalize journal and abstract metadata"
```

## Task 3: Add deterministic acoustic relevance scoring

**Files:**

- Create: `src/litwatch/search/acoustic.py`
- Create: `tests/test_acoustic_relevance.py`

**Step 1: Write failing scorer tests**

Prove that exact acoustic phrases score strongly, title matches outweigh abstract-only matches, unrelated Nature/Science examples remain below the hard threshold, and missing abstracts are handled safely.

**Step 2: Run the focused test and confirm RED**

```powershell
uv run pytest tests/test_acoustic_relevance.py -q
```

**Step 3: Implement the minimal deterministic scorer**

Centralize phrases and weights. Return a bounded `0.0..1.0` score and expose a named hard-filter threshold. Do not call providers or an LLM.

**Step 4: Verify and commit**

```powershell
uv run pytest tests/test_acoustic_relevance.py -q
uv run ruff check src/litwatch/search/acoustic.py tests/test_acoustic_relevance.py
git add src/litwatch/search/acoustic.py tests/test_acoustic_relevance.py
git commit -m "feat: score acoustic paper relevance"
```

## Task 4: Extend provider queries and candidate over-fetch

**Files:**

- Modify: `src/litwatch/providers/base.py`
- Modify: `src/litwatch/providers/openalex.py`
- Modify: `src/litwatch/providers/crossref.py`
- Modify: `src/litwatch/providers/arxiv.py`
- Modify: `src/litwatch/search/service.py`
- Modify: `tests/test_search_service.py`
- Modify: `tests/test_providers.py`

**Step 1: Write failing query/over-fetch tests**

Test that the public `SearchService.search(topic, limit)` call remains valid, journal-filtered searches request more candidates than the final limit, final results are truncated to the requested limit, and safe year hints are passed without making provider-side filtering authoritative.

**Step 2: Run focused tests and confirm RED**

```powershell
uv run pytest tests/test_search_service.py tests/test_providers.py -q
```

**Step 3: Add optional provider criteria**

Introduce a small immutable provider criteria value with resolved journal definitions and year bounds. Keep it optional so generic calls retain their behavior. Update first-party providers and test doubles.

**Step 4: Implement bounded over-fetch**

Keep the existing generic candidate calculation. For journal-constrained requests use a larger bounded pool, with each provider respecting its own documented maximum. The user-facing `limit` is applied only after local processing.

**Step 5: Verify and commit**

```powershell
uv run pytest tests/test_search_service.py tests/test_providers.py -q
uv run ruff check src tests
git add src/litwatch/providers src/litwatch/search/service.py tests
git commit -m "feat: over-fetch filtered search candidates"
```

## Task 5: Implement the shared journal/acoustic filtering and ranking pipeline

**Files:**

- Modify: `src/litwatch/search/service.py`
- Modify: `src/litwatch/search/ranking.py`
- Modify: `src/litwatch/search/__init__.py`
- Modify: `tests/test_search_service.py`
- Modify: `tests/test_search_processing.py`

**Step 1: Write failing end-to-end service tests**

Cover:

- generic non-acoustic searches remain visible when journals are omitted;
- requested journals are resolved by exact ID/alias;
- results outside requested journals are removed;
- non-acoustic Nature/Science results are removed;
- acoustic JASA and IEEE JOE results pass;
- year filtering occurs after deduplication;
- priority bonus never bypasses or outweighs acoustic relevance;
- all locally filtered candidates produce `success_empty` when a provider succeeded;
- every provider path reaches deduplication, journal resolution, scoring, and final `SearchResult`.

**Step 2: Run tests and confirm RED**

```powershell
uv run pytest tests/test_search_service.py tests/test_search_processing.py -q
```

**Step 3: Implement the ordered pipeline**

Extend the service signature compatibly:

```python
async def search(
    self,
    topic: str,
    limit: int,
    *,
    journals: Sequence[str] | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
) -> SearchResult: ...
```

Resolve requested journals once, reject unknown exact identifiers, execute global deduplication before journal resolution/filtering, score acoustics, apply the hard threshold only when journals are supplied, rank, then truncate.

**Step 4: Verify and commit**

```powershell
uv run pytest tests/test_search_service.py tests/test_search_processing.py -q
uv run ruff check src tests
git add src/litwatch/search tests
git commit -m "feat: filter and rank acoustic journal searches"
```

## Task 6: Expose backward-compatible API fields

**Files:**

- Modify: `src/litwatch/api/app.py`
- Modify: `tests/test_api.py`

**Step 1: Write failing API tests**

Test the old `{topic, limit}` body, the new journal/year body, validation of unknown journals and inverted year ranges, additive paper response fields, and persisted stable paper IDs after filtered search.

**Step 2: Run the focused test and confirm RED**

```powershell
uv run pytest tests/test_api.py -q
```

**Step 3: Implement request forwarding and error mapping**

Add optional request fields and forward them to `SearchService` without implementing filtering in FastAPI. Map domain validation failures to HTTP 422.

**Step 4: Verify and commit**

```powershell
uv run pytest tests/test_api.py -q
uv run ruff check src/litwatch/api tests/test_api.py
git add src/litwatch/api tests/test_api.py
git commit -m "feat: expose acoustic journal search criteria"
```

## Task 7: Enforce analysis eligibility without searching

**Files:**

- Modify: `src/litwatch/analysis/service.py`
- Modify: `src/litwatch/api/app.py`
- Modify: `tests/test_analysis_service.py`
- Modify: `tests/test_analysis_api.py`

**Step 1: Write failing eligibility tests**

Persist one paper with an abstract and one DOI-only paper without an abstract. Prove the complete paper can be analyzed, the pending paper is rejected with HTTP 409 before the gateway is invoked, and neither path invokes `SearchService.search()`.

**Step 2: Run focused tests and confirm RED**

```powershell
uv run pytest tests/test_analysis_service.py tests/test_analysis_api.py -q
```

**Step 3: Add the minimal domain error and guard**

Load the persisted paper, derive eligibility from its abstract, raise `PaperAnalysisUnavailableError` before the gateway call, and map it to HTTP 409. Never fetch missing metadata during analysis.

**Step 4: Verify and commit**

```powershell
uv run pytest tests/test_analysis_service.py tests/test_analysis_api.py -q
uv run ruff check src tests
git add src/litwatch/analysis src/litwatch/api tests
git commit -m "feat: guard analysis by abstract availability"
```

## Task 8: Prove SQLite and Phase 1–4 compatibility

**Files:**

- Modify: `tests/test_storage.py`
- Modify: `tests/test_search_models.py`
- Modify: `tests/test_analysis_api.py`
- Modify: `docs/MIGRATION_MATRIX.md`

**Step 1: Add compatibility tests**

Insert or deserialize a legacy paper payload missing Phase 4.5 fields and prove it derives `pending/false` when the abstract is absent. Prove complete papers survive repository/app reconstruction and analyses remain readable. Verify existing stable IDs, aliases, redirects, scans, and analyses are unchanged.

**Step 2: Run focused and full suites**

```powershell
uv run pytest tests/test_storage.py tests/test_search_models.py tests/test_analysis_api.py -q
uv run pytest
uv run ruff check .
```

**Step 3: Update migration documentation and commit**

Record the additive JSON compatibility and absence of a destructive schema migration.

```powershell
git add tests docs/MIGRATION_MATRIX.md
git commit -m "test: verify acoustic search persistence compatibility"
```

## Task 9: Run real-provider E2E and remote CI

**Files:**

- No required production-code changes; record evidence in the final report.

**Step 1: Run the real search**

Use the actual shared API/service path with:

```json
{
  "topic": "underwater acoustic TDOA localization",
  "journals": ["jasa", "ieee_joe", "ocean_engineering"],
  "limit": 10
}
```

Record provider successes/failures, fetched and final counts, paper IDs, DOI coverage, resolved journals, acoustic scores, and abstract statuses. `partial_success` is acceptable; `all_providers_failed` is not a pass.

**Step 2: Run final local verification**

```powershell
uv sync --extra dev
uv run pytest
uv run ruff check .
git status --short
```

**Step 3: Push the feature branch**

```powershell
git push -u origin feat/phase4.5-acoustic-journal-search
```

**Step 4: Wait for GitHub CI**

Use `gh run list` and `gh run watch` for the pushed branch. If CI fails, diagnose and repair on the feature branch, rerun local verification, and push the repair.

**Step 5: Stop for review**

Report commits, changed files, registry/scoring/filter/status behavior, tests, Ruff, real E2E evidence, regressions, and open issues. Do not merge `main` and do not begin Phase 5.
