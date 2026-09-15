"""The sole provider-search orchestration entry for API and future callers."""

import xml.etree.ElementTree as ET
from json import JSONDecodeError

import httpx
from pydantic import ValidationError

from litwatch.core import Paper, ProviderResult, ProviderState, SearchResult, SearchStatus
from litwatch.providers.base import LiteratureProvider
from litwatch.search.deduplication import deduplicate_papers
from litwatch.search.ranking import rank_papers


def _provider_error(error: Exception) -> tuple[ProviderState, str]:
    if isinstance(error, httpx.TimeoutException):
        return ProviderState.TIMEOUT, "timeout"
    if isinstance(error, httpx.HTTPStatusError):
        code = error.response.status_code
        if code == 429:
            return ProviderState.RATE_LIMITED, "http_429"
        if code in {401, 403}:
            return ProviderState.AUTH_ERROR, f"http_{code}"
        return ProviderState.UPSTREAM_ERROR, f"http_{code}"
    if isinstance(error, httpx.HTTPError):
        return ProviderState.UPSTREAM_ERROR, "http_error"
    if isinstance(error, (JSONDecodeError, ET.ParseError, ValidationError, TypeError, ValueError)):
        return ProviderState.PARSE_ERROR, "malformed_response"
    return ProviderState.UPSTREAM_ERROR, "provider_error"


class SearchService:
    """Collect normalized papers, isolate source errors, dedupe and rank once."""

    def __init__(self, providers: list[LiteratureProvider]) -> None:
        if not providers:
            raise ValueError("at least one literature provider is required")
        self.providers = providers

    def search(self, topic: str, limit: int) -> SearchResult:
        query = topic.strip()
        if not query:
            raise ValueError("topic must not be blank")
        if isinstance(limit, bool) or limit < 1:
            raise ValueError("limit must be a positive integer")

        candidates: list[Paper] = []
        statuses: list[ProviderResult] = []
        candidate_limit = min(max(limit * 3, limit), 100)
        for provider in self.providers:
            try:
                records = provider.search(query, candidate_limit)
                if not isinstance(records, list) or any(
                    not isinstance(record, Paper) for record in records
                ):
                    raise TypeError("provider must return normalized Paper records")
            except Exception as error:  # noqa: BLE001 - an upstream source must not abort other sources
                state, code = _provider_error(error)
                statuses.append(ProviderResult(provider=provider.name, status=state, error_code=code))
                continue

            candidates.extend(records)
            statuses.append(
                ProviderResult(
                    provider=provider.name,
                    status=ProviderState.SUCCESS if records else ProviderState.EMPTY,
                    fetched_count=len(records),
                )
            )

        working = sum(
            status.status in {ProviderState.SUCCESS, ProviderState.EMPTY} for status in statuses
        )
        failures = len(statuses) - working
        papers = rank_papers(query, deduplicate_papers(candidates))[:limit] if working else []
        for status in statuses:
            status.returned_count = sum(status.provider in paper.providers for paper in papers)

        if failures and not working:
            aggregate = SearchStatus.ALL_PROVIDERS_FAILED
        elif failures:
            aggregate = SearchStatus.PARTIAL_SUCCESS
        elif papers:
            aggregate = SearchStatus.SUCCESS
        else:
            aggregate = SearchStatus.SUCCESS_EMPTY
        return SearchResult(topic=query, status=aggregate, papers=papers, provider_results=statuses)
