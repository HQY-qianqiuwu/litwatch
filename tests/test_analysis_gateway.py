"""OpenAI-compatible gateway validates destinations and structured output."""

import json
import ssl

import httpcore
import httpx
import pytest

from litwatch.analysis import (
    GatewayResponseError,
    GatewayUpstreamError,
    InvalidBaseUrlError,
    OpenAICompatibleGateway,
)


def public_resolver(_host: str, _port: int, **_kwargs: object) -> list[tuple]:
    return [(2, 1, 6, "", ("93.184.216.34", 443))]


def private_resolver(_host: str, _port: int, **_kwargs: object) -> list[tuple]:
    return [(2, 1, 6, "", ("10.0.0.7", 443))]


class RecordingStream(httpcore.NetworkStream):
    def __init__(self, body: bytes) -> None:
        self.response = (
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\n"
            + f"Content-Length: {len(body)}\r\n\r\n".encode()
            + body
        )
        self.writes: list[bytes] = []
        self.server_hostname: str | None = None
        self.check_hostname: bool | None = None
        self.verify_mode: ssl.VerifyMode | None = None

    def read(self, _max_bytes: int, timeout: float | None = None) -> bytes:
        del timeout
        response, self.response = self.response, b""
        return response

    def write(self, buffer: bytes, timeout: float | None = None) -> None:
        del timeout
        self.writes.append(buffer)

    def close(self) -> None:
        pass

    def start_tls(
        self,
        ssl_context: ssl.SSLContext,
        server_hostname: str | None = None,
        timeout: float | None = None,
    ) -> httpcore.NetworkStream:
        del timeout
        self.server_hostname = server_hostname
        self.check_hostname = ssl_context.check_hostname
        self.verify_mode = ssl_context.verify_mode
        return self

    def get_extra_info(self, info: str) -> object:
        if info == "is_readable":
            return False
        return None


class RecordingBackend(httpcore.NetworkBackend):
    def __init__(self, stream: RecordingStream) -> None:
        self.stream = stream
        self.connections: list[tuple[str, int]] = []

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options=None,
    ) -> httpcore.NetworkStream:
        del timeout, local_address, socket_options
        self.connections.append((host, port))
        return self.stream

    def connect_unix_socket(self, *args, **kwargs) -> httpcore.NetworkStream:
        del args, kwargs
        raise AssertionError("Unix sockets are not allowed")


def quick_scan_payload() -> dict[str, object]:
    return {
        "summary": "A concise summary.",
        "research_question": "How can TDOA improve localization?",
        "methodology": "Simulation and field experiments.",
        "key_findings": ["The proposed method reduced error."],
        "innovations": ["A robust timing estimator."],
        "limitations": ["Limited field sites."],
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


def test_gateway_does_not_follow_redirects() -> None:
    calls: list[str] = []

    def reply(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://127.0.0.1/private"})

    with (
        httpx.Client(transport=httpx.MockTransport(reply), follow_redirects=True) as client,
        pytest.raises(GatewayUpstreamError),
    ):
        OpenAICompatibleGateway(client=client, resolver=public_resolver).quick_scan(
            base_url="https://llm.example.test/v1",
            model="model",
            api_key="secret-test-key",
            paper_text="paper",
        )

    assert calls == ["https://llm.example.test/v1/chat/completions"]


def test_gateway_pins_validated_ip_and_preserves_hostname_for_tls() -> None:
    resolver_calls = 0

    def rebinding_resolver(_host: str, _port: int, **_kwargs: object) -> list[tuple]:
        nonlocal resolver_calls
        resolver_calls += 1
        address = "93.184.216.34" if resolver_calls == 1 else "127.0.0.1"
        return [(2, 1, 6, "", (address, 443))]

    content = json.dumps(quick_scan_payload())
    body = json.dumps({"choices": [{"message": {"content": content}}]}).encode()
    stream = RecordingStream(body)
    backend = RecordingBackend(stream)

    result = OpenAICompatibleGateway(
        resolver=rebinding_resolver,
        network_backend=backend,
    ).quick_scan(
        base_url="https://llm.example.test/v1",
        model="model",
        api_key="secret-test-key",
        paper_text="paper",
    )

    assert result.model_dump() == quick_scan_payload()
    assert resolver_calls == 1
    assert backend.connections == [("93.184.216.34", 443)]
    assert stream.server_hostname == "llm.example.test"
    assert stream.check_hostname is True
    assert stream.verify_mode == ssl.CERT_REQUIRED
    assert b"Host: llm.example.test" in b"".join(stream.writes)


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


@pytest.mark.parametrize("field", ["key_findings", "innovations", "limitations"])
def test_gateway_rejects_string_for_list_field(field: str) -> None:
    payload = quick_scan_payload()
    payload[field] = "must be an array"
    response = {
        "choices": [{"message": {"content": __import__("json").dumps(payload)}}]
    }

    with (
        httpx.Client(
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(200, json=response)
            )
        ) as client,
        pytest.raises(GatewayResponseError),
    ):
        OpenAICompatibleGateway(client=client, resolver=public_resolver).quick_scan(
            base_url="https://llm.example.test/v1",
            model="model",
            api_key="secret-test-key",
            paper_text="paper",
        )
