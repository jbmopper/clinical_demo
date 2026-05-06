"""Tests for deterministic criterion fixing."""

from __future__ import annotations

from clinical_demo.extractor.fix import CRITERION_FIX_NOTE_PREFIX, fix_extracted_criteria
from clinical_demo.extractor.schema import ExtractedCriteria, ExtractionMetadata
from tests.matcher._fixtures import (
    crit_condition,
    crit_free_text,
    crit_measurement,
    crit_temporal_window,
)


def _extracted(*criteria) -> ExtractedCriteria:
    return ExtractedCriteria(
        criteria=list(criteria),
        metadata=ExtractionMetadata(notes=""),
    )


def test_fix_normalizes_known_condition_and_measurement_surfaces() -> None:
    out = fix_extracted_criteria(
        _extracted(
            crit_condition(text="mild to moderate hypertension"),
            crit_measurement(text="C-peptide concentrations"),
        )
    )

    condition = out.criteria[0]
    measurement = out.criteria[1]
    assert condition.condition is not None
    assert condition.condition.condition_text == "hypertension"
    assert measurement.measurement is not None
    assert measurement.measurement.measurement_text == "C-peptide"
    assert CRITERION_FIX_NOTE_PREFIX in out.metadata.notes


def test_fix_infers_blood_pressure_specificity_from_source_text() -> None:
    criterion = crit_measurement(text="blood pressure", operator="<=", value=140, unit="mmHg")
    criterion = criterion.model_copy(update={"source_text": "Systolic blood pressure <= 140 mmHg"})

    out = fix_extracted_criteria(_extracted(criterion))

    assert out.criteria[0].measurement is not None
    assert out.criteria[0].measurement.measurement_text == "systolic blood pressure"


def test_fix_converts_diagnosis_temporal_window_to_condition() -> None:
    out = fix_extracted_criteria(
        _extracted(
            crit_temporal_window(event_text="T1D diagnosis", window_days=0, direction="within_past")
        )
    )

    assert out.criteria[0].kind == "condition_present"
    assert out.criteria[0].condition is not None
    assert out.criteria[0].condition.condition_text == "type 1 diabetes"
    assert out.criteria[0].source_text == "temporal criterion"


def test_fix_routes_unsafe_composite_to_free_text_review() -> None:
    original = crit_condition(text="pregnant or breastfeeding", kind="condition_absent")

    out = fix_extracted_criteria(_extracted(original))

    assert len(out.criteria) == 1
    fixed = out.criteria[0]
    assert fixed.kind == "free_text"
    assert fixed.source_text == original.source_text
    assert fixed.free_text is not None
    assert "unsafe composite" in fixed.free_text.note
    assert "condition_absent" in fixed.free_text.note


def test_fix_emits_native_composite_groups_for_explicit_or_bundle() -> None:
    original = crit_free_text().model_copy(
        update={
            "source_text": (
                "Hyperglycemia (HbA1c >= 6.5%; OR fasting plasma glucose >= "
                "126 mg/dL; OR random plasma glucose >= 200 mg/dL)"
            )
        }
    )

    out = fix_extracted_criteria(_extracted(original))

    assert out.criteria == [original]
    assert len(out.composite_groups) == 1
    group = out.composite_groups[0]
    assert group.group_id == "criterion:0:group:001"
    assert group.operator == "any_of"
    assert group.parent_criterion_index == 0
    assert [subcheck.subcheck_id for subcheck in group.subchecks] == [
        "criterion:0:group:001:subcheck:001",
        "criterion:0:group:001:subcheck:002",
        "criterion:0:group:001:subcheck:003",
    ]
    assert group.subchecks[0].criterion.kind == "measurement_threshold"
    assert group.subchecks[1].criterion.kind == "free_text"
    assert "native composite" in out.metadata.notes
