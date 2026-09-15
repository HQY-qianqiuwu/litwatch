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
