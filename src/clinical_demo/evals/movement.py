"""Baseline-vs-comparison eval movement artifacts."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from clinical_demo.extractor.schema import CriterionKind
from clinical_demo.matcher.verdict import Verdict, VerdictReason
from clinical_demo.scoring.score_pair import EligibilityRollup

from .run import CaseRecord, RunResult

MovementDirection = Literal[
    "same",
    "indeterminate_to_determinate",
    "determinate_to_indeterminate",
    "determinate_changed",
    "reason_changed",
]

ARTIFACT_SAFETY = {
    "public_export": "synthetic",
    "contains_real_patient_data": False,
    "source_data": "Synthetic Synthea patients and public ClinicalTrials.gov trial metadata.",
}


class CaseMovementRow(BaseModel):
    """One case whose eligibility rollup changed between two eval runs."""

    row_id: str
    pair_id: str
    patient_id: str
    nct_id: str
    eval_slice: str
    baseline_eligibility: EligibilityRollup
    comparison_eligibility: EligibilityRollup
    movement: str


class CriterionMovementRow(BaseModel):
    """One criterion whose verdict or reason changed between two eval runs."""

    row_id: str
    pair_id: str
    patient_id: str
    nct_id: str
    eval_slice: str
    criterion_index: int
    criterion_kind: CriterionKind
    criterion_source_text: str
    baseline_verdict: Verdict
    baseline_reason: VerdictReason
    comparison_verdict: Verdict
    comparison_reason: VerdictReason
    movement: str
    direction: MovementDirection
    baseline_evidence_under_assumption: bool
    comparison_evidence_under_assumption: bool
    comparison_compiled_id: str | None = None
    comparison_predicate_status: str | None = None
    comparison_predicate_kind: str | None = None
    comparison_predicate_ids: list[str] = Field(default_factory=list)
    comparison_support_ids: list[str] = Field(default_factory=list)
    comparison_gap_ids: list[str] = Field(default_factory=list)


class RunMovementSummary(BaseModel):
    """Count rollups for baseline-vs-comparison movement."""

    baseline_run_id: str
    comparison_run_id: str
    common_cases: int
    changed_cases: int
    compared_criteria: int
    changed_criteria: int
    by_case_movement: dict[str, int] = Field(default_factory=dict)
    by_criterion_movement: dict[str, int] = Field(default_factory=dict)
    by_direction: dict[MovementDirection, int] = Field(default_factory=dict)


class RunMovementReport(BaseModel):
    """Stable movement artifact for two persisted eval runs."""

    artifact_safety: dict[str, object] = Field(default_factory=lambda: dict(ARTIFACT_SAFETY))
    artifact_type: str = "run-movement-review"
    baseline_run_id: str
    comparison_run_id: str
    summary: RunMovementSummary
    case_movements: list[CaseMovementRow] = Field(default_factory=list)
    criterion_movements: list[CriterionMovementRow] = Field(default_factory=list)


def build_run_movement_report(
    baseline: RunResult,
    comparison: RunResult,
    *,
    include_reason_only: bool = False,
) -> RunMovementReport:
    """Compare two persisted runs and return changed cases/criteria."""

    baseline_records = _records_by_pair_id(baseline)
    comparison_records = _records_by_pair_id(comparison)
    common_pair_ids = sorted(baseline_records.keys() & comparison_records.keys())

    case_rows: list[CaseMovementRow] = []
    criterion_rows: list[CriterionMovementRow] = []
    compared_criteria = 0
    for pair_id in common_pair_ids:
        baseline_record = baseline_records[pair_id]
        comparison_record = comparison_records[pair_id]
        if baseline_record.result is None or comparison_record.result is None:
            continue

        if baseline_record.result.eligibility != comparison_record.result.eligibility:
            case_rows.append(_case_movement_row(baseline_record, comparison_record))

        common_criteria = min(
            len(baseline_record.result.verdicts),
            len(comparison_record.result.verdicts),
        )
        compared_criteria += common_criteria
        criterion_rows.extend(
            _criterion_movement_rows(
                baseline_record,
                comparison_record,
                criteria_count=common_criteria,
                include_reason_only=include_reason_only,
            )
        )

    summary = _summary(
        baseline_run_id=baseline.run_id,
        comparison_run_id=comparison.run_id,
        common_cases=len(common_pair_ids),
        case_rows=case_rows,
        compared_criteria=compared_criteria,
        criterion_rows=criterion_rows,
    )
    return RunMovementReport(
        baseline_run_id=baseline.run_id,
        comparison_run_id=comparison.run_id,
        summary=summary,
        case_movements=case_rows,
        criterion_movements=criterion_rows,
    )


def save_run_movement_report(report: RunMovementReport, path: str | Path) -> None:
    """Write a movement report as stable JSON."""

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report.model_dump_json(indent=2) + "\n")


def render_run_movement_report(report: RunMovementReport) -> str:
    """Render a concise Markdown movement review packet."""

    lines = [
        "Public-Artifact-Safety: synthetic",
        "",
        "# Run Movement Review",
        "",
        f"- baseline: `{report.baseline_run_id}`",
        f"- comparison: `{report.comparison_run_id}`",
        f"- changed cases: {report.summary.changed_cases}/{report.summary.common_cases}",
        f"- changed criteria: {report.summary.changed_criteria}/{report.summary.compared_criteria}",
    ]
    if report.summary.by_direction:
        directions = " / ".join(
            f"{key}={value}" for key, value in report.summary.by_direction.items()
        )
        lines.append(f"- criterion directions: {directions}")

    if report.case_movements:
        lines.extend(
            [
                "",
                "## Case Movements",
                "",
                "| Pair | Slice | Baseline | Comparison |",
                "|---|---|---:|---:|",
            ]
        )
        for case_row in report.case_movements:
            lines.append(
                f"| `{case_row.pair_id}` | {case_row.eval_slice or '(none)'} | "
                f"{case_row.baseline_eligibility} | {case_row.comparison_eligibility} |"
            )

    if report.criterion_movements:
        lines.extend(
            [
                "",
                "## Criterion Movements",
                "",
                "| Pair | # | Kind | Movement | Direction | Compiled predicate | Source |",
                "|---|---:|---|---|---|---|---|",
            ]
        )
        for criterion_row in report.criterion_movements:
            source = _markdown_cell(criterion_row.criterion_source_text, max_chars=100)
            predicate = criterion_row.comparison_predicate_kind or "(none)"
            lines.append(
                f"| `{criterion_row.pair_id}` | {criterion_row.criterion_index} | "
                f"{criterion_row.criterion_kind} | {criterion_row.movement} | "
                f"{criterion_row.direction} | {predicate} | {source} |"
            )

    return "\n".join(lines) + "\n"


def save_run_movement_markdown(report: RunMovementReport, path: str | Path) -> None:
    """Write a rendered movement report."""

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_run_movement_report(report))


def _records_by_pair_id(run: RunResult) -> dict[str, CaseRecord]:
    return {record.case.pair_id: record for record in run.cases}


def _case_movement_row(
    baseline_record: CaseRecord,
    comparison_record: CaseRecord,
) -> CaseMovementRow:
    assert baseline_record.result is not None
    assert comparison_record.result is not None
    movement = f"{baseline_record.result.eligibility}->{comparison_record.result.eligibility}"
    return CaseMovementRow(
        row_id=f"case:{baseline_record.case.pair_id}",
        pair_id=baseline_record.case.pair_id,
        patient_id=baseline_record.case.patient_id,
        nct_id=baseline_record.case.nct_id,
        eval_slice=baseline_record.case.slice,
        baseline_eligibility=baseline_record.result.eligibility,
        comparison_eligibility=comparison_record.result.eligibility,
        movement=movement,
    )


def _criterion_movement_rows(
    baseline_record: CaseRecord,
    comparison_record: CaseRecord,
    *,
    criteria_count: int,
    include_reason_only: bool,
) -> list[CriterionMovementRow]:
    assert baseline_record.result is not None
    assert comparison_record.result is not None
    compiled_by_index = (
        {
            criterion.source_index: criterion
            for criterion in (comparison_record.result.compilation.criteria)
        }
        if comparison_record.result.compilation is not None
        else {}
    )
    rows: list[CriterionMovementRow] = []
    for index in range(criteria_count):
        baseline_verdict = baseline_record.result.verdicts[index]
        comparison_verdict = comparison_record.result.verdicts[index]
        if baseline_verdict.verdict == comparison_verdict.verdict and (
            not include_reason_only or baseline_verdict.reason == comparison_verdict.reason
        ):
            continue
        compiled = compiled_by_index.get(index)
        movement = f"{baseline_verdict.verdict}->{comparison_verdict.verdict}"
        rows.append(
            CriterionMovementRow(
                row_id=f"criterion:{baseline_record.case.pair_id}:{index}",
                pair_id=baseline_record.case.pair_id,
                patient_id=baseline_record.case.patient_id,
                nct_id=baseline_record.case.nct_id,
                eval_slice=baseline_record.case.slice,
                criterion_index=index,
                criterion_kind=comparison_verdict.criterion.kind,
                criterion_source_text=comparison_verdict.criterion.source_text,
                baseline_verdict=baseline_verdict.verdict,
                baseline_reason=baseline_verdict.reason,
                comparison_verdict=comparison_verdict.verdict,
                comparison_reason=comparison_verdict.reason,
                movement=movement,
                direction=_movement_direction(baseline_verdict.verdict, comparison_verdict.verdict),
                baseline_evidence_under_assumption=baseline_verdict.evidence_under_assumption,
                comparison_evidence_under_assumption=(comparison_verdict.evidence_under_assumption),
                comparison_compiled_id=compiled.compiled_id if compiled is not None else None,
                comparison_predicate_status=compiled.predicate.status
                if compiled is not None
                else None,
                comparison_predicate_kind=compiled.predicate.predicate_kind
                if compiled is not None
                else None,
                comparison_predicate_ids=list(compiled.predicate.predicate_ids)
                if compiled is not None
                else [],
                comparison_support_ids=list(compiled.predicate.support_ids)
                if compiled is not None
                else [],
                comparison_gap_ids=list(compiled.predicate.gap_ids) if compiled is not None else [],
            )
        )
    return rows


def _movement_direction(
    baseline: Verdict,
    comparison: Verdict,
) -> MovementDirection:
    baseline_determinate = _is_determinate(baseline)
    comparison_determinate = _is_determinate(comparison)
    if not baseline_determinate and comparison_determinate:
        return "indeterminate_to_determinate"
    if baseline_determinate and not comparison_determinate:
        return "determinate_to_indeterminate"
    if baseline_determinate and comparison_determinate and baseline != comparison:
        return "determinate_changed"
    if baseline == comparison:
        return "reason_changed"
    return "reason_changed"


def _is_determinate(verdict: Verdict) -> bool:
    return verdict in {"pass", "fail"}


def _summary(
    *,
    baseline_run_id: str,
    comparison_run_id: str,
    common_cases: int,
    case_rows: list[CaseMovementRow],
    compared_criteria: int,
    criterion_rows: list[CriterionMovementRow],
) -> RunMovementSummary:
    return RunMovementSummary(
        baseline_run_id=baseline_run_id,
        comparison_run_id=comparison_run_id,
        common_cases=common_cases,
        changed_cases=len(case_rows),
        compared_criteria=compared_criteria,
        changed_criteria=len(criterion_rows),
        by_case_movement=dict(sorted(Counter(row.movement for row in case_rows).items())),
        by_criterion_movement=dict(sorted(Counter(row.movement for row in criterion_rows).items())),
        by_direction=dict(sorted(Counter(row.direction for row in criterion_rows).items())),
    )


def _markdown_cell(text: str, *, max_chars: int) -> str:
    cleaned = " ".join(text.replace("|", "\\|").split())
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 3].rstrip() + "..."


__all__ = [
    "ARTIFACT_SAFETY",
    "CaseMovementRow",
    "CriterionMovementRow",
    "MovementDirection",
    "RunMovementReport",
    "RunMovementSummary",
    "build_run_movement_report",
    "render_run_movement_report",
    "save_run_movement_markdown",
    "save_run_movement_report",
]
