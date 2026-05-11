"""Tests for the compiler-facing unit registry."""

from __future__ import annotations

import pytest

from clinical_demo.units import (
    DEFAULT_REGISTRY,
    MeasurementUnitRegistry,
    UnitSpec,
    canonical_unit,
    conventional_unit,
    conversion_factor,
)


@pytest.mark.parametrize(
    ("raw_unit", "expected"),
    [
        ("mL/min/{1.73_m2}", "mL/min/1.73m2"),
        ("mL/min", "mL/min/1.73m2"),
        ("ml/min/1.73 m^2", "mL/min/1.73m2"),
        (" mL / min / 1.73 m^2 ", "mL/min/1.73m2"),
    ],
)
def test_egfr_units_canonicalize_to_single_conventional_form(
    raw_unit: str,
    expected: str,
) -> None:
    assert canonical_unit("33914-3", raw_unit) == expected


@pytest.mark.parametrize(
    ("loinc_code", "raw_unit", "expected"),
    [
        ("18262-6", "mg / dL", "mg/dL"),
        ("18262-6", "MMOL/L", "mmol/L"),
        ("18262-6", "mmol / l", "mmol/L"),
        ("4548-4", " percent ", "%"),
        ("4548-4", "%", "%"),
        ("39156-5", "kg / m^2", "kg/m2"),
        ("777-3", "µL", "count/uL"),
        ("777-3", "/ µL", "count/uL"),
        ("751-8", "/ µL", "count/uL"),
        ("1920-8", "u / L", "U/L"),
    ],
)
def test_unit_alias_lookup_accepts_conservative_normalized_variants(
    loinc_code: str,
    raw_unit: str,
    expected: str,
) -> None:
    assert canonical_unit(loinc_code, raw_unit) == expected


def test_ldl_mmol_l_to_mg_dl_conversion_factor() -> None:
    assert conversion_factor("18262-6", "mmol/L", "mg/dL") == 38.67
    assert conversion_factor("18262-6", "MMOL / L", "mg / dL") == 38.67
    assert conversion_factor("18262-6", "mg/dL", "mmol/L") == pytest.approx(1 / 38.67)


def test_hemoglobin_conversion_factors() -> None:
    assert conversion_factor("718-7", "g/L", "g/dL") == 0.1
    assert conversion_factor("718-7", "g/dL", "g/L") == 10.0


def test_platelet_conversion_factors() -> None:
    assert conversion_factor("777-3", "μL", "10*3/uL") == 0.001
    assert conversion_factor("777-3", "count/uL", "10*3/uL") == 0.001
    assert conversion_factor("777-3", "10*3/uL", "mm3") == 1000.0


def test_new_reviewed_measurement_conversion_factors() -> None:
    assert conversion_factor("751-8", "μL", "10*3/uL") == 0.001
    assert conversion_factor("2339-0", "mmol/L", "mg/dL") == 18.018
    assert conversion_factor("2571-8", "mmol/L", "mg/dL") == 88.57


@pytest.mark.parametrize(
    ("loinc_code", "raw_unit"),
    [
        ("99999-9", "mg/dL"),
        ("4548-4", "mmol/mol"),
        ("4548-4", ""),
        ("4548-4", "   "),
        ("4548-4", None),
    ],
)
def test_unknown_or_blank_units_return_none(loinc_code: str, raw_unit: str | None) -> None:
    assert canonical_unit(loinc_code, raw_unit) is None


def test_unknown_conversion_returns_none() -> None:
    assert conversion_factor("4548-4", "%", "mmol/mol") is None
    assert conversion_factor("99999-9", "mg/dL", "mmol/L") is None
    assert conversion_factor("18262-6", "", "mg/dL") is None
    assert conversion_factor("18262-6", "moles maybe", "mg/dL") is None


def test_identical_canonical_units_have_identity_conversion() -> None:
    assert conversion_factor("8480-6", "mm[Hg]", "mmHg") == 1.0


@pytest.mark.parametrize(
    ("loinc_code", "expected"),
    [
        ("33914-3", "mL/min/1.73m2"),
        ("18262-6", "mg/dL"),
        ("718-7", "g/dL"),
        ("777-3", "10*3/uL"),
        ("751-8", "10*3/uL"),
        ("1920-8", "U/L"),
        ("1975-2", "mg/dL"),
        ("2339-0", "mg/dL"),
        ("2571-8", "mg/dL"),
        ("99999-9", None),
    ],
)
def test_conventional_unit_lookup(loinc_code: str, expected: str | None) -> None:
    assert conventional_unit(loinc_code) == expected


def test_registry_exposes_unit_spec_metadata_for_compiler() -> None:
    registry = MeasurementUnitRegistry.default()
    spec = registry.spec_for("18262-6")

    assert spec is not None
    assert spec.conventional_unit == "mg/dL"
    assert spec.canonical_units == frozenset({"mg/dL", "mmol/L"})


def test_default_registry_is_reusable_singleton() -> None:
    assert DEFAULT_REGISTRY.canonical_unit("39156-5", "kg/m²") == "kg/m2"


def test_normalized_alias_collisions_fail_closed() -> None:
    registry = MeasurementUnitRegistry(
        [
            UnitSpec(
                loinc_code="test",
                name="Test measurement",
                conventional_unit="unit/a",
                aliases={
                    "x / y": "unit/a",
                    "x/y": "unit/b",
                },
            )
        ]
    )

    assert registry.canonical_unit("test", "x / y") == "unit/a"
    assert registry.canonical_unit("test", "x/y") == "unit/b"
    assert registry.canonical_unit("test", " X / Y ") is None
