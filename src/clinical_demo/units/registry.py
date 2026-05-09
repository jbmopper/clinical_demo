"""LOINC-scoped measurement unit registry.

The profile layer currently owns a small, deliberately explicit set of
unit aliases and conversions. This module gives the compiler/resolution
layer the same behavior behind an inspectable registry: it can ask what
unit a measurement conventionally uses, which raw spellings are accepted,
and whether a conversion is approved for a particular LOINC.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from pydantic import BaseModel, ConfigDict, Field


class UnitSpec(BaseModel):
    """Unit metadata for one LOINC-coded measurement."""

    model_config = ConfigDict(frozen=True)

    loinc_code: str
    name: str
    conventional_unit: str
    aliases: Mapping[str, str]
    conversion_factors: Mapping[tuple[str, str], float] = Field(default_factory=dict)

    @property
    def canonical_units(self) -> frozenset[str]:
        """All canonical units accepted for this measurement."""
        return frozenset(self.aliases.values())


class MeasurementUnitRegistry:
    """Registry for LOINC-scoped unit aliases and approved conversions."""

    def __init__(self, specs: Iterable[UnitSpec]) -> None:
        self._specs = {spec.loinc_code: spec for spec in specs}

    @classmethod
    def default(cls) -> MeasurementUnitRegistry:
        """Return the built-in registry mirroring current profile behavior."""
        return cls(DEFAULT_UNIT_SPECS)

    def spec_for(self, loinc_code: str) -> UnitSpec | None:
        """Return metadata for a LOINC, if this registry knows it."""
        return self._specs.get(loinc_code)

    def canonical_unit(self, loinc_code: str, raw_unit: str | None) -> str | None:
        """Return the canonical unit for a raw unit spelling.

        Blank, missing, unknown-LOINC, and unknown-unit inputs return None so
        threshold comparisons can fail closed instead of making an unsafe
        numerical comparison.
        """
        spec = self.spec_for(loinc_code)
        if spec is None or raw_unit is None or raw_unit.strip() == "":
            return None
        return spec.aliases.get(raw_unit)

    def conversion_factor(
        self,
        loinc_code: str,
        from_unit: str | None,
        to_unit: str | None,
    ) -> float | None:
        """Return the factor for converting `from_unit` into `to_unit`.

        Units may be raw spellings or already-canonical units. Returns 1.0
        for identical canonical units and None when no explicit conversion
        is whitelisted.
        """
        spec = self.spec_for(loinc_code)
        if spec is None:
            return None
        from_canonical = self._canonical_unit_for_conversion(spec, from_unit)
        to_canonical = self._canonical_unit_for_conversion(spec, to_unit)
        if from_canonical is None or to_canonical is None:
            return None
        if from_canonical == to_canonical:
            return 1.0
        return spec.conversion_factors.get((from_canonical, to_canonical))

    def conventional_unit(self, loinc_code: str) -> str | None:
        """Return the conventional unit expected for a LOINC, if known."""
        spec = self.spec_for(loinc_code)
        if spec is None:
            return None
        return spec.conventional_unit

    def _canonical_unit_for_conversion(self, spec: UnitSpec, unit: str | None) -> str | None:
        if unit is None or unit.strip() == "":
            return None
        canonical = spec.aliases.get(unit)
        if canonical is not None:
            return canonical
        if unit in spec.canonical_units:
            return unit
        return None


DEFAULT_UNIT_SPECS: tuple[UnitSpec, ...] = (
    UnitSpec(
        loinc_code="33914-3",
        name="Estimated glomerular filtration rate",
        conventional_unit="mL/min/1.73m2",
        aliases={
            "mL/min/{1.73_m2}": "mL/min/1.73m2",
            "mL/min": "mL/min/1.73m2",
            "ml/min/1.73 m2": "mL/min/1.73m2",
            "ml/min/1.73 m^2": "mL/min/1.73m2",
            "mL/min/1.73 m2": "mL/min/1.73m2",
            "mL/min/1.73 m^2": "mL/min/1.73m2",
            "mL/min/1.73m2": "mL/min/1.73m2",
        },
    ),
    UnitSpec(
        loinc_code="4548-4",
        name="Hemoglobin A1c/Hemoglobin.total in Blood",
        conventional_unit="%",
        aliases={"%": "%", "percent": "%"},
    ),
    UnitSpec(
        loinc_code="18262-6",
        name="LDL cholesterol",
        conventional_unit="mg/dL",
        aliases={
            "mg/dL": "mg/dL",
            "mg/dl": "mg/dL",
            "mmol/L": "mmol/L",
            "mmol/l": "mmol/L",
        },
        conversion_factors={
            ("mmol/L", "mg/dL"): 38.67,
            ("mg/dL", "mmol/L"): 1 / 38.67,
        },
    ),
    UnitSpec(
        loinc_code="8480-6",
        name="Systolic blood pressure",
        conventional_unit="mmHg",
        aliases={"mm[Hg]": "mmHg", "mmHg": "mmHg"},
    ),
    UnitSpec(
        loinc_code="8462-4",
        name="Diastolic blood pressure",
        conventional_unit="mmHg",
        aliases={"mm[Hg]": "mmHg", "mmHg": "mmHg"},
    ),
    UnitSpec(
        loinc_code="39156-5",
        name="Body mass index",
        conventional_unit="kg/m2",
        aliases={
            "kg/m2": "kg/m2",
            "Kg/m2": "kg/m2",
            "kg/M2": "kg/m2",
            "kg/m^2": "kg/m2",
            "kg/m²": "kg/m2",
            "kg/m*2": "kg/m2",
        },
    ),
    UnitSpec(
        loinc_code="718-7",
        name="Hemoglobin",
        conventional_unit="g/dL",
        aliases={
            "g/dL": "g/dL",
            "g/dl": "g/dL",
            "g/L": "g/L",
            "g/l": "g/L",
        },
        conversion_factors={
            ("g/L", "g/dL"): 0.1,
            ("g/dL", "g/L"): 10.0,
        },
    ),
    UnitSpec(
        loinc_code="777-3",
        name="Platelet count",
        conventional_unit="10*3/uL",
        aliases={
            "10*3/uL": "10*3/uL",
            "10^3/uL": "10*3/uL",
            "K/uL": "10*3/uL",
            "x10^9/L": "10*3/uL",
            "10^9/L": "10*3/uL",
            "mm3": "count/uL",
            "uL": "count/uL",
            "μL": "count/uL",
            "/uL": "count/uL",
            "/μL": "count/uL",
        },
        conversion_factors={
            ("count/uL", "10*3/uL"): 0.001,
            ("10*3/uL", "count/uL"): 1000.0,
        },
    ),
)

DEFAULT_REGISTRY = MeasurementUnitRegistry.default()


def canonical_unit(loinc_code: str, raw_unit: str | None) -> str | None:
    """Return the canonical unit for `raw_unit` under `loinc_code`."""
    return DEFAULT_REGISTRY.canonical_unit(loinc_code, raw_unit)


def conversion_factor(
    loinc_code: str,
    from_unit: str | None,
    to_unit: str | None,
) -> float | None:
    """Return a whitelisted conversion factor from one unit to another."""
    return DEFAULT_REGISTRY.conversion_factor(loinc_code, from_unit, to_unit)


def conventional_unit(loinc_code: str) -> str | None:
    """Return the conventional unit for `loinc_code`, if known."""
    return DEFAULT_REGISTRY.conventional_unit(loinc_code)


__all__ = [
    "DEFAULT_REGISTRY",
    "DEFAULT_UNIT_SPECS",
    "MeasurementUnitRegistry",
    "UnitSpec",
    "canonical_unit",
    "conventional_unit",
    "conversion_factor",
]
