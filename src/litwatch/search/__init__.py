"""The single literature search pipeline."""
"""Provider-independent search processing."""

from litwatch.search.deduplication import deduplicate_papers
from litwatch.search.ranking import rank_papers

__all__ = ["deduplicate_papers", "rank_papers"]
