from __future__ import annotations

import pytest

from clinical_demo.units import (
    REVIEWED_REFERENCE_LIMIT_REGISTRY_VERSION,
    DuplicateReviewedReferenceLimitError,
    ReviewedReferenceLimitEntry,
    ReviewedReferenceLimitRegistry,
    get_reviewed_reference_limit_registry,
)


def _entry(loinc_code: str = "1920-8") -> ReviewedReferenceLimitEntry:
    return ReviewedReferenceLimitEntry(
        loinc_code=loinc_code,
        loinc_display="Aspartate aminotransferase",
        limit_kind="upper",
        applies_to="any",
        value=40.0,
        unit="U/L",
        reason="unit test",
        source="unit test",
        provenance="unit test",
        reviewer="tests",
        reviewed_at="2026-05-12",
        resolver_version=REVIEWED_REFERENCE_LIMIT_REGISTRY_VERSION,
    )


def test_reviewed_reference_limit_registry_loads_default_entries() -> None:
    registry = get_reviewed_reference_limit_registry()

    ast = registry.lookup("1920-8", "upper")
    bilirubin = registry.lookup("1975-2", "upper")
    hemoglobin = registry.lookup_sex_specific("718-7", "upper")

    assert ast is not None
    assert ast.value == 40.0
    assert ast.unit == "U/L"
    assert bilirubin is not None
    assert bilirubin.value == 1.2
    assert bilirubin.unit == "mg/dL"
    assert {sex: entry.value for sex, entry in hemoglobin.items()} == {
        "FEMALE": 15.5,
        "MALE": 17.5,
    }


def test_reviewed_reference_limit_registry_rejects_duplicate_keys() -> None:
    with pytest.raises(DuplicateReviewedReferenceLimitError):
        ReviewedReferenceLimitRegistry([_entry(), _entry()])


def test_reviewed_reference_limit_entry_requires_registry_version() -> None:
    with pytest.raises(ValueError, match="resolver_version"):
        ReviewedReferenceLimitEntry(
            loinc_code="1920-8",
            loinc_display="Aspartate aminotransferase",
            limit_kind="upper",
            applies_to="any",
            value=40.0,
            unit="U/L",
            reason="unit test",
            source="unit test",
            provenance="unit test",
            reviewer="tests",
            reviewed_at="2026-05-12",
            resolver_version="wrong",
        )
