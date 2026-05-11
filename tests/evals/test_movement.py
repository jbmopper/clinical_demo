from __future__ import annotations

import json
from datetime import datetime

from clinical_demo.compiler import compile_extracted_criteria
from clinical_demo.evals.movement import (
    build_run_movement_report,
    render_run_movement_report,
    save_run_movement_markdown,
    save_run_movement_report,
)
from clinical_demo.evals.run import CaseRecord, EvalCase, RunResult
from clinical_demo.matcher import MATCHER_VERSION
from clinical_demo.matcher.verdict import MatchVerdict, Verdict, VerdictReason
from tests.evals._fixtures import AS_OF, make_score_pair_result
from tests.matcher._fixtures import crit_condition


def _case(pair_id: str = "pair-1") -> EvalCase:
    return EvalCase(
        pair_id=pair_id,
        patient_id="P-1",
        nct_id="NCT00000001",
        as_of=AS_OF,
        slice="movement-fixture",
    )


def _run(run_id: str, records: list[CaseRecord]) -> RunResult:
    now = datetime(2025, 1, 1, 12, 0, 0)
    return RunResult(
        run_id=run_id,
        started_at=now,
        finished_at=now,
        dataset_path="memory://movement",
        notes="movement fixture",
        cases=records,
    )


def _verdict(
    *,
    verdict: Verdict,
    reason: VerdictReason = "ok",
    text: str = "type 2 diabetes",
    evidence_under_assumption: bool = False,
) -> MatchVerdict:
    criterion = crit_condition(text=text)
    return MatchVerdict(
        criterion=criterion,
        verdict=verdict,
        reason=reason,
        rationale="movement fixture",
        evidence=[],
        matcher_version=MATCHER_VERSION,
        evidence_under_assumption=evidence_under_assumption,
    )


def _record(
    *,
    pair_id: str = "pair-1",
    eligibility: str,
    verdicts: list[MatchVerdict],
    include_compilation: bool = False,
) -> CaseRecord:
    case = _case(pair_id)
    result = make_score_pair_result(
        patient_id=case.patient_id,
        nct_id=case.nct_id,
        eligibility=eligibility,  # type: ignore[arg-type]
        verdicts=verdicts,
    )
    if include_compilation:
        result = result.model_copy(
            update={
                "compilation": compile_extracted_criteria(
                    [verdict.criterion for verdict in verdicts]
                )
            }
        )
    return CaseRecord(case=case, result=result)


def test_build_run_movement_report_projects_case_and_criterion_changes() -> None:
    baseline = _run(
        "baseline",
        [
            _record(
                eligibility="indeterminate",
                verdicts=[
                    _verdict(verdict="indeterminate", reason="unmapped_concept"),
                    _verdict(verdict="pass"),
                ],
            )
        ],
    )
    comparison = _run(
        "comparison",
        [
            _record(
                eligibility="fail",
                verdicts=[
                    _verdict(verdict="fail", text="type 2 diabetes"),
                    _verdict(verdict="pass"),
                ],
                include_compilation=True,
            )
        ],
    )

    report = build_run_movement_report(baseline, comparison)

    assert report.summary.common_cases == 1
    assert report.summary.changed_cases == 1
    assert report.summary.compared_criteria == 2
    assert report.summary.changed_criteria == 1
    assert report.summary.by_case_movement == {"indeterminate->fail": 1}
    assert report.summary.by_direction == {"indeterminate_to_determinate": 1}
    row = report.criterion_movements[0]
    assert row.pair_id == "pair-1"
    assert row.criterion_index == 0
    assert row.baseline_reason == "unmapped_concept"
    assert row.comparison_verdict == "fail"
    assert row.comparison_predicate_kind == "condition_presence"
    assert row.comparison_compiled_id == "compiled:criterion:0"


def test_save_run_movement_report_writes_safety_metadata(tmp_path) -> None:
    report = build_run_movement_report(
        _run(
            "baseline",
            [
                _record(
                    eligibility="indeterminate",
                    verdicts=[_verdict(verdict="indeterminate", reason="no_data")],
                )
            ],
        ),
        _run("comparison", [_record(eligibility="fail", verdicts=[_verdict(verdict="fail")])]),
    )
    json_path = tmp_path / "movement.json"
    md_path = tmp_path / "movement.md"

    save_run_movement_report(report, json_path)
    save_run_movement_markdown(report, md_path)

    payload = json.loads(json_path.read_text())
    assert payload["artifact_safety"]["public_export"] == "synthetic"
    assert payload["summary"]["changed_criteria"] == 1
    assert md_path.read_text().startswith("Public-Artifact-Safety: synthetic")
    assert "indeterminate_to_determinate" in render_run_movement_report(report)


def test_build_run_movement_report_skips_reason_only_changes_by_default() -> None:
    baseline = _run(
        "baseline",
        [
            _record(
                eligibility="indeterminate",
                verdicts=[_verdict(verdict="indeterminate", reason="unmapped_concept")],
            )
        ],
    )
    comparison = _run(
        "comparison",
        [
            _record(
                eligibility="indeterminate",
                verdicts=[_verdict(verdict="indeterminate", reason="human_review_required")],
            )
        ],
    )

    default_report = build_run_movement_report(baseline, comparison)
    full_report = build_run_movement_report(baseline, comparison, include_reason_only=True)

    assert default_report.summary.changed_criteria == 0
    assert full_report.summary.changed_criteria == 1
    assert full_report.summary.by_direction == {"reason_changed": 1}
