"""FastAPI exposes BYOK analysis without adding a search path."""

import asyncio
import json

import httpx
import pytest
from fastapi import FastAPI

from litwatch.analysis import OpenAICompatibleGateway, PaperAnalysisService
from litwatch.api import create_app
from litwatch.core import Paper, SearchResult, SearchStatus
from litwatch.storage import AnalysisRepository, SearchRepository


def asgi_request(
    application: FastAPI,
    method: str,
    path: str,
    *,
    payload: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    async def send() -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application), base_url="http://litwatch.test"
        ) as client:
            return await client.request(method, path, json=payload, headers=headers)

    return asyncio.run(send())


class NoSearchService:
    providers: tuple = ()

    def search(self, _topic: str, _limit: int) -> SearchResult:
        raise AssertionError("analysis must not trigger SearchService")


class NoAnalysisGateway:
    def quick_scan(self, **_kwargs: object) -> None:
        raise AssertionError("GET analysis must not invoke the LLM gateway")


def public_resolver(_host: str, _port: int, **_kwargs: object) -> list[tuple]:
    return [(2, 1, 6, "", ("93.184.216.34", 443))]


def private_resolver(_host: str, _port: int, **_kwargs: object) -> list[tuple]:
    return [(2, 1, 6, "", ("192.168.1.7", 443))]


def llm_payload() -> dict[str, object]:
    result = {
        "summary": "A concise summary.",
        "research_question": "How can TDOA improve localization?",
        "methodology": "Simulation and field experiments.",
        "key_findings": "The method reduced error.",
        "innovations": "A robust timing estimator.",
        "limitations": "Limited field sites.",
        "relevance": "Relevant to underwater localization.",
    }
    return {"choices": [{"message": {"content": json.dumps(result)}}]}


def saved_paper(repository: SearchRepository) -> Paper:
    return repository.save(
        SearchResult(
            topic="acoustic",
            status=SearchStatus.SUCCESS,
            papers=[
                Paper(
                    title="Underwater Acoustic Localization",
                    abstract="A TDOA study.",
                    doi="10.1000/acoustic",
                    provider_id="W123",
                    url="https://example.org/paper",
                    source="openalex",
                    providers=["openalex"],
                )
            ],
        )
    ).papers[0]


def make_app(tmp_path, responder, *, resolver=public_resolver):
    path = tmp_path / "litwatch.sqlite3"
    papers = SearchRepository(path)
    paper = saved_paper(papers)
    client = httpx.Client(transport=httpx.MockTransport(responder), follow_redirects=False)
    gateway = OpenAICompatibleGateway(client=client, resolver=resolver)
    service = PaperAnalysisService(papers, AnalysisRepository(path), gateway)
    application = create_app(NoSearchService(), repository=papers, analysis_service=service)
    return application, path, paper, client


def test_analyze_and_get_round_trip_uses_header_key_without_search(tmp_path) -> None:
    secret = "secret-never-persist"
    application, path, paper, client = make_app(
        tmp_path, lambda _request: httpx.Response(200, json=llm_payload())
    )
    try:
        response = asgi_request(
            application,
            "POST",
            "/api/v1/literature/analyze",
            payload={
                "paper_id": paper.paper_id,
                "analysis_mode": "quick_scan",
                "base_url": "https://llm.example.test/v1",
                "model": "example-model",
            },
            headers={"X-LitWatch-LLM-Key": secret},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["analysis_id"].startswith("A-")
        assert body["paper_id"] == paper.paper_id
        assert body["result"]["summary"] == "A concise summary."
        fetched = asgi_request(
            application, "GET", f"/api/v1/analyses/{body['analysis_id']}"
        )
        assert fetched.status_code == 200
        assert fetched.json() == body
        assert secret not in response.text
        assert secret not in fetched.text
        assert secret.encode() not in path.read_bytes()
    finally:
        client.close()


def test_mock_e2e_survives_app_and_repository_recreation(tmp_path) -> None:
    application, path, paper, client = make_app(
        tmp_path, lambda _request: httpx.Response(200, json=llm_payload())
    )
    try:
        created = asgi_request(
            application,
            "POST",
            "/api/v1/literature/analyze",
            payload={
                "paper_id": paper.paper_id,
                "analysis_mode": "quick_scan",
                "base_url": "https://llm.example.test/v1",
                "model": "example-model",
            },
            headers={"X-LitWatch-LLM-Key": "ephemeral-key"},
        )
    finally:
        client.close()
    assert created.status_code == 200

    rebuilt_papers = SearchRepository(path)
    rebuilt_service = PaperAnalysisService(
        rebuilt_papers,
        AnalysisRepository(path),
        NoAnalysisGateway(),
    )
    rebuilt_app = create_app(
        NoSearchService(),
        repository=rebuilt_papers,
        analysis_service=rebuilt_service,
    )
    restored = asgi_request(
        rebuilt_app,
        "GET",
        f"/api/v1/analyses/{created.json()['analysis_id']}",
    )

    assert restored.status_code == 200
    assert restored.json() == created.json()


def test_analyze_missing_paper_is_404_without_llm_request(tmp_path) -> None:
    calls = 0

    def responder(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=llm_payload())

    application, _path, _paper, client = make_app(tmp_path, responder)
    try:
        response = asgi_request(
            application,
            "POST",
            "/api/v1/literature/analyze",
            payload={
                "paper_id": "P-missing",
                "analysis_mode": "quick_scan",
                "base_url": "https://llm.example.test/v1",
                "model": "example-model",
            },
            headers={"X-LitWatch-LLM-Key": "secret-test-key"},
        )
    finally:
        client.close()
    assert response.status_code == 404
    assert calls == 0


def test_get_missing_analysis_is_404(tmp_path) -> None:
    application, _path, _paper, client = make_app(
        tmp_path, lambda _request: httpx.Response(200, json=llm_payload())
    )
    try:
        response = asgi_request(application, "GET", "/api/v1/analyses/A-missing")
    finally:
        client.close()
    assert response.status_code == 404


def test_private_base_url_is_422_and_does_not_call_llm(tmp_path) -> None:
    calls = 0

    def responder(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=llm_payload())

    application, _path, paper, client = make_app(
        tmp_path, responder, resolver=private_resolver
    )
    try:
        response = asgi_request(
            application,
            "POST",
            "/api/v1/literature/analyze",
            payload={
                "paper_id": paper.paper_id,
                "analysis_mode": "quick_scan",
                "base_url": "https://private.example.test/v1",
                "model": "example-model",
            },
            headers={"X-LitWatch-LLM-Key": "secret-test-key"},
        )
    finally:
        client.close()
    assert response.status_code == 422
    assert calls == 0


@pytest.mark.parametrize(
    ("responder", "expected_status"),
    [
        (lambda _request: (_ for _ in ()).throw(httpx.ReadTimeout("timed out")), 504),
        (lambda _request: httpx.Response(503, text="unavailable"), 502),
        (lambda _request: httpx.Response(200, json={"choices": []}), 502),
    ],
    ids=["timeout", "upstream", "malformed"],
)
def test_llm_failures_have_sanitized_http_statuses(tmp_path, responder, expected_status) -> None:
    application, _path, paper, client = make_app(tmp_path, responder)
    secret = "secret-not-in-error"
    try:
        response = asgi_request(
            application,
            "POST",
            "/api/v1/literature/analyze",
            payload={
                "paper_id": paper.paper_id,
                "analysis_mode": "quick_scan",
                "base_url": "https://llm.example.test/v1",
                "model": "example-model",
            },
            headers={"X-LitWatch-LLM-Key": secret},
        )
    finally:
        client.close()
    assert response.status_code == expected_status
    assert secret not in response.text
