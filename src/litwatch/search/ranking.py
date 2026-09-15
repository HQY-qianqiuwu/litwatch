"""Simple deterministic keyword and recency scoring."""

import re
from datetime import UTC, datetime

from litwatch.core import Paper


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"\w+", value.casefold()))


def rank_papers(topic: str, papers: list[Paper], *, current_year: int | None = None) -> list[Paper]:
    """Title overlap (70), abstract overlap (25), recency (up to 5)."""
    year = current_year if current_year is not None else datetime.now(UTC).year
    query_tokens = _tokens(topic)
    scored: list[Paper] = []
    for item in papers:
        title_overlap = len(query_tokens & _tokens(item.title)) / max(len(query_tokens), 1)
        abstract_overlap = len(query_tokens & _tokens(item.abstract)) / max(len(query_tokens), 1)
        age = max(0, year - item.year) if item.year is not None else None
        recency = 5 / (1 + age / 5) if age is not None else 0
        scored.append(
            item.model_copy(
                update={"score": round(70 * title_overlap + 25 * abstract_overlap + recency, 2)}
            )
        )
    return sorted(
        scored,
        key=lambda item: (
            -item.score,
            -(item.year or 0),
            item.title.casefold(),
            item.source,
            item.provider_id,
        ),
    )
