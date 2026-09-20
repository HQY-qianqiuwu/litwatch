"""Thin FastAPI boundary over the sole literature SearchService."""

import os
from typing import Annotated, Literal

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from litwatch.analysis import (
    GatewayResponseError,
    GatewayTimeoutError,
    GatewayUpstreamError,
    InvalidBaseUrlError,
    OpenAICompatibleGateway,
    PaperAnalysis,
    PaperAnalysisService,
    PaperNotFoundError,
)
from litwatch.core import ProviderState, SearchResult, SearchStatus
from litwatch.providers import ArxivProvider, CrossrefProvider, OpenAlexProvider
from litwatch.search import SearchService
from litwatch.storage import AnalysisRepository, SearchRepository


class SearchRequest(BaseModel):
    topic: str
    limit: int = Field(default=5, ge=1, le=50)
    journals: list[str] = Field(default_factory=list)
    year_from: int | None = Field(default=None, ge=1000, le=9999)
    year_to: int | None = Field(default=None, ge=1000, le=9999)

    @field_validator("topic")
    @classmethod
    def require_topic(cls, value: str) -> str:
        query = value.strip()
        if not query:
            raise ValueError("topic must not be blank")
        return query


class AnalyzeRequest(BaseModel):
    """A BYOK request; the API key deliberately has no body field."""

    model_config = ConfigDict(extra="forbid")

    paper_id: str = Field(min_length=1)
    analysis_mode: Literal["quick_scan"]
    base_url: str = Field(min_length=1)
    model: str = Field(min_length=1)

    @field_validator("paper_id", "base_url", "model")
    @classmethod
    def require_non_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized


def create_app(
    search_service: SearchService | None = None,
    *,
    repository: SearchRepository | None = None,
    analysis_service: PaperAnalysisService | None = None,
) -> FastAPI:
    """Compose providers and persistence once; a request searches only once."""
    if search_service is None:
        search_service = SearchService(
            [
                OpenAlexProvider(email=os.getenv("LITWATCH_OPENALEX_EMAIL", "")),
                ArxivProvider(),
                CrossrefProvider(email=os.getenv("LITWATCH_CROSSREF_EMAIL", "")),
            ]
        )
    if repository is None:
        repository = SearchRepository(os.getenv("LITWATCH_DATABASE_PATH", "./data/litwatch.db"))
    if analysis_service is None:
        analysis_service = PaperAnalysisService(
            repository,
            AnalysisRepository(repository.database.path),
            OpenAICompatibleGateway(),
        )

    application = FastAPI(title="LitWatch", version="0.1.0")

    @application.get("/health")
    def health() -> dict[str, str]:
        """Process liveness; individual provider health is reported by each search."""
        return {"status": "ok"}

    @application.get("/api/v1/providers")
    def list_providers() -> dict[str, list[dict[str, str | bool]]]:
        return {
            "providers": [
                {"provider": provider.name, "enabled": True, "configured": True}
                for provider in search_service.providers
            ]
        }

    @application.post("/api/v1/literature/search", response_model=SearchResult)
    def search_literature(request: SearchRequest) -> SearchResult | JSONResponse:
        try:
            search_result = search_service.search(
                request.topic,
                request.limit,
                journals=request.journals,
                year_from=request.year_from,
                year_to=request.year_to,
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None
        result = repository.save(search_result)
        if result.status is SearchStatus.ALL_PROVIDERS_FAILED:
            all_timeouts = all(
                item.status is ProviderState.TIMEOUT for item in result.provider_results
            )
            return JSONResponse(
                status_code=504 if all_timeouts else 502,
                content=result.model_dump(mode="json"),
            )
        return result

    @application.post("/api/v1/literature/analyze", response_model=PaperAnalysis)
    def analyze_literature(
        request: AnalyzeRequest,
        api_key: Annotated[
            str,
            Header(alias="X-LitWatch-LLM-Key", min_length=1),
        ],
    ) -> PaperAnalysis:
        try:
            return analysis_service.analyze(
                paper_id=request.paper_id,
                analysis_mode=request.analysis_mode,
                base_url=request.base_url,
                model=request.model,
                api_key=api_key,
            )
        except PaperNotFoundError:
            raise HTTPException(status_code=404, detail="paper not found") from None
        except InvalidBaseUrlError:
            raise HTTPException(status_code=422, detail="invalid LLM base URL") from None
        except GatewayTimeoutError:
            raise HTTPException(status_code=504, detail="LLM request timed out") from None
        except (GatewayUpstreamError, GatewayResponseError):
            raise HTTPException(status_code=502, detail="invalid LLM upstream response") from None

    @application.get("/api/v1/analyses/{analysis_id}", response_model=PaperAnalysis)
    def get_analysis(analysis_id: str) -> PaperAnalysis:
        analysis = analysis_service.get(analysis_id)
        if analysis is None:
            raise HTTPException(status_code=404, detail="analysis not found")
        return analysis

    return application


app = create_app()
