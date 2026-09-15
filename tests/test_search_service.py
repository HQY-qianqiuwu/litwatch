"""One provider-independent search path with honest aggregate status."""

import httpx
import pytest

from litwatch import search
from litwatch.core import Paper
from litwatch.providers import ArxivProvider, CrossrefProvider, OpenAlexProvider


class FakeProvider:
    def __init__(self, name: str, records: list[Paper] | None = None, error: Exception | None = None):
        self.name = name
        self.records = records if records is not None else []
        self.error = error
        self.calls: list[tuple[str, int]] = []

    def search(self, topic: str, limit: int) -> list[Paper]:
        self.calls.append((topic, limit))
        if self.error:
            raise self.error
        return self.records


def paper(title: str = "Acoustic TDOA Localization") -> Paper:
    return Paper(
        title=title,
        year=2026,
        doi="10.1000/acoustic",
        provider_id="W1",
        url="https://example.org/work",
        source="openalex",
        providers=["openalex"],
    )


@pytest.mark.parametrize(
    ("first_records", "first_error", "second_records", "second_error", "expected"),
    [
        ([paper()], None, [], None, "success"),
        ([], None, [], None, "success_empty"),
        ([paper()], None, None, httpx.ReadTimeout("arxiv timeout"), "partial_success"),
        (None, httpx.ReadTimeout("openalex timeout"), None, RuntimeError("unavailable"),
         "all_providers_failed"),
    ],
)
def test_four_search_statuses_and_one_call_per_provider(
    first_records: list[Paper] | None,
    first_error: Exception | None,
    second_records: list[Paper] | None,
    second_error: Exception | None,
    expected: str,
) -> None:
    service_type = getattr(search, "SearchService", None)
    assert service_type is not None

    first = FakeProvider("openalex", first_records, first_error)
    second = FakeProvider("arxiv", second_records, second_error)
    result = service_type([first, second]).search(" acoustic TDOA localization ", 5)

    assert result.status == expected
    assert result.paper_count == (1 if first_records else 0)
    assert [item.provider for item in result.provider_results] == ["openalex", "arxiv"]
    assert len(first.calls) == len(second.calls) == 1
    assert first.calls[0][0] == "acoustic TDOA localization"
    assert first.calls[0][1] >= 5
    if second_error and isinstance(second_error, httpx.TimeoutException):
        assert result.provider_results[1].status == "timeout"


def test_provider_rate_limit_is_a_diagnostic_not_a_success() -> None:
    service_type = getattr(search, "SearchService", None)
    assert service_type is not None

    request = httpx.Request("GET", "https://api.example.org/works")
    response = httpx.Response(429, request=request)
    limited = httpx.HTTPStatusError("rate limited", request=request, response=response)
    result = service_type([FakeProvider("crossref", error=limited)]).search("acoustic", 5)

    assert result.status == "all_providers_failed"
    assert result.provider_results[0].status == "rate_limited"
    assert result.provider_results[0].error_code == "http_429"
    assert result.paper_count == 0


def test_partial_provider_fallback_runs_normalize_deduplicate_rank_result() -> None:
    service_type = getattr(search, "SearchService", None)
    assert service_type is not None

    def openalex_reply(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [{
                    "id": "https://openalex.org/W1",
                    "title": "Acoustic TDOA Localization",
                    "doi": "https://doi.org/10.1000/acoustic",
                    "publication_year": 2026,
                    "abstract_inverted_index": {"acoustic": [0], "TDOA": [1]},
                }]
            },
        )

    def crossref_reply(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"message": {"items": [{
                "DOI": "10.1000/ACOUSTIC",
                "title": ["Acoustic TDOA Localization"],
                "author": [{"given": "Lin", "family": "Researcher"}],
                "issued": {"date-parts": [[2026]]},
            }]}}
        )

    def arxiv_timeout(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out")

    with (
        httpx.Client(transport=httpx.MockTransport(openalex_reply)) as openalex_client,
        httpx.Client(transport=httpx.MockTransport(arxiv_timeout)) as arxiv_client,
        httpx.Client(transport=httpx.MockTransport(crossref_reply)) as crossref_client,
    ):
        result = service_type([
            OpenAlexProvider(client=openalex_client),
            ArxivProvider(client=arxiv_client),
            CrossrefProvider(client=crossref_client),
        ]).search("acoustic TDOA localization", 5)

    assert result.status == "partial_success"
    assert result.paper_count == 1
    assert result.papers[0].doi == "10.1000/acoustic"
    assert result.papers[0].providers == ["openalex", "crossref"]
    assert result.papers[0].score > 0
    assert result.provider_results[1].status == "timeout"
    assert result.provider_results[0].fetched_count == 1
    assert result.provider_results[2].fetched_count == 1


@pytest.mark.parametrize(
    ("provider_type", "upstream_response"),
    [
        (
            OpenAlexProvider,
            httpx.Response(200, json={"results": [{"id": "https://openalex.org/W999", "title": ""}]}),
        ),
        (
            ArxivProvider,
            httpx.Response(
                200,
                text=(
                    '<feed xmlns="http://www.w3.org/2005/Atom">'
                    '<entry><id>https://arxiv.org/abs/2401.99999</id></entry></feed>'
                ),
            ),
        ),
        (
            CrossrefProvider,
            httpx.Response(200, json={"message": {"items": [{"DOI": "10.9999/empty", "title": []}]}}),
        ),
    ],
)
def test_nonempty_but_unusable_upstream_data_is_not_success_empty(
    provider_type: type, upstream_response: httpx.Response
) -> None:
    with httpx.Client(transport=httpx.MockTransport(lambda _request: upstream_response)) as client:
        result = search.SearchService([provider_type(client=client)]).search("acoustic", 5)

    assert result.status == "all_providers_failed"
    assert result.provider_results[0].status == "parse_error"
    assert result.paper_count == 0


def test_crossref_work_without_doi_or_url_is_not_returned_as_openable_paper() -> None:
    upstream = httpx.Response(
        200,
        json={"message": {"items": [{"title": ["Acoustic Localization"], "author": []}]}},
    )
    with httpx.Client(transport=httpx.MockTransport(lambda _request: upstream)) as client:
        result = search.SearchService([CrossrefProvider(client=client)]).search("acoustic", 5)

    assert result.status == "all_providers_failed"
    assert result.provider_results[0].status == "parse_error"
    assert result.paper_count == 0
