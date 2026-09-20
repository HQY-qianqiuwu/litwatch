"""Merge duplicates within one search; no database identity is assigned here."""

from litwatch.core import Paper, ProviderAlias
from litwatch.core.identity import normalize_arxiv_id, normalize_doi, normalized_title


def _identity_keys(paper: Paper) -> list[tuple[str, str]]:
    keys: list[tuple[str, str]] = []
    if doi := normalize_doi(paper.doi):
        keys.append(("doi", doi))
    if arxiv_id := normalize_arxiv_id(paper.arxiv_id):
        keys.append(("arxiv", arxiv_id))
    if paper.source and paper.provider_id:
        keys.append(("provider", f"{paper.source.casefold()}:{paper.provider_id.casefold()}"))
    if title := normalized_title(paper.title):
        keys.append(("title", title))
    return keys


def _merge(records: list[Paper]) -> Paper:
    merged = records[0].model_copy(deep=True)
    merged.doi = normalize_doi(merged.doi)
    merged.arxiv_id = normalize_arxiv_id(merged.arxiv_id)
    merged.journal_issns = list(dict.fromkeys(merged.journal_issns))
    merged.journal_source_ids = dict(merged.journal_source_ids)
    merged.aliases = list(
        {
            (alias.provider.casefold(), alias.provider_id.casefold()): alias
            for item in records
            for alias in [
                *item.aliases,
                *(
                    [ProviderAlias(provider=item.source, provider_id=item.provider_id)]
                    if item.source and item.provider_id
                    else []
                ),
            ]
        }.values()
    )
    for item in records[1:]:
        merged.providers = list(dict.fromkeys([*merged.providers, *item.providers, item.source]))
        merged.authors = list(dict.fromkeys([*merged.authors, *item.authors]))
        if len(item.abstract) > len(merged.abstract):
            merged.abstract = item.abstract
        merged.doi = merged.doi or normalize_doi(item.doi)
        merged.arxiv_id = merged.arxiv_id or normalize_arxiv_id(item.arxiv_id)
        merged.year = merged.year if merged.year is not None else item.year
        merged.url = merged.url or item.url
        merged.journal = merged.journal or item.journal
        merged.journal_reference = merged.journal_reference or item.journal_reference
        merged.journal_id = merged.journal_id or item.journal_id
        merged.journal_issns = list(
            dict.fromkeys([*merged.journal_issns, *item.journal_issns])
        )
        for provider, source_id in item.journal_source_ids.items():
            merged.journal_source_ids.setdefault(provider, source_id)
        merged.acoustic_relevance = max(
            merged.acoustic_relevance,
            item.acoustic_relevance,
        )
        merged.is_priority_journal = (
            merged.is_priority_journal or item.is_priority_journal
        )
    return merged


def deduplicate_papers(papers: list[Paper]) -> list[Paper]:
    """Union identities transitively, using titles only if stronger IDs do not conflict."""
    parents = list(range(len(papers)))
    dois = [{doi} if (doi := normalize_doi(paper.doi)) else set() for paper in papers]
    arxiv_ids = [
        {identifier} if (identifier := normalize_arxiv_id(paper.arxiv_id)) else set()
        for paper in papers
    ]

    def root(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    seen: dict[tuple[str, str], int] = {}
    for index, paper in enumerate(papers):
        for key in _identity_keys(paper):
            if key in seen:
                current = root(index)
                previous = root(seen[key])
                if current == previous:
                    continue
                if key[0] != "doi" and (
                    (dois[current] and dois[previous] and dois[current] != dois[previous])
                    or (
                        key[0] in {"provider", "title"}
                        and arxiv_ids[current]
                        and arxiv_ids[previous]
                        and arxiv_ids[current] != arxiv_ids[previous]
                    )
                ):
                    continue
                parents[current] = previous
                dois[previous].update(dois[current])
                arxiv_ids[previous].update(arxiv_ids[current])
            else:
                seen[key] = index

    groups: dict[int, list[Paper]] = {}
    for index, paper in enumerate(papers):
        groups.setdefault(root(index), []).append(paper)
    return [_merge(group) for group in groups.values()]
