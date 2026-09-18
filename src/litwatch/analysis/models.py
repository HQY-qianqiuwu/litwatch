"""Structured contracts for persisted paper analyses."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class QuickScan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1)
    research_question: str = Field(min_length=1)
    methodology: str = Field(min_length=1)
    key_findings: list[str] = Field(min_length=1)
    innovations: list[str] = Field(min_length=1)
    limitations: list[str] = Field(min_length=1)
    relevance: str = Field(min_length=1)


class PaperAnalysis(BaseModel):
    analysis_id: str
    paper_id: str
    analysis_mode: Literal["quick_scan"]
    model: str
    result: QuickScan
    created_at: str
