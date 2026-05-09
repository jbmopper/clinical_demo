"""Compound-logic and temporal-window compiler helpers.

These helpers are intentionally additive: they build typed compiler
plans, supports, gaps, and diagnostics without changing the current
matcher-facing criteria. The integration worker can call them from the
main compiler pipeline once predicate execution is ready.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, Field

from clinical_demo.extractor.schema import (
    CompositeCriterionGroup,
    ExtractedCriterion,
)
from clinical_demo.matcher.concept_lookup import lookup_condition
from clinical_demo.profile import ConceptSet
from clinical_demo.settings import ResolverExecutionPolicy, get_settings
from clinical_demo.terminology import TerminologyCache, TerminologyResolver

from .schema import (
    CheckablePredicatePlan,
    CompilerDiagnostic,
    CompoundLogicPlan,
    DiagnosticFact,
    ResolutionGap,
    ResolutionStatus,
    ResolutionSupport,
)

TemporalDirection = Literal["within_past", "within_future"]

_GENERIC_TEMPORAL_EVENT_SURFACES: frozenset[str] = frozenset(
    {
        "baseline",
        "day 1",
        "enrollment",
        "randomization",
        "screening",
        "study entry",
        "study visit",
        "trial entry",
        "visit",
        "week 0",
    }
)


class CompoundLogicCompilation(BaseModel):
    """Result of compiling extractor composite groups for one parent."""

    plan: CompoundLogicPlan = Field(description="Compiled compound logic plan.")
    supports: list[ResolutionSupport] = Field(
        default_factory=list,
        description="Supports produced by compound compilation.",
    )
    gaps: list[ResolutionGap] = Field(
        default_factory=list,
        description="Gaps produced by compound compilation.",
    )
    diagnostics: list[CompilerDiagnostic] = Field(
        default_factory=list,
        description="Diagnostics produced by compound compilation.",
    )


class TemporalWindowCompilation(BaseModel):
    """Result of compiling one temporal-window criterion."""

    source_criterion_id: str = Field(description="Stable source criterion id.")
    event_surface: str = Field(description="Temporal event surface from the extractor.")
    normalized_event_surface: str = Field(description="Normalized event surface.")
    window_days: int = Field(description="Normalized lookback/lookforward window in days.")
    direction: TemporalDirection = Field(description="Temporal direction from the extractor.")
    event_resolved: bool = Field(
        description="True when the event surface maps to a condition ConceptSet."
    )
    event_target_id: str | None = Field(
        description="Internal target id for the resolved event condition, when available."
    )
    event_target_label: str | None = Field(
        description="Display label for the resolved event condition, when available."
    )
    event_concept_set: ConceptSet | None = Field(
        description="Resolved event condition ConceptSet, when available."
    )
    predicate: CheckablePredicatePlan = Field(description="Compiled temporal predicate plan.")
    supports: list[ResolutionSupport] = Field(
        default_factory=list,
        description="Supports produced by temporal compilation.",
    )
    gaps: list[ResolutionGap] = Field(
        default_factory=list,
        description="Gaps produced by temporal compilation.",
    )
    diagnostics: list[CompilerDiagnostic] = Field(
        default_factory=list,
        description="Diagnostics produced by temporal compilation.",
    )


def compile_compound_logic(
    groups: Sequence[CompositeCriterionGroup],
    *,
    source_criterion_id: str,
    resolver_policy: ResolverExecutionPolicy = "cached_only",
) -> CompoundLogicCompilation:
    """Compile extractor composite groups into a `CompoundLogicPlan`.

    The function keeps every group and every subcheck id in input order.
    Multiple operators for the same parent are treated as ambiguous
    rather than collapsed into a misleading executable plan.
    """

    source_group_ids = [group.group_id for group in groups]
    subcheck_ids = [subcheck.subcheck_id for group in groups for subcheck in group.subchecks]

    if not groups:
        return CompoundLogicCompilation(
            plan=CompoundLogicPlan(
                status="skipped",
                operator="none",
                source_group_ids=[],
                subcheck_ids=[],
                gap_ids=[],
            )
        )

    group_operators = {group.operator for group in groups}
    subcheck_operators = {subcheck.operator for group in groups for subcheck in group.subchecks}
    operators = group_operators | subcheck_operators

    if len(operators) > 1:
        gap = _compound_operator_gap(
            source_criterion_id=source_criterion_id,
            source_group_ids=source_group_ids,
            operators=sorted(operators),
            resolver_policy=resolver_policy,
        )
        diagnostic = CompilerDiagnostic(
            severity="warning",
            code="compound_operator_conflict",
            message="Composite groups contain inconsistent boolean operators.",
            stage="compound_logic",
            source_criterion_id=source_criterion_id,
            facts=[
                DiagnosticFact(key="operators", value=", ".join(sorted(operators))),
                DiagnosticFact(key="group_count", value=str(len(groups))),
                DiagnosticFact(key="gap_id", value=gap.gap_id),
            ],
        )
        return CompoundLogicCompilation(
            plan=CompoundLogicPlan(
                status="ambiguous",
                operator="none",
                source_group_ids=source_group_ids,
                subcheck_ids=subcheck_ids,
                gap_ids=[gap.gap_id],
            ),
            gaps=[gap],
            diagnostics=[diagnostic],
        )

    operator = groups[0].operator
    return CompoundLogicCompilation(
        plan=CompoundLogicPlan(
            status="resolved",
            operator=operator,
            source_group_ids=source_group_ids,
            subcheck_ids=subcheck_ids,
            gap_ids=[],
        )
    )


def compile_temporal_window(
    criterion: ExtractedCriterion,
    *,
    source_criterion_id: str,
    resolver_policy: ResolverExecutionPolicy = "cached_only",
    resolver: TerminologyResolver | None = None,
) -> TemporalWindowCompilation:
    """Compile a temporal-window criterion into a checkable plan.

    Event concept lookup is deliberately cached/local only. The helper
    constructs a cached-only resolver when one is not supplied, so a
    run configured for live terminology cannot accidentally make a
    network call from the temporal compiler.
    """

    temporal = criterion.temporal_window
    if criterion.kind != "temporal_window" or temporal is None:
        return _unsupported_temporal_compilation(
            source_criterion_id=source_criterion_id,
            surface=criterion.source_text,
            normalized_surface=_normalize_surface(criterion.source_text),
            window_days=0,
            direction="within_past",
            message="Criterion is not a temporal_window criterion.",
            resolver_policy=resolver_policy,
        )

    surface = temporal.event_text
    normalized_surface = _normalize_surface(surface)
    supports: list[ResolutionSupport] = []
    gaps: list[ResolutionGap] = []
    diagnostics: list[CompilerDiagnostic] = []
    concept_set: ConceptSet | None = None

    if _is_generic_temporal_event_surface(normalized_surface):
        gaps.append(
            _temporal_gap(
                source_criterion_id=source_criterion_id,
                suffix="generic_event",
                surface=surface,
                message=(
                    "Temporal event surface is a study workflow anchor, not a patient "
                    "condition event that can be checked against condition history."
                ),
                resolver_policy=resolver_policy,
                kind="unsupported_predicate",
            )
        )
    else:
        concept_set = _lookup_condition_cached_only(surface, resolver=resolver)
        if concept_set is None:
            gaps.append(
                _temporal_gap(
                    source_criterion_id=source_criterion_id,
                    suffix="event_unmapped",
                    surface=surface,
                    message=(
                        "Temporal event surface did not map to a condition ConceptSet "
                        "using cached/local lookup."
                    ),
                    resolver_policy=resolver_policy,
                    kind="unmapped_concept",
                    stage="concept_resolution",
                    domain="condition",
                )
            )
        else:
            supports.append(
                _temporal_event_support(
                    source_criterion_id=source_criterion_id,
                    surface=surface,
                    normalized_surface=normalized_surface,
                    concept_set=concept_set,
                    resolver_policy=resolver_policy,
                )
            )

    if temporal.direction != "within_past":
        gaps.append(
            _temporal_gap(
                source_criterion_id=source_criterion_id,
                suffix="unsupported_direction",
                surface=surface,
                message=(
                    f"Temporal direction {temporal.direction!r} is not executable against "
                    "retrospective patient history."
                ),
                resolver_policy=resolver_policy,
            )
        )

    if gaps:
        status: ResolutionStatus
        status = (
            "unsupported" if any(g.kind == "unsupported_predicate" for g in gaps) else "unresolved"
        )
        expression = None
    else:
        status = "resolved"
        expression = _temporal_expression(
            support_id=supports[0].support_id,
            direction=temporal.direction,
            window_days=temporal.window_days,
        )

    predicate = CheckablePredicatePlan(
        status=status,
        predicate_kind="temporal_event",
        expression=expression,
        input_refs=[source_criterion_id],
        support_ids=[support.support_id for support in supports],
        gap_ids=[gap.gap_id for gap in gaps],
    )

    if gaps:
        diagnostics.append(
            CompilerDiagnostic(
                severity="warning",
                code="temporal_window_not_executable",
                message="Temporal-window criterion is not yet executable.",
                stage="predicate_translation",
                source_criterion_id=source_criterion_id,
                facts=[
                    DiagnosticFact(key="event_surface", value=surface),
                    DiagnosticFact(key="window_days", value=str(temporal.window_days)),
                    DiagnosticFact(key="gap_ids", value=", ".join(gap.gap_id for gap in gaps)),
                ],
            )
        )

    return TemporalWindowCompilation(
        source_criterion_id=source_criterion_id,
        event_surface=surface,
        normalized_event_surface=normalized_surface,
        window_days=temporal.window_days,
        direction=temporal.direction,
        event_resolved=concept_set is not None,
        event_target_id=concept_set.name if concept_set is not None else None,
        event_target_label=concept_set.name if concept_set is not None else None,
        event_concept_set=concept_set,
        predicate=predicate,
        supports=supports,
        gaps=gaps,
        diagnostics=diagnostics,
    )


def _compound_operator_gap(
    *,
    source_criterion_id: str,
    source_group_ids: Sequence[str],
    operators: Sequence[str],
    resolver_policy: ResolverExecutionPolicy,
) -> ResolutionGap:
    return ResolutionGap(
        gap_id=f"gap:{source_criterion_id}:compound_logic:operator_conflict",
        stage="compound_logic",
        domain="compound",
        kind="unsupported_compound",
        source_criterion_id=source_criterion_id,
        surface=", ".join(source_group_ids),
        message=(
            "Composite groups for one parent use multiple boolean operators "
            f"({', '.join(operators)}); compiler needs a nested boolean tree before execution."
        ),
        resolver_policy=resolver_policy,
    )


def _unsupported_temporal_compilation(
    *,
    source_criterion_id: str,
    surface: str,
    normalized_surface: str,
    window_days: int,
    direction: TemporalDirection,
    message: str,
    resolver_policy: ResolverExecutionPolicy,
) -> TemporalWindowCompilation:
    gap = _temporal_gap(
        source_criterion_id=source_criterion_id,
        suffix="not_temporal_window",
        surface=surface,
        message=message,
        resolver_policy=resolver_policy,
    )
    return TemporalWindowCompilation(
        source_criterion_id=source_criterion_id,
        event_surface=surface,
        normalized_event_surface=normalized_surface,
        window_days=window_days,
        direction=direction,
        event_resolved=False,
        event_target_id=None,
        event_target_label=None,
        event_concept_set=None,
        predicate=CheckablePredicatePlan(
            status="unsupported",
            predicate_kind="temporal_event",
            expression=None,
            input_refs=[source_criterion_id],
            support_ids=[],
            gap_ids=[gap.gap_id],
        ),
        supports=[],
        gaps=[gap],
        diagnostics=[],
    )


def _temporal_gap(
    *,
    source_criterion_id: str,
    suffix: str,
    surface: str,
    message: str,
    resolver_policy: ResolverExecutionPolicy,
    kind: Literal[
        "unmapped_concept",
        "unsupported_predicate",
    ] = "unsupported_predicate",
    stage: Literal["concept_resolution", "predicate_translation"] = "predicate_translation",
    domain: Literal["condition", "temporal"] = "temporal",
) -> ResolutionGap:
    return ResolutionGap(
        gap_id=f"gap:{source_criterion_id}:temporal:{suffix}",
        stage=stage,
        domain=domain,
        kind=kind,
        source_criterion_id=source_criterion_id,
        surface=surface,
        message=message,
        resolver_policy=resolver_policy,
    )


def _temporal_event_support(
    *,
    source_criterion_id: str,
    surface: str,
    normalized_surface: str,
    concept_set: ConceptSet,
    resolver_policy: ResolverExecutionPolicy,
) -> ResolutionSupport:
    return ResolutionSupport(
        support_id=f"support:{source_criterion_id}:temporal:event_condition",
        stage="concept_resolution",
        domain="condition",
        source_criterion_id=source_criterion_id,
        surface=surface,
        normalized_surface=normalized_surface,
        target_system=concept_set.system,
        target_id=concept_set.name,
        target_label=concept_set.name,
        resolver_policy=resolver_policy,
    )


def _temporal_expression(
    *,
    support_id: str,
    direction: TemporalDirection,
    window_days: int,
) -> str:
    return f"temporal_event({support_id},{direction},{window_days}d)"


def _lookup_condition_cached_only(
    surface: str,
    *,
    resolver: TerminologyResolver | None,
) -> ConceptSet | None:
    cached_only_resolver = resolver
    if cached_only_resolver is None or cached_only_resolver.execution_policy != "cached_only":
        settings = get_settings()
        cached_only_resolver = TerminologyResolver(
            TerminologyCache(settings.terminology_cache_dir),
            execution_policy="cached_only",
        )
    return lookup_condition(surface, resolver=cached_only_resolver)


def _normalize_surface(surface: str) -> str:
    return " ".join(surface.lower().strip(".,;:()[]{}\"'").split())


def _is_generic_temporal_event_surface(normalized_surface: str) -> bool:
    return normalized_surface in _GENERIC_TEMPORAL_EVENT_SURFACES


__all__ = [
    "CompoundLogicCompilation",
    "TemporalWindowCompilation",
    "compile_compound_logic",
    "compile_temporal_window",
]
