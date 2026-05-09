from __future__ import annotations

import pytest

from clinical_demo.compiler import compile_measurement_resolution
from clinical_demo.extractor.schema import (
    ExtractedCriterion,
    MeasurementCriterion,
    ThresholdOperator,
)
from clinical_demo.units import MeasurementUnitRegistry, UnitSpec


def _measurement(
    text: str,
    *,
    operator: ThresholdOperator = ">=",
    value: float | None = 7.0,
    unit: str | None = "%",
) -> ExtractedCriterion:
    return ExtractedCriterion(
        kind="measurement_threshold",
        polarity="inclusion",
        source_text=f"{text} {operator} {value or ''}{unit or ''}",
        negated=False,
        mood="actual",
        age=None,
        sex=None,
        condition=None,
        medication=None,
        measurement=MeasurementCriterion(
            measurement_text=text,
            operator=operator,
            value=value,
            value_low=None,
            value_high=None,
            unit=unit,
        ),
        temporal_window=None,
        free_text=None,
        mentions=[],
    )


def test_hba1c_percent_resolves_and_normalizes_without_conversion() -> None:
    result = compile_measurement_resolution(_measurement("HbA1c", value=7.0, unit="%"), "c:0")

    assert result.selected_loinc_code == "4548-4"
    assert result.loinc_codes == ["4548-4"]
    assert result.unit_normalization.status == "resolved"
    assert result.unit_normalization.source_unit == "%"
    assert result.unit_normalization.canonical_unit == "%"
    assert result.unit_normalization.conventional_unit == "%"
    assert result.unit_normalization.conversion_factor == 1.0
    assert result.normalized_value == 7.0
    assert result.unresolved_gaps == []
    assert [support.stage for support in result.resolved_supports] == [
        "concept_resolution",
        "unit_normalization",
    ]


def test_ldl_mmol_l_threshold_converts_to_conventional_mg_dl() -> None:
    result = compile_measurement_resolution(
        _measurement("LDL cholesterol", value=2.6, unit="mmol/L"),
        "c:1",
    )

    assert result.selected_loinc_code == "18262-6"
    assert result.unit_normalization.status == "resolved"
    assert result.unit_normalization.canonical_unit == "mmol/L"
    assert result.unit_normalization.conventional_unit == "mg/dL"
    assert result.unit_normalization.conversion_factor == 38.67
    assert result.normalized_value == pytest.approx(100.542)


def test_egfr_missing_unit_infers_single_registered_conventional_unit() -> None:
    result = compile_measurement_resolution(_measurement("eGFR", value=25.0, unit=None), "c:2")

    assert result.selected_loinc_code == "33914-3"
    assert result.unit_normalization.status == "resolved"
    assert result.unit_normalization.source_unit is None
    assert result.unit_normalization.canonical_unit == "mL/min/1.73m2"
    assert result.unit_normalization.conventional_unit == "mL/min/1.73m2"
    assert result.unit_normalization.conversion_factor == 1.0
    assert result.normalized_value == 25.0
    assert {diagnostic.code for diagnostic in result.diagnostics} == {"unit.inferred_conventional"}


def test_unknown_measurement_emits_mapping_gap() -> None:
    result = compile_measurement_resolution(_measurement("BNP", value=100.0, unit="pg/mL"), "c:3")

    assert result.concept_set is None
    assert result.selected_loinc_code is None
    assert result.unit_normalization.status == "unresolved"
    assert [gap.kind for gap in result.unresolved_gaps] == [
        "unmapped_concept",
        "ambiguous_mapping",
    ]
    assert result.unit_normalization.gap_ids == [gap.gap_id for gap in result.unresolved_gaps]
    assert "measurement.unmapped" in {diagnostic.code for diagnostic in result.diagnostics}


def test_missing_unit_unknown_measurement_emits_unit_gap_too() -> None:
    result = compile_measurement_resolution(_measurement("BNP", value=100.0, unit=None), "c:4")

    assert result.concept_set is None
    assert result.unit_normalization.status == "unresolved"
    assert [gap.kind for gap in result.unresolved_gaps] == [
        "unmapped_concept",
        "missing_unit",
    ]
    assert {diagnostic.code for diagnostic in result.diagnostics} == {
        "measurement.unmapped",
        "unit.missing",
    }


def test_unsupported_conversion_emits_structured_unit_gap() -> None:
    registry = MeasurementUnitRegistry(
        [
            UnitSpec(
                loinc_code="18262-6",
                name="LDL cholesterol",
                conventional_unit="mg/dL",
                aliases={"mg/dL": "mg/dL", "arbitrary": "arbitrary"},
                conversion_factors={},
            )
        ]
    )

    result = compile_measurement_resolution(
        _measurement("LDL", value=2.6, unit="arbitrary"),
        "c:5",
        unit_registry=registry,
    )

    assert result.selected_loinc_code == "18262-6"
    assert result.unit_normalization.status == "unsupported"
    assert result.unit_normalization.canonical_unit == "arbitrary"
    assert result.unit_normalization.conventional_unit == "mg/dL"
    assert result.unit_normalization.conversion_factor is None
    assert result.normalized_value is None
    assert [gap.kind for gap in result.unresolved_gaps] == ["unsupported_predicate"]
    assert result.unresolved_gaps[0].stage == "unit_normalization"
    assert {diagnostic.code for diagnostic in result.diagnostics} == {"unit.unsupported_conversion"}
