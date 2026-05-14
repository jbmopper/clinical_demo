"""Measurement-resolution helpers for the criterion compiler.

This module is intentionally offline-only. It resolves measurement
surfaces through the existing local matcher alias table and normalizes
threshold units through the committed unit registry. Live terminology
lookup belongs in resolver/warmer paths, not in compiler unit tests or
cached-only eval runs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from pydantic import BaseModel, Field

from clinical_demo.extractor.schema import ExtractedCriterion, ThresholdOperator
from clinical_demo.matcher.concept_lookup import lookup_lab_alias
from clinical_demo.profile import ConceptSet
from clinical_demo.profile.concept_sets import concept_set_by_id
from clinical_demo.settings import ResolverExecutionPolicy
from clinical_demo.terminology.reviewed_registry import (
    ReviewedMappingEntry,
    ReviewedMappingRegistry,
    load_reviewed_mapping_registry,
)
from clinical_demo.units import (
    DEFAULT_REGISTRY,
    MeasurementUnitRegistry,
    ReferenceLimitKind,
    ReviewedReferenceLimitEntry,
    ReviewedReferenceLimitRegistry,
    get_reviewed_reference_limit_registry,
)

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
_GLUCOSE_LOINC_CODE = "2339-0"
_PARENTHETICAL_RE = re.compile(r"\(([^()]*)\)")
_UPPER_REFERENCE_RE = re.compile(r"\b(?:u\.?\s*l\.?\s*n|upper\s+limit\s+of\s+normal)\b", re.I)
_LOWER_REFERENCE_RE = re.compile(r"\b(?:l\.?\s*l\.?\s*n|lower\s+limit\s+of\s+normal)\b", re.I)
_NORMAL_RANGE_RE = re.compile(r"\b(?:normal\s+ranges?|normal\s+limits?)\b", re.I)
_SEX_SPECIFIC_REFERENCE_RE = re.compile(r"\b(?:sex|gender)[-\s]*specific\b", re.I)
_REFERENCE_MULTIPLIER_RE = re.compile(
    r"(?P<value>\d+(?:\.\d+)?)\s*(?:x|\u00d7|\*)?\s*"
    r"(?:u\.?\s*l\.?\s*n|upper\s+limit\s+of\s+normal|"
    r"l\.?\s*l\.?\s*n|lower\s+limit\s+of\s+normal)",
    re.I,
)
_REFERENCE_DIRECTION_OPERATOR_RE = re.compile(
    r"\b(?P<word>above|greater\s+than|more\s+than|exceeds?|below|less\s+than|under)\b",
    re.I,
)
_PROVENANCE_GLUCOSE_THRESHOLD_RE = re.compile(
    r"(?P<surface>"
    r"fasting\s+plasma\s+glucose|"
    r"(?:2|two)[-\s]*hour\s+plasma\s+glucose|"
    r"random\s+plasma\s+glucose"
    r")"
    r".{0,120}?"
    r"(?P<op>>=|<=|\u2265|\u2264|>|<|=)\s*"
    r"(?P<value>\d+(?:\.\d+)?)\s*"
    r"(?P<unit>mg\s*/\s*dL|mmol\s*/\s*L)?",
    re.I,
)
_PROVENANCE_GLUCOSE_SURFACE_RE = re.compile(
    r"\b("
    r"fasting\s+plasma\s+glucose|"
    r"(?:2|two)[-\s]*hour\s+plasma\s+glucose|"
    r"random\s+plasma\s+glucose"
    r")\b",
    re.I,
)


@dataclass(frozen=True)
class _ReferenceLimitRequest:
    limit_kind: ReferenceLimitKind
    operator: ThresholdOperator
    multiplier: float
    sex_specific: bool


@dataclass(frozen=True)
class _ConvertedReferenceLimit:
    canonical_unit: str
    conventional_unit: str
    conversion_factor: float
    normalized_value: float


@dataclass(frozen=True)
class _SourceThreshold:
    surface: str
    operator: ThresholdOperator
    value: float
    unit: str | None
    provenance_kind: str
    source_excerpt: str


@dataclass(frozen=True)
class _EffectiveMeasurement:
    surface: str
    operator: ThresholdOperator
    value: float | None
    value_low: float | None
    value_high: float | None
    unit: str | None
    provenance_kind: str | None
    source_threshold: _SourceThreshold | None


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
    normalized_value_by_sex: dict[str, float] = Field(
        default_factory=dict,
        description="Sex-specific thresholds converted into the conventional unit, if available.",
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
    reviewed_registry: ReviewedMappingRegistry | None = None,
    reference_limit_registry: ReviewedReferenceLimitRegistry | None = None,
) -> MeasurementResolutionResult:
    """Resolve a measurement threshold surface and normalize its threshold unit.

    The helper never calls live terminology services. Unknown measurement
    surfaces and unsupported unit conversions are represented as typed
    compiler gaps so the integration layer can decide whether to keep,
    review, or fail closed.
    """

    registry = unit_registry or DEFAULT_REGISTRY
    mappings = reviewed_registry or load_reviewed_mapping_registry()
    reference_limits = reference_limit_registry or get_reviewed_reference_limit_registry()
    measurement = criterion.measurement
    if criterion.kind != "measurement_threshold" or measurement is None:
        return _skipped_result(
            source_criterion_id=source_criterion_id,
            measurement_surface=None,
            source_unit=None,
            resolver_policy=resolver_policy,
        )

    effective = _effective_measurement(criterion)
    surface = effective.surface
    source_unit = effective.unit
    supports: list[ResolutionSupport] = []
    gaps: list[ResolutionGap] = []
    diagnostics: list[CompilerDiagnostic] = []

    reviewed_entry = mappings.lookup("lab", surface)
    if reviewed_entry is not None:
        if reviewed_entry.status != "mapped":
            provenance_result = _provenance_sensitive_glucose_result(
                source_criterion_id=source_criterion_id,
                effective=effective,
                entry=reviewed_entry,
                unit_registry=registry,
                resolver_policy=resolver_policy,
            )
            if provenance_result is not None:
                return provenance_result
            return _reviewed_nonmapped_result(
                source_criterion_id=source_criterion_id,
                surface=surface,
                source_unit=source_unit,
                entry=reviewed_entry,
                resolver_policy=resolver_policy,
            )
        concept_set = concept_set_by_id(reviewed_entry.concept_set)
    else:
        provenance_result = _provenance_sensitive_glucose_result(
            source_criterion_id=source_criterion_id,
            effective=effective,
            entry=None,
            unit_registry=registry,
            resolver_policy=resolver_policy,
        )
        if provenance_result is not None:
            return provenance_result
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

    reference_limit_result = _reference_limit_result(
        criterion=criterion,
        source_criterion_id=source_criterion_id,
        surface=surface,
        source_unit=source_unit,
        selected_loinc_code=selected_loinc_code,
        loinc_codes=loinc_codes,
        concept_set=concept_set,
        supports=supports,
        gaps=gaps,
        diagnostics=diagnostics,
        unit_registry=registry,
        reference_limit_registry=reference_limits,
        resolver_policy=resolver_policy,
    )
    if reference_limit_result is not None:
        return reference_limit_result

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
        value=effective.value,
        value_low=effective.value_low,
        value_high=effective.value_high,
        conversion_factor=conversion_factor,
    )
    value_gaps = _threshold_value_gaps(
        source_criterion_id=source_criterion_id,
        surface=surface,
        operator=effective.operator,
        value=effective.value,
        value_low=effective.value_low,
        value_high=effective.value_high,
        resolver_policy=resolver_policy,
    )
    for gap in value_gaps:
        gaps.append(gap)
        diagnostics.append(
            _diagnostic(
                severity="warning",
                code="measurement.threshold_value_missing",
                message=gap.message,
                source_criterion_id=source_criterion_id,
                facts=[("gap_id", gap.gap_id)],
            )
        )

    return MeasurementResolutionResult(
        source_criterion_id=source_criterion_id,
        measurement_surface=surface,
        concept_set=concept_set,
        loinc_codes=loinc_codes,
        selected_loinc_code=selected_loinc_code,
        unit_normalization=plan,
        normalized_operator=effective.operator,
        normalized_value=normalized_values[0],
        normalized_value_low=normalized_values[1],
        normalized_value_high=normalized_values[2],
        resolved_supports=supports,
        unresolved_gaps=gaps,
        diagnostics=diagnostics,
    )


def _reference_limit_result(
    *,
    criterion: ExtractedCriterion,
    source_criterion_id: str,
    surface: str,
    source_unit: str | None,
    selected_loinc_code: str | None,
    loinc_codes: list[str],
    concept_set: ConceptSet | None,
    supports: list[ResolutionSupport],
    gaps: list[ResolutionGap],
    diagnostics: list[CompilerDiagnostic],
    unit_registry: MeasurementUnitRegistry,
    reference_limit_registry: ReviewedReferenceLimitRegistry,
    resolver_policy: ResolverExecutionPolicy,
) -> MeasurementResolutionResult | None:
    request = _reference_limit_request(criterion)
    if request is None:
        return None

    local_gaps = list(gaps)
    local_diagnostics = list(diagnostics)
    local_supports = list(supports)

    if selected_loinc_code is None:
        gap = _reference_limit_gap(
            source_criterion_id=source_criterion_id,
            surface=surface,
            source_unit=source_unit,
            kind="ambiguous_mapping" if loinc_codes else "unmapped_concept",
            message=(
                f"Cannot translate reference-limit threshold for measurement '{surface}' "
                "because it did not resolve to exactly one LOINC code."
            ),
            resolver_policy=resolver_policy,
        )
        local_gaps.append(gap)
        local_diagnostics.append(
            _diagnostic(
                severity="warning",
                code="measurement.reference_limit.unresolved_loinc",
                message=gap.message,
                source_criterion_id=source_criterion_id,
                facts=[("gap_id", gap.gap_id)],
            )
        )
        return _reference_limit_unresolved_result(
            source_criterion_id=source_criterion_id,
            surface=surface,
            source_unit=source_unit,
            concept_set=concept_set,
            loinc_codes=loinc_codes,
            selected_loinc_code=selected_loinc_code,
            supports=local_supports,
            gaps=local_gaps,
            diagnostics=local_diagnostics,
            status="unresolved",
        )

    if request.sex_specific:
        sex_limits = reference_limit_registry.lookup_sex_specific(
            selected_loinc_code,
            request.limit_kind,
        )
        if set(sex_limits) == {"FEMALE", "MALE"}:
            converted_by_sex: dict[str, _ConvertedReferenceLimit] = {}
            for sex, sex_limit in sex_limits.items():
                converted = _converted_reference_limit(
                    source_criterion_id=source_criterion_id,
                    surface=surface,
                    limit=sex_limit,
                    multiplier=request.multiplier,
                    unit_registry=unit_registry,
                    resolver_policy=resolver_policy,
                    gaps=local_gaps,
                    diagnostics=local_diagnostics,
                )
                if converted is None:
                    return _reference_limit_unresolved_result(
                        source_criterion_id=source_criterion_id,
                        surface=surface,
                        source_unit=source_unit,
                        concept_set=concept_set,
                        loinc_codes=loinc_codes,
                        selected_loinc_code=selected_loinc_code,
                        supports=local_supports,
                        gaps=local_gaps,
                        diagnostics=local_diagnostics,
                        status="unsupported",
                    )
                converted_by_sex[sex] = converted
                local_supports.append(
                    _reference_limit_support(
                        source_criterion_id=f"{source_criterion_id}:{sex.lower()}",
                        source_unit=source_unit,
                        loinc_code=selected_loinc_code,
                        limit=sex_limit,
                        multiplier=request.multiplier,
                        normalized_value=converted.normalized_value,
                        conventional_unit=converted.conventional_unit,
                        resolver_policy=resolver_policy,
                    )
                )
            first = converted_by_sex["MALE"]
            local_diagnostics.append(
                _diagnostic(
                    severity="info",
                    code="measurement.reference_limit.sex_specific_translated",
                    message=(
                        f"Translated sex-specific {request.limit_kind} reference limits "
                        f"for measurement '{surface}' into patient-sex-aware thresholds."
                    ),
                    source_criterion_id=source_criterion_id,
                    facts=[
                        ("loinc_code", selected_loinc_code),
                        ("male_value", f"{converted_by_sex['MALE'].normalized_value:g}"),
                        ("female_value", f"{converted_by_sex['FEMALE'].normalized_value:g}"),
                        ("unit", first.conventional_unit),
                    ],
                )
            )
            return MeasurementResolutionResult(
                source_criterion_id=source_criterion_id,
                measurement_surface=surface,
                concept_set=concept_set,
                loinc_codes=loinc_codes,
                selected_loinc_code=selected_loinc_code,
                unit_normalization=UnitNormalizationPlan(
                    status="resolved",
                    measurement_surface=surface,
                    source_unit=source_unit,
                    canonical_unit=first.canonical_unit,
                    conventional_unit=first.conventional_unit,
                    conversion_factor=first.conversion_factor,
                    gap_ids=[],
                ),
                normalized_operator=request.operator,
                normalized_value=None,
                normalized_value_by_sex={
                    sex: converted.normalized_value for sex, converted in converted_by_sex.items()
                },
                normalized_value_low=None,
                normalized_value_high=None,
                resolved_supports=local_supports,
                unresolved_gaps=local_gaps,
                diagnostics=local_diagnostics,
            )

        gap = _reference_limit_gap(
            source_criterion_id=source_criterion_id,
            surface=surface,
            source_unit=source_unit,
            kind="unsupported_predicate",
            message=(
                f"Measurement '{surface}' uses a sex-specific reference limit, but reviewed "
                "male and female reference limits are not both registered."
            ),
            resolver_policy=resolver_policy,
        )
        local_gaps.append(gap)
        local_diagnostics.append(
            _diagnostic(
                severity="warning",
                code="measurement.reference_limit.sex_specific_unsupported",
                message=gap.message,
                source_criterion_id=source_criterion_id,
                facts=[("gap_id", gap.gap_id), ("loinc_code", selected_loinc_code)],
            )
        )
        return _reference_limit_unresolved_result(
            source_criterion_id=source_criterion_id,
            surface=surface,
            source_unit=source_unit,
            concept_set=concept_set,
            loinc_codes=loinc_codes,
            selected_loinc_code=selected_loinc_code,
            supports=local_supports,
            gaps=local_gaps,
            diagnostics=local_diagnostics,
            status="unsupported",
        )

    single_limit = reference_limit_registry.lookup(selected_loinc_code, request.limit_kind)
    if single_limit is None:
        gap = _reference_limit_gap(
            source_criterion_id=source_criterion_id,
            surface=surface,
            source_unit=source_unit,
            kind="unsupported_predicate",
            message=(
                f"No reviewed {request.limit_kind} reference limit is registered for "
                f"measurement '{surface}' ({selected_loinc_code})."
            ),
            resolver_policy=resolver_policy,
        )
        local_gaps.append(gap)
        local_diagnostics.append(
            _diagnostic(
                severity="warning",
                code="measurement.reference_limit.missing_reviewed_limit",
                message=gap.message,
                source_criterion_id=source_criterion_id,
                facts=[("gap_id", gap.gap_id), ("loinc_code", selected_loinc_code)],
            )
        )
        return _reference_limit_unresolved_result(
            source_criterion_id=source_criterion_id,
            surface=surface,
            source_unit=source_unit,
            concept_set=concept_set,
            loinc_codes=loinc_codes,
            selected_loinc_code=selected_loinc_code,
            supports=local_supports,
            gaps=local_gaps,
            diagnostics=local_diagnostics,
            status="unsupported",
        )

    canonical_unit = unit_registry.canonical_unit(selected_loinc_code, single_limit.unit)
    conventional_unit = unit_registry.conventional_unit(selected_loinc_code)
    conversion_factor = unit_registry.conversion_factor(
        selected_loinc_code,
        canonical_unit,
        conventional_unit,
    )
    if canonical_unit is None or conventional_unit is None or conversion_factor is None:
        gap = _unsupported_conversion_gap(
            source_criterion_id=source_criterion_id,
            surface=surface,
            source_unit=single_limit.unit,
            canonical_unit=canonical_unit,
            conventional_unit=conventional_unit,
            resolver_policy=resolver_policy,
        )
        local_gaps.append(gap)
        local_diagnostics.append(
            _unsupported_conversion_diagnostic(
                gap=gap,
                source_criterion_id=source_criterion_id,
                source_unit=single_limit.unit,
                canonical_unit=canonical_unit,
                conventional_unit=conventional_unit,
            )
        )
        return _reference_limit_unresolved_result(
            source_criterion_id=source_criterion_id,
            surface=surface,
            source_unit=source_unit,
            concept_set=concept_set,
            loinc_codes=loinc_codes,
            selected_loinc_code=selected_loinc_code,
            supports=local_supports,
            gaps=local_gaps,
            diagnostics=local_diagnostics,
            status="unsupported",
        )

    normalized_value = single_limit.value * request.multiplier * conversion_factor
    local_supports.append(
        _reference_limit_support(
            source_criterion_id=source_criterion_id,
            source_unit=source_unit,
            loinc_code=selected_loinc_code,
            limit=single_limit,
            multiplier=request.multiplier,
            normalized_value=normalized_value,
            conventional_unit=conventional_unit,
            resolver_policy=resolver_policy,
        )
    )
    local_diagnostics.append(
        _diagnostic(
            severity="info",
            code="measurement.reference_limit.translated",
            message=(
                f"Translated {request.multiplier:g} x {request.limit_kind} reference limit "
                f"for measurement '{surface}' into {normalized_value:g} {conventional_unit}."
            ),
            source_criterion_id=source_criterion_id,
            facts=[
                ("loinc_code", selected_loinc_code),
                ("limit_kind", request.limit_kind),
                ("reference_value", f"{single_limit.value:g}"),
                ("reference_unit", single_limit.unit),
                ("multiplier", f"{request.multiplier:g}"),
            ],
        )
    )

    return MeasurementResolutionResult(
        source_criterion_id=source_criterion_id,
        measurement_surface=surface,
        concept_set=concept_set,
        loinc_codes=loinc_codes,
        selected_loinc_code=selected_loinc_code,
        unit_normalization=UnitNormalizationPlan(
            status="resolved",
            measurement_surface=surface,
            source_unit=source_unit,
            canonical_unit=canonical_unit,
            conventional_unit=conventional_unit,
            conversion_factor=conversion_factor,
            gap_ids=[],
        ),
        normalized_operator=request.operator,
        normalized_value=normalized_value,
        normalized_value_low=None,
        normalized_value_high=None,
        resolved_supports=local_supports,
        unresolved_gaps=local_gaps,
        diagnostics=local_diagnostics,
    )


def _converted_reference_limit(
    *,
    source_criterion_id: str,
    surface: str,
    limit: ReviewedReferenceLimitEntry,
    multiplier: float,
    unit_registry: MeasurementUnitRegistry,
    resolver_policy: ResolverExecutionPolicy,
    gaps: list[ResolutionGap],
    diagnostics: list[CompilerDiagnostic],
) -> _ConvertedReferenceLimit | None:
    canonical_unit = unit_registry.canonical_unit(limit.loinc_code, limit.unit)
    conventional_unit = unit_registry.conventional_unit(limit.loinc_code)
    conversion_factor = unit_registry.conversion_factor(
        limit.loinc_code,
        canonical_unit,
        conventional_unit,
    )
    if canonical_unit is None or conventional_unit is None or conversion_factor is None:
        gap = _unsupported_conversion_gap(
            source_criterion_id=source_criterion_id,
            surface=surface,
            source_unit=limit.unit,
            canonical_unit=canonical_unit,
            conventional_unit=conventional_unit,
            resolver_policy=resolver_policy,
        )
        gaps.append(gap)
        diagnostics.append(
            _unsupported_conversion_diagnostic(
                gap=gap,
                source_criterion_id=source_criterion_id,
                source_unit=limit.unit,
                canonical_unit=canonical_unit,
                conventional_unit=conventional_unit,
            )
        )
        return None
    return _ConvertedReferenceLimit(
        canonical_unit=canonical_unit,
        conventional_unit=conventional_unit,
        conversion_factor=conversion_factor,
        normalized_value=limit.value * multiplier * conversion_factor,
    )


def _effective_measurement(criterion: ExtractedCriterion) -> _EffectiveMeasurement:
    measurement = criterion.measurement
    if measurement is None:
        raise ValueError("_effective_measurement requires a measurement criterion")

    source_threshold = _source_text_provenance_glucose_threshold(
        criterion.source_text,
        measurement.measurement_text,
    )
    surface = measurement.measurement_text
    provenance_kind = _provenance_glucose_kind(surface)
    if source_threshold is not None:
        surface = source_threshold.surface
        provenance_kind = source_threshold.provenance_kind

    value = (
        measurement.value if measurement.value is not None else _threshold_value(source_threshold)
    )
    unit = measurement.unit or (source_threshold.unit if source_threshold is not None else None)

    return _EffectiveMeasurement(
        surface=surface,
        operator=(
            source_threshold.operator
            if source_threshold is not None and measurement.value is None
            else measurement.operator
        ),
        value=value,
        value_low=measurement.value_low,
        value_high=measurement.value_high,
        unit=unit,
        provenance_kind=provenance_kind,
        source_threshold=source_threshold,
    )


def _threshold_value(source_threshold: _SourceThreshold | None) -> float | None:
    if source_threshold is None:
        return None
    return source_threshold.value


def _source_text_provenance_glucose_threshold(
    *texts: str | None,
) -> _SourceThreshold | None:
    for text in texts:
        if text is None or not text.strip():
            continue
        match = _PROVENANCE_GLUCOSE_THRESHOLD_RE.search(text)
        if match is None:
            continue
        surface = _normalized_provenance_glucose_surface(match.group("surface"))
        return _SourceThreshold(
            surface=surface,
            operator=_normalized_threshold_operator(match.group("op")),
            value=float(match.group("value")),
            unit=_compact_unit(match.group("unit")),
            provenance_kind=_provenance_glucose_kind(surface) or "glucose_provenance",
            source_excerpt=match.group(0).strip(),
        )
    return None


def _normalized_provenance_glucose_surface(surface: str) -> str:
    if re.search(r"\bfasting\s+plasma\s+glucose\b", surface, re.I):
        return "fasting plasma glucose"
    if re.search(r"\b(?:2|two)[-\s]*hour\s+plasma\s+glucose\b", surface, re.I):
        return "2-hour plasma glucose"
    return "random plasma glucose"


def _provenance_glucose_kind(surface: str) -> str | None:
    match = _PROVENANCE_GLUCOSE_SURFACE_RE.search(surface)
    if match is None:
        return None
    normalized_surface = _normalized_provenance_glucose_surface(match.group(1))
    if normalized_surface == "fasting plasma glucose":
        return "fasting_state_required"
    if normalized_surface == "2-hour plasma glucose":
        return "ogtt_timing_required"
    return "random_glucose_context_required"


def _normalized_threshold_operator(operator: str) -> ThresholdOperator:
    if operator == "\u2265":
        return ">="
    if operator == "\u2264":
        return "<="
    return operator  # type: ignore[return-value]


def _compact_unit(unit: str | None) -> str | None:
    if unit is None:
        return None
    return re.sub(r"\s*/\s*", "/", unit.strip())


def _reference_limit_request(criterion: ExtractedCriterion) -> _ReferenceLimitRequest | None:
    measurement = criterion.measurement
    if measurement is None:
        return None
    reference_text = " ".join(
        part for part in (criterion.source_text, measurement.unit) if part is not None
    )
    if not reference_text.strip():
        return None
    has_upper = _UPPER_REFERENCE_RE.search(reference_text) is not None
    has_lower = _LOWER_REFERENCE_RE.search(reference_text) is not None
    if not has_upper and not has_lower and _NORMAL_RANGE_RE.search(reference_text) is None:
        return None
    if not has_upper and not has_lower:
        return None

    operator = _reference_limit_operator(measurement.operator, reference_text)
    if operator is None:
        return None

    return _ReferenceLimitRequest(
        limit_kind="upper" if has_upper else "lower",
        operator=operator,
        multiplier=_reference_limit_multiplier(measurement.value, reference_text),
        sex_specific=_SEX_SPECIFIC_REFERENCE_RE.search(reference_text) is not None,
    )


def _reference_limit_operator(
    operator: ThresholdOperator,
    reference_text: str,
) -> ThresholdOperator | None:
    if operator in {"<", "<=", "=", ">=", ">"}:
        return operator
    match = _REFERENCE_DIRECTION_OPERATOR_RE.search(reference_text)
    if match is None:
        return None
    direction = " ".join(match.group("word").lower().split())
    if direction in {"above", "greater than", "more than", "exceed", "exceeds"}:
        return ">"
    return "<"


def _reference_limit_multiplier(value: float | None, reference_text: str) -> float:
    if value is not None:
        return value
    match = _REFERENCE_MULTIPLIER_RE.search(reference_text)
    if match is not None:
        return float(match.group("value"))
    return 1.0


def _reference_limit_unresolved_result(
    *,
    source_criterion_id: str,
    surface: str,
    source_unit: str | None,
    concept_set: ConceptSet | None,
    loinc_codes: list[str],
    selected_loinc_code: str | None,
    supports: list[ResolutionSupport],
    gaps: list[ResolutionGap],
    diagnostics: list[CompilerDiagnostic],
    status: ResolutionStatus,
) -> MeasurementResolutionResult:
    return MeasurementResolutionResult(
        source_criterion_id=source_criterion_id,
        measurement_surface=surface,
        concept_set=concept_set,
        loinc_codes=loinc_codes,
        selected_loinc_code=selected_loinc_code,
        unit_normalization=UnitNormalizationPlan(
            status=status,
            measurement_surface=surface,
            source_unit=source_unit,
            canonical_unit=None,
            conventional_unit=None,
            conversion_factor=None,
            gap_ids=[gap.gap_id for gap in gaps],
        ),
        normalized_operator=None,
        normalized_value=None,
        normalized_value_low=None,
        normalized_value_high=None,
        resolved_supports=supports,
        unresolved_gaps=gaps,
        diagnostics=diagnostics,
    )


def _reference_limit_gap(
    *,
    source_criterion_id: str,
    surface: str,
    source_unit: str | None,
    kind: ResolutionGapKind,
    message: str,
    resolver_policy: ResolverExecutionPolicy,
) -> ResolutionGap:
    return _gap(
        gap_id=f"{source_criterion_id}:reference-limit:gap",
        stage="unit_normalization",
        domain="measurement",
        kind=kind,
        source_criterion_id=source_criterion_id,
        surface=source_unit or surface,
        message=message,
        resolver_policy=resolver_policy,
    )


def _reference_limit_support(
    *,
    source_criterion_id: str,
    source_unit: str | None,
    loinc_code: str,
    limit: ReviewedReferenceLimitEntry,
    multiplier: float,
    normalized_value: float,
    conventional_unit: str,
    resolver_policy: ResolverExecutionPolicy,
) -> ResolutionSupport:
    return _support(
        support_id=f"{source_criterion_id}:reference-limit:{limit.limit_kind}",
        stage="unit_normalization",
        domain="unit",
        source_criterion_id=source_criterion_id,
        surface=source_unit,
        normalized_surface=f"{multiplier:g} x {limit.limit_kind} reference limit",
        target_system="reviewed_reference_limits",
        target_id=f"{loinc_code}:{limit.limit_kind}:{limit.applies_to}",
        target_label=f"{normalized_value:g} {conventional_unit}",
        resolver_policy=resolver_policy,
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


def _provenance_sensitive_glucose_result(
    *,
    source_criterion_id: str,
    effective: _EffectiveMeasurement,
    entry: ReviewedMappingEntry | None,
    unit_registry: MeasurementUnitRegistry,
    resolver_policy: ResolverExecutionPolicy,
) -> MeasurementResolutionResult | None:
    if (
        effective.provenance_kind is None
        or effective.value is None
        or effective.operator not in {"<", "<=", "=", ">=", ">"}
    ):
        return None

    source_unit = effective.unit
    canonical_unit: str | None = None
    conventional_unit = unit_registry.conventional_unit(_GLUCOSE_LOINC_CODE)
    conversion_factor: float | None = None
    normalized_value: float | None = None
    supports: list[ResolutionSupport] = []
    diagnostics: list[CompilerDiagnostic] = []

    if source_unit is not None:
        canonical_unit = unit_registry.canonical_unit(_GLUCOSE_LOINC_CODE, source_unit)
        conversion_factor = unit_registry.conversion_factor(
            _GLUCOSE_LOINC_CODE,
            canonical_unit,
            conventional_unit,
        )
        if (
            canonical_unit is not None
            and conventional_unit is not None
            and conversion_factor is not None
        ):
            normalized_value = effective.value * conversion_factor
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

    if effective.source_threshold is not None:
        supports.append(
            _support(
                support_id=f"{source_criterion_id}:measurement:source-threshold",
                stage="predicate_translation",
                domain="measurement",
                source_criterion_id=source_criterion_id,
                surface=effective.source_threshold.source_excerpt,
                normalized_surface=(
                    f"{effective.surface} {effective.operator} "
                    f"{effective.value:g} {source_unit or ''}".strip()
                ),
                target_system="source_text",
                target_id=effective.provenance_kind,
                target_label="provenance-sensitive glucose threshold",
                resolver_policy=resolver_policy,
            )
        )

    gap = _gap(
        gap_id=f"{source_criterion_id}:measurement:gap:glucose_provenance",
        stage="predicate_translation",
        domain="measurement",
        kind="unsupported_predicate",
        source_criterion_id=source_criterion_id,
        surface=effective.surface,
        message=(
            f"Measurement '{effective.surface}' has a numeric glucose threshold, but "
            f"{_glucose_provenance_requirement(effective.provenance_kind)} is not "
            "represented in the current patient profile; threshold details are preserved "
            "for review and not collapsed to ordinary glucose."
        ),
        resolver_policy=resolver_policy,
    )
    diagnostics.append(
        _diagnostic(
            severity="warning",
            code="measurement.provenance_sensitive_glucose.unsupported",
            message=gap.message,
            source_criterion_id=source_criterion_id,
            facts=[
                ("gap_id", gap.gap_id),
                ("provenance_kind", effective.provenance_kind),
                (
                    "reviewed_status",
                    entry.status if entry is not None else "local_provenance_guard",
                ),
            ],
        )
    )
    diagnostics.append(
        _diagnostic(
            severity="info",
            code="measurement.provenance_sensitive_glucose.threshold_extracted",
            message=(
                f"Preserved source glucose threshold {effective.operator} {effective.value:g} "
                f"{source_unit or ''} for measurement '{effective.surface}'."
            ),
            source_criterion_id=source_criterion_id,
            facts=[
                ("loinc_unit_basis", _GLUCOSE_LOINC_CODE),
                ("operator", effective.operator),
                ("value", f"{effective.value:g}"),
                ("source_unit", source_unit or ""),
                ("canonical_unit", canonical_unit or ""),
                ("conventional_unit", conventional_unit or ""),
                (
                    "normalized_value",
                    "" if normalized_value is None else f"{normalized_value:g}",
                ),
            ],
        )
    )

    return MeasurementResolutionResult(
        source_criterion_id=source_criterion_id,
        measurement_surface=effective.surface,
        concept_set=None,
        loinc_codes=[],
        selected_loinc_code=None,
        unit_normalization=UnitNormalizationPlan(
            status="unsupported",
            measurement_surface=effective.surface,
            source_unit=source_unit,
            canonical_unit=canonical_unit,
            conventional_unit=conventional_unit,
            conversion_factor=conversion_factor,
            gap_ids=[gap.gap_id],
        ),
        normalized_operator=effective.operator,
        normalized_value=normalized_value,
        normalized_value_low=None,
        normalized_value_high=None,
        resolved_supports=supports,
        unresolved_gaps=[gap],
        diagnostics=diagnostics,
    )


def _glucose_provenance_requirement(provenance_kind: str) -> str:
    if provenance_kind == "fasting_state_required":
        return "fasting-state provenance"
    if provenance_kind == "ogtt_timing_required":
        return "oral-glucose-tolerance-test timing provenance"
    if provenance_kind == "random_glucose_context_required":
        return "random-glucose symptom or hyperglycemic-crisis context"
    return "glucose provenance"


def _reviewed_nonmapped_result(
    *,
    source_criterion_id: str,
    surface: str,
    source_unit: str | None,
    entry: ReviewedMappingEntry,
    resolver_policy: ResolverExecutionPolicy,
) -> MeasurementResolutionResult:
    gap_kind = _reviewed_nonmapped_gap_kind(entry)
    gap = _gap(
        gap_id=f"{source_criterion_id}:measurement:gap:reviewed-{entry.status}",
        stage="concept_resolution",
        domain="measurement",
        kind=gap_kind,
        source_criterion_id=source_criterion_id,
        surface=surface,
        message=f"Reviewed lab surface classified as {entry.status}: {entry.reason}",
        resolver_policy=resolver_policy,
    )
    status: ResolutionStatus = (
        "unsupported" if gap_kind == "unsupported_predicate" else "unresolved"
    )
    return MeasurementResolutionResult(
        source_criterion_id=source_criterion_id,
        measurement_surface=surface,
        concept_set=None,
        loinc_codes=[],
        selected_loinc_code=None,
        unit_normalization=UnitNormalizationPlan(
            status=status,
            measurement_surface=surface,
            source_unit=source_unit,
            canonical_unit=None,
            conventional_unit=None,
            conversion_factor=None,
            gap_ids=[gap.gap_id],
        ),
        normalized_operator=None,
        normalized_value=None,
        normalized_value_low=None,
        normalized_value_high=None,
        resolved_supports=[],
        unresolved_gaps=[gap],
        diagnostics=[
            _diagnostic(
                severity="warning",
                code=f"measurement.reviewed.{entry.status}",
                message=gap.message,
                source_criterion_id=source_criterion_id,
                facts=[
                    ("gap_id", gap.gap_id),
                    ("status", entry.status),
                    ("reviewer", entry.reviewer),
                    ("provenance", entry.provenance),
                ],
            )
        ],
    )


def _reviewed_nonmapped_gap_kind(entry: ReviewedMappingEntry) -> ResolutionGapKind:
    if entry.status == "ambiguous":
        return "ambiguous_mapping"
    return "unsupported_predicate"


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


def _threshold_value_gaps(
    *,
    source_criterion_id: str,
    surface: str,
    operator: ThresholdOperator,
    value: float | None,
    value_low: float | None,
    value_high: float | None,
    resolver_policy: ResolverExecutionPolicy,
) -> list[ResolutionGap]:
    missing_single_value = operator in {"<", "<=", "=", ">=", ">"} and value is None
    missing_range_value = operator in {"in_range", "out_of_range"} and (
        value_low is None or value_high is None
    )
    if not missing_single_value and not missing_range_value:
        return []
    return [
        _gap(
            gap_id=f"{source_criterion_id}:measurement:gap:threshold_value",
            stage="predicate_translation",
            domain="measurement",
            kind="insufficient_source",
            source_criterion_id=source_criterion_id,
            surface=surface,
            message=(
                f"Measurement '{surface}' has operator {operator!r} but lacks the numeric "
                "threshold fields needed for an executable predicate."
            ),
            resolver_policy=resolver_policy,
        )
    ]


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
