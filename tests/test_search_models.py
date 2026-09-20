"""Domain contracts for the new search core."""

from litwatch import core


def test_paper_carries_the_provider_independent_metadata() -> None:
    paper_type = getattr(core, "Paper", None)
    assert paper_type is not None

    paper = paper_type(
        title="Underwater Acoustic Localization",
        authors=["A. Researcher"],
        abstract="TDOA methods in shallow water.",
        year=2026,
        doi="10.1000/acoustic",
        arxiv_id=None,
        provider_id="W123",
        url="https://example.org/paper",
        source="openalex",
        providers=["openalex"],
    )

    assert paper.model_dump()["authors"] == ["A. Researcher"]
    assert paper.model_dump()["score"] == 0.0
    assert paper.model_dump()["abstract_status"] == "complete"
    assert paper.model_dump()["analysis_eligible"] is True


def test_paper_derives_pending_analysis_state_from_blank_abstract() -> None:
    paper = core.Paper(
        title="Metadata-only acoustic paper",
        abstract="   ",
        provider_id="W-pending",
        url="https://example.org/pending",
        source="openalex",
        providers=["openalex"],
        analysis_eligible=True,
    )

    payload = paper.model_dump()
    assert payload["abstract_status"] == "pending"
    assert payload["analysis_eligible"] is False


def test_search_result_reports_paper_count_and_provider_diagnostics() -> None:
    result_type = getattr(core, "SearchResult", None)
    assert result_type is not None

    provider_result_type = getattr(core, "ProviderResult", None)
    assert provider_result_type is not None

    result = result_type(
        topic="acoustic localization",
        status="success",
        papers=[
            core.Paper(
                title="Acoustic Localization",
                provider_id="W123",
                url="https://example.org/paper",
                source="openalex",
                providers=["openalex"],
            )
        ],
        provider_results=[provider_result_type(provider="openalex", status="success", fetched_count=1)],
    )

    payload = result.model_dump(mode="json")
    assert payload["paper_count"] == 1
    assert payload["provider_results"][0]["fetched_count"] == 1
