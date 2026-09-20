"""One provider-independent search path with honest aggregate status."""

import httpx
import pytest

from litwatch import search
from litwatch.core import Paper
from litwatch.providers import ArxivProvider, CrossrefProvider, OpenAlexProvider
from litwatch.providers.base import ProviderSearchCriteria


class FakeProvider:
    def __init__(self, name: str, records: list[Paper] | None = None, error: Exception | None = None):
        self.name = name
        self.records = records if records is not None else []
        self.error = error
        self.calls: list[tuple[str, int, ProviderSearchCriteria | None]] = []

    def search(
        self,
        topic: str,
        limit: int,
        *,
        criteria: ProviderSearchCriteria | None = None,
    ) -> list[Paper]:
        self.calls.append((topic, limit, criteria))
        if self.error:
            raise self.error
        return self.records


def paper(
    title: str = "Acoustic TDOA Localization",
    *,
    doi: str = "10.1000/acoustic",
    source: str = "openalex",
    provider_id: str = "W1",
    abstract: str = "",
    year: int | None = 2026,
    journal: str | None = None,
    journal_issns: list[str] | None = None,
    journal_source_ids: dict[str, str] | None = None,
) -> Paper:
    return Paper(
        title=title,
        abstract=abstract,
        year=year,
        doi=doi,
        provider_id=provider_id,
        url="https://example.org/work",
        source=source,
        providers=[source],
        journal=journal,
        journal_issns=journal_issns or [],
        journal_source_ids=journal_source_ids or {},
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


def test_journal_search_overfetches_then_applies_the_final_limit() -> None:
    records = [
        Paper(
            title=f"Underwater acoustic localization study {index}",
            year=2026 - index,
            doi=f"10.1000/acoustic-{index}",
            provider_id=f"W{index}",
            url=f"https://example.org/work/{index}",
            source="openalex",
            providers=["openalex"],
            journal="The Journal of the Acoustical Society of America",
            journal_issns=["0001-4966"],
        )
        for index in range(8)
    ]
    provider = FakeProvider("openalex", records)

    result = search.SearchService([provider]).search(
        "acoustic localization",
        2,
        journals=["jasa"],
        year_from=2020,
        year_to=2026,
    )

    assert result.paper_count == 2
    assert provider.calls[0][1] == 100
    criteria = provider.calls[0][2]
    assert criteria is not None
    assert [journal.journal_id for journal in criteria.journals] == ["jasa"]
    assert (criteria.year_from, criteria.year_to) == (2020, 2026)


def test_generic_search_keeps_non_acoustic_papers_without_journal_filter() -> None:
    candidate = paper(
        "Quantum error correction in superconducting qubits",
        journal="Nature",
        journal_issns=["0028-0836"],
    )

    result = search.SearchService([FakeProvider("openalex", [candidate])]).search(
        "quantum error correction", 5
    )

    assert result.status == "success"
    assert result.papers[0].title == candidate.title
    assert result.papers[0].journal_id == "nature"
    assert result.papers[0].acoustic_relevance == 0.0


def test_journal_search_requires_requested_journal_and_acoustic_relevance() -> None:
    records = [
        paper(
            "Quantum error correction in superconducting qubits",
            doi="10.1000/nature-quantum",
            provider_id="W-nature",
            journal="Nature",
            journal_issns=["0028-0836"],
        ),
        paper(
            "Underwater acoustic TDOA source localization",
            doi="10.1000/jasa-acoustic",
            provider_id="W-jasa",
            journal="Incorrect provider label",
            journal_issns=["0001-4966"],
        ),
        paper(
            "Sonar beamforming with hydrophone arrays",
            doi="10.1000/joe-acoustic",
            provider_id="W-joe",
            journal="IEEE Journal of Oceanic Engineering",
            journal_source_ids={"openalex": "S132957497"},
        ),
        paper(
            "Underwater acoustic propagation",
            doi="10.1000/ocean-acoustic",
            provider_id="W-ocean",
            journal="Ocean Engineering",
            journal_issns=["0029-8018"],
        ),
    ]

    result = search.SearchService([FakeProvider("openalex", records)]).search(
        "underwater acoustic localization",
        10,
        journals=["JASA", "IEEE J.O.E.", "Nature"],
    )

    assert result.status == "success"
    assert {item.journal_id for item in result.papers} == {"jasa", "ieee_joe"}
    assert all(item.acoustic_relevance > 0 for item in result.papers)
    assert {item.doi for item in result.papers} == {
        "10.1000/jasa-acoustic",
        "10.1000/joe-acoustic",
    }


def test_year_filter_runs_after_cross_provider_deduplication() -> None:
    openalex = FakeProvider(
        "openalex",
        [
            paper(
                "Underwater acoustic propagation",
                doi="10.1000/merged-year",
                provider_id="W-year",
                year=None,
                journal_issns=["0001-4966"],
            )
        ],
    )
    crossref = FakeProvider(
        "crossref",
        [
            paper(
                "Underwater acoustic propagation",
                doi="10.1000/merged-year",
                source="crossref",
                provider_id="10.1000/merged-year",
                year=2024,
                journal="JASA",
            )
        ],
    )

    result = search.SearchService([openalex, crossref]).search(
        "underwater acoustic propagation",
        5,
        journals=["jasa"],
        year_from=2024,
        year_to=2024,
    )

    assert result.paper_count == 1
    assert result.papers[0].year == 2024
    assert result.papers[0].providers == ["openalex", "crossref"]


def test_local_filter_empty_is_success_empty_not_provider_failure() -> None:
    result = search.SearchService(
        [
            FakeProvider(
                "openalex",
                [
                    paper(
                        "Quantum materials",
                        journal="Nature",
                        journal_issns=["0028-0836"],
                    )
                ],
            )
        ]
    ).search("underwater acoustics", 5, journals=["nature"])

    assert result.status == "success_empty"
    assert result.paper_count == 0
    assert result.provider_results[0].status == "success"
    assert result.provider_results[0].fetched_count == 1


def test_acoustic_relevance_outranks_priority_bonus_in_journal_mode() -> None:
    records = [
        paper(
            "Acoustic sensing",
            doi="10.1000/nature-weak",
            provider_id="W-nature-weak",
            journal="Nature",
            journal_issns=["0028-0836"],
        ),
        paper(
            "Underwater acoustic source localization with sonar beamforming",
            doi="10.1000/jasa-strong",
            provider_id="W-jasa-strong",
            journal="JASA",
            journal_issns=["0001-4966"],
        ),
    ]

    result = search.SearchService([FakeProvider("openalex", records)]).search(
        "acoustic sensing",
        5,
        journals=["nature", "jasa"],
    )

    assert [item.doi for item in result.papers] == [
        "10.1000/jasa-strong",
        "10.1000/nature-weak",
    ]
    assert result.papers[0].acoustic_relevance > result.papers[1].acoustic_relevance


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
    assert result.papers[0].acoustic_relevance > 0
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
