"""Reviewed normal-reference limits for measurement compilation.

These rows are project-owned review decisions, not live lab reference ranges.
The compiler uses them only when trial text expresses a threshold relative to
ULN/LLN and no patient-observation reference range is available yet.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

ReferenceLimitKind = Literal["lower", "upper"]
ReferenceLimitApplicability = Literal["any", "male", "female"]

REVIEWED_REFERENCE_LIMIT_REGISTRY_VERSION = "reviewed-reference-limit-registry-v1"
DEFAULT_REVIEWED_REFERENCE_LIMIT_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "terminology" / "reviewed_reference_limits.json"
)


class ReviewedReferenceLimitEntry(BaseModel):
    """A committed reference-limit decision for one LOINC-coded measurement."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    loinc_code: str
    loinc_display: str
    limit_kind: ReferenceLimitKind
    applies_to: ReferenceLimitApplicability = "any"
    value: float
    unit: str
    reason: str
    source: str
    provenance: str
    reviewer: str
    reviewed_at: str
    resolver_version: str

    @field_validator(
        "loinc_code",
        "loinc_display",
        "unit",
        "reason",
        "source",
        "provenance",
        "reviewer",
        "reviewed_at",
        "resolver_version",
    )
    @classmethod
    def _strip_strings(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("string fields must not be blank")
        return stripped

    @model_validator(mode="after")
    def _validate_entry(self) -> ReviewedReferenceLimitEntry:
        if self.value <= 0:
            raise ValueError("reference-limit values must be positive")
        if self.resolver_version != REVIEWED_REFERENCE_LIMIT_REGISTRY_VERSION:
            raise ValueError(
                f"resolver_version must equal {REVIEWED_REFERENCE_LIMIT_REGISTRY_VERSION!r}"
            )
        return self


class ReviewedReferenceLimitFile(BaseModel):
    """On-disk reviewed reference-limit registry shape."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = 1
    reference_limits: tuple[ReviewedReferenceLimitEntry, ...]


class DuplicateReviewedReferenceLimitError(ValueError):
    """Raised when two rows claim the same reference-limit key."""


class ReviewedReferenceLimitRegistry:
    """Lookup wrapper with deterministic duplicate validation."""

    def __init__(
        self,
        entries: tuple[ReviewedReferenceLimitEntry, ...] | list[ReviewedReferenceLimitEntry],
    ) -> None:
        self._entries = tuple(entries)
        index: dict[
            tuple[str, ReferenceLimitKind, ReferenceLimitApplicability],
            ReviewedReferenceLimitEntry,
        ] = {}
        for entry in self._entries:
            key = (entry.loinc_code, entry.limit_kind, entry.applies_to)
            existing = index.get(key)
            if existing is not None:
                raise DuplicateReviewedReferenceLimitError(
                    "duplicate reviewed reference limit for "
                    f"{entry.loinc_code}:{entry.limit_kind}:{entry.applies_to} "
                    f"({existing.loinc_display!r} and {entry.loinc_display!r})"
                )
            index[key] = entry
        self._index = index

    @property
    def entries(self) -> tuple[ReviewedReferenceLimitEntry, ...]:
        return self._entries

    def lookup(
        self,
        loinc_code: str,
        limit_kind: ReferenceLimitKind,
        *,
        applies_to: ReferenceLimitApplicability = "any",
    ) -> ReviewedReferenceLimitEntry | None:
        """Return a reviewed reference limit for a LOINC/kind/applicability."""

        return self._index.get((loinc_code, limit_kind, applies_to))

    def has_sex_specific_limit(self, loinc_code: str, limit_kind: ReferenceLimitKind) -> bool:
        """Return whether this registry has male/female rows for a LOINC/kind."""

        return any(
            (loinc_code, limit_kind, applies_to) in self._index for applies_to in ("male", "female")
        )

    def lookup_sex_specific(
        self,
        loinc_code: str,
        limit_kind: ReferenceLimitKind,
    ) -> dict[str, ReviewedReferenceLimitEntry]:
        """Return reviewed male/female entries keyed by profile sex values."""

        entries: dict[str, ReviewedReferenceLimitEntry] = {}
        male = self.lookup(loinc_code, limit_kind, applies_to="male")
        female = self.lookup(loinc_code, limit_kind, applies_to="female")
        if male is not None:
            entries["MALE"] = male
        if female is not None:
            entries["FEMALE"] = female
        return entries


def load_reviewed_reference_limit_registry(
    path: Path | str = DEFAULT_REVIEWED_REFERENCE_LIMIT_PATH,
) -> ReviewedReferenceLimitRegistry:
    """Load the committed reviewed reference-limit registry from JSON."""

    registry_path = Path(path)
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    parsed = ReviewedReferenceLimitFile.model_validate(payload)
    return ReviewedReferenceLimitRegistry(parsed.reference_limits)


@lru_cache(maxsize=1)
def get_reviewed_reference_limit_registry() -> ReviewedReferenceLimitRegistry:
    """Load committed reference-limit decisions once."""

    return load_reviewed_reference_limit_registry()


__all__ = [
    "DEFAULT_REVIEWED_REFERENCE_LIMIT_PATH",
    "REVIEWED_REFERENCE_LIMIT_REGISTRY_VERSION",
    "DuplicateReviewedReferenceLimitError",
    "ReferenceLimitApplicability",
    "ReferenceLimitKind",
    "ReviewedReferenceLimitEntry",
    "ReviewedReferenceLimitFile",
    "ReviewedReferenceLimitRegistry",
    "get_reviewed_reference_limit_registry",
    "load_reviewed_reference_limit_registry",
]
