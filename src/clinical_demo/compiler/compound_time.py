"""Compound-logic and temporal-window compiler helpers.

These helpers are intentionally additive: they build typed compiler
plans, supports, gaps, and diagnostics without changing the current
matcher-facing criteria. The integration worker can call them from the
main compiler pipeline once predicate execution is ready.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
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
from clinical_demo.terminology.reviewed_registry import (
    ReviewedMappingEntry,
    ReviewedMappingRegistry,
)

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
_GENERIC_TEMPORAL_EVENT_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"^(?:baseline|screening|enrollment|randomization|study entry|trial entry)\s+visit$",
        r"^(?:baseline|screening|enrollment|randomization)\s+(?:assessment|evaluation)$",
    )
)
_PARENTHETICAL_RE = re.compile(r"\([^()]*\)|\[[^\[\]]*\]|\{[^{}]*\}")
_HISTORY_PREFIX_RE = re.compile(
    r"^(?:personal\s+)?(?:(?:past\s+)?medical\s+)?history\s+(?:of|for)\s+",
    re.IGNORECASE,
)
_DIAGNOSIS_PREFIX_RE = re.compile(r"^(?:diagnosis\s+of|diagnosed\s+with)\s+", re.IGNORECASE)
_DIAGNOSIS_SUFFIX_RE = re.compile(r"\s+(?:diagnosis|diagnoses)\s*$", re.IGNORECASE)
_QUALIFIER_PREFIX_RE = re.compile(
    r"^(?:known|documented|confirmed|current|active|prior|previous|recent)\s+",
    re.IGNORECASE,
)
_ONSET_PREFIX_RE = re.compile(r"^(?:new\s+onset|newly\s+diagnosed)\s+", re.IGNORECASE)
_TEMPORAL_EVENT_ALIAS_VARIANTS: dict[str, str] = {
    "t1d": "type 1 diabetes",
    "t1dm": "type 1 diabetes",
    "t2d": "type 2 diabetes",
    "t2dm": "type 2 diabetes",
}


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
    reviewed_registry: ReviewedMappingRegistry | None = None,
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
        reviewed_nonmapped = _reviewed_nonmapped_temporal_event(surface, reviewed_registry)
        if reviewed_nonmapped is not None:
            reviewed_entry, lookup_surface, transforms = reviewed_nonmapped
            gaps.append(
                _temporal_gap(
                    source_criterion_id=source_criterion_id,
                    suffix=f"reviewed_{reviewed_entry.status}",
                    surface=surface,
                    message=(
                        f"Reviewed temporal event surface {lookup_surface!r} is classified as "
                        f"{reviewed_entry.status}: {reviewed_entry.reason}"
                    ),
                    resolver_policy=resolver_policy,
                    kind=_reviewed_nonmapped_temporal_gap_kind(reviewed_entry),
                    stage="concept_resolution",
                    domain="condition",
                )
            )
            diagnostics.append(
                CompilerDiagnostic(
                    severity="warning",
                    code=f"temporal_event.reviewed.{reviewed_entry.status}",
                    message=(
                        f"Reviewed temporal event surface {lookup_surface!r} is classified as "
                        f"{reviewed_entry.status}: {reviewed_entry.reason}"
                    ),
                    stage="concept_resolution",
                    source_criterion_id=source_criterion_id,
                    facts=[
                        DiagnosticFact(key="event_surface", value=surface),
                        DiagnosticFact(key="lookup_surface", value=lookup_surface),
                        DiagnosticFact(key="reviewed_status", value=reviewed_entry.status),
                        DiagnosticFact(key="transforms", value=", ".join(transforms) or "none"),
                    ],
                )
            )
        else:
            lookup = _lookup_temporal_event_condition(surface, resolver=resolver)
            concept_set = lookup.concept_set
            if concept_set is None:
                gaps.append(
                    _temporal_gap(
                        source_criterion_id=source_criterion_id,
                        suffix="event_unmapped",
                        surface=surface,
                        message=(
                            "Temporal event surface did not map to a condition ConceptSet "
                            "using cached/local lookup. Tried event variants: "
                            f"{', '.join(lookup.tried_surfaces)}."
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
                        surface=lookup.lookup_surface,
                        normalized_surface=lookup.normalized_lookup_surface,
                        concept_set=concept_set,
                        resolver_policy=resolver_policy,
                    )
                )
                if lookup.normalized_lookup_surface != normalized_surface:
                    diagnostics.append(
                        CompilerDiagnostic(
                            severity="info",
                            code="temporal_event_surface_normalized",
                            message=(
                                "Temporal event surface was normalized before condition lookup."
                            ),
                            stage="concept_resolution",
                            source_criterion_id=source_criterion_id,
                            facts=[
                                DiagnosticFact(key="event_surface", value=surface),
                                DiagnosticFact(key="lookup_surface", value=lookup.lookup_surface),
                                DiagnosticFact(
                                    key="transforms",
                                    value=", ".join(lookup.transforms) or "none",
                                ),
                            ],
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
        "ambiguous_mapping",
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


def _reviewed_nonmapped_temporal_event(
    surface: str,
    reviewed_registry: ReviewedMappingRegistry | None,
) -> tuple[ReviewedMappingEntry, str, tuple[str, ...]] | None:
    if reviewed_registry is None:
        return None
    for lookup_surface, transforms in _temporal_event_lookup_variants(surface):
        entry = reviewed_registry.lookup("condition", lookup_surface)
        if entry is not None and entry.status != "mapped":
            return entry, lookup_surface, transforms
    return None


def _reviewed_nonmapped_temporal_gap_kind(
    entry: ReviewedMappingEntry,
) -> Literal["ambiguous_mapping", "unsupported_predicate"]:
    if entry.status == "ambiguous":
        return "ambiguous_mapping"
    return "unsupported_predicate"


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


class _TemporalEventLookup(BaseModel):
    concept_set: ConceptSet | None
    lookup_surface: str
    normalized_lookup_surface: str
    transforms: tuple[str, ...] = Field(default_factory=tuple)
    tried_surfaces: tuple[str, ...] = Field(default_factory=tuple)


def _lookup_temporal_event_condition(
    surface: str,
    *,
    resolver: TerminologyResolver | None,
) -> _TemporalEventLookup:
    variants = _temporal_event_lookup_variants(surface)
    tried: list[str] = []
    for lookup_surface, transforms in variants:
        normalized = _normalize_surface(lookup_surface)
        if _is_generic_temporal_event_surface(normalized):
            continue
        tried.append(lookup_surface)
        concept_set = _lookup_condition_cached_only(lookup_surface, resolver=resolver)
        if concept_set is not None:
            return _TemporalEventLookup(
                concept_set=concept_set,
                lookup_surface=lookup_surface,
                normalized_lookup_surface=normalized,
                transforms=transforms,
                tried_surfaces=tuple(tried),
            )
    normalized_surface = _normalize_surface(surface)
    return _TemporalEventLookup(
        concept_set=None,
        lookup_surface=surface,
        normalized_lookup_surface=normalized_surface,
        transforms=(),
        tried_surfaces=tuple(tried) or (surface,),
    )


def _temporal_event_lookup_variants(surface: str) -> tuple[tuple[str, tuple[str, ...]], ...]:
    states: list[tuple[str, tuple[str, ...]]] = []
    seen: set[str] = set()

    def add(candidate: str, transforms: tuple[str, ...]) -> None:
        normalized = _normalize_surface(candidate)
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        states.append((normalized, transforms))

    add(surface, ())
    transforms: tuple[tuple[str, Callable[[str], str]], ...] = (
        ("parenthetical_cleanup", _remove_parentheticals),
        ("history_of_stripped", _strip_history_prefix),
        ("qualifier_prefix_stripped", _strip_qualifier_prefix),
        ("onset_prefix_stripped", _strip_onset_prefix),
        ("diagnosis_prefix_stripped", _strip_diagnosis_prefix),
        ("diagnosis_suffix_stripped", _strip_diagnosis_suffix),
    )
    for transform_name, transform in transforms:
        for candidate, prior_transforms in tuple(states):
            add(transform(candidate), (*prior_transforms, transform_name))

    for candidate, prior_transforms in tuple(states):
        alias = _TEMPORAL_EVENT_ALIAS_VARIANTS.get(_normalize_surface(candidate))
        if alias is not None:
            add(alias, (*prior_transforms, "temporal_event_alias"))

    return tuple(states)


def _remove_parentheticals(surface: str) -> str:
    return _PARENTHETICAL_RE.sub(" ", surface)


def _strip_history_prefix(surface: str) -> str:
    return _HISTORY_PREFIX_RE.sub("", surface)


def _strip_diagnosis_prefix(surface: str) -> str:
    return _DIAGNOSIS_PREFIX_RE.sub("", surface)


def _strip_diagnosis_suffix(surface: str) -> str:
    return _DIAGNOSIS_SUFFIX_RE.sub("", surface)


def _strip_qualifier_prefix(surface: str) -> str:
    return _QUALIFIER_PREFIX_RE.sub("", surface)


def _strip_onset_prefix(surface: str) -> str:
    return _ONSET_PREFIX_RE.sub("", surface)


def _normalize_surface(surface: str) -> str:
    return " ".join(surface.lower().strip(".,;:()[]{}\"'").split())


def _is_generic_temporal_event_surface(normalized_surface: str) -> bool:
    return normalized_surface in _GENERIC_TEMPORAL_EVENT_SURFACES or any(
        pattern.match(normalized_surface) for pattern in _GENERIC_TEMPORAL_EVENT_PATTERNS
    )


__all__ = [
    "CompoundLogicCompilation",
    "TemporalWindowCompilation",
    "compile_compound_logic",
    "compile_temporal_window",
]
