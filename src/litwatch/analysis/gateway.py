"""OpenAI-compatible chat-completions gateway with destination validation."""

import ipaddress
import json
import socket
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

import httpcore
import httpx
from pydantic import ValidationError

from litwatch.analysis.models import QuickScan

Resolver = Callable[..., list[tuple]]


class InvalidBaseUrlError(ValueError):
    pass


class GatewayTimeoutError(RuntimeError):
    pass


class GatewayUpstreamError(RuntimeError):
    pass


class GatewayResponseError(RuntimeError):
    pass


@dataclass(frozen=True)
class _ValidatedEndpoint:
    base_url: str
    hostname: str
    port: int
    addresses: tuple[str, ...]


def _is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return bool(
        ip.is_global
        and not ip.is_private
        and not ip.is_loopback
        and not ip.is_link_local
        and not ip.is_reserved
        and not ip.is_multicast
        and not ip.is_unspecified
    )


def _validated_endpoint(
    base_url: str, resolver: Resolver = socket.getaddrinfo
) -> _ValidatedEndpoint:
    try:
        parsed = urlsplit(base_url.strip())
        port = parsed.port or 443
    except ValueError:
        raise InvalidBaseUrlError("invalid LLM base URL") from None
    hostname = parsed.hostname
    if (
        parsed.scheme.casefold() != "https"
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or hostname.casefold() == "localhost"
        or hostname.casefold().endswith(".localhost")
    ):
        raise InvalidBaseUrlError("LLM base URL must be a public HTTPS endpoint")

    try:
        literal = ipaddress.ip_address(hostname.strip("[]"))
        addresses = (str(literal),)
    except ValueError:
        try:
            addresses = tuple(
                dict.fromkeys(
                    str(ipaddress.ip_address(item[4][0]))
                    for item in resolver(hostname, port, type=socket.SOCK_STREAM)
                    if item[4]
                )
            )
        except (OSError, ValueError):
            raise InvalidBaseUrlError("LLM base URL hostname could not be resolved") from None
    if not addresses or any(not _is_public(address) for address in addresses):
        raise InvalidBaseUrlError("LLM base URL resolves to a non-public address")

    path = parsed.path.rstrip("/")
    return _ValidatedEndpoint(
        base_url=urlunsplit(("https", parsed.netloc, path, "", "")),
        hostname=hostname,
        port=port,
        addresses=addresses,
    )


def validate_base_url(base_url: str, resolver: Resolver = socket.getaddrinfo) -> str:
    return _validated_endpoint(base_url, resolver).base_url


class _PinnedNetworkBackend(httpcore.NetworkBackend):
    """Connect an already-validated origin to its captured public addresses."""

    def __init__(
        self,
        endpoint: _ValidatedEndpoint,
        backend: httpcore.NetworkBackend,
    ) -> None:
        self.endpoint = endpoint
        self.backend = backend

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options=None,
    ) -> httpcore.NetworkStream:
        if host.casefold() != self.endpoint.hostname.casefold() or port != self.endpoint.port:
            raise httpcore.ConnectError("connection target differs from validated LLM origin")

        last_error: httpcore.ConnectError | httpcore.ConnectTimeout | None = None
        for address in self.endpoint.addresses:
            try:
                return self.backend.connect_tcp(
                    address,
                    port,
                    timeout=timeout,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except (httpcore.ConnectError, httpcore.ConnectTimeout) as error:
                last_error = error
        assert last_error is not None
        raise last_error

    def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options=None,
    ) -> httpcore.NetworkStream:
        del path, timeout, socket_options
        raise httpcore.ConnectError("Unix sockets are not allowed for LLM requests")


class _PinnedHTTPTransport(httpx.HTTPTransport):
    def __init__(
        self,
        endpoint: _ValidatedEndpoint,
        backend: httpcore.NetworkBackend,
    ) -> None:
        self._pool = httpcore.ConnectionPool(
            ssl_context=httpx.create_ssl_context(verify=True, trust_env=False),
            network_backend=_PinnedNetworkBackend(endpoint, backend),
        )


class OpenAICompatibleGateway:
    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        resolver: Resolver = socket.getaddrinfo,
        network_backend: httpcore.NetworkBackend | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.client = client
        self.resolver = resolver
        self.network_backend = network_backend
        self.timeout = timeout

    def quick_scan(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str,
        paper_text: str,
    ) -> QuickScan:
        endpoint = _validated_endpoint(base_url, self.resolver)
        payload = {
            "model": model,
            "temperature": 0,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Analyze only the supplied paper metadata. Return one JSON object. "
                        "summary, research_question, methodology, and relevance must be strings. "
                        "key_findings, innovations, and limitations must be arrays of strings. "
                        "Use 'unavailable' for an unsupported string field and ['unavailable'] "
                        "for an unsupported array field; never invent details."
                    ),
                },
                {"role": "user", "content": paper_text},
            ],
        }
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        try:
            if self.client is None:
                transport = _PinnedHTTPTransport(
                    endpoint,
                    self.network_backend or httpcore.SyncBackend(),
                )
                with httpx.Client(
                    timeout=self.timeout,
                    follow_redirects=False,
                    trust_env=False,
                    transport=transport,
                ) as client:
                    response = self._send(client, endpoint.base_url, headers, payload)
            else:
                response = self._send(self.client, endpoint.base_url, headers, payload)
        except httpx.TimeoutException:
            raise GatewayTimeoutError("LLM request timed out") from None
        except httpx.HTTPError:
            raise GatewayUpstreamError("LLM upstream request failed") from None

        try:
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise TypeError
            return QuickScan.model_validate(json.loads(content))
        except (KeyError, IndexError, TypeError, ValueError, ValidationError):
            raise GatewayResponseError("LLM returned an invalid structured response") from None

    @staticmethod
    def _send(
        client: httpx.Client,
        safe_base_url: str,
        headers: dict[str, str],
        payload: dict[str, object],
    ) -> httpx.Response:
        request = client.build_request(
            "POST", f"{safe_base_url}/chat/completions", headers=headers, json=payload
        )
        response = client.send(request, follow_redirects=False)
        response.raise_for_status()
        return response
