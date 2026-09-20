"""SQLite scans remain available across repository instances."""

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

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


def test_legacy_payload_without_phase45_fields_derives_safe_pending_state(tmp_path) -> None:
    path = tmp_path / "litwatch.sqlite3"
    repository = storage.SearchRepository(path)
    saved = repository.save(_result(_paper(abstract="")))
    paper_id = saved.papers[0].paper_id

    with sqlite3.connect(path) as connection:
        payload = json.loads(
            connection.execute(
                "SELECT payload FROM papers WHERE paper_id = ?", (paper_id,)
            ).fetchone()[0]
        )
        for field in (
            "journal",
            "journal_id",
            "journal_issns",
            "journal_source_ids",
            "acoustic_relevance",
            "is_priority_journal",
            "abstract_status",
            "analysis_eligible",
        ):
            payload.pop(field, None)
        connection.execute(
            "UPDATE papers SET payload = ? WHERE paper_id = ?",
            (json.dumps(payload), paper_id),
        )

    loaded = storage.SearchRepository(path).get_paper(paper_id)
    assert loaded.abstract_status == "pending"
    assert loaded.analysis_eligible is False
    assert loaded.journal_id is None
    assert loaded.journal_issns == []


def test_repeat_search_enriches_legacy_record_with_phase45_metadata(tmp_path) -> None:
    path = tmp_path / "litwatch.sqlite3"
    repository = storage.SearchRepository(path)
    legacy = repository.save(_result(_paper(abstract=""))).papers[0]

    enriched = repository.save(
        _result(
            _paper(
                abstract="Underwater acoustic propagation measurements.",
                journal="The Journal of the Acoustical Society of America",
                journal_id="jasa",
                journal_issns=["0001-4966", "1520-8524"],
                journal_source_ids={"openalex": "S11296630"},
                acoustic_relevance=0.8,
                is_priority_journal=True,
            )
        )
    ).papers[0]

    assert enriched.paper_id == legacy.paper_id
    restarted = storage.SearchRepository(path).get_paper(legacy.paper_id)
    assert restarted.journal_id == "jasa"
    assert restarted.journal_issns == ["0001-4966", "1520-8524", "1520-9024"]
    assert restarted.journal_source_ids == {"openalex": "S11296630"}
    assert restarted.acoustic_relevance == 0.8
    assert restarted.is_priority_journal is True
    assert restarted.abstract_status == "complete"
    assert restarted.analysis_eligible is True


def test_new_reliable_journal_identifier_replaces_stale_name_identity(tmp_path) -> None:
    path = tmp_path / "litwatch.sqlite3"
    repository = storage.SearchRepository(path)
    first = repository.save(
        _result(
            _paper(
                journal="Nature",
                journal_id="nature",
                journal_issns=["0028-0836"],
            )
        )
    ).papers[0]

    second = repository.save(
        _result(
            _paper(
                journal="The Journal of the Acoustical Society of America",
                journal_id="jasa",
                journal_issns=["0001-4966"],
                journal_source_ids={"openalex": "S11296630"},
            )
        )
    ).papers[0]

    assert second.paper_id == first.paper_id
    assert second.journal_id == "jasa"
    assert second.journal == "The Journal of the Acoustical Society of America"


def test_each_empty_search_has_its_own_persisted_scan(tmp_path) -> None:
    repository_type = getattr(storage, "SearchRepository", None)
    assert repository_type is not None
    repository = repository_type(tmp_path / "litwatch.sqlite3")
    first = repository.save(_result())
    second = repository.save(_result())

    assert first.scan_id != second.scan_id
    assert repository.get_scan(first.scan_id).status == SearchStatus.SUCCESS_EMPTY
    assert repository.get_scan(second.scan_id).papers == []


@pytest.mark.parametrize(
    ("first", "second"),
    [
        (
            {"doi": "10.1000/ACOUSTIC"},
            {"doi": "https://doi.org/10.1000/acoustic", "source": "crossref",
             "provider_id": "10.1000/acoustic", "providers": ["crossref"], "title": "Other title"},
        ),
        (
            {"doi": None, "arxiv_id": "2401.12345", "source": "arxiv",
             "provider_id": "2401.12345", "providers": ["arxiv"]},
            {"doi": None, "arxiv_id": "2401.12345v2", "provider_id": "W999",
             "title": "Other title"},
        ),
        (
            {"doi": None, "provider_id": "W123"},
            {"doi": None, "provider_id": "w123", "title": "Other title"},
        ),
        (
            {"doi": None, "provider_id": "W123"},
            {"doi": None, "source": "crossref", "provider_id": "X999",
             "providers": ["crossref"], "title": "underwater acoustic: TDOA localization!"},
        ),
    ],
    ids=["doi", "arxiv", "provider", "title-fallback"],
)
def test_paper_identity_reused_across_searches_and_restart(tmp_path, first, second) -> None:
    repository = storage.SearchRepository(tmp_path / "litwatch.sqlite3")
    original = repository.save(_result(_paper(**first)))
    restarted = storage.SearchRepository(tmp_path / "litwatch.sqlite3")
    repeated = restarted.save(_result(_paper(**second)))

    assert repeated.scan_id != original.scan_id
    assert repeated.papers[0].paper_id == original.papers[0].paper_id
    with sqlite3.connect(tmp_path / "litwatch.sqlite3") as connection:
        assert connection.execute("SELECT COUNT(*) FROM papers").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM scan_papers").fetchone()[0] == 2


def test_conflicting_doi_does_not_merge_on_title_or_provider_id(tmp_path) -> None:
    repository = storage.SearchRepository(tmp_path / "litwatch.sqlite3")
    first = repository.save(_result(_paper(doi="10.1000/first")))
    second = repository.save(_result(_paper(doi="10.1000/second")))

    assert first.papers[0].paper_id != second.papers[0].paper_id
    with sqlite3.connect(tmp_path / "litwatch.sqlite3") as connection:
        assert connection.execute("SELECT COUNT(*) FROM papers").fetchone()[0] == 2


def test_aliases_from_both_providers_survive_single_search_and_restart(tmp_path) -> None:
    from litwatch.search import deduplicate_papers

    merged = deduplicate_papers(
        [
            _paper(provider_id="W123"),
            _paper(source="crossref", provider_id="10.1000/acoustic",
                   providers=["crossref"]),
        ]
    )
    assert len(merged) == 1
    path = tmp_path / "litwatch.sqlite3"
    saved = storage.SearchRepository(path).save(_result(*merged))
    loaded = storage.SearchRepository(path).get_paper(saved.papers[0].paper_id)

    assert {(alias.provider, alias.provider_id) for alias in loaded.aliases} == {
        ("openalex", "W123"),
        ("crossref", "10.1000/acoustic"),
    }
    with sqlite3.connect(path) as connection:
        aliases = set(connection.execute("SELECT kind, value FROM paper_aliases"))
        assert ("doi", "10.1000/acoustic") in aliases
        assert ("provider", "openalex:w123") in aliases
        assert ("provider", "crossref:10.1000/acoustic") in aliases


def test_repeat_search_enriches_without_erasing_existing_fields(tmp_path) -> None:
    repository = storage.SearchRepository(tmp_path / "litwatch.sqlite3")
    first = repository.save(
        _result(_paper(abstract="Useful existing abstract", authors=["Lin Researcher"]))
    )
    second = repository.save(
        _result(_paper(abstract="", authors=[], url="", source="crossref",
                       provider_id="10.1000/acoustic", providers=["crossref"]))
    )
    paper = repository.get_paper(first.papers[0].paper_id)

    assert second.papers[0].paper_id == first.papers[0].paper_id
    assert paper.abstract == "Useful existing abstract"
    assert paper.authors == ["Lin Researcher"]
    assert paper.url == "https://openalex.org/W123"


def test_concurrent_searches_reuse_one_database_identity(tmp_path) -> None:
    path = tmp_path / "litwatch.sqlite3"

    def save_once(_index: int) -> str:
        return storage.SearchRepository(path).save(_result(_paper())).papers[0].paper_id

    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(save_once, range(2)))

    assert ids[0] == ids[1]
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM papers").fetchone()[0] == 1


def test_historical_aliases_collapse_two_search_results_to_one_scan_paper(tmp_path) -> None:
    from litwatch.search import deduplicate_papers

    path = tmp_path / "litwatch.sqlite3"
    repository = storage.SearchRepository(path)
    established = deduplicate_papers(
        [
            _paper(provider_id="W123", doi="10.1000/acoustic"),
            _paper(source="crossref", provider_id="C123", providers=["crossref"],
                   doi="10.1000/acoustic"),
        ]
    )
    first = repository.save(_result(*established))
    second = repository.save(
        _result(
            _paper(title="Metadata title A", provider_id="W123", doi="10.1000/acoustic"),
            _paper(title="Metadata title B", source="crossref", provider_id="C123",
                   providers=["crossref"], doi=None),
        )
    )

    assert second.paper_count == 1
    assert second.papers[0].paper_id == first.papers[0].paper_id
    assert repository.get_scan(second.scan_id).paper_count == 1
    with sqlite3.connect(path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM scan_papers WHERE scan_id = ?", (second.scan_id,)
        ).fetchone()[0] == 1


def test_late_alias_bridge_reconciles_papers_and_keeps_old_id_readable(tmp_path) -> None:
    path = tmp_path / "litwatch.sqlite3"
    repository = storage.SearchRepository(path)
    first = repository.save(_result(_paper(title="Early title", doi=None, provider_id="W123")))
    second = repository.save(
        _result(_paper(title="Different title", doi="10.1000/bridge", source="crossref",
                       provider_id="C123", providers=["crossref"]))
    )
    bridge = repository.save(
        _result(_paper(title="Bridge title", doi="10.1000/bridge", provider_id="W123"))
    )

    canonical_id = first.papers[0].paper_id
    assert bridge.papers[0].paper_id == canonical_id
    assert repository.get_scan(second.scan_id).papers[0].paper_id == canonical_id
    assert repository.get_paper(second.papers[0].paper_id).paper_id == canonical_id
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM papers").fetchone()[0] == 1
        owners = set(connection.execute("SELECT paper_id FROM paper_aliases"))
        assert owners == {(canonical_id,)}
        assert connection.execute("SELECT COUNT(*) FROM scan_papers").fetchone()[0] == 3


def test_conflicting_doi_cannot_steal_another_papers_provider_alias(tmp_path) -> None:
    path = tmp_path / "litwatch.sqlite3"
    repository = storage.SearchRepository(path)
    first = repository.save(_result(_paper(title="First", doi="10.1000/first")))
    second = repository.save(
        _result(_paper(title="Second", doi="10.1000/second", provider_id="W123"))
    )

    assert first.papers[0].paper_id != second.papers[0].paper_id
    with sqlite3.connect(path) as connection:
        owner = connection.execute(
            "SELECT paper_id FROM paper_aliases WHERE kind = 'provider' AND value = 'openalex:w123'"
        ).fetchone()[0]
    assert owner == first.papers[0].paper_id
    assert all(alias.provider_id.casefold() != "w123" for alias in (
        repository.get_paper(second.papers[0].paper_id).aliases
    ))


def test_conflicting_doi_does_not_claim_another_papers_arxiv_alias(tmp_path) -> None:
    path = tmp_path / "litwatch.sqlite3"
    repository = storage.SearchRepository(path)
    first = repository.save(
        _result(_paper(title="First", doi="10.1000/first", arxiv_id="2401.12345"))
    )
    second = repository.save(
        _result(_paper(title="Second", doi="10.1000/second", source="crossref",
                       provider_id="C123", providers=["crossref"]))
    )
    repeated = repository.save(
        _result(_paper(title="Third", doi="10.1000/second", arxiv_id="2401.12345",
                       source="crossref", provider_id="C123", providers=["crossref"]))
    )

    assert repeated.papers[0].paper_id == second.papers[0].paper_id
    assert first.papers[0].paper_id != repeated.papers[0].paper_id
    assert repository.get_paper(second.papers[0].paper_id).arxiv_id is None
    with sqlite3.connect(path) as connection:
        owner = connection.execute(
            "SELECT paper_id FROM paper_aliases WHERE kind = 'arxiv' AND value = '2401.12345'"
        ).fetchone()[0]
    assert owner == first.papers[0].paper_id


def test_doi_match_wins_over_incompatible_older_arxiv_match(tmp_path) -> None:
    path = tmp_path / "litwatch.sqlite3"
    repository = storage.SearchRepository(path)
    older = repository.save(
        _result(_paper(title="Older arxiv", doi=None, arxiv_id="2401.11111"))
    )
    doi_owner = repository.save(
        _result(_paper(title="DOI owner", doi="10.1000/priority", arxiv_id="2401.22222",
                       source="crossref", provider_id="C123", providers=["crossref"]))
    )
    repeated = repository.save(
        _result(_paper(title="New metadata", doi="10.1000/priority",
                       arxiv_id="2401.11111", source="crossref", provider_id="C123",
                       providers=["crossref"]))
    )

    assert repeated.papers[0].paper_id == doi_owner.papers[0].paper_id
    assert older.papers[0].paper_id != repeated.papers[0].paper_id
    assert repository.get_paper(doi_owner.papers[0].paper_id).arxiv_id == "2401.22222"
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM papers").fetchone()[0] == 2
