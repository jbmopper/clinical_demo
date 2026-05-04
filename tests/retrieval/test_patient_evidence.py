"""Tests for structured patient-evidence retrieval."""

from __future__ import annotations

import pytest

from clinical_demo.retrieval import RetrievalSourceRow, retrieve_structured_patient_evidence
from tests.matcher._fixtures import crit_condition, crit_measurement


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
