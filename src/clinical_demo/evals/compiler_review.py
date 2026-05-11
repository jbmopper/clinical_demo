"""Eval artifact projection for unresolved compiler reviewer gaps."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from hashlib import sha1
from pathlib import Path

from pydantic import BaseModel, Field

from clinical_demo.compiler import compiler_gap_queue
from clinical_demo.compiler.reviewer_queue import RecommendedAction, Severity
from clinical_demo.compiler.schema import (
    CompiledCriterion,
    ResolutionDomain,
    ResolutionGapKind,
    ResolutionStage,
)
from clinical_demo.extractor.schema import CriterionKind
from clinical_demo.settings import ResolverExecutionPolicy

from .run import RunResult


class CompilerGapReviewRow(BaseModel):
    """One stable reviewer artifact row for a compiler gap in an eval run."""

    row_id: str = Field(description="Stable row id derived from pair id and compiler gap id.")
    pair_id: str
    patient_id: str
    nct_id: str
    eval_slice: str
    criterion_index: int = Field(description="Zero-based criterion index in source criteria.")
    source_index: int = Field(description="Alias of criterion_index for compiler queue parity.")
    source_criterion_id: str
    compiled_id: str | None = Field(description="Compiled criterion id, when findable.")
    criterion_kind: CriterionKind
    criterion_source_text: str
    gap_id: str
    gap_kind: ResolutionGapKind
    stage: ResolutionStage
    domain: ResolutionDomain
    surface: str | None
    message: str
    resolver_policy: ResolverExecutionPolicy
    recommended_action: RecommendedAction
    priority: int
    severity: Severity


class CompilerGapReviewSummary(BaseModel):
    """Small count summary for a compiler gap review artifact."""

    total_rows: int
    by_recommended_action: dict[str, int]
    by_severity: dict[str, int]
    by_gap_kind: dict[str, int]


class CompilerGapReviewExample(BaseModel):
    """One concise row example attached to a deduped compiler gap group."""

    row_id: str
    pair_id: str
    nct_id: str
    eval_slice: str
    criterion_index: int
    criterion_kind: CriterionKind
    criterion_source_text: str
    gap_id: str
    message: str


class CompilerGapReviewGroup(BaseModel):
    """Deduped reviewer work item grouping equivalent compiler gap rows."""

    group_id: str = Field(description="Stable id derived from the group key.")
    recommended_action: RecommendedAction
    priority: int
    severity: Severity
    gap_kind: ResolutionGapKind
    stage: ResolutionStage
    domain: ResolutionDomain
    surface: str | None
    normalized_surface: str
    resolver_policy: ResolverExecutionPolicy
    occurrence_count: int
    case_count: int
    trial_count: int
    eval_slices: list[str]
    criterion_kinds: list[CriterionKind]
    message_examples: list[str]
    example_rows: list[CompilerGapReviewExample]


class CompilerGapReviewGroupSummary(BaseModel):
    """Small count summary for deduped compiler gap review groups."""

    total_rows: int
    total_groups: int
    by_recommended_action: dict[str, int]
    by_severity: dict[str, int]
    by_gap_kind: dict[str, int]
    by_domain: dict[str, int]


type CompilerGapReviewRows = list[CompilerGapReviewRow]
type CompilerGapReviewGroups = list[CompilerGapReviewGroup]


ARTIFACT_SAFETY = {
    "public_export": "synthetic",
    "contains_real_patient_data": False,
    "source_data": "Synthetic Synthea patients and public ClinicalTrials.gov trial metadata.",
}


def build_compiler_gap_review_rows(run: RunResult) -> CompilerGapReviewRows:
    """Project unresolved compiler gaps from a persisted eval run into review rows."""

    rows: list[CompilerGapReviewRow] = []
    for record in run.cases:
        result = record.result
        if result is None or result.compilation is None:
            continue

        compiled_by_source = {
            criterion.source_criterion_id: criterion for criterion in result.compilation.criteria
        }
        for item in compiler_gap_queue(result.compilation):
            criterion = compiled_by_source.get(item.source_criterion_id)
            rows.append(
                CompilerGapReviewRow(
                    row_id=f"{record.case.pair_id}:{item.gap_id}",
                    pair_id=record.case.pair_id,
                    patient_id=record.case.patient_id,
                    nct_id=record.case.nct_id,
                    eval_slice=record.case.slice,
                    criterion_index=item.source_index,
                    source_index=item.source_index,
                    source_criterion_id=item.source_criterion_id,
                    compiled_id=_compiled_id(criterion),
                    criterion_kind=item.criterion_kind,
                    criterion_source_text=_criterion_source_text(criterion),
                    gap_id=item.gap_id,
                    gap_kind=item.gap_kind,
                    stage=item.stage,
                    domain=item.domain,
                    surface=item.surface,
                    message=item.message,
                    resolver_policy=item.resolver_policy,
                    recommended_action=item.recommended_action,
                    priority=item.priority,
                    severity=item.severity,
                )
            )

    return sorted(rows, key=_row_sort_key)


def save_compiler_gap_review_rows(
    rows: CompilerGapReviewRows,
    path: str | Path,
) -> None:
    """Write compiler review rows as a stable JSON list artifact."""

    ordered = sorted(rows, key=_row_sort_key)
    payload = {
        "artifact_safety": ARTIFACT_SAFETY,
        "artifact_type": "compiler-gap-review-rows",
        "rows": [row.model_dump(mode="json") for row in ordered],
    }
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def build_compiler_gap_review_groups(
    rows: Sequence[CompilerGapReviewRow],
    *,
    max_examples_per_group: int = 3,
    max_message_examples_per_group: int = 3,
) -> CompilerGapReviewGroups:
    """Deduplicate review rows into stable surface/action work items."""

    grouped: dict[_ReviewGroupKey, list[CompilerGapReviewRow]] = defaultdict(list)
    for row in rows:
        grouped[_group_key(row)].append(row)

    groups = [
        _review_group_for_rows(
            group_rows,
            max_examples_per_group=max_examples_per_group,
            max_message_examples_per_group=max_message_examples_per_group,
        )
        for group_rows in grouped.values()
    ]
    return sorted(groups, key=_group_sort_key)


def save_compiler_gap_review_groups(
    groups: CompilerGapReviewGroups,
    path: str | Path,
) -> None:
    """Write deduped compiler review groups as a stable JSON artifact."""

    ordered = sorted(groups, key=_group_sort_key)
    payload = {
        "artifact_safety": ARTIFACT_SAFETY,
        "artifact_type": "compiler-gap-review-groups",
        "groups": [group.model_dump(mode="json") for group in ordered],
    }
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def load_compiler_gap_review_groups(path: str | Path) -> CompilerGapReviewGroups:
    """Load deduped compiler review groups from a JSON list artifact."""

    raw = json.loads(Path(path).read_text())
    if isinstance(raw, dict):
        raw = raw.get("groups")
    if not isinstance(raw, list):
        raise ValueError("compiler gap review group artifact must contain a JSON list")
    return [CompilerGapReviewGroup.model_validate(item) for item in raw]


def load_compiler_gap_review_rows(path: str | Path) -> CompilerGapReviewRows:
    """Load compiler review rows from a JSON list artifact."""

    raw = json.loads(Path(path).read_text())
    if isinstance(raw, dict):
        raw = raw.get("rows")
    if not isinstance(raw, list):
        raise ValueError("compiler gap review artifact must contain a JSON list")
    return [CompilerGapReviewRow.model_validate(item) for item in raw]


def summarize_compiler_gap_review_rows(
    rows: CompilerGapReviewRows,
) -> CompilerGapReviewSummary:
    """Return count rollups for a compiler gap review artifact."""

    return CompilerGapReviewSummary(
        total_rows=len(rows),
        by_recommended_action=dict(sorted(Counter(row.recommended_action for row in rows).items())),
        by_severity=dict(sorted(Counter(row.severity for row in rows).items())),
        by_gap_kind=dict(sorted(Counter(row.gap_kind for row in rows).items())),
    )


def summarize_compiler_gap_review_groups(
    groups: CompilerGapReviewGroups,
) -> CompilerGapReviewGroupSummary:
    """Return count rollups for deduped compiler gap review groups."""

    return CompilerGapReviewGroupSummary(
        total_rows=sum(group.occurrence_count for group in groups),
        total_groups=len(groups),
        by_recommended_action=dict(
            sorted(Counter(group.recommended_action for group in groups).items())
        ),
        by_severity=dict(sorted(Counter(group.severity for group in groups).items())),
        by_gap_kind=dict(sorted(Counter(group.gap_kind for group in groups).items())),
        by_domain=dict(sorted(Counter(group.domain for group in groups).items())),
    )


def _compiled_id(criterion: CompiledCriterion | None) -> str | None:
    if criterion is None:
        return None
    return criterion.compiled_id


def _criterion_source_text(criterion: CompiledCriterion | None) -> str:
    if criterion is None:
        return ""
    return criterion.source_text


def _row_sort_key(row: CompilerGapReviewRow) -> tuple[int, str, int, str, str]:
    return (row.priority, row.pair_id, row.source_index, row.gap_id, row.row_id)


type _ReviewGroupKey = tuple[
    RecommendedAction,
    ResolutionGapKind,
    ResolutionStage,
    ResolutionDomain,
    str,
    ResolverExecutionPolicy,
]


def _group_key(row: CompilerGapReviewRow) -> _ReviewGroupKey:
    return (
        row.recommended_action,
        row.gap_kind,
        row.stage,
        row.domain,
        _normalize_surface(row.surface),
        row.resolver_policy,
    )


def _review_group_for_rows(
    rows: list[CompilerGapReviewRow],
    *,
    max_examples_per_group: int,
    max_message_examples_per_group: int,
) -> CompilerGapReviewGroup:
    ordered = sorted(rows, key=_row_sort_key)
    first = ordered[0]
    key = _group_key(first)
    return CompilerGapReviewGroup(
        group_id=_group_id(key),
        recommended_action=first.recommended_action,
        priority=min(row.priority for row in ordered),
        severity=_max_severity(row.severity for row in ordered),
        gap_kind=first.gap_kind,
        stage=first.stage,
        domain=first.domain,
        surface=_display_surface(ordered),
        normalized_surface=key[4],
        resolver_policy=first.resolver_policy,
        occurrence_count=len(ordered),
        case_count=len({row.pair_id for row in ordered}),
        trial_count=len({row.nct_id for row in ordered}),
        eval_slices=_sorted_nonblank({row.eval_slice for row in ordered}),
        criterion_kinds=sorted({row.criterion_kind for row in ordered}),
        message_examples=_message_examples(
            ordered,
            max_message_examples_per_group=max_message_examples_per_group,
        ),
        example_rows=[_example_for_row(row) for row in ordered[: max(0, max_examples_per_group)]],
    )


def _group_id(key: _ReviewGroupKey) -> str:
    encoded = "\x1f".join(str(part) for part in key)
    digest = sha1(encoded.encode("utf-8")).hexdigest()[:12]
    return f"compiler-gap-group:{digest}"


def _normalize_surface(surface: str | None) -> str:
    if surface is None:
        return ""
    return " ".join(surface.lower().strip(".,;:()[]{}\"'").split())


def _display_surface(rows: Sequence[CompilerGapReviewRow]) -> str | None:
    surfaces = [row.surface for row in rows if row.surface]
    if not surfaces:
        return None
    return Counter(surfaces).most_common(1)[0][0]


def _sorted_nonblank(values: set[str]) -> list[str]:
    return sorted(value for value in values if value)


def _message_examples(
    rows: Sequence[CompilerGapReviewRow],
    *,
    max_message_examples_per_group: int,
) -> list[str]:
    examples: list[str] = []
    seen: set[str] = set()
    for row in rows:
        if row.message in seen:
            continue
        seen.add(row.message)
        examples.append(row.message)
        if len(examples) >= max(0, max_message_examples_per_group):
            break
    return examples


def _example_for_row(row: CompilerGapReviewRow) -> CompilerGapReviewExample:
    return CompilerGapReviewExample(
        row_id=row.row_id,
        pair_id=row.pair_id,
        nct_id=row.nct_id,
        eval_slice=row.eval_slice,
        criterion_index=row.criterion_index,
        criterion_kind=row.criterion_kind,
        criterion_source_text=row.criterion_source_text,
        gap_id=row.gap_id,
        message=row.message,
    )


def _max_severity(severities: Iterable[Severity]) -> Severity:
    rank: dict[Severity, int] = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    return min(severities, key=lambda severity: rank[severity])


def _group_sort_key(group: CompilerGapReviewGroup) -> tuple[int, int, str, str, str, str]:
    return (
        group.priority,
        -group.occurrence_count,
        group.recommended_action,
        group.domain,
        group.normalized_surface,
        group.group_id,
    )


__all__ = [
    "ARTIFACT_SAFETY",
    "CompilerGapReviewExample",
    "CompilerGapReviewGroup",
    "CompilerGapReviewGroupSummary",
    "CompilerGapReviewGroups",
    "CompilerGapReviewRow",
    "CompilerGapReviewRows",
    "CompilerGapReviewSummary",
    "build_compiler_gap_review_groups",
    "build_compiler_gap_review_rows",
    "load_compiler_gap_review_groups",
    "load_compiler_gap_review_rows",
    "save_compiler_gap_review_groups",
    "save_compiler_gap_review_rows",
    "summarize_compiler_gap_review_groups",
    "summarize_compiler_gap_review_rows",
]
