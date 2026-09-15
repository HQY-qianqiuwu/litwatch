"""Lightweight, non-persistent identifiers shared by providers and search."""

import re


def normalize_doi(value: str | None) -> str | None:
    if not value:
        return None
    doi = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", value.strip(), flags=re.IGNORECASE)
    doi = re.sub(r"^doi:\s*", "", doi, flags=re.IGNORECASE).casefold()
    return doi or None


def normalize_arxiv_id(value: str | None) -> str | None:
    if not value:
        return None
    identifier = value.strip().rsplit("/abs/", 1)[-1]
    identifier = re.sub(r"v\d+$", "", identifier, flags=re.IGNORECASE)
    return identifier.casefold() or None


def normalized_title(value: str) -> str:
    return " ".join(re.findall(r"\w+", value.casefold()))
