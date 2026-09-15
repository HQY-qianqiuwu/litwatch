"""Merge duplicates within one search; no database identity is assigned here."""

from litwatch.core import Paper
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
    for item in records[1:]:
        merged.providers = list(dict.fromkeys([*merged.providers, *item.providers, item.source]))
        merged.authors = list(dict.fromkeys([*merged.authors, *item.authors]))
        if len(item.abstract) > len(merged.abstract):
            merged.abstract = item.abstract
        merged.doi = merged.doi or normalize_doi(item.doi)
        merged.arxiv_id = merged.arxiv_id or normalize_arxiv_id(item.arxiv_id)
        merged.year = merged.year if merged.year is not None else item.year
        merged.url = merged.url or item.url
    return merged


def deduplicate_papers(papers: list[Paper]) -> list[Paper]:
    """Union matching DOI, arXiv, provider, or title identities transitively."""
    parents = list(range(len(papers)))

    def root(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    seen: dict[tuple[str, str], int] = {}
    for index, paper in enumerate(papers):
        for key in _identity_keys(paper):
            if key in seen:
                parents[root(index)] = root(seen[key])
            else:
                seen[key] = index

    groups: dict[int, list[Paper]] = {}
    for index, paper in enumerate(papers):
        groups.setdefault(root(index), []).append(paper)
    return [_merge(group) for group in groups.values()]
