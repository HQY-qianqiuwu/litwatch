"""Exact journal aliases and reliable provider identifiers."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass


def _normalize_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if character.isalnum())


def _normalize_issn(value: str) -> str:
    compact = re.sub(r"[^0-9Xx]", "", value)
    if len(compact) != 8:
        return ""
    return f"{compact[:4]}-{compact[4:].upper()}"


def _normalize_source_id(provider: str, value: str) -> str:
    normalized = value.strip().casefold().rstrip("/")
    if provider.casefold() == "openalex":
        normalized = normalized.removeprefix("https://openalex.org/")
    return normalized


@dataclass(frozen=True, slots=True)
class JournalDefinition:
    journal_id: str
    canonical_name: str
    abbreviation: str
    aliases: tuple[str, ...] = ()
    issns: tuple[str, ...] = ()
    provider_source_ids: tuple[tuple[str, str], ...] = ()
    priority: float = 0.0


class JournalRegistry:
    """Resolve journals only through exact normalized identities."""

    def __init__(self, journals: Iterable[JournalDefinition]) -> None:
        self._journals = tuple(journals)
        self._by_id = {journal.journal_id: journal for journal in self._journals}
        self._by_name: dict[str, JournalDefinition] = {}
        self._by_issn: dict[str, JournalDefinition] = {}
        self._by_provider_source: dict[tuple[str, str], JournalDefinition] = {}

        for journal in self._journals:
            for value in (
                journal.journal_id,
                journal.canonical_name,
                journal.abbreviation,
                *journal.aliases,
            ):
                self._by_name[_normalize_name(value)] = journal
            for issn in journal.issns:
                self._by_issn[_normalize_issn(issn)] = journal
            for provider, source_id in journal.provider_source_ids:
                key = (provider.casefold(), _normalize_source_id(provider, source_id))
                self._by_provider_source[key] = journal

    def all(self) -> tuple[JournalDefinition, ...]:
        return self._journals

    def get(self, journal_id: str) -> JournalDefinition | None:
        return self._by_id.get(journal_id)

    def resolve_requested(self, value: str) -> JournalDefinition | None:
        return self._by_name.get(_normalize_name(value))

    def resolve_identity(
        self,
        *,
        issns: Iterable[str] = (),
        provider_source_ids: Mapping[str, str] | None = None,
        internal_id: str | None = None,
        name: str | None = None,
    ) -> JournalDefinition | None:
        for issn in issns:
            resolved = self._by_issn.get(_normalize_issn(issn))
            if resolved is not None:
                return resolved

        for provider, source_id in (provider_source_ids or {}).items():
            key = (provider.casefold(), _normalize_source_id(provider, source_id))
            resolved = self._by_provider_source.get(key)
            if resolved is not None:
                return resolved

        if internal_id:
            resolved = self.get(internal_id)
            if resolved is not None:
                return resolved

        if name:
            return self._by_name.get(_normalize_name(name))
        return None


JOURNAL_REGISTRY = JournalRegistry(
    (
        JournalDefinition(
            journal_id="nature_communications",
            canonical_name="Nature Communications",
            abbreviation="Nat Commun",
            aliases=("Nature Comms",),
            issns=("2041-1723",),
            provider_source_ids=(("openalex", "S64187185"),),
            priority=0.7,
        ),
        JournalDefinition(
            journal_id="science_advances",
            canonical_name="Science Advances",
            abbreviation="Sci Adv",
            issns=("2375-2548",),
            provider_source_ids=(("openalex", "S2737427234"),),
            priority=0.7,
        ),
        JournalDefinition(
            journal_id="nature",
            canonical_name="Nature",
            abbreviation="Nature",
            issns=("0028-0836", "1476-4687"),
            provider_source_ids=(("openalex", "S137773608"),),
            priority=1.0,
        ),
        JournalDefinition(
            journal_id="science",
            canonical_name="Science",
            abbreviation="Science",
            issns=("0036-8075", "0193-4511", "1095-9203"),
            provider_source_ids=(("openalex", "S3880285"),),
            priority=1.0,
        ),
        JournalDefinition(
            journal_id="jasa",
            canonical_name="The Journal of the Acoustical Society of America",
            abbreviation="JASA",
            aliases=("Journal of the Acoustical Society of America",),
            issns=("0001-4966", "1520-8524", "1520-9024"),
            provider_source_ids=(("openalex", "S11296630"),),
            priority=0.9,
        ),
        JournalDefinition(
            journal_id="ocean_engineering",
            canonical_name="Ocean Engineering",
            abbreviation="Ocean Eng",
            issns=("0029-8018", "1873-5258"),
            provider_source_ids=(("openalex", "S76910236"),),
            priority=0.8,
        ),
        JournalDefinition(
            journal_id="ieee_joe",
            canonical_name="IEEE Journal of Oceanic Engineering",
            abbreviation="IEEE JOE",
            aliases=("IEEE J.O.E.",),
            issns=("0364-9059", "1558-1691", "2373-7786"),
            provider_source_ids=(("openalex", "S132957497"),),
            priority=0.9,
        ),
        JournalDefinition(
            journal_id="acta_acustica_cn",
            canonical_name="声学学报",
            abbreviation="Acta Acustica",
            aliases=("Acta Acustica Sinica",),
            provider_source_ids=(("openalex", "S4306546527"),),
            priority=0.8,
        ),
        JournalDefinition(
            journal_id="ieee_iot_j",
            canonical_name="IEEE Internet of Things Journal",
            abbreviation="IEEE IoT J",
            aliases=("IEEE IoT Journal",),
            issns=("2327-4662", "2372-2541"),
            provider_source_ids=(("openalex", "S2480266640"),),
            priority=0.6,
        ),
    )
)
