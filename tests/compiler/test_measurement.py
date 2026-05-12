from __future__ import annotations

import pytest

from clinical_demo.compiler import compile_measurement_resolution
from clinical_demo.extractor.schema import (
    ExtractedCriterion,
    MeasurementCriterion,
    ThresholdOperator,
)
from clinical_demo.terminology.reviewed_registry import (
    ReviewedMappingEntry,
    ReviewedMappingRegistry,
)
from clinical_demo.units import (
    REVIEWED_REFERENCE_LIMIT_REGISTRY_VERSION,
    MeasurementUnitRegistry,
    ReviewedReferenceLimitEntry,
    ReviewedReferenceLimitRegistry,
    UnitSpec,
)


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


@pytest.mark.parametrize(
    ("surface", "unit", "expected_canonical", "expected_conventional", "expected_factor"),
    [
        ("LDL cholesterol", "MMOL / L", "mmol/L", "mg/dL", 38.67),
        ("HbA1c", " percent ", "%", "%", 1.0),
        ("BMI", "kg / m^2", "kg/m2", "kg/m2", 1.0),
        ("eGFR", "mL / min / 1.73 m^2", "mL/min/1.73m2", "mL/min/1.73m2", 1.0),
    ],
)
def test_measurement_resolution_accepts_normalized_unit_variants(
    surface: str,
    unit: str,
    expected_canonical: str,
    expected_conventional: str,
    expected_factor: float,
) -> None:
    result = compile_measurement_resolution(
        _measurement(surface, value=2.6, unit=unit),
        "c:normalized",
    )

    assert result.unit_normalization.status == "resolved"
    assert result.unit_normalization.source_unit == unit
    assert result.unit_normalization.canonical_unit == expected_canonical
    assert result.unit_normalization.conventional_unit == expected_conventional
    assert result.unit_normalization.conversion_factor == expected_factor
    assert result.unresolved_gaps == []


def test_measurement_resolution_accepts_parenthetical_surface_variant() -> None:
    result = compile_measurement_resolution(
        _measurement("body mass index (bmi)", value=45.0, unit="kg/m2"),
        "c:parenthetical",
    )

    assert result.concept_set is not None
    assert result.loinc_codes == ["39156-5"]
    assert result.unit_normalization.status == "resolved"
    assert result.unit_normalization.conventional_unit == "kg/m2"
    assert result.unresolved_gaps == []


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


def test_reviewed_out_of_scope_measurement_emits_unsupported_gap() -> None:
    result = compile_measurement_resolution(
        _measurement("pulmonary vascular resistance (PVR)", value=4.0, unit="Wood units"),
        "c:reviewed",
        reviewed_registry=ReviewedMappingRegistry(
            [
                ReviewedMappingEntry(
                    kind="lab",
                    surface="pulmonary vascular resistance (PVR)",
                    normalized_surface="pulmonary vascular resistance (pvr",
                    status="out_of_scope",
                    concept_set=None,
                    candidates=(),
                    reason=(
                        "Requires right-heart catheterization/hemodynamic observations not "
                        "modeled in the current patient profile."
                    ),
                    source="compiler-review",
                    provenance="unit test",
                    reviewer="tests",
                    reviewed_at="2026-05-11",
                    resolver_version="reviewed-registry-v1",
                    expansion_policy="exact_code",
                )
            ]
        ),
    )

    assert result.concept_set is None
    assert result.unit_normalization.status == "unsupported"
    assert [gap.kind for gap in result.unresolved_gaps] == ["unsupported_predicate"]
    assert result.unresolved_gaps[0].stage == "concept_resolution"
    assert {diagnostic.code for diagnostic in result.diagnostics} == {
        "measurement.reviewed.out_of_scope"
    }


def test_reviewed_mapped_measurement_resolves_without_alias_entry() -> None:
    result = compile_measurement_resolution(
        _measurement("fasting serum LDL-C", value=2.6, unit="mmol/L"),
        "c:reviewed-mapped",
        reviewed_registry=ReviewedMappingRegistry(
            [
                ReviewedMappingEntry.model_validate(
                    {
                        "kind": "lab",
                        "surface": "fasting serum LDL-C",
                        "status": "mapped",
                        "concept_set": "LDL_CHOLESTEROL",
                        "candidates": [],
                        "reason": "unit-test reviewed LDL decision",
                        "source": "compiler-review",
                        "provenance": "unit test",
                        "reviewer": "tests",
                        "reviewed_at": "2026-05-11",
                        "resolver_version": "reviewed-registry-v1",
                        "expansion_policy": "exact_code",
                    }
                )
            ]
        ),
    )

    assert result.selected_loinc_code == "18262-6"
    assert result.unit_normalization.status == "resolved"
    assert result.normalized_value == pytest.approx(100.542)
    assert result.unresolved_gaps == []


def test_missing_threshold_value_emits_predicate_translation_gap() -> None:
    result = compile_measurement_resolution(
        _measurement("aspartate aminotransferase", operator="<=", value=None, unit=None),
        "c:missing-value",
        reviewed_registry=ReviewedMappingRegistry(
            [
                ReviewedMappingEntry.model_validate(
                    {
                        "kind": "lab",
                        "surface": "aspartate aminotransferase",
                        "status": "mapped",
                        "concept_set": "ASPARTATE_AMINOTRANSFERASE",
                        "candidates": [],
                        "reason": "unit-test reviewed AST decision",
                        "source": "compiler-review",
                        "provenance": "unit test",
                        "reviewer": "tests",
                        "reviewed_at": "2026-05-11",
                        "resolver_version": "reviewed-registry-v1",
                        "expansion_policy": "exact_code",
                    }
                )
            ]
        ),
    )

    assert result.selected_loinc_code == "1920-8"
    assert result.unit_normalization.status == "resolved"
    assert [gap.kind for gap in result.unresolved_gaps] == ["insufficient_source"]
    assert result.unresolved_gaps[0].stage == "predicate_translation"
    assert "measurement.threshold_value_missing" in {
        diagnostic.code for diagnostic in result.diagnostics
    }


def test_uln_threshold_translates_through_reviewed_reference_limit() -> None:
    result = compile_measurement_resolution(
        _measurement(
            "aspartate aminotransferase",
            operator="<=",
            value=3.0,
            unit="x upper limit of normal (ULN)",
        ),
        "c:uln",
    )

    assert result.selected_loinc_code == "1920-8"
    assert result.unit_normalization.status == "resolved"
    assert result.unit_normalization.source_unit == "x upper limit of normal (ULN)"
    assert result.unit_normalization.conventional_unit == "U/L"
    assert result.normalized_operator == "<="
    assert result.normalized_value == 120.0
    assert result.unresolved_gaps == []
    assert "measurement.reference_limit.translated" in {
        diagnostic.code for diagnostic in result.diagnostics
    }


def test_uln_multiplier_defaults_to_one_when_source_says_above_uln() -> None:
    result = compile_measurement_resolution(
        _measurement(
            "total bilirubin",
            operator=">",
            value=None,
            unit="ULN",
        ).model_copy(update={"source_text": "Total bilirubin above ULN"}),
        "c:uln-default",
    )

    assert result.selected_loinc_code == "1975-2"
    assert result.unit_normalization.status == "resolved"
    assert result.normalized_value == 1.2
    assert result.unresolved_gaps == []


def test_sex_specific_uln_translates_to_patient_sex_thresholds() -> None:
    result = compile_measurement_resolution(
        _measurement(
            "hemoglobin",
            operator=">",
            value=None,
            unit="gender-specific ULN",
        ).model_copy(update={"source_text": "Hemoglobin at screening above gender-specific ULN"}),
        "c:sex-specific-uln",
    )

    assert result.selected_loinc_code == "718-7"
    assert result.unit_normalization.status == "resolved"
    assert result.unit_normalization.conventional_unit == "g/dL"
    assert result.normalized_value is None
    assert result.normalized_value_by_sex == {"FEMALE": 15.5, "MALE": 17.5}
    assert result.unresolved_gaps == []
    assert "measurement.reference_limit.sex_specific_translated" in {
        diagnostic.code for diagnostic in result.diagnostics
    }


def test_missing_reviewed_reference_limit_emits_structured_gap() -> None:
    result = compile_measurement_resolution(
        _measurement(
            "aspartate aminotransferase",
            operator="<=",
            value=3.0,
            unit="ULN",
        ),
        "c:missing-uln",
        reference_limit_registry=ReviewedReferenceLimitRegistry([]),
    )

    assert result.selected_loinc_code == "1920-8"
    assert result.unit_normalization.status == "unsupported"
    assert result.normalized_value is None
    assert [gap.kind for gap in result.unresolved_gaps] == ["unsupported_predicate"]
    assert "No reviewed upper reference limit" in result.unresolved_gaps[0].message
    assert "measurement.reference_limit.missing_reviewed_limit" in {
        diagnostic.code for diagnostic in result.diagnostics
    }


def test_reference_limit_registry_can_be_injected() -> None:
    result = compile_measurement_resolution(
        _measurement("total bilirubin", operator="<=", value=2.0, unit="ULN"),
        "c:custom-uln",
        reference_limit_registry=ReviewedReferenceLimitRegistry(
            [
                ReviewedReferenceLimitEntry(
                    loinc_code="1975-2",
                    loinc_display="Total bilirubin",
                    limit_kind="upper",
                    applies_to="any",
                    value=1.0,
                    unit="mg/dL",
                    reason="unit test",
                    source="unit test",
                    provenance="unit test",
                    reviewer="tests",
                    reviewed_at="2026-05-12",
                    resolver_version=REVIEWED_REFERENCE_LIMIT_REGISTRY_VERSION,
                )
            ]
        ),
    )

    assert result.normalized_value == 2.0
    assert result.unit_normalization.conventional_unit == "mg/dL"


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


def test_unknown_normalized_unit_variant_still_fails_closed() -> None:
    result = compile_measurement_resolution(
        _measurement("HbA1c", value=7.0, unit="percent-ish"),
        "c:6",
    )

    assert result.selected_loinc_code == "4548-4"
    assert result.unit_normalization.status == "unsupported"
    assert result.unit_normalization.canonical_unit is None
    assert result.unit_normalization.conversion_factor is None
    assert result.normalized_value is None
    assert [gap.kind for gap in result.unresolved_gaps] == ["unsupported_predicate"]
