"""arXiv Atom feed adapter."""

import re
import xml.etree.ElementTree as ET

import httpx

from litwatch.core import Paper
from litwatch.core.identity import normalize_arxiv_id, normalize_doi
from litwatch.providers.base import HttpProvider

ATOM = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


def _text(node: ET.Element, path: str) -> str:
    child = node.find(path, ATOM)
    return " ".join(child.text.split()) if child is not None and child.text else ""


def normalize_entry(entry: ET.Element) -> Paper | None:
    title = _text(entry, "atom:title")
    if not title:
        return None
    identifier = normalize_arxiv_id(_text(entry, "atom:id"))
    if not identifier:
        raise ValueError("arXiv entry has no article id")
    published = _text(entry, "atom:published")
    return Paper(
        title=title,
        authors=[
            name
            for author in entry.findall("atom:author", ATOM)
            if (name := _text(author, "atom:name"))
        ],
        abstract=_text(entry, "atom:summary"),
        year=int(published[:4]) if published[:4].isdigit() else None,
        doi=normalize_doi(_text(entry, "arxiv:doi")),
        arxiv_id=identifier,
        provider_id=identifier,
        url=f"https://arxiv.org/abs/{identifier}",
        source="arxiv",
        providers=["arxiv"],
        journal=_text(entry, "arxiv:journal_ref") or None,
    )


class ArxivProvider(HttpProvider):
    name = "arxiv"
    endpoint = "https://export.arxiv.org/api/query"

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        timeout: float = 15.0,
        endpoint: str | None = None,
    ) -> None:
        super().__init__(client=client, timeout=timeout)
        self.endpoint = endpoint or self.endpoint

    def search(self, topic: str, limit: int) -> list[Paper]:
        terms = re.findall(r"\w+", topic.casefold())[:6]
        query = " OR ".join(f"all:{term}" for term in terms) or f'all:"{topic}"'
        response = self._get(
            self.endpoint,
            params={
                "search_query": query,
                "start": 0,
                "max_results": min(limit, 100),
                "sortBy": "relevance",
                "sortOrder": "descending",
            },
            headers={"User-Agent": "LitWatch/0.1 (academic metadata search)"},
        )
        root = ET.fromstring(response.content)
        if root.tag != f"{{{ATOM['atom']}}}feed":
            raise ValueError("arXiv response must be an Atom feed")
        entries = root.findall("atom:entry", ATOM)
        records: list[Paper] = []
        for entry in entries:
            if paper := normalize_entry(entry):
                records.append(paper)
        if entries and not records:
            raise TypeError("arXiv returned no usable entries")
        return records
