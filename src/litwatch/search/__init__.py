"""The single literature search pipeline."""
"""Provider-independent search processing."""

from litwatch.search.acoustic import (
    ACOUSTIC_HARD_FILTER_THRESHOLD,
    score_acoustic_relevance,
)
from litwatch.search.deduplication import deduplicate_papers
from litwatch.search.ranking import rank_papers
from litwatch.search.service import SearchService

__all__ = [
    "ACOUSTIC_HARD_FILTER_THRESHOLD",
    "SearchService",
    "deduplicate_papers",
    "rank_papers",
    "score_acoustic_relevance",
]
