"""Deterministic acoustic-topic relevance scoring."""

import re

from litwatch.core import Paper

ACOUSTIC_HARD_FILTER_THRESHOLD = 0.25

_PHRASE_WEIGHTS: tuple[tuple[str, float], ...] = (
    ("underwater acoustic communication", 0.40),
    ("acoustic source localization", 0.35),
    ("acoustic target detection", 0.35),
    ("underwater acoustics", 0.30),
    ("underwater acoustic", 0.30),
    ("ocean acoustics", 0.30),
    ("acoustic propagation", 0.30),
    ("passive acoustics", 0.30),
    ("hydrophone", 0.30),
    ("sonar", 0.28),
    ("acoustic sensing", 0.25),
    ("array signal processing", 0.22),
    ("tdoa", 0.20),
    ("beamforming", 0.18),
    ("acoustic", 0.08),
)


def _normalized_text(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def _evidence_score(value: str) -> float:
    padded = f" {_normalized_text(value)} "
    return sum(
        weight
        for phrase, weight in _PHRASE_WEIGHTS
        if f" {phrase} " in padded
    )


def score_acoustic_relevance(paper: Paper) -> float:
    """Return a bounded score with title evidence weighted above abstract evidence."""
    title_score = _evidence_score(paper.title)
    abstract_score = _evidence_score(paper.abstract) * 0.35
    return round(min(title_score + abstract_score, 1.0), 4)
