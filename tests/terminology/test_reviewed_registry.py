from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from clinical_demo.terminology.reviewed_registry import (
    REVIEWED_REGISTRY_VERSION,
    DuplicateReviewedMappingError,
    ReviewedMappingEntry,
    ReviewedMappingRegistry,
    load_reviewed_mapping_registry,
    normalize_surface,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _entry(surface: str, *, concept_set: str | None = "FRACTURE") -> ReviewedMappingEntry:
    return ReviewedMappingEntry.model_validate(
        {
            "kind": "condition",
            "surface": surface,
            "status": "mapped",
            "concept_set": concept_set,
            "reason": "test review",
            "source": "test",
            "provenance": "unit test",
            "reviewer": "test",
            "reviewed_at": "2026-05-08",
            "resolver_version": REVIEWED_REGISTRY_VERSION,
            "expansion_policy": "reviewed_code_list",
        }
    )


def test_normalize_surface_matches_resolver_surface_rule() -> None:
    assert normalize_surface("  Bone   fractures. ") == "bone fractures"
    assert normalize_surface("(Bone fractures)") == "bone fractures"


def test_entry_computes_normalized_surface_when_omitted() -> None:
    entry = _entry(" Bone   fractures. ")
    assert entry.normalized_surface == "bone fractures"


def test_entry_rejects_incorrect_normalized_surface() -> None:
    with pytest.raises(ValidationError, match="normalized_surface must equal"):
        ReviewedMappingEntry(
            kind="condition",
            surface="Bone fractures",
            normalized_surface="wrong",
            status="mapped",
            concept_set="FRACTURE",
            reason="test review",
            source="test",
            provenance="unit test",
            reviewer="test",
            reviewed_at="2026-05-08",
            resolver_version=REVIEWED_REGISTRY_VERSION,
            expansion_policy="reviewed_code_list",
        )


def test_lookup_uses_kind_and_normalized_surface() -> None:
    registry = ReviewedMappingRegistry([_entry("Bone fractures")])

    assert registry.lookup("condition", " bone   fractures. ") is not None
    assert registry.lookup("lab", " bone   fractures. ") is None


def test_duplicate_kind_surface_rejected_deterministically() -> None:
    with pytest.raises(DuplicateReviewedMappingError, match="condition:'bone fractures'"):
        ReviewedMappingRegistry(
            [
                _entry("Bone fractures"),
                _entry(" bone   fractures. "),
            ]
        )


def test_committed_bone_fractures_mapping_loads() -> None:
    registry = load_reviewed_mapping_registry(
        REPO_ROOT / "data" / "terminology" / "reviewed_mappings.json"
    )

    entry = registry.lookup("condition", "Bone fractures")

    assert entry is not None
    assert entry.status == "mapped"
    assert entry.concept_set == "FRACTURE"
    assert entry.expansion_policy == "reviewed_code_list"
    assert entry.resolver_version == REVIEWED_REGISTRY_VERSION
    assert entry.candidates[0].concept_set == "FRACTURE"


def test_committed_medication_mappings_load() -> None:
    registry = load_reviewed_mapping_registry(
        REPO_ROOT / "data" / "terminology" / "reviewed_mappings.json"
    )

    metformin = registry.lookup("medication", "metformin")
    marijuana = registry.lookup("medication", "marijuana")

    assert metformin is not None
    assert metformin.status == "mapped"
    assert metformin.concept_set == "METFORMIN"
    assert metformin.expansion_policy == "patient_vocabulary_closure"
    assert marijuana is not None
    assert marijuana.status == "out_of_scope"
