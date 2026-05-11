"""Committed reviewed medication-class expansions.

The compiler uses this registry for class-like medication surfaces that are
safe to expand without a live RxClass call. Entries are project-owned review
decisions, not resolver cache rows: each class expands to member medication
surfaces that still have to resolve through the cached/reviewed RxNorm path
before an executable predicate is emitted.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from clinical_demo.terminology.reviewed_registry import ExpansionPolicy

REVIEWED_MEDICATION_CLASS_REGISTRY_VERSION = "reviewed-medication-class-registry-v1"
DEFAULT_REVIEWED_MEDICATION_CLASS_PATH = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "terminology"
    / "reviewed_medication_classes.json"
)

MedicationClassExpansionPolicy = Literal["reviewed_code_list", "patient_vocabulary_closure"]


def normalize_medication_class_surface(surface: str) -> str:
    """Normalize a medication class surface for deterministic lookup."""

    stripped = surface.strip().lower().strip(".,;:()[]{}\"'")
    return " ".join(stripped.split())


class ReviewedMedicationClassEntry(BaseModel):
    """A committed review decision for one medication class expansion."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    class_id: str
    display: str
    surfaces: tuple[str, ...]
    member_surfaces: tuple[str, ...]
    expansion_policy: MedicationClassExpansionPolicy
    reason: str
    source: str
    provenance: str
    reviewer: str
    reviewed_at: str
    resolver_version: str

    @field_validator(
        "class_id",
        "display",
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

    @field_validator("surfaces", "member_surfaces")
    @classmethod
    def _strip_tuple_strings(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        stripped = tuple(value.strip() for value in values)
        if not stripped or any(not value for value in stripped):
            raise ValueError("surface lists must contain at least one non-blank value")
        return stripped

    @model_validator(mode="after")
    def _validate_entry(self) -> ReviewedMedicationClassEntry:
        if self.resolver_version != REVIEWED_MEDICATION_CLASS_REGISTRY_VERSION:
            raise ValueError(
                f"resolver_version must equal {REVIEWED_MEDICATION_CLASS_REGISTRY_VERSION!r}"
            )
        if self.expansion_policy not in _CLASS_EXPANSION_POLICIES:
            raise ValueError("unsupported medication class expansion_policy")
        return self

    @property
    def normalized_surfaces(self) -> tuple[str, ...]:
        """Normalized lookup surfaces covered by this class entry."""

        return tuple(normalize_medication_class_surface(surface) for surface in self.surfaces)


class ReviewedMedicationClassFile(BaseModel):
    """On-disk medication-class registry shape."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = 1
    classes: tuple[ReviewedMedicationClassEntry, ...]


class DuplicateMedicationClassSurfaceError(ValueError):
    """Raised when two class entries claim the same normalized surface."""


class ReviewedMedicationClassRegistry:
    """Lookup wrapper with deterministic duplicate validation."""

    def __init__(
        self,
        entries: tuple[ReviewedMedicationClassEntry, ...] | list[ReviewedMedicationClassEntry],
    ) -> None:
        self._entries = tuple(entries)
        index: dict[str, ReviewedMedicationClassEntry] = {}
        for entry in self._entries:
            for normalized in entry.normalized_surfaces:
                existing = index.get(normalized)
                if existing is not None:
                    raise DuplicateMedicationClassSurfaceError(
                        "duplicate reviewed medication class surface "
                        f"{normalized!r} ({existing.class_id!r} and {entry.class_id!r})"
                    )
                index[normalized] = entry
        self._index = index

    @property
    def entries(self) -> tuple[ReviewedMedicationClassEntry, ...]:
        return self._entries

    def lookup(self, surface: str) -> ReviewedMedicationClassEntry | None:
        """Return the reviewed class entry for ``surface``, if present."""

        return self._index.get(normalize_medication_class_surface(surface))


def load_reviewed_medication_class_registry(
    path: Path | str = DEFAULT_REVIEWED_MEDICATION_CLASS_PATH,
) -> ReviewedMedicationClassRegistry:
    """Load the committed reviewed medication-class registry from JSON."""

    registry_path = Path(path)
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    parsed = ReviewedMedicationClassFile.model_validate(payload)
    return ReviewedMedicationClassRegistry(parsed.classes)


@lru_cache(maxsize=1)
def get_reviewed_medication_class_registry() -> ReviewedMedicationClassRegistry:
    """Load committed medication-class expansion decisions once."""

    return load_reviewed_medication_class_registry()


_CLASS_EXPANSION_POLICIES: frozenset[ExpansionPolicy] = frozenset(
    {"reviewed_code_list", "patient_vocabulary_closure"}
)


__all__ = [
    "DEFAULT_REVIEWED_MEDICATION_CLASS_PATH",
    "REVIEWED_MEDICATION_CLASS_REGISTRY_VERSION",
    "DuplicateMedicationClassSurfaceError",
    "MedicationClassExpansionPolicy",
    "ReviewedMedicationClassEntry",
    "ReviewedMedicationClassFile",
    "ReviewedMedicationClassRegistry",
    "get_reviewed_medication_class_registry",
    "load_reviewed_medication_class_registry",
    "normalize_medication_class_surface",
]
