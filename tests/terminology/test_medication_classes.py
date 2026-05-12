from __future__ import annotations

from pathlib import Path

import pytest

from clinical_demo.terminology.medication_classes import (
    REVIEWED_MEDICATION_CLASS_REGISTRY_VERSION,
    DuplicateMedicationClassSurfaceError,
    ReviewedMedicationClassEntry,
    ReviewedMedicationClassRegistry,
    load_reviewed_medication_class_registry,
    normalize_medication_class_surface,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _entry(
    *,
    class_id: str = "reviewed-medication-class:statins",
    surfaces: tuple[str, ...] = ("statins",),
    member_surfaces: tuple[str, ...] = ("atorvastatin", "simvastatin"),
) -> ReviewedMedicationClassEntry:
    return ReviewedMedicationClassEntry(
        class_id=class_id,
        display="Statins",
        surfaces=surfaces,
        member_surfaces=member_surfaces,
        expansion_policy="patient_vocabulary_closure",
        reason="test review",
        source="test",
        provenance="unit test",
        reviewer="test",
        reviewed_at="2026-05-11",
        resolver_version=REVIEWED_MEDICATION_CLASS_REGISTRY_VERSION,
    )


def test_normalize_medication_class_surface_is_stable() -> None:
    assert normalize_medication_class_surface("  GLP-1   RA. ") == "glp-1 ra"
    assert normalize_medication_class_surface("(SGLT2 inhibitors)") == "sglt2 inhibitors"


def test_lookup_uses_all_reviewed_surfaces() -> None:
    registry = ReviewedMedicationClassRegistry(
        [
            _entry(
                surfaces=(
                    "statin",
                    "statins",
                    "statin therapy",
                )
            )
        ]
    )

    assert registry.lookup(" statins. ") is not None
    assert registry.lookup("STATIN THERAPY") is not None
    assert registry.lookup("pcsk9 inhibitors") is None


def test_duplicate_surface_rejected_deterministically() -> None:
    with pytest.raises(DuplicateMedicationClassSurfaceError, match="'statins'"):
        ReviewedMedicationClassRegistry(
            [
                _entry(class_id="reviewed-medication-class:statins", surfaces=("statins",)),
                _entry(class_id="reviewed-medication-class:other", surfaces=(" statins. ",)),
            ]
        )


def test_committed_reviewed_medication_classes_load() -> None:
    registry = load_reviewed_medication_class_registry(
        REPO_ROOT / "data" / "terminology" / "reviewed_medication_classes.json"
    )

    statins = registry.lookup("statins")
    lipid_lowering = registry.lookup("lipid-lowering oral drugs")
    bisphosphonates = registry.lookup("bisphosphonate treatment")
    raas = registry.lookup("RASB")
    glp1 = registry.lookup("GLP-1 RA")
    sglt2 = registry.lookup("sglt-2 inhibitors")

    assert statins is not None
    assert statins.member_surfaces == ("atorvastatin", "simvastatin")
    assert statins.expansion_policy == "patient_vocabulary_closure"
    assert statins.resolver_version == REVIEWED_MEDICATION_CLASS_REGISTRY_VERSION
    assert registry.lookup("low or moderate-intensity statins") is statins
    assert lipid_lowering is not None
    assert lipid_lowering.member_surfaces == ("atorvastatin", "simvastatin")
    assert bisphosphonates is not None
    assert bisphosphonates.member_surfaces == ("alendronic acid",)
    assert raas is not None
    assert raas.member_surfaces == ("lisinopril", "losartan")
    assert glp1 is not None
    assert glp1.member_surfaces == ("semaglutide",)
    assert sglt2 is not None
    assert sglt2.member_surfaces == ("dapagliflozin",)
