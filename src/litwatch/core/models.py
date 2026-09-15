"""Provider-independent search contracts."""

from enum import StrEnum

from pydantic import BaseModel, Field, computed_field


class ProviderAlias(BaseModel):
    provider: str = Field(min_length=1)
    provider_id: str = Field(min_length=1)


class Paper(BaseModel):
    paper_id: str | None = None
    title: str = Field(min_length=1)
    authors: list[str] = Field(default_factory=list)
    abstract: str = ""
    year: int | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    provider_id: str
    url: str
    source: str
    providers: list[str]
    aliases: list[ProviderAlias] = Field(default_factory=list)
    score: float = 0.0


class ProviderState(StrEnum):
    SUCCESS = "success"
    EMPTY = "empty"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    AUTH_ERROR = "auth_error"
    UPSTREAM_ERROR = "upstream_error"
    PARSE_ERROR = "parse_error"


class ProviderResult(BaseModel):
    provider: str
    status: ProviderState
    fetched_count: int = 0
    returned_count: int = 0
    error_code: str | None = None


class SearchStatus(StrEnum):
    SUCCESS = "success"
    SUCCESS_EMPTY = "success_empty"
    PARTIAL_SUCCESS = "partial_success"
    ALL_PROVIDERS_FAILED = "all_providers_failed"


class SearchResult(BaseModel):
    scan_id: str | None = None
    topic: str
    status: SearchStatus
    papers: list[Paper] = Field(default_factory=list)
    provider_results: list[ProviderResult] = Field(default_factory=list)

    @computed_field
    @property
    def paper_count(self) -> int:
        return len(self.papers)
