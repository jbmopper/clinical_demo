"""No-op criterion compiler pipeline.

This module gives downstream code a stable typed compilation boundary
without changing current matcher behavior. The result keeps the
extractor criteria as `matcher_inputs` and records future compiler
stages as `not_attempted`/`skipped` plans.
"""

from __future__ import annotations

from collections.abc import Sequence

from clinical_demo.extractor.schema import (
    CompositeCriterionGroup,
    CriterionKind,
    ExtractedCriteria,
    ExtractedCriterion,
)

from .schema import (
    COMPILER_VERSION,
    CheckablePredicatePlan,
    CompiledCriterion,
    CompoundLogicPlan,
    CriterionCompilationResult,
    ExpansionPlan,
    PredicateKind,
    ResolutionDomain,
    ResolverExecutionPolicy,
    UnitNormalizationPlan,
)


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

    compiled = [
        _compile_criterion(
            criterion,
            index=index,
            resolver_policy=resolver_policy,
            composite_groups=groups_by_parent.get(index, []),
        )
        for index, criterion in enumerate(criteria)
    ]

    return CriterionCompilationResult(
        compiler_version=compiler_version,
        resolver_policy=resolver_policy,
        source_criteria_count=len(criteria),
        criteria=compiled,
        matcher_inputs=list(criteria),
        resolved_supports=[],
        unresolved_gaps=[],
        diagnostics=[],
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
) -> CompiledCriterion:
    source_id = source_criterion_id(index)
    domain = _resolution_domain(criterion.kind)
    surface = _criterion_surface(criterion)

    return CompiledCriterion(
        compiled_id=compiled_criterion_id(index),
        source_criterion_id=source_id,
        source_index=index,
        criterion_kind=criterion.kind,
        source_text=criterion.source_text,
        resolver_policy=resolver_policy,
        matcher_input=criterion,
        resolved_supports=[],
        unresolved_gaps=[],
        expansion=ExpansionPlan(
            status="not_attempted",
            domain=domain,
            source_surface=surface,
            strategy="none",
            support_ids=[],
            gap_ids=[],
        ),
        compound_logic=_compound_logic_plan(composite_groups),
        unit_normalization=_unit_normalization_plan(criterion),
        predicate=CheckablePredicatePlan(
            status="not_attempted",
            predicate_kind=_predicate_kind(criterion.kind),
            expression=None,
            input_refs=[source_id],
            support_ids=[],
            gap_ids=[],
        ),
        diagnostics=[],
    )


def _compound_logic_plan(groups: Sequence[CompositeCriterionGroup]) -> CompoundLogicPlan:
    if not groups:
        return CompoundLogicPlan(
            status="skipped",
            operator="none",
            source_group_ids=[],
            subcheck_ids=[],
            gap_ids=[],
        )

    operators = {group.operator for group in groups}
    operator = next(iter(operators)) if len(operators) == 1 else "none"
    subcheck_ids = [subcheck.subcheck_id for group in groups for subcheck in group.subchecks]
    return CompoundLogicPlan(
        status="not_attempted",
        operator=operator,
        source_group_ids=[group.group_id for group in groups],
        subcheck_ids=subcheck_ids,
        gap_ids=[],
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
