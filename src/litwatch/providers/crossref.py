"""Crossref Works JSON adapter."""

import html
import re
from typing import Any

import httpx

from litwatch.core import Paper
from litwatch.core.identity import normalize_doi, normalized_title
from litwatch.providers.base import HttpProvider


def _first_text(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return next((item.strip() for item in value if isinstance(item, str) and item.strip()), "")
    return ""


def _abstract(value: object) -> str:
    if not isinstance(value, str):
        return ""
    plain = re.sub(r"<[^>]+>", " ", value)
    return " ".join(html.unescape(plain).split())


def _year(raw: dict[str, Any]) -> int | None:
    for key in ("published", "published-online", "published-print", "issued"):
        date_info = raw.get(key)
        if isinstance(date_info, dict):
            parts = date_info.get("date-parts")
            if isinstance(parts, list) and parts and isinstance(parts[0], list) and parts[0]:
                try:
                    return int(parts[0][0])
                except (TypeError, ValueError):
                    continue
    return None


def normalize_work(raw: dict[str, Any]) -> Paper | None:
    title = _first_text(raw.get("title"))
    if not title:
        return None
    doi = normalize_doi(raw.get("DOI"))
    url = str(raw.get("URL") or (f"https://doi.org/{doi}" if doi else "")).strip()
    authors = []
    for author in raw.get("author") or []:
        if isinstance(author, dict):
            name = " ".join(
                part for key in ("given", "family") if (part := str(author.get(key) or "").strip())
            )
            if name:
                authors.append(name)
    return Paper(
        title=title,
        authors=authors,
        abstract=_abstract(raw.get("abstract")),
        year=_year(raw),
        doi=doi,
        provider_id=doi or url or normalized_title(title),
        url=url,
        source="crossref",
        providers=["crossref"],
    )


class CrossrefProvider(HttpProvider):
    name = "crossref"
    endpoint = "https://api.crossref.org/works"

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

    def search(self, topic: str, limit: int) -> list[Paper]:
        params: dict[str, str | int] = {"query.bibliographic": topic, "rows": min(limit, 100)}
        if self.email:
            params["mailto"] = self.email
        identity = (
            f"LitWatch/0.1 (mailto:{self.email})"
            if self.email
            else "LitWatch/0.1 (academic metadata search)"
        )
        response = self._get(self.endpoint, params=params, headers={"User-Agent": identity})
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("message"), dict):
            raise TypeError("Crossref response must contain message")
        items = payload["message"].get("items")
        if not isinstance(items, list):
            raise TypeError("Crossref response must contain message.items")
        records: list[Paper] = []
        for item in items:
            if not isinstance(item, dict):
                raise TypeError("Crossref work must be an object")
            if paper := normalize_work(item):
                records.append(paper)
        return records
