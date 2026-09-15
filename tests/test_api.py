"""FastAPI exposes the existing SearchService rather than another search path."""

import asyncio

import httpx
import pytest
from fastapi import FastAPI

from litwatch import api
from litwatch.core import Paper
from litwatch.search import SearchService


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

    def search(self, topic: str, limit: int) -> list[Paper]:
        self.calls += 1
        if self.error:
            raise self.error
        return [
            Paper(
                title="Underwater Acoustic TDOA Localization",
                doi="10.1000/acoustic",
                provider_id="W1",
                url="https://example.org/work",
                source=self.name,
                providers=[self.name],
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
