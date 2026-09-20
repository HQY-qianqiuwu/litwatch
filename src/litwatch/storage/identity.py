"""Database identity keys and safe metadata enrichment."""

import sqlite3

from litwatch.core import Paper, ProviderAlias
from litwatch.core.identity import normalize_arxiv_id, normalize_doi, normalized_title


def prepare_paper(paper: Paper) -> Paper:
    prepared = paper.model_copy(deep=True)
    prepared.doi = normalize_doi(prepared.doi)
    prepared.arxiv_id = normalize_arxiv_id(prepared.arxiv_id)
    candidates = list(prepared.aliases)
    if prepared.source and prepared.provider_id:
        candidates.append(ProviderAlias(provider=prepared.source, provider_id=prepared.provider_id))
    prepared.aliases = list(
        {
            (item.provider.casefold(), item.provider_id.casefold()): item
            for item in candidates
        }.values()
    )
    return prepared


def identity_aliases(paper: Paper) -> list[tuple[str, str]]:
    keys: list[tuple[str, str]] = []
    if paper.doi:
        keys.append(("doi", paper.doi))
    if paper.arxiv_id:
        keys.append(("arxiv", paper.arxiv_id))
    keys.extend(
        ("provider", f"{alias.provider.casefold()}:{alias.provider_id.casefold()}")
        for alias in paper.aliases
    )
    return list(dict.fromkeys(keys))


def compatible(existing: Paper, incoming: Paper, kind: str) -> bool:
    if existing.doi and incoming.doi and existing.doi != incoming.doi:
        return False
    return not (
        kind in {"provider", "title"}
        and existing.arxiv_id
        and incoming.arxiv_id
        and existing.arxiv_id != incoming.arxiv_id
    )


def _from_row(row: sqlite3.Row) -> Paper:
    paper = Paper.model_validate_json(row["payload"])
    paper.paper_id = row["paper_id"]
    return paper


def find_matches(connection: sqlite3.Connection, incoming: Paper) -> list[Paper]:
    matches: dict[str, Paper] = {}
    for kind, value in identity_aliases(incoming):
        row = connection.execute(
            """SELECT papers.paper_id, papers.payload FROM paper_aliases
               JOIN papers USING (paper_id) WHERE kind = ? AND value = ?""",
            (kind, value),
        ).fetchone()
        if row is not None:
            candidate = _from_row(row)
            if compatible(candidate, incoming, kind):
                matches.setdefault(candidate.paper_id, candidate)
    if matches:
        return list(matches.values())

    matches = connection.execute(
        "SELECT paper_id, payload FROM papers WHERE normalized_title = ?",
        (normalized_title(incoming.title),),
    ).fetchall()
    title_matches = [
        candidate
        for row in matches
        if compatible(candidate := _from_row(row), incoming, "title")
    ]
    return title_matches if len(title_matches) == 1 else []


def enrich(existing: Paper, incoming: Paper) -> Paper:
    updated = existing.model_copy(deep=True)
    updated.authors = list(dict.fromkeys([*existing.authors, *incoming.authors]))
    updated.providers = list(dict.fromkeys([*existing.providers, *incoming.providers]))
    updated.aliases = prepare_paper(
        updated.model_copy(update={"aliases": [*existing.aliases, *incoming.aliases]})
    ).aliases
    if len(incoming.abstract) > len(existing.abstract):
        updated.abstract = incoming.abstract
    updated.year = existing.year if existing.year is not None else incoming.year
    updated.doi = existing.doi or incoming.doi
    updated.arxiv_id = existing.arxiv_id or incoming.arxiv_id
    updated.url = existing.url or incoming.url
    updated.score = max(existing.score, incoming.score)
    updated.journal = existing.journal or incoming.journal
    updated.journal_id = existing.journal_id or incoming.journal_id
    updated.journal_issns = list(
        dict.fromkeys([*existing.journal_issns, *incoming.journal_issns])
    )
    updated.journal_source_ids = {
        **incoming.journal_source_ids,
        **existing.journal_source_ids,
    }
    updated.acoustic_relevance = max(
        existing.acoustic_relevance,
        incoming.acoustic_relevance,
    )
    updated.is_priority_journal = (
        existing.is_priority_journal or incoming.is_priority_journal
    )
    return updated
