"""OpenAlex Works JSON adapter."""

from typing import Any

import httpx

from litwatch.core import Paper
from litwatch.core.identity import normalize_arxiv_id, normalize_doi
from litwatch.providers.base import HttpProvider, ProviderSearchCriteria


def _abstract_from_index(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    positions: dict[int, str] = {}
    for word, offsets in value.items():
        if isinstance(word, str) and isinstance(offsets, list):
            for offset in offsets:
                if isinstance(offset, int) and offset >= 0:
                    positions[offset] = word
    return " ".join(positions[index] for index in sorted(positions))


def normalize_work(raw: dict[str, Any]) -> Paper | None:
    title = str(raw.get("title") or "").strip()
    if not title:
        return None
    doi = normalize_doi(raw.get("doi"))
    identifier = str(raw.get("id") or "").strip()
    authorships = raw.get("authorships") or []
    authors = [
        name
        for entry in authorships
        if isinstance(entry, dict)
        and isinstance(entry.get("author"), dict)
        and (name := str(entry["author"].get("display_name") or "").strip())
    ]
    location = raw.get("primary_location") or {}
    source = location.get("source") if isinstance(location, dict) else None
    source = source if isinstance(source, dict) else {}
    source_id = str(source.get("id") or "").strip().rsplit("/", 1)[-1]
    journal_issns = source.get("issn") if isinstance(source.get("issn"), list) else []
    ids = raw.get("ids") or {}
    year = raw.get("publication_year")
    return Paper(
        title=title,
        authors=authors,
        abstract=_abstract_from_index(raw.get("abstract_inverted_index")),
        year=int(year) if year else None,
        doi=doi,
        arxiv_id=normalize_arxiv_id(ids.get("arxiv")) if isinstance(ids, dict) else None,
        provider_id=identifier.rsplit("/", 1)[-1] or doi or title,
        url=location.get("landing_page_url") or raw.get("doi") or identifier,
        source="openalex",
        providers=["openalex"],
        journal=str(source.get("display_name") or "").strip() or None,
        journal_issns=[str(value).strip() for value in journal_issns if str(value).strip()],
        journal_source_ids={"openalex": source_id} if source_id else {},
    )


class OpenAlexProvider(HttpProvider):
    name = "openalex"
    endpoint = "https://api.openalex.org/works"

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        timeout: float = 15.0,
        email: str = "",
        endpoint: str | None = None,
    ) -> None:
        super().__init__(client=client, timeout=timeout)
        self.email = email.strip()
        self.endpoint = endpoint or self.endpoint

    def search(
        self,
        topic: str,
        limit: int,
        *,
        criteria: ProviderSearchCriteria | None = None,
    ) -> list[Paper]:
        params: dict[str, str | int] = {"search": topic, "per-page": min(limit, 200)}
        filters: list[str] = []
        if criteria is not None:
            if criteria.year_from is not None:
                filters.append(f"from_publication_date:{criteria.year_from}-01-01")
            if criteria.year_to is not None:
                filters.append(f"to_publication_date:{criteria.year_to}-12-31")
            source_ids = [
                source_id
                for journal in criteria.journals
                for provider, source_id in journal.provider_source_ids
                if provider.casefold() == "openalex"
            ]
            if source_ids:
                filters.append(f"primary_location.source.id:{'|'.join(source_ids)}")
        if filters:
            params["filter"] = ",".join(filters)
        if self.email:
            params["mailto"] = self.email
        response = self._get(self.endpoint, params=params)
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
            raise TypeError("OpenAlex response must contain results")
        records: list[Paper] = []
        for item in payload["results"]:
            if not isinstance(item, dict):
                raise TypeError("OpenAlex work must be an object")
            if paper := normalize_work(item):
                records.append(paper)
        if payload["results"] and not records:
            raise TypeError("OpenAlex returned no usable works")
        return records
