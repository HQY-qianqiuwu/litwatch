"""OpenAI-compatible chat-completions gateway with destination validation."""

import ipaddress
import json
import socket
from collections.abc import Callable
from urllib.parse import urlsplit, urlunsplit

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


def validate_base_url(base_url: str, resolver: Resolver = socket.getaddrinfo) -> str:
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
        addresses = {str(literal)}
    except ValueError:
        try:
            addresses = {
                str(item[4][0])
                for item in resolver(hostname, port, type=socket.SOCK_STREAM)
                if item[4]
            }
        except OSError:
            raise InvalidBaseUrlError("LLM base URL hostname could not be resolved") from None
    if not addresses or any(not _is_public(address) for address in addresses):
        raise InvalidBaseUrlError("LLM base URL resolves to a non-public address")

    path = parsed.path.rstrip("/")
    return urlunsplit(("https", parsed.netloc, path, "", ""))


class OpenAICompatibleGateway:
    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        resolver: Resolver = socket.getaddrinfo,
        timeout: float = 30.0,
    ) -> None:
        self.client = client
        self.resolver = resolver
        self.timeout = timeout

    def quick_scan(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str,
        paper_text: str,
    ) -> QuickScan:
        safe_base_url = validate_base_url(base_url, self.resolver)
        payload = {
            "model": model,
            "temperature": 0,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Analyze only the supplied paper metadata. Return one JSON object with "
                        "exactly these string fields: summary, research_question, methodology, "
                        "key_findings, innovations, limitations, relevance. Use 'unavailable' for "
                        "anything not supported by the supplied metadata; never invent details."
                    ),
                },
                {"role": "user", "content": paper_text},
            ],
        }
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        try:
            if self.client is None:
                with httpx.Client(timeout=self.timeout, follow_redirects=False) as client:
                    response = self._send(client, safe_base_url, headers, payload)
            else:
                response = self._send(self.client, safe_base_url, headers, payload)
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
