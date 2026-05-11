"""Eval artifact projection for unresolved compiler reviewer gaps."""

from __future__ import annotations

import json
from collections import Counter
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


type CompilerGapReviewRows = list[CompilerGapReviewRow]


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
    payload = [row.model_dump(mode="json") for row in ordered]
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def load_compiler_gap_review_rows(path: str | Path) -> CompilerGapReviewRows:
    """Load compiler review rows from a JSON list artifact."""

    raw = json.loads(Path(path).read_text())
    if not isinstance(raw, list):
        raise ValueError("compiler gap review artifact must be a JSON list")
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


__all__ = [
    "CompilerGapReviewRow",
    "CompilerGapReviewRows",
    "CompilerGapReviewSummary",
    "build_compiler_gap_review_rows",
    "load_compiler_gap_review_rows",
    "save_compiler_gap_review_rows",
    "summarize_compiler_gap_review_rows",
]
