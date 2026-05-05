"""Turn top unmapped surfaces into a terminology work queue.

This is the small operational layer behind PLAN task 2.18. The eval
diagnostic already tells us which surfaces dominate `unmapped_concept`;
this module resolves or classifies those surfaces through the open
terminology front door so the list becomes an actionable queue instead
of another static report.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from clinical_demo.evals.diagnostics import EvalDiagnostics, SurfaceCount
from clinical_demo.profile import ConceptSet
from clinical_demo.settings import get_settings
from clinical_demo.terminology.cache import (
    SurfaceResolution,
    SurfaceResolutionCandidate,
    SurfaceResolutionKind,
    SurfaceResolutionStatus,
    TerminologyCache,
)
from clinical_demo.terminology.resolver import (
    OPEN_SURFACE_RESOLVER_VERSION,
    TerminologyResolver,
    get_resolver,
)

WorkQueueStatus = Literal[
    "resolved",
    "ambiguous",
    "true_miss",
    "composite_unhandled",
    "extractor_bug",
    "out_of_scope",
    "unresolved",
]


class SurfaceWorkItem(BaseModel):
    """One classified surface from `EvalDiagnostics.top_unmapped_surfaces`."""

    surface: str
    criterion_kind: str
    resolver_kind: SurfaceResolutionKind | None
    count: int
    status: WorkQueueStatus
    cache_status: Literal["hit", "written", "miss"]
    concept_set: ConceptSet | None = None
    candidates: list[SurfaceResolutionCandidate] = Field(default_factory=list)
    reason: str


class SurfaceRegression(BaseModel):
    """A surface previously classified as resolved but now unmapped."""

    surface: str
    criterion_kind: str
    count: int
    threshold: int
    reason: str


def build_surface_work_queue(
    diagnostics: EvalDiagnostics,
    *,
    cache: TerminologyCache | None = None,
    resolver: TerminologyResolver | None = None,
    limit: int | None = None,
) -> list[SurfaceWorkItem]:
    """Resolve/classify top unmapped surfaces and warm cache rows.

    The resolver is still the source of truth for mappings. This layer
    adds fallback classification for obvious composites and unsupported
    criterion kinds so humans can triage the remaining queue quickly.
    """

    cache = cache or TerminologyCache(get_settings().terminology_cache_dir)
    resolver = resolver or get_resolver()
    surfaces = diagnostics.top_unmapped_surfaces[:limit]
    return [_classify_surface(item, cache=cache, resolver=resolver) for item in surfaces]


def render_surface_work_queue(items: list[SurfaceWorkItem]) -> str:
    lines = ["terminology surface work queue"]
    for item in items:
        lines.append(f"{item.count:>3}  {item.status:<20} {item.criterion_kind:<24} {item.surface}")
        if item.reason:
            lines.append(f"     {item.reason}")
    return "\n".join(lines) + "\n"


def surface_work_queue_to_json(items: list[SurfaceWorkItem]) -> str:
    return json.dumps([item.model_dump(mode="json") for item in items], indent=2)


def write_surface_work_queue(path: Path | str, items: list[SurfaceWorkItem]) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(surface_work_queue_to_json(items) + "\n")


def load_surface_work_queue(path: Path | str) -> list[SurfaceWorkItem]:
    raw = json.loads(Path(path).read_text())
    if not isinstance(raw, list):
        raise ValueError(f"surface work queue {path} must contain a JSON list")
    return [SurfaceWorkItem.model_validate(item) for item in raw]


def find_resolved_surface_regressions(
    diagnostics: EvalDiagnostics,
    resolved_items: list[SurfaceWorkItem],
    *,
    min_count: int = 1,
) -> list[SurfaceRegression]:
    """Find watched resolved surfaces that regressed to unmapped.

    `resolved_items` is intentionally just the same JSON shape emitted by
    `warm_terminology_surfaces.py`; a team can either preserve a prior
    work-queue output or maintain a tiny resolved-surface watchlist by hand.
    """

    watched = {
        (item.criterion_kind, item.surface): item
        for item in resolved_items
        if item.status == "resolved"
    }
    regressions: list[SurfaceRegression] = []
    for surface in diagnostics.top_unmapped_surfaces:
        if surface.count < min_count:
            continue
        item = watched.get((surface.kind, surface.surface))
        if item is None:
            continue
        regressions.append(
            SurfaceRegression(
                surface=surface.surface,
                criterion_kind=surface.kind,
                count=surface.count,
                threshold=min_count,
                reason=item.reason,
            )
        )
    return regressions


def render_surface_regressions(regressions: list[SurfaceRegression]) -> str:
    if not regressions:
        return "No resolved terminology surface regressions.\n"
    lines = ["Resolved terminology surfaces regressed to unmapped:"]
    for item in regressions:
        lines.append(
            f"  {item.count:>3}  {item.criterion_kind:<24} {item.surface} "
            f"(threshold={item.threshold})"
        )
        if item.reason:
            lines.append(f"       prior resolution: {item.reason}")
    return "\n".join(lines) + "\n"


def _classify_surface(
    item: SurfaceCount,
    *,
    cache: TerminologyCache,
    resolver: TerminologyResolver,
) -> SurfaceWorkItem:
    resolver_kind = _resolver_kind(item.kind)
    if resolver_kind is None:
        return SurfaceWorkItem(
            surface=item.surface,
            criterion_kind=item.kind,
            resolver_kind=None,
            count=item.count,
            status="out_of_scope",
            cache_status="miss",
            reason=f"No terminology resolver for criterion kind {item.kind!r}.",
        )

    # Hand-curated overrides win over terminology resolution. Some
    # surfaces (life expectancy, ECOG performance status) do have
    # UMLS/LOINC hits, but those hits are not usefully matchable
    # against Synthea patients -- the correct triage label is
    # `extractor_bug` / `out_of_scope`, not a resolved ConceptSet
    # that the matcher will silently fail against. Apply the manual
    # classification first; let the resolver run only if no manual
    # override exists for this surface.
    manual = _manual_nonresolved(item)
    before = cache.get_surface_resolution(resolver_kind, item.surface)
    if manual is not None:
        status, reason = manual
        resolution = _nonresolved_resolution(item, resolver_kind, status=status, reason=reason)
        cache.put_surface_resolution(resolution)
        return SurfaceWorkItem(
            surface=item.surface,
            criterion_kind=item.kind,
            resolver_kind=resolver_kind,
            count=item.count,
            status=status,
            cache_status="hit" if before is not None and before.status == status else "written",
            reason=reason,
        )

    concept_set = _resolve(resolver, resolver_kind, item.surface)
    after = cache.get_surface_resolution(resolver_kind, item.surface)

    if concept_set is not None:
        return SurfaceWorkItem(
            surface=item.surface,
            criterion_kind=item.kind,
            resolver_kind=resolver_kind,
            count=item.count,
            status="resolved",
            cache_status="hit" if before is not None else "written",
            concept_set=concept_set,
            candidates=after.candidates if after else [],
            reason=(after.reason if after else "Resolved by terminology resolver."),
        )

    current = after or before
    if current is not None and current.resolver_version == OPEN_SURFACE_RESOLVER_VERSION:
        return SurfaceWorkItem(
            surface=item.surface,
            criterion_kind=item.kind,
            resolver_kind=resolver_kind,
            count=item.count,
            status=current.status,
            cache_status="hit" if before is not None else "written",
            candidates=current.candidates,
            reason=current.reason,
        )

    if _looks_composite(item.surface):
        resolution = _nonresolved_resolution(
            item,
            resolver_kind,
            status="composite_unhandled",
            reason="Surface contains conjunction/list punctuation and should be split or reviewed.",
        )
        cache.put_surface_resolution(resolution)
        return SurfaceWorkItem(
            surface=item.surface,
            criterion_kind=item.kind,
            resolver_kind=resolver_kind,
            count=item.count,
            status="composite_unhandled",
            cache_status="written",
            reason=resolution.reason,
        )

    if item.kind == "temporal_window":
        resolution = _nonresolved_resolution(
            item,
            resolver_kind,
            status="composite_unhandled",
            reason="Temporal-window event needs event extraction/review before terminology mapping.",
        )
        cache.put_surface_resolution(resolution)
        return SurfaceWorkItem(
            surface=item.surface,
            criterion_kind=item.kind,
            resolver_kind=resolver_kind,
            count=item.count,
            status="composite_unhandled",
            cache_status="written",
            reason=resolution.reason,
        )

    return SurfaceWorkItem(
        surface=item.surface,
        criterion_kind=item.kind,
        resolver_kind=resolver_kind,
        count=item.count,
        status="unresolved",
        cache_status="miss",
        reason="No resolver hit or explicit non-resolution classification yet.",
    )


def _resolver_kind(criterion_kind: str) -> SurfaceResolutionKind | None:
    if criterion_kind in {"condition_present", "condition_absent", "temporal_window"}:
        return "condition"
    if criterion_kind in {"medication_present", "medication_absent"}:
        return "medication"
    if criterion_kind == "measurement_threshold":
        return "lab"
    return None


def _resolve(
    resolver: TerminologyResolver,
    kind: SurfaceResolutionKind,
    surface: str,
) -> ConceptSet | None:
    if kind == "condition":
        return resolver.resolve_condition(surface)
    if kind == "lab":
        return resolver.resolve_lab(surface)
    return resolver.resolve_medication(surface)


def _looks_composite(surface: str) -> bool:
    normalized = f" {surface.lower()} "
    return any(token in normalized for token in (" and ", " or ", ",", ";", "/"))


def _manual_nonresolved(item: SurfaceCount) -> tuple[SurfaceResolutionStatus, str] | None:
    """Known top-surface decisions that are not terminology API wins.

    These should stay tiny and empirical. They separate "map this next"
    from "this cannot work with the current patient data model or extractor
    type" without pretending a ConceptSet exists.
    """

    surface = item.surface.lower().strip()
    if surface in {"pulmonary vascular resistance (pvr)", "pulmonary vascular resistance"}:
        return (
            "out_of_scope",
            "Requires right-heart catheterization/hemodynamic observations not modeled in the current Synthea profile.",
        )
    if surface == "history of full pneumonectomy":
        return (
            "out_of_scope",
            "Procedure-history evidence is not modeled by the current condition/medication/lab matcher primitives.",
        )
    if surface == "life expectancy":
        return (
            "extractor_bug",
            "Life expectancy is prognostic/free-text review, not a structured measurement threshold in the current matcher.",
        )
    if surface == "ecog performance status":
        return (
            "out_of_scope",
            "Functional-status observations such as ECOG are not present in the current Synthea profile.",
        )
    return None


def _nonresolved_resolution(
    item: SurfaceCount,
    kind: SurfaceResolutionKind,
    *,
    status: SurfaceResolutionStatus,
    reason: str,
) -> SurfaceResolution:
    normalized = " ".join(item.surface.lower().strip().split())
    return SurfaceResolution(
        kind=kind,
        surface=item.surface,
        normalized_surface=normalized,
        status=status,
        concept_set=None,
        candidates=[],
        reason=reason,
        resolver_version=OPEN_SURFACE_RESOLVER_VERSION,
    )


__all__ = [
    "SurfaceRegression",
    "SurfaceWorkItem",
    "build_surface_work_queue",
    "find_resolved_surface_regressions",
    "load_surface_work_queue",
    "render_surface_regressions",
    "render_surface_work_queue",
    "surface_work_queue_to_json",
    "write_surface_work_queue",
]
