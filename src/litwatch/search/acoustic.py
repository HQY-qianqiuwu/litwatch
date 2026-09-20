"""Deterministic acoustic-topic relevance scoring."""

import re
import unicodedata

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
    ("hydrophones", 0.30),
    ("sonar", 0.28),
    ("acoustic sensing", 0.25),
    ("array signal processing", 0.22),
    ("tdoa", 0.20),
    ("beamforming", 0.18),
    ("acoustic", 0.08),
    ("水下声学", 0.35),
    ("海洋声学", 0.35),
    ("声源定位", 0.35),
    ("时差定位", 0.30),
    ("阵列信号处理", 0.30),
    ("声传播", 0.30),
    ("水声通信", 0.35),
    ("声学传感", 0.25),
    ("声呐", 0.30),
    ("目标检测", 0.25),
    ("波束形成", 0.30),
    ("水听器", 0.30),
    ("被动声学", 0.30),
)


def _normalized_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.findall(r"\w+", normalized, flags=re.UNICODE))


def _evidence_score(value: str) -> float:
    normalized = _normalized_text(value)
    padded = f" {normalized} "
    compact = normalized.replace(" ", "")
    return sum(
        weight
        for phrase, weight in _PHRASE_WEIGHTS
        if (
            phrase in compact
            if any(ord(character) > 127 for character in phrase)
            else f" {phrase} " in padded
        )
    )


def score_acoustic_relevance(paper: Paper) -> float:
    """Return a bounded score with title evidence weighted above abstract evidence."""
    title_score = _evidence_score(paper.title)
    abstract_score = _evidence_score(paper.abstract) * 0.35
    return round(min(title_score + abstract_score, 1.0), 4)
