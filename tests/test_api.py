"""FastAPI exposes the existing SearchService rather than another search path."""

import asyncio

import httpx
import pytest
from fastapi import FastAPI

from litwatch import api
from litwatch.core import Paper
from litwatch.providers.base import ProviderSearchCriteria
from litwatch.search import SearchService
from litwatch.storage import SearchRepository


def asgi_request(
    application: FastAPI, method: str, path: str, payload: dict[str, object] | None = None
) -> httpx.Response:
    async def send() -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application), base_url="http://litwatch.test"
        ) as client:
            return await client.request(method, path, json=payload)

    return asyncio.run(send())


class CountingProvider:
    name = "openalex"

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls = 0
        self.last_criteria: ProviderSearchCriteria | None = None

    def search(
        self,
        topic: str,
        limit: int,
        *,
        criteria: ProviderSearchCriteria | None = None,
    ) -> list[Paper]:
        self.calls += 1
        self.last_criteria = criteria
        if self.error:
            raise self.error
        return [
            Paper(
                title="Underwater Acoustic TDOA Localization",
                year=2026,
                doi="10.1000/acoustic",
                provider_id="W1",
                url="https://example.org/work",
                source=self.name,
                providers=[self.name],
                journal="The Journal of the Acoustical Society of America",
                journal_issns=["0001-4966"],
            )
        ]


def test_health_and_default_provider_listing() -> None:
    factory = getattr(api, "create_app", None)
    assert factory is not None

    application = factory()
    health = asgi_request(application, "GET", "/health")
    providers = asgi_request(application, "GET", "/api/v1/providers")

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert providers.status_code == 200
    assert [item["provider"] for item in providers.json()["providers"]] == [
        "openalex", "arxiv", "crossref"
    ]
    assert all(item["enabled"] and item["configured"] for item in providers.json()["providers"])


def test_search_route_uses_one_search_service_call_and_returns_papers() -> None:
    factory = getattr(api, "create_app", None)
    assert factory is not None

    provider = CountingProvider()
    response = asgi_request(
        factory(SearchService([provider])),
        "POST",
        "/api/v1/literature/search",
        {"topic": "underwater acoustic TDOA localization", "limit": 5},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["paper_count"] == 1
    assert response.json()["papers"][0]["doi"] == "10.1000/acoustic"
    assert response.json()["provider_results"][0]["provider"] == "openalex"
    assert provider.calls == 1


@pytest.mark.parametrize(
    ("error", "http_status", "provider_status"),
    [
        (httpx.ReadTimeout("source timeout"), 504, "timeout"),
        (RuntimeError("source unavailable"), 502, "upstream_error"),
    ],
)
def test_all_provider_failures_are_http_errors_with_diagnostics(
    error: Exception, http_status: int, provider_status: str
) -> None:
    factory = getattr(api, "create_app", None)
    assert factory is not None

    response = asgi_request(
        factory(SearchService([CountingProvider(error)])),
        "POST",
        "/api/v1/literature/search",
        {"topic": "acoustic", "limit": 5},
    )

    assert response.status_code == http_status
    assert response.json()["status"] == "all_providers_failed"
    assert response.json()["paper_count"] == 0
    assert response.json()["provider_results"][0]["status"] == provider_status


def test_invalid_search_request_is_rejected_before_search() -> None:
    factory = getattr(api, "create_app", None)
    assert factory is not None

    provider = CountingProvider()
    response = asgi_request(
        factory(SearchService([provider])),
        "POST",
        "/api/v1/literature/search",
        {"topic": "   ", "limit": 0},
    )

    assert response.status_code == 422
    assert provider.calls == 0


@pytest.mark.parametrize(
    "payload",
    [
        {"topic": "underwater acoustics", "journals": ["unknown journal"]},
        {"topic": "underwater acoustics", "year_from": 2026, "year_to": 2020},
    ],
)
def test_invalid_search_criteria_return_422_without_provider_call(
    payload: dict[str, object],
) -> None:
    provider = CountingProvider()

    response = asgi_request(
        api.create_app(SearchService([provider])),
        "POST",
        "/api/v1/literature/search",
        payload,
    )

    assert response.status_code == 422
    assert provider.calls == 0


def test_filtered_search_forwards_criteria_and_persists_additive_metadata(tmp_path) -> None:
    path = tmp_path / "filtered.sqlite3"
    provider = CountingProvider()
    application = api.create_app(
        SearchService([provider]),
        repository=SearchRepository(path),
    )
    payload = {
        "topic": "underwater acoustic TDOA localization",
        "journals": ["JASA"],
        "year_from": 2020,
        "year_to": 2026,
        "limit": 5,
    }

    first = asgi_request(application, "POST", "/api/v1/literature/search", payload)
    second = asgi_request(application, "POST", "/api/v1/literature/search", payload)

    assert first.status_code == second.status_code == 200
    body = first.json()
    assert body["papers"][0]["journal_id"] == "jasa"
    assert body["papers"][0]["journal"] == (
        "The Journal of the Acoustical Society of America"
    )
    assert body["papers"][0]["acoustic_relevance"] > 0
    assert body["papers"][0]["abstract_status"] == "pending"
    assert body["papers"][0]["analysis_eligible"] is False
    assert body["papers"][0]["paper_id"] == second.json()["papers"][0]["paper_id"]
    assert provider.last_criteria is not None
    assert [journal.journal_id for journal in provider.last_criteria.journals] == ["jasa"]
    assert (provider.last_criteria.year_from, provider.last_criteria.year_to) == (
        2020,
        2026,
    )
    persisted = SearchRepository(path).get_paper(body["papers"][0]["paper_id"])
    assert persisted.journal_id == "jasa"
    assert persisted.analysis_eligible is False


def test_api_search_returns_persistent_scan_and_stable_paper_id(tmp_path) -> None:
    path = tmp_path / "litwatch.sqlite3"
    provider = CountingProvider()
    application = api.create_app(SearchService([provider]), repository=SearchRepository(path))

    first = asgi_request(
        application, "POST", "/api/v1/literature/search", {"topic": "acoustic", "limit": 5}
    )
    second = asgi_request(
        application, "POST", "/api/v1/literature/search", {"topic": "acoustic", "limit": 5}
    )

    assert first.status_code == second.status_code == 200
    assert first.json()["scan_id"] != second.json()["scan_id"]
    assert first.json()["papers"][0]["paper_id"] == second.json()["papers"][0]["paper_id"]
    assert provider.calls == 2  # one provider request for each API search, never a second search
    restarted = SearchRepository(path)
    assert restarted.get_scan(first.json()["scan_id"]).papers[0].paper_id == (
        first.json()["papers"][0]["paper_id"]
    )
    assert restarted.get_paper(first.json()["papers"][0]["paper_id"]).doi == (
        "10.1000/acoustic"
    )


def test_failed_provider_search_also_persists_scan_diagnostics(tmp_path) -> None:
    path = tmp_path / "litwatch.sqlite3"
    provider = CountingProvider(RuntimeError("unavailable"))
    response = asgi_request(
        api.create_app(SearchService([provider]), repository=SearchRepository(path)),
        "POST",
        "/api/v1/literature/search",
        {"topic": "acoustic", "limit": 5},
    )

    assert response.status_code == 502
    assert response.json()["scan_id"]
    assert SearchRepository(path).get_scan(response.json()["scan_id"]).status == (
        "all_providers_failed"
    )


def test_app_uses_configured_database_path_for_search(tmp_path, monkeypatch) -> None:
    path = tmp_path / "configured.sqlite3"
    monkeypatch.setenv("LITWATCH_DATABASE_PATH", str(path))
    response = asgi_request(
        api.create_app(SearchService([CountingProvider()])),
        "POST",
        "/api/v1/literature/search",
        {"topic": "acoustic", "limit": 5},
    )

    assert response.status_code == 200
    assert path.is_file()
    assert SearchRepository(path).get_scan(response.json()["scan_id"]) is not None
