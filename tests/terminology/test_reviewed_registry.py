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
    semaglutide = registry.lookup("medication", "semaglutide")
    amylin = registry.lookup("medication", "amylin")
    calcitonin = registry.lookup("medication", "calcitonin")

    assert metformin is not None
    assert metformin.status == "mapped"
    assert metformin.concept_set == "METFORMIN"
    assert metformin.expansion_policy == "patient_vocabulary_closure"
    assert marijuana is not None
    assert marijuana.status == "out_of_scope"
    assert semaglutide is not None
    assert semaglutide.status == "mapped"
    assert semaglutide.concept_set == "reviewed:medication:semaglutide"
    assert len(semaglutide.candidates[0].codes) == 40
    assert amylin is not None
    assert amylin.status == "mapped"
    assert amylin.candidates[0].codes == frozenset({"861042", "861043", "861044", "861045"})
    assert calcitonin is not None
    assert calcitonin.status == "mapped"
    assert calcitonin.candidates[0].codes == frozenset(
        {"213570", "248087", "248088", "308866", "313919"}
    )


def test_committed_cache_independent_closure_mappings_load() -> None:
    registry = load_reviewed_mapping_registry(
        REPO_ROOT / "data" / "terminology" / "reviewed_mappings.json"
    )

    pregnancy = registry.lookup("condition", "pregnancy")
    ph = registry.lookup("condition", "PH")
    sotatercept = registry.lookup("medication", "Sotatercept")
    active_liver_disease = registry.lookup("condition", "active liver disease")

    assert pregnancy is not None
    assert pregnancy.status == "mapped"
    assert pregnancy.concept_set == "reviewed:condition:pregnancy"
    assert pregnancy.candidates[0].codes == frozenset({"289908002", "77386006"})
    assert ph is not None
    assert ph.status == "mapped"
    assert ph.concept_set == "reviewed:condition:pulmonary-hypertension"
    assert ph.candidates[0].codes == frozenset({"70995007"})
    assert sotatercept is not None
    assert sotatercept.status == "mapped"
    assert len(sotatercept.candidates[0].codes) == 8
    assert active_liver_disease is not None
    assert active_liver_disease.status == "composite_unhandled"


def test_committed_condition_long_tail_review_rows_load() -> None:
    registry = load_reviewed_mapping_registry(
        REPO_ROOT / "data" / "terminology" / "reviewed_mappings.json"
    )

    type_2_dm = registry.lookup("condition", "type 2 dm")
    cpcph = registry.lookup("condition", "cpcPH")
    kidney_transplant = registry.lookup("condition", "history of kidney transplant")
    egfr = registry.lookup("condition", "EGFR ex20ins status")
    hofh = registry.lookup("condition", "HoFH")
    congenital = registry.lookup("condition", "history of congenital heart disease")
    arrhythmia = registry.lookup("condition", "uncontrolled severe arrhythmia")
    hypoglycemia = registry.lookup("condition", "\u22653 severe hypoglycemic events")
    renal_glycosuria = registry.lookup("condition", "primary renal glycosuria")
    organ_transplant = registry.lookup("condition", "organ transplant")
    diabetes_type_ii = registry.lookup("condition", "diabetes Type II")
    t1dm = registry.lookup("condition", "T1DM")
    hf = registry.lookup("condition", "HF")
    pregnancy_test = registry.lookup("condition", "positive pregnancy test")
    major_psych = registry.lookup("condition", "major psychiatric disorders")
    active_hiv = registry.lookup("condition", "active HIV infection")
    anticoagulation = registry.lookup("condition", "chronic anticoagulation therapy")
    measurable_disease = registry.lookup("condition", "measurable disease")

    assert type_2_dm is not None
    assert type_2_dm.status == "mapped"
    assert type_2_dm.concept_set == "T2DM"
    assert cpcph is not None
    assert cpcph.status == "composite_unhandled"
    assert cpcph.candidates[0].codes == frozenset({"70995007"})
    assert kidney_transplant is not None
    assert kidney_transplant.status == "out_of_scope"
    assert egfr is not None
    assert egfr.status == "out_of_scope"
    assert hofh is not None
    assert hofh.status == "mapped"
    assert hofh.concept_set == "reviewed:condition:homozygous-familial-hypercholesterolemia"
    assert hofh.candidates[0].codes == frozenset({"238078005"})
    assert congenital is not None
    assert congenital.status == "mapped"
    assert congenital.candidates[0].codes == frozenset({"13213009"})
    assert congenital.expansion_policy == "exact_code"
    assert arrhythmia is not None
    assert arrhythmia.status == "composite_unhandled"
    assert arrhythmia.candidates[0].codes == frozenset({"698247007"})
    assert hypoglycemia is not None
    assert hypoglycemia.status == "composite_unhandled"
    assert hypoglycemia.candidates[0].codes == frozenset({"237636001"})
    assert renal_glycosuria is not None
    assert renal_glycosuria.status == "true_miss"
    assert organ_transplant is not None
    assert organ_transplant.status == "out_of_scope"
    assert diabetes_type_ii is not None
    assert diabetes_type_ii.status == "mapped"
    assert diabetes_type_ii.concept_set == "T2DM"
    assert t1dm is not None
    assert t1dm.status == "mapped"
    assert t1dm.concept_set == "T1DM"
    assert hf is not None
    assert hf.status == "mapped"
    assert hf.candidates[0].codes == frozenset({"84114007"})
    assert pregnancy_test is not None
    assert pregnancy_test.status == "mapped"
    assert pregnancy_test.candidates[0].codes == frozenset({"250423000"})
    assert major_psych is not None
    assert major_psych.status == "mapped"
    assert major_psych.expansion_policy == "descendants"
    assert active_hiv is not None
    assert active_hiv.status == "out_of_scope"
    assert anticoagulation is not None
    assert anticoagulation.status == "extractor_bug"
    assert measurable_disease is not None
    assert measurable_disease.kind == "condition"
    assert measurable_disease.status == "out_of_scope"


def test_committed_cardiovascular_decomposition_atoms_load() -> None:
    registry = load_reviewed_mapping_registry(
        REPO_ROOT / "data" / "terminology" / "reviewed_mappings.json"
    )

    expected_codes = {
        "myocardial infarction": "22298006",
        "acute coronary syndrome": "394659003",
        "stroke": "230690007",
        "transient ischemic attack": "266257000",
        "deep venous thrombosis": "128053003",
        "pulmonary embolism": "59282003",
        "interstitial lung disease": "233703007",
    }

    for surface, code in expected_codes.items():
        entry = registry.lookup("condition", surface)

        assert entry is not None
        assert entry.status == "mapped"
        assert entry.candidates[0].codes == frozenset({code})
        assert entry.expansion_policy == "exact_code"
