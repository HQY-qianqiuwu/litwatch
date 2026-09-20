"""Deterministic acoustic relevance behavior."""

from litwatch.core import Paper
from litwatch.search.acoustic import (
    ACOUSTIC_HARD_FILTER_THRESHOLD,
    score_acoustic_relevance,
)


def paper(title: str, abstract: str = "") -> Paper:
    return Paper(
        title=title,
        abstract=abstract,
        provider_id="candidate",
        url="https://example.org/candidate",
        source="openalex",
        providers=["openalex"],
    )


def test_exact_acoustic_phrases_pass_the_hard_filter() -> None:
    score = score_acoustic_relevance(
        paper("Underwater acoustic TDOA localization using hydrophone arrays")
    )

    assert score >= ACOUSTIC_HARD_FILTER_THRESHOLD
    assert score <= 1.0


def test_title_evidence_outweighs_the_same_abstract_only_evidence() -> None:
    title_score = score_acoustic_relevance(paper("Passive acoustics for marine monitoring"))
    abstract_score = score_acoustic_relevance(
        paper("Marine monitoring", "This study applies passive acoustics.")
    )

    assert title_score > abstract_score > 0.0


def test_unrelated_flagship_paper_stays_below_the_hard_filter() -> None:
    score = score_acoustic_relevance(
        paper(
            "Quantum error correction in superconducting qubits",
            "A fault-tolerant architecture for scalable quantum computation.",
        )
    )

    assert score < ACOUSTIC_HARD_FILTER_THRESHOLD


def test_missing_abstract_is_safe_when_title_has_acoustic_evidence() -> None:
    score = score_acoustic_relevance(paper("Sonar beamforming with a hydrophone array"))

    assert score >= ACOUSTIC_HARD_FILTER_THRESHOLD


def test_single_generic_acoustic_word_is_not_enough_for_hard_filter() -> None:
    score = score_acoustic_relevance(paper("Acoustic properties of a concert hall"))

    assert 0.0 < score < ACOUSTIC_HARD_FILTER_THRESHOLD
