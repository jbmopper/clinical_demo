"""Committed reviewed terminology expansion closures.

The surface resolver maps an extracted phrase to a parent concept or reviewed
code list. This module covers the next step: expanding a reviewed parent or
value set into the concrete codes that the deterministic matcher can execute.

Rows in ``reviewed_expansions.json`` are repo-owned review artifacts, not
terminology cache rows. They are intentionally small and auditable until a
live/cache-backed SNOMED graph or value-set service can produce larger frozen
closures with per-code provenance.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from clinical_demo.profile import ConceptSet
from clinical_demo.terminology.reviewed_registry import ExpansionPolicy

ReviewedExpansionPolicy = Literal["descendants", "value_set_oid"]

REVIEWED_EXPANSION_REGISTRY_VERSION = "reviewed-expansion-registry-v1"
DEFAULT_REVIEWED_EXPANSION_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "terminology" / "reviewed_expansions.json"
)


class ReviewedExpansionCode(BaseModel):
    """One reviewed code included in an expansion closure."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    display: str | None = None
    reason: str

    @field_validator("code", "display", "reason")
    @classmethod
    def _strip_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("string fields must not be blank")
        return stripped


class ReviewedExpansionEntry(BaseModel):
    """A committed expansion decision for one parent concept or value set."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    policy: ReviewedExpansionPolicy
    source_system: str
    source_codes: frozenset[str]
    source_display: str
    expanded_name: str
    expanded_codes: tuple[ReviewedExpansionCode, ...]
    reason: str
    source: str
    provenance: str
    reviewer: str
    reviewed_at: str
    resolver_version: str
    value_set_oid: str | None = None

    @field_validator(
        "source_system",
        "source_display",
        "expanded_name",
        "reason",
        "source",
        "provenance",
        "reviewer",
        "reviewed_at",
        "resolver_version",
        "value_set_oid",
    )
    @classmethod
    def _strip_optional_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("string fields must not be blank")
        return stripped

    @model_validator(mode="after")
    def _validate_expansion(self) -> ReviewedExpansionEntry:
        if not self.source_codes:
            raise ValueError("reviewed expansions must include at least one source code")
        if not self.expanded_codes:
            raise ValueError("reviewed expansions must include at least one expanded code")
        expanded = [item.code for item in self.expanded_codes]
        if len(set(expanded)) != len(expanded):
            raise ValueError("reviewed expansions must not contain duplicate expanded codes")
        if self.policy == "value_set_oid" and self.value_set_oid is None:
            raise ValueError("value_set_oid expansions must include value_set_oid")
        if self.policy == "descendants" and self.value_set_oid is not None:
            raise ValueError("descendants expansions must not include value_set_oid")
        return self

    @property
    def expanded_code_values(self) -> frozenset[str]:
        """Return just the executable code strings."""

        return frozenset(item.code for item in self.expanded_codes)

    def to_concept_set(self) -> ConceptSet:
        """Return the matcher-ready ``ConceptSet`` for this expansion."""

        return ConceptSet(
            name=self.expanded_name,
            system=self.source_system,
            codes=self.expanded_code_values,
        )


class ReviewedExpansionFile(BaseModel):
    """On-disk reviewed expansion registry shape."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = 1
    expansions: tuple[ReviewedExpansionEntry, ...]


class DuplicateReviewedExpansionError(ValueError):
    """Raised when a registry contains duplicate expansion keys."""


class ReviewedExpansionRegistry:
    """Lookup wrapper with deterministic duplicate validation."""

    def __init__(
        self, entries: tuple[ReviewedExpansionEntry, ...] | list[ReviewedExpansionEntry]
    ) -> None:
        self._entries = tuple(entries)
        index: dict[
            tuple[ReviewedExpansionPolicy, str, frozenset[str], str | None],
            ReviewedExpansionEntry,
        ] = {}
        for entry in self._entries:
            key = self._key(
                policy=entry.policy,
                system=entry.source_system,
                codes=entry.source_codes,
                value_set_oid=entry.value_set_oid,
            )
            existing = index.get(key)
            if existing is not None:
                raise DuplicateReviewedExpansionError(
                    "duplicate reviewed expansion for "
                    f"{entry.policy}:{entry.source_system}:{sorted(entry.source_codes)} "
                    f"({existing.source_display!r} and {entry.source_display!r})"
                )
            index[key] = entry
        self._index = index

    @property
    def entries(self) -> tuple[ReviewedExpansionEntry, ...]:
        return self._entries

    def lookup(
        self,
        *,
        concept_set: ConceptSet,
        policy: ExpansionPolicy,
        value_set_oid: str | None = None,
    ) -> ReviewedExpansionEntry | None:
        """Return the reviewed expansion for a concept set and policy, if present."""

        if policy not in {"descendants", "value_set_oid"}:
            return None
        expansion_policy = cast(ReviewedExpansionPolicy, policy)
        return self._index.get(
            self._key(
                policy=expansion_policy,
                system=concept_set.system,
                codes=concept_set.codes,
                value_set_oid=value_set_oid,
            )
        )

    @staticmethod
    def _key(
        *,
        policy: ReviewedExpansionPolicy,
        system: str,
        codes: frozenset[str],
        value_set_oid: str | None,
    ) -> tuple[ReviewedExpansionPolicy, str, frozenset[str], str | None]:
        return (policy, system, frozenset(codes), value_set_oid)


def load_reviewed_expansion_registry(
    path: Path | str = DEFAULT_REVIEWED_EXPANSION_PATH,
) -> ReviewedExpansionRegistry:
    """Load the committed reviewed expansion registry from JSON."""

    registry_path = Path(path)
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    parsed = ReviewedExpansionFile.model_validate(payload)
    return ReviewedExpansionRegistry(parsed.expansions)


__all__ = [
    "DEFAULT_REVIEWED_EXPANSION_PATH",
    "REVIEWED_EXPANSION_REGISTRY_VERSION",
    "DuplicateReviewedExpansionError",
    "ReviewedExpansionCode",
    "ReviewedExpansionEntry",
    "ReviewedExpansionFile",
    "ReviewedExpansionPolicy",
    "ReviewedExpansionRegistry",
    "load_reviewed_expansion_registry",
]
