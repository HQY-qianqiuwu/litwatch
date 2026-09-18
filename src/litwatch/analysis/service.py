"""Analyze an already-persisted paper without invoking literature search."""

from typing import Protocol

from litwatch.analysis.models import PaperAnalysis, QuickScan
from litwatch.core import Paper


class PaperReader(Protocol):
    def get_paper(self, paper_id: str) -> Paper | None: ...


class AnalysisWriter(Protocol):
    def save(
        self,
        *,
        paper_id: str,
        analysis_mode: str,
        model: str,
        result: QuickScan,
    ) -> PaperAnalysis: ...

    def get(self, analysis_id: str) -> PaperAnalysis | None: ...


class QuickScanGateway(Protocol):
    def quick_scan(
        self, *, base_url: str, model: str, api_key: str, paper_text: str
    ) -> QuickScan: ...


class PaperNotFoundError(LookupError):
    pass


def _paper_text(paper: Paper) -> str:
    def value(item: object) -> str:
        if item is None or item == "" or item == []:
            return "unavailable"
        if isinstance(item, list):
            return ", ".join(str(part) for part in item)
        return str(item)

    return "\n".join(
        [
            f"Title: {value(paper.title)}",
            f"Authors: {value(paper.authors)}",
            f"Year: {value(paper.year)}",
            f"Abstract: {value(paper.abstract)}",
            f"DOI: {value(paper.doi)}",
            f"arXiv ID: {value(paper.arxiv_id)}",
        ]
    )


class PaperAnalysisService:
    def __init__(
        self,
        paper_reader: PaperReader,
        analysis_repository: AnalysisWriter,
        gateway: QuickScanGateway,
    ) -> None:
        self.paper_reader = paper_reader
        self.analysis_repository = analysis_repository
        self.gateway = gateway

    def analyze(
        self,
        *,
        paper_id: str,
        analysis_mode: str,
        base_url: str,
        model: str,
        api_key: str,
    ) -> PaperAnalysis:
        paper = self.paper_reader.get_paper(paper_id)
        if paper is None:
            raise PaperNotFoundError("paper not found")
        if analysis_mode != "quick_scan":
            raise ValueError("unsupported analysis mode")
        result = self.gateway.quick_scan(
            base_url=base_url,
            model=model,
            api_key=api_key,
            paper_text=_paper_text(paper),
        )
        return self.analysis_repository.save(
            paper_id=paper.paper_id or paper_id,
            analysis_mode=analysis_mode,
            model=model,
            result=result,
        )

    def get(self, analysis_id: str) -> PaperAnalysis | None:
        return self.analysis_repository.get(analysis_id)
