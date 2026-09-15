"""Thin FastAPI boundary over the sole literature SearchService."""

import os

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from litwatch.core import ProviderState, SearchResult, SearchStatus
from litwatch.providers import ArxivProvider, CrossrefProvider, OpenAlexProvider
from litwatch.search import SearchService


class SearchRequest(BaseModel):
    topic: str
    limit: int = Field(default=5, ge=1, le=50)

    @field_validator("topic")
    @classmethod
    def require_topic(cls, value: str) -> str:
        query = value.strip()
        if not query:
            raise ValueError("topic must not be blank")
        return query


def create_app(search_service: SearchService | None = None) -> FastAPI:
    """Compose public providers once; callers can inject the same service for tests."""
    if search_service is None:
        search_service = SearchService(
            [
                OpenAlexProvider(email=os.getenv("LITWATCH_OPENALEX_EMAIL", "")),
                ArxivProvider(),
                CrossrefProvider(email=os.getenv("LITWATCH_CROSSREF_EMAIL", "")),
            ]
        )

    application = FastAPI(title="LitWatch", version="0.1.0")

    @application.get("/health")
    def health() -> dict[str, str]:
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
        result = search_service.search(request.topic, request.limit)
        if result.status is SearchStatus.ALL_PROVIDERS_FAILED:
            all_timeouts = all(
                item.status is ProviderState.TIMEOUT for item in result.provider_results
            )
            return JSONResponse(
                status_code=504 if all_timeouts else 502,
                content=result.model_dump(mode="json"),
            )
        return result

    return application


app = create_app()
