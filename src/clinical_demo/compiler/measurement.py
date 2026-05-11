"""Measurement-resolution helpers for the criterion compiler.

This module is intentionally offline-only. It resolves measurement
surfaces through the existing local matcher alias table and normalizes
threshold units through the committed unit registry. Live terminology
lookup belongs in resolver/warmer paths, not in compiler unit tests or
cached-only eval runs.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from clinical_demo.extractor.schema import ExtractedCriterion, ThresholdOperator
from clinical_demo.matcher.concept_lookup import lookup_lab_alias
from clinical_demo.profile import ConceptSet
from clinical_demo.settings import ResolverExecutionPolicy
from clinical_demo.units import DEFAULT_REGISTRY, MeasurementUnitRegistry

from .schema import (
    CompilerDiagnostic,
    DiagnosticFact,
    DiagnosticSeverity,
    ResolutionDomain,
    ResolutionGap,
    ResolutionGapKind,
    ResolutionStage,
    ResolutionStatus,
    ResolutionSupport,
    UnitNormalizationPlan,
)

LOINC_SYSTEM = "http://loinc.org"
_PARENTHETICAL_RE = re.compile(r"\(([^()]*)\)")


class MeasurementResolutionResult(BaseModel):
    """Compiler-local result for one measurement threshold criterion."""

    source_criterion_id: str = Field(description="Stable compiler source criterion id.")
    measurement_surface: str | None = Field(description="Trial measurement surface.")
    concept_set: ConceptSet | None = Field(description="Resolved LOINC concept set, if any.")
    loinc_codes: list[str] = Field(
        default_factory=list,
        description="Resolved LOINC codes sorted for deterministic downstream use.",
    )
    selected_loinc_code: str | None = Field(
        description="Single LOINC used for unit normalization, when unambiguous."
    )
    unit_normalization: UnitNormalizationPlan = Field(description="Unit normalization plan.")
    normalized_operator: ThresholdOperator | None = Field(
        description="Threshold operator preserved for predicate translation."
    )
    normalized_value: float | None = Field(
        description="Single threshold converted into the conventional unit, if available."
    )
    normalized_value_low: float | None = Field(
        description="Range lower bound converted into the conventional unit, if available."
    )
    normalized_value_high: float | None = Field(
        description="Range upper bound converted into the conventional unit, if available."
    )
    resolved_supports: list[ResolutionSupport] = Field(default_factory=list)
    unresolved_gaps: list[ResolutionGap] = Field(default_factory=list)
    diagnostics: list[CompilerDiagnostic] = Field(default_factory=list)


def compile_measurement_resolution(
    criterion: ExtractedCriterion,
    source_criterion_id: str,
    *,
    resolver_policy: ResolverExecutionPolicy = "cached_only",
    unit_registry: MeasurementUnitRegistry | None = None,
) -> MeasurementResolutionResult:
    """Resolve a measurement threshold surface and normalize its threshold unit.

    The helper never calls live terminology services. Unknown measurement
    surfaces and unsupported unit conversions are represented as typed
    compiler gaps so the integration layer can decide whether to keep,
    review, or fail closed.
    """

    registry = unit_registry or DEFAULT_REGISTRY
    measurement = criterion.measurement
    if criterion.kind != "measurement_threshold" or measurement is None:
        return _skipped_result(
            source_criterion_id=source_criterion_id,
            measurement_surface=None,
            source_unit=None,
            resolver_policy=resolver_policy,
        )

    surface = measurement.measurement_text
    source_unit = measurement.unit
    supports: list[ResolutionSupport] = []
    gaps: list[ResolutionGap] = []
    diagnostics: list[CompilerDiagnostic] = []

    concept_set = _lookup_measurement_concept_set(surface)
    loinc_codes = _loinc_codes(concept_set)
    selected_loinc_code = loinc_codes[0] if len(loinc_codes) == 1 else None

    if concept_set is not None:
        supports.append(
            _support(
                support_id=f"{source_criterion_id}:measurement:loinc",
                stage="concept_resolution",
                domain="measurement",
                source_criterion_id=source_criterion_id,
                surface=surface,
                normalized_surface=_normalize_surface(surface),
                target_system=concept_set.system,
                target_id=",".join(loinc_codes),
                target_label=concept_set.name,
                resolver_policy=resolver_policy,
            )
        )
    else:
        gap = _gap(
            gap_id=f"{source_criterion_id}:measurement:gap:unmapped",
            stage="concept_resolution",
            domain="measurement",
            kind="unmapped_concept",
            source_criterion_id=source_criterion_id,
            surface=surface,
            message=f"No cached/local LOINC mapping is available for measurement '{surface}'.",
            resolver_policy=resolver_policy,
        )
        gaps.append(gap)
        diagnostics.append(
            _diagnostic(
                severity="warning",
                code="measurement.unmapped",
                message=gap.message,
                source_criterion_id=source_criterion_id,
                facts=[("gap_id", gap.gap_id)],
            )
        )

    canonical_unit: str | None = None
    conventional_unit: str | None = None
    conversion_factor: float | None = None

    if source_unit is None or source_unit.strip() == "":
        inferred = _infer_missing_unit(
            source_criterion_id=source_criterion_id,
            surface=surface,
            selected_loinc_code=selected_loinc_code,
            registry=registry,
            resolver_policy=resolver_policy,
            supports=supports,
            gaps=gaps,
            diagnostics=diagnostics,
        )
        canonical_unit = inferred
        conventional_unit = inferred
        conversion_factor = 1.0 if inferred is not None else None
    elif selected_loinc_code is None:
        gap = _gap(
            gap_id=f"{source_criterion_id}:unit:gap:ambiguous_loinc",
            stage="unit_normalization",
            domain="unit",
            kind="ambiguous_mapping",
            source_criterion_id=source_criterion_id,
            surface=source_unit,
            message=(
                f"Cannot normalize unit '{source_unit}' because measurement '{surface}' "
                "did not resolve to exactly one LOINC code."
            ),
            resolver_policy=resolver_policy,
        )
        gaps.append(gap)
        diagnostics.append(
            _diagnostic(
                severity="warning",
                code="unit.ambiguous_measurement",
                message=gap.message,
                source_criterion_id=source_criterion_id,
                facts=[("gap_id", gap.gap_id)],
            )
        )
    else:
        canonical_unit = registry.canonical_unit(selected_loinc_code, source_unit)
        conventional_unit = registry.conventional_unit(selected_loinc_code)
        if canonical_unit is None or conventional_unit is None:
            gap = _unsupported_conversion_gap(
                source_criterion_id=source_criterion_id,
                surface=surface,
                source_unit=source_unit,
                canonical_unit=canonical_unit,
                conventional_unit=conventional_unit,
                resolver_policy=resolver_policy,
            )
            gaps.append(gap)
            diagnostics.append(
                _unsupported_conversion_diagnostic(
                    gap=gap,
                    source_criterion_id=source_criterion_id,
                    source_unit=source_unit,
                    canonical_unit=canonical_unit,
                    conventional_unit=conventional_unit,
                )
            )
        else:
            conversion_factor = registry.conversion_factor(
                selected_loinc_code,
                canonical_unit,
                conventional_unit,
            )
            if conversion_factor is None:
                gap = _unsupported_conversion_gap(
                    source_criterion_id=source_criterion_id,
                    surface=surface,
                    source_unit=source_unit,
                    canonical_unit=canonical_unit,
                    conventional_unit=conventional_unit,
                    resolver_policy=resolver_policy,
                )
                gaps.append(gap)
                diagnostics.append(
                    _unsupported_conversion_diagnostic(
                        gap=gap,
                        source_criterion_id=source_criterion_id,
                        source_unit=source_unit,
                        canonical_unit=canonical_unit,
                        conventional_unit=conventional_unit,
                    )
                )
            else:
                supports.append(
                    _unit_support(
                        source_criterion_id=source_criterion_id,
                        source_unit=source_unit,
                        canonical_unit=canonical_unit,
                        conventional_unit=conventional_unit,
                        conversion_factor=conversion_factor,
                        resolver_policy=resolver_policy,
                    )
                )

    status = _unit_status(gaps, conversion_factor)
    gap_ids = [gap.gap_id for gap in gaps]
    plan = UnitNormalizationPlan(
        status=status,
        measurement_surface=surface,
        source_unit=source_unit,
        canonical_unit=canonical_unit,
        conventional_unit=conventional_unit,
        conversion_factor=conversion_factor,
        gap_ids=gap_ids,
    )

    normalized_values = _normalized_values(
        value=measurement.value,
        value_low=measurement.value_low,
        value_high=measurement.value_high,
        conversion_factor=conversion_factor,
    )

    return MeasurementResolutionResult(
        source_criterion_id=source_criterion_id,
        measurement_surface=surface,
        concept_set=concept_set,
        loinc_codes=loinc_codes,
        selected_loinc_code=selected_loinc_code,
        unit_normalization=plan,
        normalized_operator=measurement.operator,
        normalized_value=normalized_values[0],
        normalized_value_low=normalized_values[1],
        normalized_value_high=normalized_values[2],
        resolved_supports=supports,
        unresolved_gaps=gaps,
        diagnostics=diagnostics,
    )


def _skipped_result(
    *,
    source_criterion_id: str,
    measurement_surface: str | None,
    source_unit: str | None,
    resolver_policy: ResolverExecutionPolicy,
) -> MeasurementResolutionResult:
    return MeasurementResolutionResult(
        source_criterion_id=source_criterion_id,
        measurement_surface=measurement_surface,
        concept_set=None,
        loinc_codes=[],
        selected_loinc_code=None,
        unit_normalization=UnitNormalizationPlan(
            status="skipped",
            measurement_surface=measurement_surface,
            source_unit=source_unit,
            canonical_unit=None,
            conventional_unit=None,
            conversion_factor=None,
            gap_ids=[],
        ),
        normalized_operator=None,
        normalized_value=None,
        normalized_value_low=None,
        normalized_value_high=None,
        resolved_supports=[],
        unresolved_gaps=[],
        diagnostics=[
            _diagnostic(
                severity="info",
                code="measurement.skipped",
                message="Criterion is not a measurement threshold.",
                source_criterion_id=source_criterion_id,
                facts=[("resolver_policy", resolver_policy)],
            )
        ],
    )


def _lookup_measurement_concept_set(surface: str) -> ConceptSet | None:
    for variant in _measurement_surface_variants(surface):
        concept_set = lookup_lab_alias(variant)
        if concept_set is not None:
            return concept_set
    return None


def _measurement_surface_variants(surface: str) -> tuple[str, ...]:
    variants: list[str] = []
    seen: set[str] = set()

    def add(candidate: str) -> None:
        normalized = _normalize_surface(candidate)
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        variants.append(candidate)

    add(surface)
    add(_PARENTHETICAL_RE.sub(lambda match: f" {match.group(1)} ", surface))
    add(_PARENTHETICAL_RE.sub(" ", surface))
    return tuple(variants)


def _loinc_codes(concept_set: ConceptSet | None) -> list[str]:
    if concept_set is None or concept_set.system != LOINC_SYSTEM:
        return []
    return sorted(concept_set.codes)


def _infer_missing_unit(
    *,
    source_criterion_id: str,
    surface: str,
    selected_loinc_code: str | None,
    registry: MeasurementUnitRegistry,
    resolver_policy: ResolverExecutionPolicy,
    supports: list[ResolutionSupport],
    gaps: list[ResolutionGap],
    diagnostics: list[CompilerDiagnostic],
) -> str | None:
    if selected_loinc_code is not None:
        conventional = registry.conventional_unit(selected_loinc_code)
        if conventional is not None:
            supports.append(
                _unit_support(
                    source_criterion_id=source_criterion_id,
                    source_unit=None,
                    canonical_unit=conventional,
                    conventional_unit=conventional,
                    conversion_factor=1.0,
                    resolver_policy=resolver_policy,
                )
            )
            diagnostics.append(
                _diagnostic(
                    severity="info",
                    code="unit.inferred_conventional",
                    message=(
                        f"Inferred conventional unit '{conventional}' for measurement '{surface}'."
                    ),
                    source_criterion_id=source_criterion_id,
                    facts=[
                        ("loinc_code", selected_loinc_code),
                        ("conventional_unit", conventional),
                    ],
                )
            )
            return conventional

    gap = _gap(
        gap_id=f"{source_criterion_id}:unit:gap:missing_unit",
        stage="unit_normalization",
        domain="unit",
        kind="missing_unit",
        source_criterion_id=source_criterion_id,
        surface=surface,
        message=(
            f"Cannot infer a missing unit for measurement '{surface}' because it did not "
            "resolve to exactly one LOINC code with a registered conventional unit."
        ),
        resolver_policy=resolver_policy,
    )
    gaps.append(gap)
    diagnostics.append(
        _diagnostic(
            severity="warning",
            code="unit.missing",
            message=gap.message,
            source_criterion_id=source_criterion_id,
            facts=[("gap_id", gap.gap_id)],
        )
    )
    return None


def _unit_status(
    gaps: list[ResolutionGap],
    conversion_factor: float | None,
) -> ResolutionStatus:
    unit_gaps = [gap for gap in gaps if gap.stage == "unit_normalization"]
    if not unit_gaps and conversion_factor is not None:
        return "resolved"
    if any(diagnostic_gap.kind == "unsupported_predicate" for diagnostic_gap in unit_gaps):
        return "unsupported"
    return "unresolved"


def _normalized_values(
    *,
    value: float | None,
    value_low: float | None,
    value_high: float | None,
    conversion_factor: float | None,
) -> tuple[float | None, float | None, float | None]:
    if conversion_factor is None:
        return None, None, None
    return (
        _convert_threshold(value, conversion_factor),
        _convert_threshold(value_low, conversion_factor),
        _convert_threshold(value_high, conversion_factor),
    )


def _convert_threshold(value: float | None, conversion_factor: float) -> float | None:
    if value is None:
        return None
    return value * conversion_factor


def _unit_support(
    *,
    source_criterion_id: str,
    source_unit: str | None,
    canonical_unit: str,
    conventional_unit: str,
    conversion_factor: float,
    resolver_policy: ResolverExecutionPolicy,
) -> ResolutionSupport:
    return _support(
        support_id=f"{source_criterion_id}:unit:normalization",
        stage="unit_normalization",
        domain="unit",
        source_criterion_id=source_criterion_id,
        surface=source_unit,
        normalized_surface=canonical_unit,
        target_system="unit_registry",
        target_id=conventional_unit,
        target_label=f"conversion_factor={conversion_factor:g}",
        resolver_policy=resolver_policy,
    )


def _unsupported_conversion_gap(
    *,
    source_criterion_id: str,
    surface: str,
    source_unit: str,
    canonical_unit: str | None,
    conventional_unit: str | None,
    resolver_policy: ResolverExecutionPolicy,
) -> ResolutionGap:
    return _gap(
        gap_id=f"{source_criterion_id}:unit:gap:unsupported_conversion",
        stage="unit_normalization",
        domain="unit",
        kind="unsupported_predicate",
        source_criterion_id=source_criterion_id,
        surface=source_unit,
        message=(
            f"Cannot convert unit '{source_unit}' for measurement '{surface}' "
            f"(canonical={canonical_unit or 'unknown'}, "
            f"conventional={conventional_unit or 'unknown'})."
        ),
        resolver_policy=resolver_policy,
    )


def _unsupported_conversion_diagnostic(
    *,
    gap: ResolutionGap,
    source_criterion_id: str,
    source_unit: str,
    canonical_unit: str | None,
    conventional_unit: str | None,
) -> CompilerDiagnostic:
    return _diagnostic(
        severity="warning",
        code="unit.unsupported_conversion",
        message=gap.message,
        source_criterion_id=source_criterion_id,
        facts=[
            ("gap_id", gap.gap_id),
            ("source_unit", source_unit),
            ("canonical_unit", canonical_unit or ""),
            ("conventional_unit", conventional_unit or ""),
        ],
    )


def _support(
    *,
    support_id: str,
    stage: ResolutionStage,
    domain: ResolutionDomain,
    source_criterion_id: str,
    surface: str | None,
    normalized_surface: str | None,
    target_system: str | None,
    target_id: str | None,
    target_label: str | None,
    resolver_policy: ResolverExecutionPolicy,
) -> ResolutionSupport:
    return ResolutionSupport(
        support_id=support_id,
        stage=stage,
        domain=domain,
        source_criterion_id=source_criterion_id,
        surface=surface,
        normalized_surface=normalized_surface,
        target_system=target_system,
        target_id=target_id,
        target_label=target_label,
        resolver_policy=resolver_policy,
    )


def _gap(
    *,
    gap_id: str,
    stage: ResolutionStage,
    domain: ResolutionDomain,
    kind: ResolutionGapKind,
    source_criterion_id: str,
    surface: str | None,
    message: str,
    resolver_policy: ResolverExecutionPolicy,
) -> ResolutionGap:
    return ResolutionGap(
        gap_id=gap_id,
        stage=stage,
        domain=domain,
        kind=kind,
        source_criterion_id=source_criterion_id,
        surface=surface,
        message=message,
        resolver_policy=resolver_policy,
    )


def _diagnostic(
    *,
    severity: DiagnosticSeverity,
    code: str,
    message: str,
    source_criterion_id: str,
    facts: list[tuple[str, str]],
) -> CompilerDiagnostic:
    return CompilerDiagnostic(
        severity=severity,
        code=code,
        message=message,
        stage="unit_normalization",
        source_criterion_id=source_criterion_id,
        facts=[DiagnosticFact(key=key, value=value) for key, value in facts],
    )


def _normalize_surface(surface: str) -> str:
    return " ".join(surface.lower().strip(".,;:()[]{}\"'").split())


__all__ = [
    "MeasurementResolutionResult",
    "compile_measurement_resolution",
]
