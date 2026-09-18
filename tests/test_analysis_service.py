"""Paper analysis reads persisted papers and stores structured results."""

import sqlite3

import pytest

from litwatch.analysis import PaperAnalysisService, PaperNotFoundError, QuickScan
from litwatch.core import Paper, SearchResult, SearchStatus
from litwatch.storage import AnalysisRepository, SearchRepository

RESULT = QuickScan(
    summary="A concise summary.",
    research_question="How can TDOA improve localization?",
    methodology="Simulation and field experiments.",
    key_findings=["The method reduced error."],
    innovations=["A robust timing estimator."],
    limitations=["Limited field sites."],
    relevance="Relevant to underwater localization.",
)


class RecordingGateway:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def quick_scan(self, **arguments: str) -> QuickScan:
        self.calls.append(arguments)
        return RESULT


def save_paper(repository: SearchRepository) -> Paper:
    result = repository.save(
        SearchResult(
            topic="underwater acoustic localization",
            status=SearchStatus.SUCCESS,
            papers=[
                Paper(
                    title="Underwater Acoustic TDOA Localization",
                    authors=["Lin Researcher"],
                    abstract="A study of robust TDOA localization in underwater channels.",
                    year=2026,
                    doi="10.1000/acoustic",
                    provider_id="W123",
                    url="https://example.org/paper",
                    source="openalex",
                    providers=["openalex"],
                )
            ],
        )
    )
    return result.papers[0]


def test_quick_scan_uses_saved_paper_and_persists_analysis(tmp_path) -> None:
    path = tmp_path / "litwatch.sqlite3"
    search_repository = SearchRepository(path)
    paper = save_paper(search_repository)
    analysis_repository = AnalysisRepository(path)
    gateway = RecordingGateway()
    service = PaperAnalysisService(search_repository, analysis_repository, gateway)

    analysis = service.analyze(
        paper_id=paper.paper_id,
        analysis_mode="quick_scan",
        base_url="https://llm.example.test/v1",
        model="example-model",
        api_key="secret-test-key",
    )

    assert analysis.analysis_id.startswith("A-")
    assert analysis.paper_id == paper.paper_id
    assert analysis.result == RESULT
    assert len(gateway.calls) == 1
    assert gateway.calls[0]["api_key"] == "secret-test-key"
    assert "Underwater Acoustic TDOA Localization" in gateway.calls[0]["paper_text"]
    assert "robust TDOA localization" in gateway.calls[0]["paper_text"]
    stored = analysis_repository.get(analysis.analysis_id)
    assert stored == analysis


def test_analysis_survives_repository_restart_without_api_key(tmp_path) -> None:
    path = tmp_path / "litwatch.sqlite3"
    papers = SearchRepository(path)
    paper = save_paper(papers)
    secret = "secret-must-never-be-persisted"
    saved = PaperAnalysisService(papers, AnalysisRepository(path), RecordingGateway()).analyze(
        paper_id=paper.paper_id,
        analysis_mode="quick_scan",
        base_url="https://llm.example.test/v1",
        model="example-model",
        api_key=secret,
    )

    restarted = AnalysisRepository(path)
    loaded = restarted.get(saved.analysis_id)
    assert loaded == saved
    assert secret.encode() not in path.read_bytes()
    assert secret not in loaded.model_dump_json()
    with sqlite3.connect(path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(analyses)")}
        assert columns == {
            "analysis_id", "paper_id", "analysis_mode", "model", "result_json", "created_at"
        }


def test_missing_paper_fails_before_gateway_call(tmp_path) -> None:
    path = tmp_path / "litwatch.sqlite3"
    gateway = RecordingGateway()
    service = PaperAnalysisService(SearchRepository(path), AnalysisRepository(path), gateway)

    with pytest.raises(PaperNotFoundError):
        service.analyze(
            paper_id="P-missing",
            analysis_mode="quick_scan",
            base_url="https://llm.example.test/v1",
            model="example-model",
            api_key="secret-test-key",
        )

    assert gateway.calls == []


def test_analysis_follows_paper_when_late_identity_bridge_reconciles(tmp_path) -> None:
    path = tmp_path / "litwatch.sqlite3"
    papers = SearchRepository(path)
    older = papers.save(
        SearchResult(
            topic="older",
            status=SearchStatus.SUCCESS,
            papers=[Paper(title="Early metadata", provider_id="W123", url="https://openalex.org/W123",
                          source="openalex", providers=["openalex"])],
        )
    ).papers[0]
    doi_owner = papers.save(
        SearchResult(
            topic="doi",
            status=SearchStatus.SUCCESS,
            papers=[Paper(title="DOI metadata", doi="10.1000/bridge", provider_id="C123",
                          url="https://doi.org/10.1000/bridge", source="crossref",
                          providers=["crossref"])],
        )
    ).papers[0]
    analyses = AnalysisRepository(path)
    saved = PaperAnalysisService(papers, analyses, RecordingGateway()).analyze(
        paper_id=doi_owner.paper_id,
        analysis_mode="quick_scan",
        base_url="https://llm.example.test/v1",
        model="example-model",
        api_key="secret-test-key",
    )

    papers.save(
        SearchResult(
            topic="bridge",
            status=SearchStatus.SUCCESS,
            papers=[Paper(title="Bridge", doi="10.1000/bridge", provider_id="W123",
                          url="https://openalex.org/W123", source="openalex",
                          providers=["openalex"])],
        )
    )

    reloaded = analyses.get(saved.analysis_id)
    assert reloaded.paper_id == older.paper_id
    assert reloaded.result == RESULT
