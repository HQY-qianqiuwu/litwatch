"""SQLite scans remain available across repository instances."""

import sqlite3

from litwatch import storage
from litwatch.core import Paper, ProviderResult, ProviderState, SearchResult, SearchStatus


def _result(*papers: Paper) -> SearchResult:
    return SearchResult(
        topic="underwater acoustic TDOA localization",
        status=SearchStatus.SUCCESS if papers else SearchStatus.SUCCESS_EMPTY,
        papers=list(papers),
        provider_results=[
            ProviderResult(provider="openalex", status=ProviderState.SUCCESS, fetched_count=1)
        ],
    )


def _paper(**changes: object) -> Paper:
    fields: dict[str, object] = {
        "title": "Underwater Acoustic TDOA Localization",
        "doi": "10.1000/acoustic",
        "provider_id": "W123",
        "url": "https://openalex.org/W123",
        "source": "openalex",
        "providers": ["openalex"],
    }
    return Paper(**(fields | changes))


def test_scan_and_paper_survive_repository_restart(tmp_path) -> None:
    repository_type = getattr(storage, "SearchRepository", None)
    assert repository_type is not None
    path = tmp_path / "litwatch.sqlite3"
    first = repository_type(path)
    saved = first.save(_result(_paper()))

    assert saved.scan_id
    assert saved.papers[0].paper_id
    with sqlite3.connect(path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master")}
        assert {"search_scans", "papers", "scan_papers", "paper_aliases"} <= tables
        assert connection.execute("SELECT COUNT(*) FROM scan_papers").fetchone()[0] == 1

    restarted = repository_type(path)
    loaded = restarted.get_scan(saved.scan_id)
    assert loaded is not None
    assert loaded.scan_id == saved.scan_id
    assert loaded.topic == saved.topic
    assert loaded.status == saved.status
    assert loaded.provider_results[0].status == ProviderState.SUCCESS
    assert loaded.papers[0].paper_id == saved.papers[0].paper_id
    assert restarted.get_paper(saved.papers[0].paper_id).title == saved.papers[0].title


def test_each_empty_search_has_its_own_persisted_scan(tmp_path) -> None:
    repository_type = getattr(storage, "SearchRepository", None)
    assert repository_type is not None
    repository = repository_type(tmp_path / "litwatch.sqlite3")
    first = repository.save(_result())
    second = repository.save(_result())

    assert first.scan_id != second.scan_id
    assert repository.get_scan(first.scan_id).status == SearchStatus.SUCCESS_EMPTY
    assert repository.get_scan(second.scan_id).papers == []
