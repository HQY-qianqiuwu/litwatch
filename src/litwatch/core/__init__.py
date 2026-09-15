"""Shared configuration, errors, and domain models."""
"""Shared domain contracts."""

from litwatch.core.models import (
    Paper,
    ProviderAlias,
    ProviderResult,
    ProviderState,
    SearchResult,
    SearchStatus,
)

__all__ = ["Paper", "ProviderAlias", "ProviderResult", "ProviderState", "SearchResult", "SearchStatus"]
