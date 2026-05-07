"""Tests for structured patient-evidence retrieval."""

from __future__ import annotations

from datetime import date

import pytest

from clinical_demo.domain import ClinicalNote
from clinical_demo.extractor.schema import EntityMention
from clinical_demo.retrieval import (
    RetrievalSourceRow,
    retrieve_patient_evidence_with_composite_subchecks,
    retrieve_structured_patient_evidence,
    structured_source_rows_for_pair,
)
from tests.matcher._fixtures import (
    crit_condition,
    crit_free_text,
    crit_measurement,
    make_patient,
    make_trial,
)


def _row(
    row_id: str,
    *,
    kind: str,
    label: str,
    value: str | None = None,
    code: str | None = None,
    source: str = "patient",
) -> RetrievalSourceRow:
    return RetrievalSourceRow(
        row_id=row_id,
        source=source,
        kind=kind,
        label=label,
        value=value or label,
        code=code,
        system="http://snomed.info/sct" if code else None,
    )


def test_retrieve_uses_code_anchor_when_concept_mapping_exists() -> None:
    rows = [
        _row("patient:000", kind="condition", label="Essential hypertension", code="59621000"),
        _row("patient:001", kind="condition", label="Full-time employment", code="160903007"),
    ]

    retrieved = retrieve_structured_patient_evidence(
        crit_condition(text="hypertension"),
        rows,
    )

    assert [item.row.row_id for item in retrieved] == ["patient:000"]
    assert "code:59621000" in retrieved[0].reasons


def test_retrieve_falls_back_to_lexical_overlap_when_unmapped() -> None:
    rows = [
        _row("patient:000", kind="condition", label="Pulmonary arterial hypertension"),
        _row("patient:001", kind="condition", label="Type 2 diabetes mellitus"),
    ]

    retrieved = retrieve_structured_patient_evidence(
        crit_condition(text="pulmonary arterial hypertension"),
        rows,
    )

    assert retrieved[0].row.row_id == "patient:000"
    assert "term:pulmonary" in retrieved[0].reasons


def test_retrieve_prefers_observations_for_measurements() -> None:
    rows = [
        _row("patient:000", kind="condition", label="Hemoglobinopathy"),
        _row("patient:001", kind="observation", label="Hemoglobin A1c/Hemoglobin.total"),
    ]

    retrieved = retrieve_structured_patient_evidence(
        crit_measurement(text="hemoglobin a1c"),
        rows,
    )

    assert retrieved[0].row.row_id == "patient:001"
    assert "kind:observation" in retrieved[0].reasons


def test_retrieve_uses_composite_subcheck_criteria() -> None:
    criterion = crit_free_text().model_copy(
        update={
            "source_text": ("Hyperglycemia (HbA1c >= 6.5%; OR fasting plasma glucose >= 126 mg/dL)")
        }
    )
    rows = [
        _row(
            "patient:000",
            kind="observation",
            label="HbA1c",
            value="6.1 %",
            code="4548-4",
        )
    ]

    retrieved = retrieve_patient_evidence_with_composite_subchecks(
        criterion,
        rows,
        criterion_index=2,
    )

    assert [item.row.row_id for item in retrieved] == ["patient:000"]
    assert "subcheck:criterion:2:group:001:subcheck:001" in retrieved[0].reasons


def test_free_text_condition_mentions_use_structured_code_anchors() -> None:
    criterion = crit_free_text().model_copy(
        update={
            "source_text": "History of hypertension requiring medication.",
            "mentions": [EntityMention(text="hypertension", type="Condition")],
        }
    )
    rows = [
        _row("patient:000", kind="condition", label="Essential hypertension", code="59621000"),
        _row("patient:001", kind="condition", label="Full-time employment", code="160903007"),
    ]

    retrieved = retrieve_structured_patient_evidence(criterion, rows)

    assert [item.row.row_id for item in retrieved] == ["patient:000"]
    assert "correlatable_free_text:condition_present" in retrieved[0].reasons
    assert "code:59621000" in retrieved[0].reasons


def test_free_text_measurement_mentions_prefer_observation_rows() -> None:
    criterion = crit_free_text().model_copy(
        update={
            "source_text": "Body mass index must be reviewed before enrollment.",
            "mentions": [EntityMention(text="BMI", type="Measurement")],
        }
    )
    rows = [
        _row("patient:000", kind="condition", label="Obesity"),
        _row("patient:001", kind="observation", label="Body mass index", value="31 kg/m2"),
    ]

    retrieved = retrieve_structured_patient_evidence(criterion, rows)

    assert retrieved[0].row.row_id == "patient:001"
    assert "correlatable_free_text:measurement_threshold" in retrieved[0].reasons
    assert "kind:observation" in retrieved[0].reasons


def test_retrieve_ignores_numeric_only_overlap() -> None:
    rows = [
        _row(
            "patient:000",
            kind="observation",
            label="Estimated Glomerular Filtration Rate",
            value="121.26 mL/min/{1.73_m2}",
        ),
        _row("patient:001", kind="condition", label="Full-time employment"),
    ]

    retrieved = retrieve_structured_patient_evidence(
        crit_condition(text="type 1 diabetes"),
        rows,
    )

    assert retrieved == []


def test_retrieve_rejects_non_positive_limit() -> None:
    with pytest.raises(ValueError, match="limit must be positive"):
        retrieve_structured_patient_evidence(crit_condition(), [], limit=0)


def test_note_snippets_are_citeable_patient_source_rows() -> None:
    patient = make_patient(
        notes=[
            ClinicalNote(
                note_id="doc-support",
                title="Cardiology note",
                date=date(2024, 12, 1),
                text="Patient has uncontrolled hypertension despite therapy.",
            )
        ]
    )

    rows = structured_source_rows_for_pair(patient, make_trial())

    note_rows = [row for row in rows if row.kind == "note"]
    assert len(note_rows) == 1
    assert note_rows[0].source == "patient"
    assert note_rows[0].label == "Cardiology note"
    assert note_rows[0].value == "Patient has uncontrolled hypertension despite therapy."
    assert note_rows[0].date == "2024-12-01"
    assert note_rows[0].status == "note_id=doc-support"


@pytest.mark.parametrize(
    ("text", "criterion_text", "expected_retrieved"),
    [
        (
            "Assessment: patient has type 2 diabetes with elevated A1c.",
            "type 2 diabetes",
            True,
        ),
        (
            "Assessment: no history of type 2 diabetes is documented.",
            "type 2 diabetes",
            True,
        ),
        (
            "History: myocardial infarction occurred in 2010; no recent cardiac event.",
            "myocardial infarction within 6 months",
            True,
        ),
        (
            "Discussed diet and exercise goals.",
            "type 2 diabetes",
            False,
        ),
    ],
)
def test_retrieve_note_snippets_for_support_contradiction_and_temporal_review(
    text: str,
    criterion_text: str,
    expected_retrieved: bool,
) -> None:
    patient = make_patient(
        notes=[
            ClinicalNote(
                note_id="doc1",
                title="Progress note",
                date=date(2024, 12, 1),
                text=text,
            )
        ]
    )
    rows = structured_source_rows_for_pair(patient, make_trial())

    retrieved = retrieve_structured_patient_evidence(
        crit_condition(text=criterion_text),
        rows,
    )

    note_hits = [item for item in retrieved if item.row.kind == "note"]
    assert bool(note_hits) is expected_retrieved
    if expected_retrieved:
        assert "kind:note" in note_hits[0].reasons
