"""Simple deterministic keyword and recency scoring."""

import re
from datetime import UTC, datetime

from litwatch.core import Paper


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"\w+", value.casefold()))


def rank_papers(
    topic: str,
    papers: list[Paper],
    *,
    current_year: int | None = None,
    journal_mode: bool = False,
) -> list[Paper]:
    """Title overlap (70), abstract overlap (25), recency (up to 5)."""
    year = current_year if current_year is not None else datetime.now(UTC).year
    query_tokens = _tokens(topic)
    scored: list[tuple[Paper, float]] = []
    for item in papers:
        title_overlap = len(query_tokens & _tokens(item.title)) / max(len(query_tokens), 1)
        abstract_overlap = len(query_tokens & _tokens(item.abstract)) / max(len(query_tokens), 1)
        age = max(0, year - item.year) if item.year is not None else None
        recency = 5 / (1 + age / 5) if age is not None else 0
        query_score = 70 * title_overlap + 25 * abstract_overlap + recency
        paper = item.model_copy(
            update={
                "score": round(query_score + (2 if item.is_priority_journal else 0), 2)
            }
        )
        scored.append((paper, query_score))

    if journal_mode:
        scored.sort(
            key=lambda pair: (
                -pair[0].acoustic_relevance,
                -pair[1],
                -int(pair[0].analysis_eligible),
                -int(pair[0].is_priority_journal),
                -(pair[0].year or 0),
                pair[0].title.casefold(),
                pair[0].source,
                pair[0].provider_id,
            )
        )
    else:
        scored.sort(
            key=lambda pair: (
                -pair[0].score,
                -(pair[0].year or 0),
                pair[0].title.casefold(),
                pair[0].source,
                pair[0].provider_id,
            )
        )
    return [paper for paper, _query_score in scored]
