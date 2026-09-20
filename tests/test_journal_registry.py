"""Behavioral tests for exact journal identity resolution."""

from litwatch.journals import JOURNAL_REGISTRY


def test_registry_exposes_required_canonical_journals() -> None:
    expected_ids = {
        "nature_communications",
        "science_advances",
        "nature",
        "science",
        "jasa",
        "ocean_engineering",
        "ieee_joe",
        "acta_acustica_cn",
        "ieee_iot_j",
    }

    assert {journal.journal_id for journal in JOURNAL_REGISTRY.all()} == expected_ids
    assert JOURNAL_REGISTRY.get("jasa").canonical_name == (
        "The Journal of the Acoustical Society of America"
    )


def test_requested_journal_resolves_exact_normalized_aliases() -> None:
    assert JOURNAL_REGISTRY.resolve_requested("JASA").journal_id == "jasa"
    assert JOURNAL_REGISTRY.resolve_requested("IEEE J.O.E.").journal_id == "ieee_joe"
    assert JOURNAL_REGISTRY.resolve_requested("声学学报").journal_id == "acta_acustica_cn"


def test_requested_journal_rejects_fuzzy_substrings() -> None:
    assert JOURNAL_REGISTRY.resolve_requested("ocean") is None
    assert JOURNAL_REGISTRY.resolve_requested("nature communications article") is None


def test_identity_prefers_issn_over_conflicting_name() -> None:
    resolved = JOURNAL_REGISTRY.resolve_identity(
        issns=["0001-4966"],
        name="Nature",
    )

    assert resolved is not None
    assert resolved.journal_id == "jasa"


def test_identity_prefers_verified_provider_source_over_internal_id_and_name() -> None:
    resolved = JOURNAL_REGISTRY.resolve_identity(
        provider_source_ids={"openalex": "S132957497"},
        internal_id="nature",
        name="Science",
    )

    assert resolved is not None
    assert resolved.journal_id == "ieee_joe"


def test_identity_uses_internal_id_before_exact_name() -> None:
    resolved = JOURNAL_REGISTRY.resolve_identity(
        internal_id="ocean_engineering",
        name="Nature",
    )

    assert resolved is not None
    assert resolved.journal_id == "ocean_engineering"


def test_identity_normalizes_issn_and_provider_source_url() -> None:
    assert (
        JOURNAL_REGISTRY.resolve_identity(issns=["ISSN 2327 4662"]).journal_id
        == "ieee_iot_j"
    )
    assert (
        JOURNAL_REGISTRY.resolve_identity(
            provider_source_ids={"openalex": "https://openalex.org/S64187185"}
        ).journal_id
        == "nature_communications"
    )
