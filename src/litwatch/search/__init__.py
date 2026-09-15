"""The single literature search pipeline."""
"""Provider-independent search processing."""

from litwatch.search.deduplication import deduplicate_papers
from litwatch.search.ranking import rank_papers
from litwatch.search.service import SearchService

__all__ = ["SearchService", "deduplicate_papers", "rank_papers"]
