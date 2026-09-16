"""OpenAI-compatible gateway validates destinations and structured output."""

import httpx
import pytest

from litwatch.analysis import (
    GatewayResponseError,
    InvalidBaseUrlError,
    OpenAICompatibleGateway,
)


def public_resolver(_host: str, _port: int, **_kwargs: object) -> list[tuple]:
    return [(2, 1, 6, "", ("93.184.216.34", 443))]


def private_resolver(_host: str, _port: int, **_kwargs: object) -> list[tuple]:
    return [(2, 1, 6, "", ("10.0.0.7", 443))]


def quick_scan_payload() -> dict[str, str]:
    return {
        "summary": "A concise summary.",
        "research_question": "How can TDOA improve localization?",
        "methodology": "Simulation and field experiments.",
        "key_findings": "The proposed method reduced error.",
        "innovations": "A robust timing estimator.",
        "limitations": "Limited field sites.",
        "relevance": "Directly relevant to underwater localization.",
    }


def test_gateway_returns_validated_quick_scan_without_following_redirects() -> None:
    seen: dict[str, object] = {}

    def reply(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["authorization"] = request.headers.get("authorization")
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": __import__("json").dumps(
                quick_scan_payload()
            )}}]},
        )

    with httpx.Client(transport=httpx.MockTransport(reply), follow_redirects=False) as client:
        result = OpenAICompatibleGateway(client=client, resolver=public_resolver).quick_scan(
            base_url="https://llm.example.test/v1",
            model="example-model",
            api_key="secret-test-key",
            paper_text="Title: Underwater acoustic localization",
        )

    assert result.model_dump() == quick_scan_payload()
    assert seen == {
        "url": "https://llm.example.test/v1/chat/completions",
        "authorization": "Bearer secret-test-key",
    }


@pytest.mark.parametrize(
    ("base_url", "resolver"),
    [
        ("http://api.example.test/v1", public_resolver),
        ("https://localhost/v1", public_resolver),
        ("https://127.0.0.1/v1", public_resolver),
        ("https://169.254.169.254/v1", public_resolver),
        ("https://10.0.0.7/v1", public_resolver),
        ("https://llm.example.test/v1", private_resolver),
        ("https://user:password@llm.example.test/v1", public_resolver),
    ],
)
def test_gateway_rejects_unsafe_base_urls_before_http(
    base_url: str, resolver
) -> None:
    calls = 0

    def reply(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200)

    with (
        httpx.Client(transport=httpx.MockTransport(reply)) as client,
        pytest.raises(InvalidBaseUrlError),
    ):
        OpenAICompatibleGateway(client=client, resolver=resolver).quick_scan(
            base_url=base_url,
            model="model",
            api_key="secret-test-key",
            paper_text="paper",
        )
    assert calls == 0


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"choices": []},
        {"choices": [{"message": {"content": "not-json"}}]},
        {"choices": [{"message": {"content": '{"summary": "only one field"}'}}]},
    ],
)
def test_gateway_rejects_malformed_llm_response(payload: dict) -> None:
    with (
        httpx.Client(
            transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=payload))
        ) as client,
        pytest.raises(GatewayResponseError),
    ):
        OpenAICompatibleGateway(client=client, resolver=public_resolver).quick_scan(
            base_url="https://llm.example.test/v1",
            model="model",
            api_key="secret-test-key",
            paper_text="paper",
        )
