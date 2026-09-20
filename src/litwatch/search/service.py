"""The sole provider-search orchestration entry for API and future callers."""

import xml.etree.ElementTree as ET
from collections.abc import Sequence
from json import JSONDecodeError

import httpx
from pydantic import ValidationError

from litwatch.core import Paper, ProviderResult, ProviderState, SearchResult, SearchStatus
from litwatch.journals import JOURNAL_REGISTRY
from litwatch.providers.base import LiteratureProvider, ProviderSearchCriteria
from litwatch.search.acoustic import (
    ACOUSTIC_HARD_FILTER_THRESHOLD,
    score_acoustic_relevance,
)
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

    def search(
        self,
        topic: str,
        limit: int,
        *,
        journals: Sequence[str] | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
    ) -> SearchResult:
        query = topic.strip()
        if not query:
            raise ValueError("topic must not be blank")
        if isinstance(limit, bool) or limit < 1:
            raise ValueError("limit must be a positive integer")
        requested_journals = []
        for value in journals or ():
            journal = JOURNAL_REGISTRY.resolve_requested(value)
            if journal is None:
                raise ValueError(f"unknown journal: {value}")
            if journal not in requested_journals:
                requested_journals.append(journal)
        if year_from is not None and year_to is not None and year_from > year_to:
            raise ValueError("year_from must not be greater than year_to")

        criteria = ProviderSearchCriteria(
            journals=tuple(requested_journals),
            year_from=year_from,
            year_to=year_to,
        )
        filtered = bool(requested_journals or year_from is not None or year_to is not None)

        candidates: list[Paper] = []
        statuses: list[ProviderResult] = []
        candidate_limit = (
            min(max(limit * 10, 100), 200)
            if filtered
            else min(max(limit * 3, limit), 100)
        )
        for provider in self.providers:
            try:
                records = (
                    provider.search(query, candidate_limit, criteria=criteria)
                    if filtered
                    else provider.search(query, candidate_limit)
                )
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
        papers: list[Paper] = []
        if working:
            resolved_papers: list[Paper] = []
            for paper in deduplicate_papers(candidates):
                journal = JOURNAL_REGISTRY.resolve_identity(
                    issns=paper.journal_issns,
                    provider_source_ids=paper.journal_source_ids,
                    internal_id=paper.journal_id,
                    name=paper.journal,
                )
                if journal is not None:
                    paper = paper.model_copy(
                        update={
                            "journal": journal.canonical_name,
                            "journal_id": journal.journal_id,
                            "is_priority_journal": journal.priority > 0,
                        }
                    )
                resolved_papers.append(paper)

            requested_ids = {journal.journal_id for journal in requested_journals}
            filtered_papers = [
                paper
                for paper in resolved_papers
                if (year_from is None or paper.year is not None and paper.year >= year_from)
                and (year_to is None or paper.year is not None and paper.year <= year_to)
                and (not requested_ids or paper.journal_id in requested_ids)
            ]
            scored_papers = [
                paper.model_copy(
                    update={"acoustic_relevance": score_acoustic_relevance(paper)}
                )
                for paper in filtered_papers
            ]
            if requested_ids:
                scored_papers = [
                    paper
                    for paper in scored_papers
                    if paper.acoustic_relevance >= ACOUSTIC_HARD_FILTER_THRESHOLD
                ]
            papers = rank_papers(
                query,
                scored_papers,
                journal_mode=bool(requested_ids),
            )[:limit]
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
