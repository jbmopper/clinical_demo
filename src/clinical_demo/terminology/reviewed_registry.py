"""Committed reviewed terminology mappings.

This module is intentionally separate from ``terminology.cache``. Cache rows
record what a resolver observed from local/live terminology sources at a point
in time; reviewed registry rows record explicit project decisions that should
be code-reviewed, diffed, and shipped with the repo.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ReviewedMappingKind = Literal["condition", "lab", "medication", "procedure"]
ReviewedMappingStatus = Literal[
    "mapped",
    "ambiguous",
    "true_miss",
    "composite_unhandled",
    "extractor_bug",
    "out_of_scope",
]
ExpansionPolicy = Literal[
    "exact_code",
    "descendants",
    "value_set_oid",
    "reviewed_code_list",
    "patient_vocabulary_closure",
]


REVIEWED_REGISTRY_VERSION = "reviewed-registry-v1"
DEFAULT_REVIEWED_MAPPING_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "terminology" / "reviewed_mappings.json"
)


def normalize_surface(surface: str) -> str:
    """Normalize a trial-side surface for deterministic registry lookup."""

    stripped = surface.strip().lower().strip(".,;:()[]{}\"'")
    return " ".join(stripped.split())


class ReviewedMappingCandidate(BaseModel):
    """One candidate considered during human review."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str | None = None
    concept_set: str | None = None
    system: str | None = None
    codes: frozenset[str] = Field(default_factory=frozenset)
    source: str
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    reason: str | None = None

    @field_validator("name", "concept_set", "system", "source", "reason")
    @classmethod
    def _strip_optional_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("string fields must not be blank")
        return stripped


class ReviewedMappingEntry(BaseModel):
    """A committed review decision for one extracted terminology surface."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: ReviewedMappingKind
    surface: str
    normalized_surface: str
    status: ReviewedMappingStatus
    concept_set: str | None = None
    candidates: tuple[ReviewedMappingCandidate, ...] = Field(default_factory=tuple)
    reason: str
    source: str
    provenance: str
    reviewer: str
    reviewed_at: str
    resolver_version: str
    expansion_policy: ExpansionPolicy

    @model_validator(mode="before")
    @classmethod
    def _fill_normalized_surface(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        surface = data.get("surface")
        normalized = data.get("normalized_surface")
        if isinstance(surface, str) and normalized is None:
            return {**data, "normalized_surface": normalize_surface(surface)}
        return data

    @field_validator(
        "surface",
        "normalized_surface",
        "concept_set",
        "reason",
        "source",
        "provenance",
        "reviewer",
        "reviewed_at",
        "resolver_version",
    )
    @classmethod
    def _strip_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("string fields must not be blank")
        return stripped

    @model_validator(mode="after")
    def _validate_decision(self) -> ReviewedMappingEntry:
        expected = normalize_surface(self.surface)
        if self.normalized_surface != expected:
            raise ValueError(
                "normalized_surface must equal normalize_surface(surface): "
                f"{self.normalized_surface!r} != {expected!r}"
            )
        if self.status == "mapped" and self.concept_set is None:
            raise ValueError("mapped reviewed entries must include concept_set")
        return self


class ReviewedMappingFile(BaseModel):
    """On-disk registry shape."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = 1
    mappings: tuple[ReviewedMappingEntry, ...]


class DuplicateReviewedMappingError(ValueError):
    """Raised when a registry contains duplicate kind/surface decisions."""


class ReviewedMappingRegistry:
    """Lookup wrapper with deterministic duplicate validation."""

    def __init__(
        self, entries: tuple[ReviewedMappingEntry, ...] | list[ReviewedMappingEntry]
    ) -> None:
        self._entries = tuple(entries)
        index: dict[tuple[ReviewedMappingKind, str], ReviewedMappingEntry] = {}
        for entry in self._entries:
            key = (entry.kind, entry.normalized_surface)
            existing = index.get(key)
            if existing is not None:
                raise DuplicateReviewedMappingError(
                    "duplicate reviewed mapping for "
                    f"{entry.kind}:{entry.normalized_surface!r} "
                    f"({existing.surface!r} and {entry.surface!r})"
                )
            index[key] = entry
        self._index = index

    @property
    def entries(self) -> tuple[ReviewedMappingEntry, ...]:
        return self._entries

    def lookup(self, kind: ReviewedMappingKind, surface: str) -> ReviewedMappingEntry | None:
        """Return the reviewed decision for ``kind`` + ``surface``, if present."""

        return self._index.get((kind, normalize_surface(surface)))


def load_reviewed_mapping_registry(
    path: Path | str = DEFAULT_REVIEWED_MAPPING_PATH,
) -> ReviewedMappingRegistry:
    """Load the committed reviewed registry from JSON."""

    registry_path = Path(path)
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    parsed = ReviewedMappingFile.model_validate(payload)
    return ReviewedMappingRegistry(parsed.mappings)
