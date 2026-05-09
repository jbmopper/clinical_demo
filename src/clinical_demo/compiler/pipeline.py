"""Criterion compiler pipeline.

This module gives downstream code a stable typed compilation boundary
without changing current matcher behavior. The result keeps the
extractor criteria as `matcher_inputs` while also producing typed
resolution supports, gaps, expansion plans, unit plans, and checkable
predicates for the new compiler path.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from clinical_demo.extractor.schema import (
    CompositeCriterionGroup,
    CriterionKind,
    ExtractedCriteria,
    ExtractedCriterion,
    ThresholdOperator,
)
from clinical_demo.matcher.concept_lookup import lookup_condition_alias
from clinical_demo.profile import ConceptSet
from clinical_demo.settings import get_settings
from clinical_demo.terminology.cache import TerminologyCache
from clinical_demo.terminology.candidates import (
    CandidateSource,
    CandidateSourceKind,
    TerminologyCandidate,
    bucket_for_score,
    gate_candidate_set,
    generate_query_variants,
)
from clinical_demo.terminology.expansion import expand_concept_set
from clinical_demo.terminology.resolver import TerminologyResolver
from clinical_demo.terminology.reviewed_registry import (
    ExpansionPolicy,
    ReviewedMappingRegistry,
    load_reviewed_mapping_registry,
)

from .compound_time import (
    TemporalWindowCompilation,
    compile_compound_logic,
    compile_temporal_window,
)
from .measurement import MeasurementResolutionResult, compile_measurement_resolution
from .medication import MedicationCompilationResult, compile_medication_resolution
from .schema import (
    COMPILER_VERSION,
    CheckablePredicate,
    CheckablePredicatePlan,
    CompiledCriterion,
    CompilerDiagnostic,
    CriterionCompilationResult,
    DiagnosticFact,
    DiagnosticSeverity,
    ExpansionPlan,
    PredicateKind,
    ResolutionDomain,
    ResolutionGap,
    ResolutionGapKind,
    ResolutionStage,
    ResolutionStatus,
    ResolutionSupport,
    ResolverExecutionPolicy,
    UnitNormalizationPlan,
)


@dataclass(frozen=True)
class _CompilerResolutionContext:
    resolver_policy: ResolverExecutionPolicy
    resolver: TerminologyResolver
    reviewed_registry: ReviewedMappingRegistry


def compile_extracted_criteria(
    extracted: ExtractedCriteria | Sequence[ExtractedCriterion],
    *,
    resolver_policy: ResolverExecutionPolicy = "cached_only",
    compiler_version: str = COMPILER_VERSION,
) -> CriterionCompilationResult:
    """Compile extractor output into the initial compiler IR.

    This first implementation is deliberately behavior-preserving: it
    assigns stable ids and typed plans, but `matcher_inputs` is exactly
    the input criterion list in the original order.
    """

    criteria, composite_groups = _coerce_extracted(extracted)
    groups_by_parent = _groups_by_parent(composite_groups)
    context = _resolution_context(resolver_policy)

    compiled = [
        _compile_criterion(
            criterion,
            index=index,
            resolver_policy=resolver_policy,
            composite_groups=groups_by_parent.get(index, []),
            context=context,
        )
        for index, criterion in enumerate(criteria)
    ]

    return CriterionCompilationResult(
        compiler_version=compiler_version,
        resolver_policy=resolver_policy,
        source_criteria_count=len(criteria),
        criteria=compiled,
        matcher_inputs=list(criteria),
        resolved_supports=[support for item in compiled for support in item.resolved_supports],
        unresolved_gaps=[gap for item in compiled for gap in item.unresolved_gaps],
        checkable_predicates=[
            predicate for item in compiled for predicate in item.checkable_predicates
        ],
        diagnostics=[diagnostic for item in compiled for diagnostic in item.diagnostics],
    )


def source_criterion_id(index: int) -> str:
    """Return the stable id for an extractor criterion index."""

    return f"criterion:{index}"


def compiled_criterion_id(index: int) -> str:
    """Return the stable id for a compiled criterion index."""

    return f"compiled:criterion:{index}"


def _coerce_extracted(
    extracted: ExtractedCriteria | Sequence[ExtractedCriterion],
) -> tuple[list[ExtractedCriterion], list[CompositeCriterionGroup]]:
    if isinstance(extracted, ExtractedCriteria):
        return list(extracted.criteria), list(extracted.composite_groups)
    return list(extracted), []


def _groups_by_parent(
    groups: Sequence[CompositeCriterionGroup],
) -> dict[int, list[CompositeCriterionGroup]]:
    grouped: dict[int, list[CompositeCriterionGroup]] = {}
    for group in groups:
        grouped.setdefault(group.parent_criterion_index, []).append(group)
    return grouped


def _compile_criterion(
    criterion: ExtractedCriterion,
    *,
    index: int,
    resolver_policy: ResolverExecutionPolicy,
    composite_groups: Sequence[CompositeCriterionGroup],
    context: _CompilerResolutionContext,
) -> CompiledCriterion:
    source_id = source_criterion_id(index)
    domain = _resolution_domain(criterion.kind)
    surface = _criterion_surface(criterion)
    supports: list[ResolutionSupport] = []
    gaps: list[ResolutionGap] = []
    predicates: list[CheckablePredicate] = []
    diagnostics: list[CompilerDiagnostic] = []

    compound = compile_compound_logic(
        composite_groups,
        source_criterion_id=source_id,
        resolver_policy=resolver_policy,
    )
    supports.extend(compound.supports)
    gaps.extend(compound.gaps)
    diagnostics.extend(compound.diagnostics)

    expansion = _default_expansion_plan(domain=domain, surface=surface)
    unit_normalization = _unit_normalization_plan(criterion)
    predicate = _default_predicate_plan(criterion, source_id)

    if criterion.kind in {"age", "sex"}:
        predicate, predicates, demographic_gaps, demographic_diagnostics = _compile_demographic(
            criterion,
            source_criterion_id=source_id,
            resolver_policy=resolver_policy,
        )
        gaps.extend(demographic_gaps)
        diagnostics.extend(demographic_diagnostics)
    elif criterion.kind in {"condition_present", "condition_absent"}:
        condition = _compile_condition_resolution(
            criterion,
            source_criterion_id=source_id,
            context=context,
        )
        expansion = condition.expansion
        predicate = condition.predicate
        predicates.extend(condition.predicates)
        supports.extend(condition.supports)
        gaps.extend(condition.gaps)
        diagnostics.extend(condition.diagnostics)
    elif criterion.kind == "measurement_threshold":
        measurement = compile_measurement_resolution(
            criterion,
            source_id,
            resolver_policy=resolver_policy,
        )
        unit_normalization = measurement.unit_normalization
        supports.extend(measurement.resolved_supports)
        gaps.extend(measurement.unresolved_gaps)
        diagnostics.extend(measurement.diagnostics)
        predicate, measurement_predicates = _measurement_predicate(
            criterion,
            source_criterion_id=source_id,
            measurement=measurement,
        )
        predicates.extend(measurement_predicates)
    elif criterion.kind == "temporal_window":
        temporal = compile_temporal_window(
            criterion,
            source_criterion_id=source_id,
            resolver_policy=resolver_policy,
            resolver=context.resolver,
        )
        supports.extend(temporal.supports)
        gaps.extend(temporal.gaps)
        diagnostics.extend(temporal.diagnostics)
        predicate, temporal_predicates = _temporal_predicate(
            criterion,
            source_criterion_id=source_id,
            temporal=temporal,
        )
        predicates.extend(temporal_predicates)
    elif criterion.kind in {"medication_present", "medication_absent"}:
        medication = compile_medication_resolution(
            criterion,
            source_criterion_id=source_id,
            resolver_policy=resolver_policy,
            resolver=context.resolver,
        )
        supports.extend(medication.resolved_supports)
        gaps.extend(medication.unresolved_gaps)
        diagnostics.extend(medication.diagnostics)
        predicate, medication_predicates = _medication_predicate(
            criterion,
            source_criterion_id=source_id,
            medication=medication,
        )
        predicates.extend(medication_predicates)

    return CompiledCriterion(
        compiled_id=compiled_criterion_id(index),
        source_criterion_id=source_id,
        source_index=index,
        criterion_kind=criterion.kind,
        source_text=criterion.source_text,
        resolver_policy=resolver_policy,
        matcher_input=criterion,
        resolved_supports=supports,
        unresolved_gaps=gaps,
        checkable_predicates=predicates,
        expansion=expansion,
        compound_logic=compound.plan,
        unit_normalization=unit_normalization,
        predicate=predicate,
        diagnostics=diagnostics,
    )


def _unit_normalization_plan(criterion: ExtractedCriterion) -> UnitNormalizationPlan:
    if criterion.kind != "measurement_threshold" or criterion.measurement is None:
        return UnitNormalizationPlan(
            status="skipped",
            measurement_surface=None,
            source_unit=None,
            canonical_unit=None,
            conventional_unit=None,
            conversion_factor=None,
            gap_ids=[],
        )

    return UnitNormalizationPlan(
        status="not_attempted",
        measurement_surface=criterion.measurement.measurement_text,
        source_unit=criterion.measurement.unit,
        canonical_unit=None,
        conventional_unit=None,
        conversion_factor=None,
        gap_ids=[],
    )


def _resolution_context(resolver_policy: ResolverExecutionPolicy) -> _CompilerResolutionContext:
    settings = get_settings()
    return _CompilerResolutionContext(
        resolver_policy=resolver_policy,
        resolver=TerminologyResolver(
            TerminologyCache(settings.terminology_cache_dir),
            execution_policy=resolver_policy,
        ),
        reviewed_registry=load_reviewed_mapping_registry(),
    )


def _default_expansion_plan(
    *,
    domain: ResolutionDomain,
    surface: str | None,
) -> ExpansionPlan:
    status: ResolutionStatus = (
        "skipped" if domain not in {"condition", "medication"} else "not_attempted"
    )
    return ExpansionPlan(
        status=status,
        domain=domain,
        source_surface=surface,
        strategy="none",
        support_ids=[],
        gap_ids=[],
    )


def _default_predicate_plan(
    criterion: ExtractedCriterion,
    source_criterion_id: str,
) -> CheckablePredicatePlan:
    return CheckablePredicatePlan(
        status="not_attempted",
        predicate_kind=_predicate_kind(criterion.kind),
        expression=None,
        input_refs=[source_criterion_id],
        support_ids=[],
        gap_ids=[],
    )


@dataclass(frozen=True)
class _ConditionCompilation:
    expansion: ExpansionPlan
    predicate: CheckablePredicatePlan
    predicates: list[CheckablePredicate]
    supports: list[ResolutionSupport]
    gaps: list[ResolutionGap]
    diagnostics: list[CompilerDiagnostic]


def _compile_condition_resolution(
    criterion: ExtractedCriterion,
    *,
    source_criterion_id: str,
    context: _CompilerResolutionContext,
) -> _ConditionCompilation:
    surface = criterion.condition.condition_text if criterion.condition is not None else None
    if surface is None:
        gap = _gap(
            gap_id=f"{source_criterion_id}:condition:gap:missing-source",
            stage="concept_resolution",
            domain="condition",
            kind="insufficient_source",
            source_criterion_id=source_criterion_id,
            surface=None,
            message="Condition compiler received a criterion without a condition payload.",
            resolver_policy=context.resolver_policy,
        )
        return _condition_output(
            criterion,
            source_criterion_id=source_criterion_id,
            surface=None,
            expansion=_default_expansion_plan(domain="condition", surface=None).model_copy(
                update={"status": "unresolved", "gap_ids": [gap.gap_id]}
            ),
            supports=[],
            gaps=[gap],
            diagnostics=[],
            concept_set=None,
            support_ids=[],
        )

    candidates, concept_sets = _condition_candidates(surface, context=context)
    decision = gate_candidate_set(candidates)
    if decision.verdict != "auto_map" or decision.selected is None:
        kind: ResolutionGapKind = (
            "unmapped_concept" if decision.verdict == "no_candidates" else "ambiguous_mapping"
        )
        gap = _gap(
            gap_id=f"{source_criterion_id}:condition:gap:{decision.verdict}",
            stage="concept_resolution",
            domain="condition",
            kind=kind,
            source_criterion_id=source_criterion_id,
            surface=surface,
            message=decision.reason,
            resolver_policy=context.resolver_policy,
        )
        diagnostic = _diagnostic(
            severity="warning",
            code=f"condition.{decision.verdict}",
            message=decision.reason,
            stage="concept_resolution",
            source_criterion_id=source_criterion_id,
            facts=[
                ("candidate_count", str(len(decision.ranked_candidates))),
                ("gap_id", gap.gap_id),
            ],
        )
        return _condition_output(
            criterion,
            source_criterion_id=source_criterion_id,
            surface=surface,
            expansion=_default_expansion_plan(domain="condition", surface=surface).model_copy(
                update={"status": "unresolved", "gap_ids": [gap.gap_id]}
            ),
            supports=[],
            gaps=[gap],
            diagnostics=[diagnostic],
            concept_set=None,
            support_ids=[],
        )

    concept_set = concept_sets[decision.selected.target_key]
    policy = _condition_expansion_policy(decision.selected, surface, context)
    concept_support = _support(
        support_id=f"{source_criterion_id}:condition:support:concept-set",
        stage="concept_resolution",
        domain="condition",
        source_criterion_id=source_criterion_id,
        surface=surface,
        normalized_surface=decision.selected.matched_variant,
        target_system=concept_set.system,
        target_id=_concept_set_target_id(concept_set),
        target_label=concept_set.name,
        resolver_policy=context.resolver_policy,
    )
    supports = [concept_support]
    gaps: list[ResolutionGap] = []
    diagnostics = [
        _diagnostic(
            severity="info",
            code="condition.mapped",
            message=(
                f"Mapped condition surface {surface!r} through "
                f"{decision.selected.source.kind} candidate {decision.selected.matched_variant!r}."
            ),
            stage="concept_resolution",
            source_criterion_id=source_criterion_id,
            facts=[
                ("matched_variant", decision.selected.matched_variant),
                ("candidate_source", decision.selected.source.kind),
            ],
        )
    ]

    expansion_result = expand_concept_set(concept_set, policy=policy)
    expanded_concept_set = expansion_result.expanded_concept_set
    expansion_support_ids = [concept_support.support_id]
    if expansion_result.status == "resolved" and expanded_concept_set is not None:
        expansion_support = _support(
            support_id=f"{source_criterion_id}:condition:support:expansion",
            stage="expansion",
            domain="condition",
            source_criterion_id=source_criterion_id,
            surface=surface,
            normalized_surface=decision.selected.matched_variant,
            target_system=expanded_concept_set.system,
            target_id=",".join(sorted(expanded_concept_set.codes)),
            target_label=expanded_concept_set.name,
            resolver_policy=context.resolver_policy,
        )
        supports.append(expansion_support)
        expansion_support_ids.append(expansion_support.support_id)
    else:
        gap = _gap(
            gap_id=f"{source_criterion_id}:condition:gap:expansion",
            stage="expansion",
            domain="condition",
            kind="unsupported_predicate"
            if expansion_result.status == "unsupported"
            else "insufficient_source",
            source_criterion_id=source_criterion_id,
            surface=surface,
            message=expansion_result.reason,
            resolver_policy=context.resolver_policy,
        )
        gaps.append(gap)
        diagnostics.append(
            _diagnostic(
                severity="warning",
                code=f"condition.expansion.{expansion_result.status}",
                message=expansion_result.reason,
                stage="expansion",
                source_criterion_id=source_criterion_id,
                facts=[("gap_id", gap.gap_id), ("policy", policy)],
            )
        )

    expansion = ExpansionPlan(
        status=expansion_result.status,
        domain="condition",
        source_surface=surface,
        strategy=policy,
        support_ids=expansion_support_ids,
        gap_ids=[gap.gap_id for gap in gaps],
    )
    return _condition_output(
        criterion,
        source_criterion_id=source_criterion_id,
        surface=surface,
        expansion=expansion,
        supports=supports,
        gaps=gaps,
        diagnostics=diagnostics,
        concept_set=expanded_concept_set if expanded_concept_set is not None else concept_set,
        support_ids=expansion_support_ids,
    )


def _condition_candidates(
    surface: str,
    *,
    context: _CompilerResolutionContext,
) -> tuple[list[TerminologyCandidate], dict[tuple[str, str], ConceptSet]]:
    candidates: list[TerminologyCandidate] = []
    concept_sets: dict[tuple[str, str], ConceptSet] = {}

    for variant in generate_query_variants(surface):
        reviewed_entry = context.reviewed_registry.lookup("condition", variant.variant)
        concept_set = (
            context.resolver.resolve_condition(variant.variant)
            if context.resolver_policy != "disabled"
            else None
        )
        source_kind: CandidateSourceKind = (
            "reviewed_registry" if reviewed_entry is not None else "surface_cache"
        )
        if concept_set is None and reviewed_entry is None and context.resolver_policy != "disabled":
            concept_set = lookup_condition_alias(variant.variant)
            source_kind = "local_alias"
        if concept_set is None:
            continue

        score = _candidate_score(source_kind, len(variant.transforms))
        candidate = TerminologyCandidate(
            source=CandidateSource(kind=source_kind, name=source_kind),
            matched_surface=surface,
            matched_variant=variant.variant,
            code=_concept_set_target_id(concept_set),
            system=concept_set.system,
            name=concept_set.name,
            score=score,
            confidence_bucket=bucket_for_score(score),
        )
        candidates.append(candidate)
        concept_sets[candidate.target_key] = concept_set

    return candidates, concept_sets


def _candidate_score(source_kind: CandidateSourceKind, transform_count: int) -> float:
    base = {
        "reviewed_registry": 1.0,
        "surface_cache": 0.96,
        "local_alias": 0.93,
    }.get(source_kind, 0.70)
    return max(0.0, base - min(transform_count, 6) * 0.005)


def _condition_expansion_policy(
    candidate: TerminologyCandidate,
    original_surface: str,
    context: _CompilerResolutionContext,
) -> ExpansionPolicy:
    entry = context.reviewed_registry.lookup("condition", candidate.matched_variant)
    if entry is None:
        entry = context.reviewed_registry.lookup("condition", original_surface)
    return entry.expansion_policy if entry is not None else "exact_code"


def _condition_output(
    criterion: ExtractedCriterion,
    *,
    source_criterion_id: str,
    surface: str | None,
    expansion: ExpansionPlan,
    supports: list[ResolutionSupport],
    gaps: list[ResolutionGap],
    diagnostics: list[CompilerDiagnostic],
    concept_set: ConceptSet | None,
    support_ids: list[str],
) -> _ConditionCompilation:
    gap_ids = [gap.gap_id for gap in gaps]
    predicates: list[CheckablePredicate] = []
    predicate_ids: list[str] = []
    expression = None
    status: ResolutionStatus = "resolved" if concept_set is not None and not gaps else "unresolved"
    if concept_set is not None and not gaps:
        predicate = _checkable_predicate(
            predicate_id=f"{source_criterion_id}:predicate:condition",
            predicate_kind="condition_presence",
            source_criterion_id=source_criterion_id,
            criterion=criterion,
            surface=surface,
            target_system=concept_set.system,
            target_codes=concept_set.codes,
            negated=_criterion_is_absence(criterion),
            support_ids=support_ids,
            gap_ids=[],
        )
        predicates.append(predicate)
        predicate_ids.append(predicate.predicate_id)
        expression = _coded_expression(predicate)

    return _ConditionCompilation(
        expansion=expansion,
        predicate=CheckablePredicatePlan(
            status=status,
            predicate_kind="condition_presence",
            expression=expression,
            predicate_ids=predicate_ids,
            input_refs=[source_criterion_id],
            support_ids=support_ids,
            gap_ids=gap_ids,
        ),
        predicates=predicates,
        supports=supports,
        gaps=gaps,
        diagnostics=diagnostics,
    )


def _compile_demographic(
    criterion: ExtractedCriterion,
    *,
    source_criterion_id: str,
    resolver_policy: ResolverExecutionPolicy,
) -> tuple[
    CheckablePredicatePlan,
    list[CheckablePredicate],
    list[ResolutionGap],
    list[CompilerDiagnostic],
]:
    predicate_id = f"{source_criterion_id}:predicate:demographic"
    if criterion.age is not None:
        operator: ThresholdOperator | None = None
        value = None
        value_low = criterion.age.minimum_years
        value_high = criterion.age.maximum_years
        if value_low is not None and value_high is not None:
            operator = "in_range"
        elif value_low is not None:
            operator = ">="
            value = value_low
            value_low = None
        elif value_high is not None:
            operator = "<="
            value = value_high
            value_high = None
        else:
            return _unsupported_demographic(
                criterion,
                source_criterion_id=source_criterion_id,
                resolver_policy=resolver_policy,
                message="Age criterion has neither minimum nor maximum age.",
            )
        predicate = _checkable_predicate(
            predicate_id=predicate_id,
            predicate_kind="demographic",
            source_criterion_id=source_criterion_id,
            criterion=criterion,
            surface=criterion.source_text,
            target_system="demographic.age",
            target_codes=frozenset(),
            operator=operator,
            value=value,
            value_low=value_low,
            value_high=value_high,
            unit="years",
        )
        return _resolved_predicate_plan(predicate), [predicate], [], []

    if criterion.sex is not None:
        predicate = _checkable_predicate(
            predicate_id=predicate_id,
            predicate_kind="demographic",
            source_criterion_id=source_criterion_id,
            criterion=criterion,
            surface=criterion.source_text,
            target_system="demographic.sex",
            target_codes=frozenset({criterion.sex.sex}),
        )
        return _resolved_predicate_plan(predicate), [predicate], [], []

    return _unsupported_demographic(
        criterion,
        source_criterion_id=source_criterion_id,
        resolver_policy=resolver_policy,
        message="Demographic compiler received age/sex kind without a payload.",
    )


def _unsupported_demographic(
    criterion: ExtractedCriterion,
    *,
    source_criterion_id: str,
    resolver_policy: ResolverExecutionPolicy,
    message: str,
) -> tuple[
    CheckablePredicatePlan,
    list[CheckablePredicate],
    list[ResolutionGap],
    list[CompilerDiagnostic],
]:
    gap = _gap(
        gap_id=f"{source_criterion_id}:demographic:gap:insufficient-source",
        stage="predicate_translation",
        domain="demographic",
        kind="insufficient_source",
        source_criterion_id=source_criterion_id,
        surface=criterion.source_text,
        message=message,
        resolver_policy=resolver_policy,
    )
    return (
        CheckablePredicatePlan(
            status="unresolved",
            predicate_kind="demographic",
            expression=None,
            input_refs=[source_criterion_id],
            support_ids=[],
            gap_ids=[gap.gap_id],
        ),
        [],
        [gap],
        [],
    )


def _measurement_predicate(
    criterion: ExtractedCriterion,
    *,
    source_criterion_id: str,
    measurement: MeasurementResolutionResult,
) -> tuple[CheckablePredicatePlan, list[CheckablePredicate]]:
    support_ids = [support.support_id for support in measurement.resolved_supports]
    gap_ids = [gap.gap_id for gap in measurement.unresolved_gaps]
    if measurement.concept_set is None or measurement.unit_normalization.status != "resolved":
        return (
            CheckablePredicatePlan(
                status="unsupported"
                if any(gap.kind == "unsupported_predicate" for gap in measurement.unresolved_gaps)
                else "unresolved",
                predicate_kind="measurement_threshold",
                expression=None,
                input_refs=[source_criterion_id],
                support_ids=support_ids,
                gap_ids=gap_ids,
            ),
            [],
        )

    predicate = _checkable_predicate(
        predicate_id=f"{source_criterion_id}:predicate:measurement",
        predicate_kind="measurement_threshold",
        source_criterion_id=source_criterion_id,
        criterion=criterion,
        surface=measurement.measurement_surface,
        target_system=measurement.concept_set.system,
        target_codes=frozenset(measurement.loinc_codes),
        operator=measurement.normalized_operator,
        value=measurement.normalized_value,
        value_low=measurement.normalized_value_low,
        value_high=measurement.normalized_value_high,
        unit=measurement.unit_normalization.conventional_unit,
        support_ids=support_ids,
        gap_ids=[],
    )
    return _resolved_predicate_plan(predicate, support_ids=support_ids), [predicate]


def _temporal_predicate(
    criterion: ExtractedCriterion,
    *,
    source_criterion_id: str,
    temporal: TemporalWindowCompilation,
) -> tuple[CheckablePredicatePlan, list[CheckablePredicate]]:
    if temporal.predicate.status != "resolved" or temporal.event_concept_set is None:
        return temporal.predicate, []

    predicate = _checkable_predicate(
        predicate_id=f"{source_criterion_id}:predicate:temporal",
        predicate_kind="temporal_event",
        source_criterion_id=source_criterion_id,
        criterion=criterion,
        surface=temporal.event_surface,
        target_system=temporal.event_concept_set.system,
        target_codes=temporal.event_concept_set.codes,
        window_days=temporal.window_days,
        support_ids=temporal.predicate.support_ids,
        gap_ids=[],
    )
    return temporal.predicate.model_copy(update={"predicate_ids": [predicate.predicate_id]}), [
        predicate
    ]


def _medication_predicate(
    criterion: ExtractedCriterion,
    *,
    source_criterion_id: str,
    medication: MedicationCompilationResult,
) -> tuple[CheckablePredicatePlan, list[CheckablePredicate]]:
    if medication.predicate.status != "resolved" or medication.concept_set is None:
        return medication.predicate, []

    predicate = _checkable_predicate(
        predicate_id=f"{source_criterion_id}:predicate:medication",
        predicate_kind="medication_exposure",
        source_criterion_id=source_criterion_id,
        criterion=criterion,
        surface=medication.surface,
        target_system=medication.concept_set.system,
        target_codes=medication.concept_set.codes,
        negated=_criterion_is_absence(criterion),
        support_ids=medication.predicate.support_ids,
        gap_ids=[],
    )
    return medication.predicate.model_copy(update={"predicate_ids": [predicate.predicate_id]}), [
        predicate
    ]


def _resolved_predicate_plan(
    predicate: CheckablePredicate,
    *,
    support_ids: list[str] | None = None,
) -> CheckablePredicatePlan:
    return CheckablePredicatePlan(
        status="resolved",
        predicate_kind=predicate.predicate_kind,
        expression=_coded_expression(predicate),
        predicate_ids=[predicate.predicate_id],
        input_refs=[predicate.source_criterion_id],
        support_ids=support_ids or predicate.support_ids,
        gap_ids=[],
    )


def _checkable_predicate(
    *,
    predicate_id: str,
    predicate_kind: PredicateKind,
    source_criterion_id: str,
    criterion: ExtractedCriterion,
    surface: str | None,
    target_system: str | None,
    target_codes: frozenset[str],
    negated: bool | None = None,
    operator: ThresholdOperator | None = None,
    value: float | None = None,
    value_low: float | None = None,
    value_high: float | None = None,
    unit: str | None = None,
    window_days: int | None = None,
    support_ids: list[str] | None = None,
    gap_ids: list[str] | None = None,
) -> CheckablePredicate:
    return CheckablePredicate(
        predicate_id=predicate_id,
        predicate_kind=predicate_kind,
        source_criterion_id=source_criterion_id,
        polarity=criterion.polarity,
        negated=criterion.negated if negated is None else negated,
        surface=surface,
        target_system=target_system,
        target_codes=target_codes,
        operator=operator,
        value=value,
        value_low=value_low,
        value_high=value_high,
        unit=unit,
        window_days=window_days,
        support_ids=support_ids or [],
        gap_ids=gap_ids or [],
    )


def _coded_expression(predicate: CheckablePredicate) -> str:
    code_count = len(predicate.target_codes)
    return f"{predicate.predicate_kind}({predicate.predicate_id},codes={code_count})"


def _criterion_is_absence(criterion: ExtractedCriterion) -> bool:
    return criterion.negated or criterion.kind in {"condition_absent", "medication_absent"}


def _concept_set_target_id(concept_set: ConceptSet) -> str:
    return f"{concept_set.name}|{','.join(sorted(concept_set.codes))}"


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
    stage: ResolutionStage,
    source_criterion_id: str,
    facts: list[tuple[str, str]],
) -> CompilerDiagnostic:
    return CompilerDiagnostic(
        severity=severity,
        code=code,
        message=message,
        stage=stage,
        source_criterion_id=source_criterion_id,
        facts=[DiagnosticFact(key=key, value=value) for key, value in facts],
    )


def _resolution_domain(kind: CriterionKind) -> ResolutionDomain:
    if kind == "age" or kind == "sex":
        return "demographic"
    if kind in {"condition_present", "condition_absent"}:
        return "condition"
    if kind in {"medication_present", "medication_absent"}:
        return "medication"
    if kind == "measurement_threshold":
        return "measurement"
    if kind == "temporal_window":
        return "temporal"
    return "free_text"


def _predicate_kind(kind: CriterionKind) -> PredicateKind:
    if kind == "age" or kind == "sex":
        return "demographic"
    if kind in {"condition_present", "condition_absent"}:
        return "condition_presence"
    if kind in {"medication_present", "medication_absent"}:
        return "medication_exposure"
    if kind == "measurement_threshold":
        return "measurement_threshold"
    if kind == "temporal_window":
        return "temporal_event"
    if kind == "free_text":
        return "free_text_review"
    return "unsupported"


def _criterion_surface(criterion: ExtractedCriterion) -> str | None:
    if criterion.condition is not None:
        return criterion.condition.condition_text
    if criterion.medication is not None:
        return criterion.medication.medication_text
    if criterion.measurement is not None:
        return criterion.measurement.measurement_text
    if criterion.temporal_window is not None:
        return criterion.temporal_window.event_text
    if criterion.free_text is not None:
        return criterion.source_text
    if criterion.age is not None or criterion.sex is not None:
        return criterion.source_text
    return None
