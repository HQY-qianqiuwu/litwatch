# Phase 4.5 Acoustic Journal Search Design

## Scope

Phase 4.5 extends the existing search core with optional acoustic-journal search. It does not make LitWatch globally acoustic-specific and does not change the Phase 4 analysis architecture.

The existing generic request remains valid:

```text
POST /api/v1/literature/search
{"topic": "graph neural networks", "limit": 10}
```

Journal-constrained requests add optional `journals`, `year_from`, and `year_to` fields. Supplying journals enables both exact journal filtering and an acoustic-relevance hard filter. Omitting journals keeps the general search behavior and never hard-filters non-acoustic papers.

## Processing Pipeline

Every provider result follows one shared pipeline:

```text
provider fetch / candidate over-fetch
→ normalize
→ global identity and deduplication
→ journal identity resolution
→ year and journal filtering
→ acoustic relevance scoring
→ optional acoustic hard filter
→ abstract status derivation
→ ranking
→ final limit
→ analysis eligibility derivation
→ persistence and response
```

Global paper identity remains:

```text
DOI > arXiv ID > canonical/provider ID > normalized title fallback
```

Conflicting DOI records must never merge solely by title. A paper returned by multiple providers merges into one stable `paper_id` before journal filtering.

## Candidate Over-fetch

The API `limit` is the final response limit, not the provider candidate limit. Generic searches preserve the current over-fetch behavior. Requests with journals or local hard filters use a larger bounded candidate pool before local filtering, ranking, and final truncation. Individual providers may apply safe server-side year or exact-source hints, but local processing is authoritative.

## Journal Registry

A central registry contains these initial journals:

- `nature_communications`
- `science_advances`
- `nature`
- `science`
- `jasa`
- `ocean_engineering`
- `ieee_joe`
- `acta_acustica_cn`
- `ieee_iot_j`

Each entry contains an internal ID, canonical name, abbreviation, exact aliases, verified ISSN/eISSN values when available, verified provider source IDs when available, and a priority weight.

Journal identity resolution uses this fixed precedence:

```text
ISSN/eISSN
> verified provider source ID
> internal journal ID
> normalized canonical name or exact alias
```

Resolution never uses fuzzy substring matching. When provider metadata conflicts, a reliable identifier wins over a name.

## Provider Normalization

OpenAlex, Crossref, and arXiv continue to implement provider retrieval. Their normalized `Paper` records carry raw journal metadata required for post-deduplication resolution:

- display name or journal reference
- ISSN/eISSN values
- provider source identifiers

OpenAlex uses primary-location source metadata, Crossref uses container title and ISSN metadata, and arXiv uses a journal reference only when present. All three providers feed the same shared post-fetch pipeline.

## Acoustic Relevance

Acoustic relevance is deterministic and local; it does not call an LLM. A centrally maintained vocabulary covers underwater/ocean acoustics, localization and TDOA, array processing, propagation, underwater communication, sensing, sonar, target detection, beamforming, hydrophones, and passive acoustics.

Title evidence weighs more than abstract evidence. Multi-word acoustic phrases weigh more than generic single tokens. The score is exposed as `acoustic_relevance`.

- Without journals: compute the score for metadata and ranking, but never use it as a hard filter.
- With journals: require both a resolved requested journal and an acoustic relevance score at or above the documented threshold.

Thus a non-acoustic Nature or Science paper is excluded from a journal-constrained acoustic search.

## Abstract Completeness and Analysis Eligibility

`abstract_status` and `analysis_eligible` are derived values, not independently trusted stored flags:

```text
non-blank abstract → complete + true
missing or blank abstract → pending + false
```

Legacy SQLite payloads that lack either field derive both values from the abstract. A payload can never deserialize into a paper with a missing abstract and `analysis_eligible=true`.

Pending papers remain searchable and persistable, especially when a DOI is available, but `POST /api/v1/literature/analyze` rejects them before any LLM request. Analysis still consumes only an already persisted `paper_id` and never invokes a literature provider.

## Ranking

Generic search retains existing query relevance and recency behavior, with only a small allowed priority-journal bonus.

Journal-constrained ranking orders by:

1. acoustic relevance,
2. query relevance,
3. abstract completeness,
4. priority-journal bonus,
5. recency.

Priority cannot make a weakly acoustic paper outrank or bypass the acoustic hard filter.

## API and Error Semantics

`POST /api/v1/literature/search` adds optional fields while preserving old clients:

```json
{
  "topic": "underwater acoustic TDOA localization",
  "journals": ["jasa", "ieee_joe", "ocean_engineering"],
  "year_from": 2020,
  "year_to": 2026,
  "limit": 10
}
```

Unknown journal IDs or aliases and invalid year ranges return HTTP 422. Provider status semantics remain `success`, `success_empty`, `partial_success`, and `all_providers_failed`. A valid search with candidates removed by filters is `success_empty`, not a provider failure.

## Persistence Compatibility

The existing SQLite schema and stable identity tables remain intact. New paper metadata is stored additively in the existing JSON payload. No database rebuild or destructive migration is required. Existing scans, aliases, redirects, papers, and analyses remain readable.

## Verification Boundary

Unit and integration tests cover registry resolution, identifier precedence, deduplication, provider normalization, optional hard filtering, ranking, derived abstract state, analysis refusal, SQLite compatibility, and all Phase 1–4 regressions. The final real-provider E2E uses the acoustic query and target journal set, accepts partial provider success, and rejects `all_providers_failed` as success.

Phase 4.5 does not add a UI, Pages, PDF processing, RAG, scraping, scheduler, email, Zotero, Dify, Docker, accounts, or paid LLM calls.
