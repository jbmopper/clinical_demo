"""Medication criterion compilation helpers.

This is the CC-09 foundation: it turns one extracted medication
criterion into typed compiler supports/gaps/predicate plans without
performing live terminology calls. RxNorm class/route/ingredient
expansion is deliberately represented as placeholders so the later
integration worker can attach richer resolution without changing the
compiler boundary again.
"""

from __future__ import annotations

import re
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from clinical_demo.extractor.schema import ExtractedCriterion, MedicationCriterion
from clinical_demo.profile import ConceptSet
from clinical_demo.settings import ResolverExecutionPolicy, get_settings
from clinical_demo.terminology.medication_classes import (
    ReviewedMedicationClassEntry,
    get_reviewed_medication_class_registry,
)
from clinical_demo.terminology.resolver import get_resolver
from clinical_demo.terminology.reviewed_registry import (
    ReviewedMappingEntry,
    ReviewedMappingRegistry,
    load_reviewed_mapping_registry,
)

from .schema import (
    CheckablePredicatePlan,
    CompilerDiagnostic,
    DiagnosticFact,
    ResolutionGap,
    ResolutionGapKind,
    ResolutionStatus,
    ResolutionSupport,
)

MedicationPresence = Literal["present", "absent"]
MedicationAspectKind = Literal["route", "ingredient", "medication_class"]

_LIST_TOKENS = (",", ";", "/", " and ", " or ")
_CLASS_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bglp-?1\b",
        r"\bsglt-?2\b",
        r"\bdpp-?4\b",
        r"\bpcsk9\b",
        r"\b(?:raas|rasb)\b",
        r"\bbisphosphonates?\b",
        r"\b(?:receptor\s+)?agonists?\b",
        r"\bantagonists?\b",
        r"\binhibitors?\b",
        r"\bblockers?\b",
        r"\bstatins?\b",
        r"\b(?:drug|medication|therapy|therapeutic)\s+class(?:es)?\b",
        r"\b(?:agents?|drugs?|medications?|therap(?:y|ies)|treatments?)\b",
    )
)
_ROUTE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("oral", re.compile(r"\b(?:oral|orally|po|p\.o\.)\b", re.IGNORECASE)),
    ("subcutaneous", re.compile(r"\b(?:subcutaneous|subcut|sc|s\.c\.)\b", re.IGNORECASE)),
    ("intravenous", re.compile(r"\b(?:intravenous|iv|i\.v\.)\b", re.IGNORECASE)),
    ("inhaled", re.compile(r"\b(?:inhaled|inhalation)\b", re.IGNORECASE)),
    ("topical", re.compile(r"\btopical(?:ly)?\b", re.IGNORECASE)),
)


class MedicationResolver(Protocol):
    """Minimal resolver protocol consumed by this helper."""

    def resolve_medication(self, surface: str) -> ConceptSet | None:
        """Resolve a medication surface to a ConceptSet, or None on miss."""


class MedicationAspectPlan(BaseModel):
    """Placeholder for route/ingredient/class resolution."""

    aspect: MedicationAspectKind = Field(description="Medication aspect represented by this plan.")
    status: ResolutionStatus = Field(description="Resolution status for this aspect.")
    surface: str | None = Field(description="Surface text for this aspect, when detected.")
    normalized_surface: str | None = Field(description="Normalized surface text, when detected.")
    support_ids: list[str] = Field(default_factory=list)
    gap_ids: list[str] = Field(default_factory=list)


class MedicationCompilationResult(BaseModel):
    """CC-09 result for one medication criterion."""

    source_criterion_id: str = Field(description="Compiler/source criterion id.")
    surface: str | None = Field(description="Medication surface as extracted.")
    normalized_surface: str | None = Field(description="Normalized medication surface.")
    required_presence: MedicationPresence | None = Field(
        description="Whether the predicate checks exposure presence or absence."
    )
    concept_set: ConceptSet | None = Field(description="Resolved medication ConceptSet, if any.")
    route: MedicationAspectPlan = Field(description="Route placeholder.")
    ingredient: MedicationAspectPlan = Field(description="Ingredient placeholder.")
    medication_class: MedicationAspectPlan = Field(description="Class placeholder.")
    predicate: CheckablePredicatePlan = Field(description="Checkable medication predicate plan.")
    resolved_supports: list[ResolutionSupport] = Field(default_factory=list)
    unresolved_gaps: list[ResolutionGap] = Field(default_factory=list)
    diagnostics: list[CompilerDiagnostic] = Field(default_factory=list)

    @property
    def supports(self) -> list[ResolutionSupport]:
        """Alias for consistency with compiler schema terminology."""

        return self.resolved_supports

    @property
    def gaps(self) -> list[ResolutionGap]:
        """Alias for consistency with compiler schema terminology."""

        return self.unresolved_gaps


def compile_medication_resolution(
    criterion: ExtractedCriterion | MedicationCriterion,
    *,
    source_criterion_id: str,
    resolver_policy: ResolverExecutionPolicy = "cached_only",
    resolver: MedicationResolver | None = None,
    reviewed_registry: ReviewedMappingRegistry | None = None,
) -> MedicationCompilationResult:
    """Compile medication concept resolution for one criterion.

    The helper is intentionally cache/review-only. It calls a resolver
    only when `resolver_policy == "cached_only"` and either the
    injected resolver has no explicit execution policy (test doubles)
    or reports `execution_policy == "cached_only"`.
    """

    mappings = reviewed_registry or load_reviewed_mapping_registry()
    surface, required_presence = _criterion_surface_and_presence(criterion)
    normalized = normalize_medication_surface(surface) if surface is not None else None
    route_plan = _route_plan(surface)
    ingredient_surface = _ingredient_surface_without_route(surface) if surface is not None else None
    ingredient_normalized = (
        normalize_medication_surface(ingredient_surface) if ingredient_surface else None
    )
    ingredient_plan = MedicationAspectPlan(
        aspect="ingredient",
        status="not_attempted" if surface else "skipped",
        surface=ingredient_surface,
        normalized_surface=ingredient_normalized,
    )
    class_plan = MedicationAspectPlan(
        aspect="medication_class",
        status="skipped",
        surface=None,
        normalized_surface=None,
    )

    if surface is None or required_presence is None:
        gap = _gap(
            source_criterion_id,
            surface=None,
            kind="insufficient_source",
            message="Medication compiler received a criterion without a medication payload.",
            resolver_policy=resolver_policy,
            suffix="missing-source",
        )
        return _result(
            source_criterion_id=source_criterion_id,
            surface=None,
            normalized_surface=None,
            required_presence=required_presence,
            concept_set=None,
            route=route_plan,
            ingredient=ingredient_plan.model_copy(update={"status": "skipped"}),
            medication_class=class_plan,
            predicate=_predicate_plan(
                source_criterion_id,
                required_presence=required_presence,
                status="unresolved",
                gap_ids=[gap.gap_id],
            ),
            gaps=[gap],
        )

    reviewed_nonmapped = _reviewed_nonmapped_medication_entry(
        mappings,
        surface=surface,
        ingredient_surface=ingredient_surface,
    )
    if reviewed_nonmapped is not None:
        entry, lookup_surface = reviewed_nonmapped
        return _reviewed_nonmapped_medication_result(
            source_criterion_id=source_criterion_id,
            surface=surface,
            normalized_surface=normalized,
            lookup_surface=lookup_surface,
            required_presence=required_presence,
            route_plan=route_plan,
            ingredient_plan=ingredient_plan,
            class_plan=class_plan,
            entry=entry,
            resolver_policy=resolver_policy,
        )

    class_entry = get_reviewed_medication_class_registry().lookup(surface)
    if class_entry is not None:
        return _compile_reviewed_medication_class(
            source_criterion_id=source_criterion_id,
            surface=surface,
            normalized_surface=normalized,
            required_presence=required_presence,
            route_plan=route_plan,
            ingredient_plan=ingredient_plan,
            class_entry=class_entry,
            resolver_policy=resolver_policy,
            resolver=resolver,
        )

    composite_reason = _class_or_composite_reason(surface)
    if composite_reason is not None:
        gap_kind: ResolutionGapKind = (
            "ambiguous_mapping"
            if composite_reason == "medication_list"
            else "unsupported_predicate"
        )
        gap = _gap(
            source_criterion_id,
            surface=surface,
            kind=gap_kind,
            message=_class_or_composite_message(surface, composite_reason),
            resolver_policy=resolver_policy,
            suffix=composite_reason,
        )
        status: ResolutionStatus = (
            "ambiguous" if composite_reason == "medication_list" else "unsupported"
        )
        return _result(
            source_criterion_id=source_criterion_id,
            surface=surface,
            normalized_surface=normalized,
            required_presence=required_presence,
            concept_set=None,
            route=route_plan,
            ingredient=ingredient_plan.model_copy(update={"status": "skipped"}),
            medication_class=MedicationAspectPlan(
                aspect="medication_class",
                status=status,
                surface=surface,
                normalized_surface=normalized,
                gap_ids=[gap.gap_id],
            ),
            predicate=_predicate_plan(
                source_criterion_id,
                required_presence=required_presence,
                status=status,
                gap_ids=[gap.gap_id],
            ),
            gaps=[gap],
            diagnostics=[
                _diagnostic(
                    source_criterion_id,
                    code=f"medication.{composite_reason}",
                    message=gap.message,
                    severity="warning",
                    facts=[DiagnosticFact(key="gap_id", value=gap.gap_id)],
                )
            ],
        )

    if ingredient_surface is None or ingredient_normalized is None:
        gap = _gap(
            source_criterion_id,
            surface=surface,
            kind="insufficient_source",
            message=(
                f"Medication surface {surface!r} only contained route text after "
                "route normalization; no ingredient remained to resolve."
            ),
            resolver_policy=resolver_policy,
            suffix="missing-ingredient",
        )
        return _result(
            source_criterion_id=source_criterion_id,
            surface=surface,
            normalized_surface=normalized,
            required_presence=required_presence,
            concept_set=None,
            route=route_plan,
            ingredient=ingredient_plan.model_copy(
                update={"status": "unresolved", "gap_ids": [gap.gap_id]}
            ),
            medication_class=class_plan,
            predicate=_predicate_plan(
                source_criterion_id,
                required_presence=required_presence,
                status="unresolved",
                gap_ids=[gap.gap_id],
            ),
            gaps=[gap],
        )

    concept_set, resolver_diagnostic = _resolve_cached_only(
        ingredient_surface,
        source_criterion_id=source_criterion_id,
        resolver_policy=resolver_policy,
        resolver=resolver,
    )
    diagnostics = [resolver_diagnostic] if resolver_diagnostic is not None else []

    if concept_set is None:
        gap = _gap(
            source_criterion_id,
            surface=ingredient_surface,
            kind="unmapped_concept",
            message=(
                f"No cached/reviewed ConceptSet mapping for medication {ingredient_surface!r}."
            ),
            resolver_policy=resolver_policy,
            suffix="unmapped",
        )
        return _result(
            source_criterion_id=source_criterion_id,
            surface=surface,
            normalized_surface=normalized,
            required_presence=required_presence,
            concept_set=None,
            route=route_plan,
            ingredient=ingredient_plan.model_copy(
                update={"status": "unresolved", "gap_ids": [gap.gap_id]}
            ),
            medication_class=class_plan,
            predicate=_predicate_plan(
                source_criterion_id,
                required_presence=required_presence,
                status="unresolved",
                gap_ids=[gap.gap_id],
            ),
            gaps=[gap],
            diagnostics=diagnostics,
        )

    support = ResolutionSupport(
        support_id=f"{source_criterion_id}:medication:support:concept-set",
        stage="concept_resolution",
        domain="medication",
        source_criterion_id=source_criterion_id,
        surface=ingredient_surface,
        normalized_surface=ingredient_normalized,
        target_system=concept_set.system,
        target_id=concept_set.name,
        target_label=concept_set.name,
        resolver_policy=resolver_policy,
    )
    return _result(
        source_criterion_id=source_criterion_id,
        surface=surface,
        normalized_surface=normalized,
        required_presence=required_presence,
        concept_set=concept_set,
        route=route_plan,
        ingredient=ingredient_plan.model_copy(
            update={"status": "resolved", "support_ids": [support.support_id]}
        ),
        medication_class=class_plan,
        predicate=_predicate_plan(
            source_criterion_id,
            required_presence=required_presence,
            status="resolved",
            support_ids=[support.support_id],
            concept_set=concept_set,
        ),
        supports=[support],
        diagnostics=diagnostics,
    )


def normalize_medication_surface(surface: str) -> str:
    """Normalize medication text for stable compiler ids/audit fields."""

    return " ".join(surface.lower().strip(".,;:()[]{}\"'").split())


def _criterion_surface_and_presence(
    criterion: ExtractedCriterion | MedicationCriterion,
) -> tuple[str | None, MedicationPresence | None]:
    if isinstance(criterion, ExtractedCriterion):
        if criterion.kind not in {"medication_present", "medication_absent"}:
            return None, None
        if criterion.medication is None:
            return None, _presence_for_kind(criterion.kind)
        return criterion.medication.medication_text, _presence_for_kind(criterion.kind)
    return criterion.medication_text, "present"


def _presence_for_kind(kind: str) -> MedicationPresence:
    return "absent" if kind == "medication_absent" else "present"


def _class_or_composite_reason(
    surface: str,
) -> Literal["medication_list", "medication_class"] | None:
    padded = f" {surface.lower()} "
    if any(token in padded for token in _LIST_TOKENS):
        return "medication_list"
    if any(pattern.search(surface) for pattern in _CLASS_PATTERNS):
        return "medication_class"
    return None


def _class_or_composite_message(
    surface: str,
    reason: Literal["medication_list", "medication_class"],
) -> str:
    if reason == "medication_list":
        return (
            f"Medication surface {surface!r} names multiple drugs or classes; "
            "compound medication decomposition is required before mapping."
        )
    return (
        f"Medication surface {surface!r} appears to name a medication class; "
        "no reviewed medication-class expansion exists for this surface."
    )


def _compile_reviewed_medication_class(
    *,
    source_criterion_id: str,
    surface: str,
    normalized_surface: str | None,
    required_presence: MedicationPresence,
    route_plan: MedicationAspectPlan,
    ingredient_plan: MedicationAspectPlan,
    class_entry: ReviewedMedicationClassEntry,
    resolver_policy: ResolverExecutionPolicy,
    resolver: MedicationResolver | None,
) -> MedicationCompilationResult:
    supports: list[ResolutionSupport] = []
    diagnostics: list[CompilerDiagnostic] = []
    resolved_members: list[tuple[str, ConceptSet]] = []
    missing_members: list[str] = []

    for index, member_surface in enumerate(class_entry.member_surfaces, start=1):
        concept_set, resolver_diagnostic = _resolve_cached_only(
            member_surface,
            source_criterion_id=source_criterion_id,
            resolver_policy=resolver_policy,
            resolver=resolver,
        )
        if resolver_diagnostic is not None:
            diagnostics.append(resolver_diagnostic)
        if concept_set is None:
            missing_members.append(member_surface)
            continue
        resolved_members.append((member_surface, concept_set))
        supports.append(
            ResolutionSupport(
                support_id=(f"{source_criterion_id}:medication:support:class-member-{index:03d}"),
                stage="concept_resolution",
                domain="medication",
                source_criterion_id=source_criterion_id,
                surface=member_surface,
                normalized_surface=normalize_medication_surface(member_surface),
                target_system=concept_set.system,
                target_id=_concept_set_target_id(concept_set),
                target_label=concept_set.name,
                resolver_policy=resolver_policy,
            )
        )

    if missing_members:
        gap = _gap(
            source_criterion_id,
            surface=surface,
            kind="unmapped_concept",
            message=(
                f"Reviewed medication class {class_entry.display!r} could not be "
                "compiled because these member surfaces did not resolve through "
                f"cached/reviewed RxNorm lookup: {', '.join(missing_members)}."
            ),
            resolver_policy=resolver_policy,
            suffix="class-member-unmapped",
        )
        diagnostics.append(
            _diagnostic(
                source_criterion_id,
                code="medication.class_member_unmapped",
                message=gap.message,
                severity="warning",
                facts=[
                    DiagnosticFact(key="class_id", value=class_entry.class_id),
                    DiagnosticFact(key="missing_members", value=", ".join(missing_members)),
                    DiagnosticFact(key="gap_id", value=gap.gap_id),
                ],
            )
        )
        return _result(
            source_criterion_id=source_criterion_id,
            surface=surface,
            normalized_surface=normalized_surface,
            required_presence=required_presence,
            concept_set=None,
            route=route_plan,
            ingredient=ingredient_plan.model_copy(update={"status": "skipped"}),
            medication_class=MedicationAspectPlan(
                aspect="medication_class",
                status="unresolved",
                surface=surface,
                normalized_surface=normalized_surface,
                gap_ids=[gap.gap_id],
            ),
            predicate=_predicate_plan(
                source_criterion_id,
                required_presence=required_presence,
                status="unresolved",
                support_ids=[support.support_id for support in supports],
                gap_ids=[gap.gap_id],
            ),
            supports=supports,
            gaps=[gap],
            diagnostics=diagnostics,
        )

    systems = {concept_set.system for _, concept_set in resolved_members}
    if len(systems) != 1:
        gap = _gap(
            source_criterion_id,
            surface=surface,
            kind="ambiguous_mapping",
            message=(
                f"Reviewed medication class {class_entry.display!r} resolved to "
                "member ConceptSets from multiple coding systems; compiler requires "
                "one executable target system per medication predicate."
            ),
            resolver_policy=resolver_policy,
            suffix="class-system-conflict",
        )
        return _result(
            source_criterion_id=source_criterion_id,
            surface=surface,
            normalized_surface=normalized_surface,
            required_presence=required_presence,
            concept_set=None,
            route=route_plan,
            ingredient=ingredient_plan.model_copy(update={"status": "skipped"}),
            medication_class=MedicationAspectPlan(
                aspect="medication_class",
                status="ambiguous",
                surface=surface,
                normalized_surface=normalized_surface,
                support_ids=[support.support_id for support in supports],
                gap_ids=[gap.gap_id],
            ),
            predicate=_predicate_plan(
                source_criterion_id,
                required_presence=required_presence,
                status="ambiguous",
                support_ids=[support.support_id for support in supports],
                gap_ids=[gap.gap_id],
            ),
            supports=supports,
            gaps=[gap],
            diagnostics=diagnostics,
        )

    system = next(iter(systems))
    codes = frozenset(code for _, concept_set in resolved_members for code in concept_set.codes)
    if not codes:
        gap = _gap(
            source_criterion_id,
            surface=surface,
            kind="unmapped_concept",
            message=(
                f"Reviewed medication class {class_entry.display!r} resolved member "
                "ConceptSets, but their code union was empty."
            ),
            resolver_policy=resolver_policy,
            suffix="class-empty-code-union",
        )
        return _result(
            source_criterion_id=source_criterion_id,
            surface=surface,
            normalized_surface=normalized_surface,
            required_presence=required_presence,
            concept_set=None,
            route=route_plan,
            ingredient=ingredient_plan.model_copy(update={"status": "skipped"}),
            medication_class=MedicationAspectPlan(
                aspect="medication_class",
                status="unresolved",
                surface=surface,
                normalized_surface=normalized_surface,
                support_ids=[support.support_id for support in supports],
                gap_ids=[gap.gap_id],
            ),
            predicate=_predicate_plan(
                source_criterion_id,
                required_presence=required_presence,
                status="unresolved",
                support_ids=[support.support_id for support in supports],
                gap_ids=[gap.gap_id],
            ),
            supports=supports,
            gaps=[gap],
            diagnostics=diagnostics,
        )

    class_concept_set = ConceptSet(
        name=class_entry.display,
        system=system,
        codes=codes,
    )
    class_support = ResolutionSupport(
        support_id=f"{source_criterion_id}:medication:support:class-expansion",
        stage="expansion",
        domain="medication",
        source_criterion_id=source_criterion_id,
        surface=surface,
        normalized_surface=normalized_surface,
        target_system=system,
        target_id=class_entry.class_id,
        target_label=class_entry.display,
        resolver_policy=resolver_policy,
    )
    all_supports = [class_support, *supports]
    support_ids = [support.support_id for support in all_supports]
    return _result(
        source_criterion_id=source_criterion_id,
        surface=surface,
        normalized_surface=normalized_surface,
        required_presence=required_presence,
        concept_set=class_concept_set,
        route=route_plan,
        ingredient=ingredient_plan.model_copy(update={"status": "skipped"}),
        medication_class=MedicationAspectPlan(
            aspect="medication_class",
            status="resolved",
            surface=surface,
            normalized_surface=normalized_surface,
            support_ids=support_ids,
        ),
        predicate=_predicate_plan(
            source_criterion_id,
            required_presence=required_presence,
            status="resolved",
            support_ids=support_ids,
            concept_set=class_concept_set,
        ),
        supports=all_supports,
        diagnostics=diagnostics,
    )


def _reviewed_nonmapped_medication_entry(
    registry: ReviewedMappingRegistry,
    *,
    surface: str,
    ingredient_surface: str | None,
) -> tuple[ReviewedMappingEntry, str] | None:
    lookup_surfaces = (ingredient_surface, surface)
    seen: set[str] = set()
    for lookup_surface in lookup_surfaces:
        if lookup_surface is None:
            continue
        normalized = normalize_medication_surface(lookup_surface)
        if normalized in seen:
            continue
        seen.add(normalized)
        entry = registry.lookup("medication", lookup_surface)
        if entry is not None and entry.status != "mapped":
            return entry, lookup_surface
    return None


def _reviewed_nonmapped_medication_result(
    *,
    source_criterion_id: str,
    surface: str,
    normalized_surface: str | None,
    lookup_surface: str,
    required_presence: MedicationPresence,
    route_plan: MedicationAspectPlan,
    ingredient_plan: MedicationAspectPlan,
    class_plan: MedicationAspectPlan,
    entry: ReviewedMappingEntry,
    resolver_policy: ResolverExecutionPolicy,
) -> MedicationCompilationResult:
    gap_kind: ResolutionGapKind = (
        "ambiguous_mapping" if entry.status == "ambiguous" else "unsupported_predicate"
    )
    status: ResolutionStatus = "ambiguous" if gap_kind == "ambiguous_mapping" else "unsupported"
    gap = _gap(
        source_criterion_id,
        surface=lookup_surface,
        kind=gap_kind,
        message=f"Reviewed medication surface classified as {entry.status}: {entry.reason}",
        resolver_policy=resolver_policy,
        suffix=f"reviewed-{entry.status}",
    )
    is_class_like = _class_or_composite_reason(surface) == "medication_class"
    return _result(
        source_criterion_id=source_criterion_id,
        surface=surface,
        normalized_surface=normalized_surface,
        required_presence=required_presence,
        concept_set=None,
        route=route_plan,
        ingredient=ingredient_plan.model_copy(
            update={
                "status": "skipped" if is_class_like else status,
                "gap_ids": [] if is_class_like else [gap.gap_id],
            }
        ),
        medication_class=(
            MedicationAspectPlan(
                aspect="medication_class",
                status=status,
                surface=surface,
                normalized_surface=normalized_surface,
                gap_ids=[gap.gap_id],
            )
            if is_class_like
            else class_plan
        ),
        predicate=_predicate_plan(
            source_criterion_id,
            required_presence=required_presence,
            status=status,
            gap_ids=[gap.gap_id],
        ),
        gaps=[gap],
        diagnostics=[
            _diagnostic(
                source_criterion_id,
                code=f"medication.reviewed.{entry.status}",
                message=gap.message,
                severity="warning",
                facts=[
                    DiagnosticFact(key="gap_id", value=gap.gap_id),
                    DiagnosticFact(key="status", value=entry.status),
                    DiagnosticFact(key="reviewer", value=entry.reviewer),
                    DiagnosticFact(key="provenance", value=entry.provenance),
                ],
            )
        ],
    )


def _route_plan(surface: str | None) -> MedicationAspectPlan:
    if surface is None:
        return MedicationAspectPlan(
            aspect="route",
            status="skipped",
            surface=None,
            normalized_surface=None,
        )

    for route, pattern in _ROUTE_PATTERNS:
        if pattern.search(surface):
            return MedicationAspectPlan(
                aspect="route",
                status="resolved",
                surface=route,
                normalized_surface=route,
            )

    return MedicationAspectPlan(
        aspect="route",
        status="skipped",
        surface=None,
        normalized_surface=None,
    )


def _ingredient_surface_without_route(surface: str) -> str | None:
    ingredient_surface = surface
    for _, pattern in _ROUTE_PATTERNS:
        ingredient_surface = pattern.sub(" ", ingredient_surface)
    ingredient_surface = " ".join(ingredient_surface.strip(".,;:()[]{}\"'").split())
    return ingredient_surface or None


def _resolve_cached_only(
    surface: str,
    *,
    source_criterion_id: str,
    resolver_policy: ResolverExecutionPolicy,
    resolver: MedicationResolver | None,
) -> tuple[ConceptSet | None, CompilerDiagnostic | None]:
    if resolver_policy != "cached_only":
        return None, _diagnostic(
            source_criterion_id,
            code="medication.resolver_policy_not_cached_only",
            message=(
                "Medication compiler skipped terminology lookup because CC-09 permits "
                "only cached_only resolver execution."
            ),
            severity="warning",
            facts=[DiagnosticFact(key="resolver_policy", value=resolver_policy)],
        )

    resolver_to_use = resolver
    if resolver_to_use is None:
        settings = get_settings()
        if settings.resolver_execution_policy != "cached_only":
            return None, _diagnostic(
                source_criterion_id,
                code="medication.default_resolver_not_cached_only",
                message=(
                    "Medication compiler skipped the default resolver because process "
                    "settings are not cached_only."
                ),
                severity="warning",
                facts=[
                    DiagnosticFact(
                        key="settings.resolver_execution_policy",
                        value=settings.resolver_execution_policy,
                    )
                ],
            )
        resolver_to_use = get_resolver()

    execution_policy = getattr(resolver_to_use, "execution_policy", "cached_only")
    if execution_policy != "cached_only":
        return None, _diagnostic(
            source_criterion_id,
            code="medication.injected_resolver_not_cached_only",
            message=(
                "Medication compiler skipped the injected resolver because it is not "
                "configured for cached_only execution."
            ),
            severity="warning",
            facts=[DiagnosticFact(key="resolver.execution_policy", value=str(execution_policy))],
        )

    return resolver_to_use.resolve_medication(surface), None


def _predicate_plan(
    source_criterion_id: str,
    *,
    required_presence: MedicationPresence | None,
    status: ResolutionStatus,
    support_ids: list[str] | None = None,
    gap_ids: list[str] | None = None,
    concept_set: ConceptSet | None = None,
) -> CheckablePredicatePlan:
    expression = None
    if concept_set is not None and required_presence is not None:
        expression = (
            f"medication_exposure(required={required_presence},concept_set={concept_set.name})"
        )
    return CheckablePredicatePlan(
        status=status,
        predicate_kind="medication_exposure",
        expression=expression,
        input_refs=[source_criterion_id],
        support_ids=support_ids or [],
        gap_ids=gap_ids or [],
    )


def _concept_set_target_id(concept_set: ConceptSet) -> str:
    return f"{concept_set.name}|{','.join(sorted(concept_set.codes))}"


def _gap(
    source_criterion_id: str,
    *,
    surface: str | None,
    kind: ResolutionGapKind,
    message: str,
    resolver_policy: ResolverExecutionPolicy,
    suffix: str,
) -> ResolutionGap:
    return ResolutionGap(
        gap_id=f"{source_criterion_id}:medication:gap:{suffix}",
        stage="concept_resolution",
        domain="medication",
        kind=kind,
        source_criterion_id=source_criterion_id,
        surface=surface,
        message=message,
        resolver_policy=resolver_policy,
    )


def _diagnostic(
    source_criterion_id: str,
    *,
    code: str,
    message: str,
    severity: Literal["info", "warning", "error"],
    facts: list[DiagnosticFact] | None = None,
) -> CompilerDiagnostic:
    return CompilerDiagnostic(
        severity=severity,
        code=code,
        message=message,
        stage="concept_resolution",
        source_criterion_id=source_criterion_id,
        facts=facts or [],
    )


def _result(
    *,
    source_criterion_id: str,
    surface: str | None,
    normalized_surface: str | None,
    required_presence: MedicationPresence | None,
    concept_set: ConceptSet | None,
    route: MedicationAspectPlan,
    ingredient: MedicationAspectPlan,
    medication_class: MedicationAspectPlan,
    predicate: CheckablePredicatePlan,
    supports: list[ResolutionSupport] | None = None,
    gaps: list[ResolutionGap] | None = None,
    diagnostics: list[CompilerDiagnostic] | None = None,
) -> MedicationCompilationResult:
    return MedicationCompilationResult(
        source_criterion_id=source_criterion_id,
        surface=surface,
        normalized_surface=normalized_surface,
        required_presence=required_presence,
        concept_set=concept_set,
        route=route,
        ingredient=ingredient,
        medication_class=medication_class,
        predicate=predicate,
        resolved_supports=supports or [],
        unresolved_gaps=gaps or [],
        diagnostics=diagnostics or [],
    )


__all__ = [
    "MedicationAspectPlan",
    "MedicationCompilationResult",
    "MedicationPresence",
    "MedicationResolver",
    "compile_medication_resolution",
    "normalize_medication_surface",
]
