"""One-search identity and ranking rules, independent of HTTP providers."""

from litwatch import search
from litwatch.core import Paper


def paper(
    title: str,
    *,
    source: str = "openalex",
    provider_id: str = "W1",
    doi: str | None = None,
    arxiv_id: str | None = None,
    abstract: str = "",
    year: int | None = None,
    journal: str | None = None,
    journal_issns: list[str] | None = None,
    journal_source_ids: dict[str, str] | None = None,
) -> Paper:
    return Paper(
        title=title,
        abstract=abstract,
        year=year,
        doi=doi,
        arxiv_id=arxiv_id,
        provider_id=provider_id,
        url="https://example.org/paper",
        source=source,
        providers=[source],
        journal=journal,
        journal_issns=journal_issns or [],
        journal_source_ids=journal_source_ids or {},
    )


def test_same_doi_merges_records_and_preserves_both_sources() -> None:
    deduplicate = getattr(search, "deduplicate_papers", None)
    assert deduplicate is not None

    records = [
        paper("Acoustic TDOA", doi="10.1234/acoustic"),
        paper(
            "Acoustic TDOA: a review",
            source="crossref",
            provider_id="10.1234/acoustic",
            doi="https://doi.org/10.1234/ACOUSTIC",
            abstract="A useful abstract.",
        ),
    ]

    unique = deduplicate(records)
    assert len(unique) == 1
    assert unique[0].providers == ["openalex", "crossref"]
    assert unique[0].abstract == "A useful abstract."


def test_same_doi_merges_complementary_journal_metadata() -> None:
    unique = search.deduplicate_papers(
        [
            paper(
                "Underwater propagation",
                doi="10.1234/journal-metadata",
                journal="The Journal of the Acoustical Society of America",
                journal_source_ids={"openalex": "S11296630"},
            ),
            paper(
                "Underwater propagation",
                source="crossref",
                provider_id="10.1234/journal-metadata",
                doi="10.1234/journal-metadata",
                journal="JASA",
                journal_issns=["0001-4966", "1520-8524"],
            ),
        ]
    )

    assert len(unique) == 1
    assert unique[0].journal == "The Journal of the Acoustical Society of America"
    assert unique[0].journal_issns == ["0001-4966", "1520-8524"]
    assert unique[0].journal_source_ids == {"openalex": "S11296630"}


def test_single_search_dedup_keeps_both_provider_identities() -> None:
    unique = search.deduplicate_papers(
        [
            paper("Acoustic TDOA", provider_id="W123", doi="10.1000/acoustic"),
            paper(
                "Acoustic TDOA",
                source="crossref",
                provider_id="10.1000/acoustic",
                doi="10.1000/acoustic",
            ),
        ]
    )
    assert len(unique) == 1
    assert {(alias.provider, alias.provider_id) for alias in unique[0].aliases} == {
        ("openalex", "W123"),
        ("crossref", "10.1000/acoustic"),
    }


def test_same_provider_id_cannot_override_conflicting_dois() -> None:
    unique = search.deduplicate_papers(
        [
            paper("Methods", provider_id="W1", doi="10.1000/first"),
            paper("Methods", provider_id="W1", doi="10.1000/second"),
        ]
    )
    assert len(unique) == 2


def test_same_arxiv_id_ignores_version_suffix() -> None:
    deduplicate = getattr(search, "deduplicate_papers", None)
    assert deduplicate is not None

    unique = deduplicate(
        [
            paper("TDOA Localization", source="arxiv", provider_id="2401.12345", arxiv_id="2401.12345"),
            paper(
                "Different metadata title",
                source="openalex",
                provider_id="W2",
                arxiv_id="2401.12345v2",
            ),
        ]
    )
    assert len(unique) == 1
    assert unique[0].providers == ["arxiv", "openalex"]


def test_normalized_title_is_the_fallback_identity() -> None:
    deduplicate = getattr(search, "deduplicate_papers", None)
    assert deduplicate is not None

    unique = deduplicate(
        [
            paper("Underwater Acoustic: TDOA Localization", provider_id="W3"),
            paper(
                "underwater acoustic tdoa localization!",
                source="crossref",
                provider_id="X3",
            ),
        ]
    )
    assert len(unique) == 1
    assert unique[0].providers == ["openalex", "crossref"]


def test_same_title_does_not_override_conflicting_dois() -> None:
    unique = search.deduplicate_papers(
        [
            paper("Methods", source="crossref", provider_id="10.1000/first", doi="10.1000/first"),
            paper("Methods", source="crossref", provider_id="10.1000/second", doi="10.1000/second"),
        ]
    )
    assert len(unique) == 2
    assert {item.doi for item in unique} == {"10.1000/first", "10.1000/second"}


def test_same_title_does_not_override_conflicting_arxiv_ids() -> None:
    unique = search.deduplicate_papers(
        [
            paper("Acoustic Localization", source="arxiv", provider_id="2401.00001", arxiv_id="2401.00001"),
            paper("Acoustic Localization", source="arxiv", provider_id="2401.00002", arxiv_id="2401.00002"),
        ]
    )
    assert len(unique) == 2
    assert {item.arxiv_id for item in unique} == {"2401.00001", "2401.00002"}


def test_provider_identity_and_transitive_matches_do_not_leave_duplicate_groups() -> None:
    deduplicate = getattr(search, "deduplicate_papers", None)
    assert deduplicate is not None

    unique = deduplicate(
        [
            paper("Title A", provider_id="W4", doi="10.5555/bridge"),
            paper("Title B", source="arxiv", provider_id="2401.50000", arxiv_id="2401.50000"),
            paper(
                "Title B",
                source="crossref",
                provider_id="X4",
                doi="10.5555/bridge",
            ),
            paper("Title A (updated)", provider_id="W4"),
        ]
    )
    assert len(unique) == 1
    assert unique[0].providers == ["openalex", "arxiv", "crossref"]


def test_title_overlap_outweighs_abstract_only_overlap() -> None:
    rank = getattr(search, "rank_papers", None)
    assert rank is not None

    ranked = rank(
        "underwater acoustic TDOA localization",
        [
            paper(
                "Unrelated Sensor Networks",
                provider_id="W5",
                abstract="underwater acoustic TDOA localization",
                year=2026,
            ),
            paper("Underwater Acoustic TDOA Localization", provider_id="W6", year=2020),
        ],
        current_year=2026,
    )
    assert ranked[0].title == "Underwater Acoustic TDOA Localization"
    assert ranked[0].score > ranked[1].score


def test_recency_breaks_a_relevance_tie_deterministically() -> None:
    rank = getattr(search, "rank_papers", None)
    assert rank is not None

    ranked = rank(
        "acoustic localization",
        [
            paper("Acoustic Localization", provider_id="W7", year=2016),
            paper("Acoustic Localization", provider_id="W8", year=2026),
        ],
        current_year=2026,
    )
    assert [item.year for item in ranked] == [2026, 2016]
    assert ranked[0].score > ranked[1].score
