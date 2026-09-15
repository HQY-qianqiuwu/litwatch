"""Academic metadata provider adapters."""
"""Academic metadata adapters."""

from litwatch.providers.arxiv import ArxivProvider
from litwatch.providers.base import LiteratureProvider
from litwatch.providers.crossref import CrossrefProvider
from litwatch.providers.openalex import OpenAlexProvider

__all__ = ["ArxivProvider", "CrossrefProvider", "LiteratureProvider", "OpenAlexProvider"]
