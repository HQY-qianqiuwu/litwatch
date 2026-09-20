"""Common search interface and bounded HTTP transport for source adapters."""

from dataclasses import dataclass
from typing import Protocol

import httpx

from litwatch.core import Paper
from litwatch.journals import JournalDefinition


@dataclass(frozen=True, slots=True)
class ProviderSearchCriteria:
    journals: tuple[JournalDefinition, ...] = ()
    year_from: int | None = None
    year_to: int | None = None


class LiteratureProvider(Protocol):
    name: str

    def search(
        self,
        topic: str,
        limit: int,
        *,
        criteria: ProviderSearchCriteria | None = None,
    ) -> list[Paper]: ...


class HttpProvider:
    def __init__(self, *, client: httpx.Client | None = None, timeout: float = 15.0) -> None:
        if timeout <= 0:
            raise ValueError("provider timeout must be positive")
        self.client = client
        self.timeout = timeout

    def _get(
        self,
        endpoint: str,
        *,
        params: dict[str, str | int],
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        if self.client is not None:
            response = self.client.get(
                endpoint, params=params, headers=headers, timeout=self.timeout
            )
        else:
            with httpx.Client(timeout=self.timeout, follow_redirects=False) as client:
                response = client.get(endpoint, params=params, headers=headers)
        response.raise_for_status()
        return response
