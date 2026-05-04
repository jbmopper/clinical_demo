"""Tests for patient-side FHIR evidence calibration helpers."""

from __future__ import annotations

from datetime import datetime

from clinical_demo.evals.layer_three import (
    JudgeTarget,
    LayerThreeJudgment,
    LayerThreeReport,
    LayerThreeSourceContext,
    LayerThreeSourceRecord,
)
from clinical_demo.evals.patient_evidence import (
    PatientEvidenceHumanLabel,
    build_patient_evidence_rows,
    patient_evidence_bucket,
    select_patient_evidence_targets,
    summarize_patient_evidence_rows,
)
from clinical_demo.evals.run import CaseRecord, EvalCase, RunResult
from clinical_demo.matcher import (
    DEFAULT_MATCHER_ASSUMPTION_MODE,
    MATCHER_VERSION,
    MatchVerdict,
    Verdict,
    VerdictReason,
)
from tests.matcher._fixtures import crit_age, crit_condition, crit_measurement

from ._fixtures import AS_OF, make_score_pair_result


def _case(pair_id: str = "p1__T1", *, slice: str = "t2dm-industry") -> EvalCase:
    return EvalCase(
        pair_id=pair_id,
        patient_id="p1",
        nct_id="T1",
        as_of=AS_OF,
        slice=slice,
    )


def _run(verdicts: list[MatchVerdict]) -> RunResult:
    return RunResult(
        started_at=datetime(2025, 1, 1, 0, 0, 0),
        finished_at=datetime(2025, 1, 1, 0, 0, 1),
        dataset_path="seed.json",
        notes="patient evidence test",
        cases=[
            CaseRecord(
                case=_case(),
                result=make_score_pair_result(verdicts=verdicts),
            )
        ],
    )


def _verdict(
    criterion_kind: str = "condition_present",
    *,
    verdict: Verdict = "indeterminate",
    reason: VerdictReason = "unmapped_concept",
) -> MatchVerdict:
    if criterion_kind == "measurement_threshold":
        criterion = crit_measurement()
    elif criterion_kind == "age":
        criterion = crit_age()
    else:
        criterion = crit_condition()
    return MatchVerdict(
        criterion=criterion,
        verdict=verdict,
        reason=reason,
        rationale="test rationale",
        evidence=[],
        matcher_version=MATCHER_VERSION,
    )


def _report(judgments: list[LayerThreeJudgment]) -> LayerThreeReport:
    return LayerThreeReport(
        judgments=judgments,
        total_judgments=len(judgments),
        label_counts={},
        confidence_counts={},
        error_category_counts={},
    )


def _judgment(
    target: JudgeTarget,
    *,
    label: str = "incorrect",
) -> LayerThreeJudgment:
    return LayerThreeJudgment(
        pair_id=target.pair_id,
        patient_id=target.patient_id,
        nct_id=target.nct_id,
        criterion_index=target.criterion_index,
        matcher_verdict=target.verdict.verdict,
        judge_label=label,  # type: ignore[arg-type]
        confidence="high",
        error_categories=["wrong_verdict"] if label == "incorrect" else [],
        rationale="judge rationale",
    )


def test_select_patient_evidence_targets_prioritizes_judge_incorrect_rows() -> None:
    run = _run(
        [
            _verdict("condition_present", reason="unmapped_concept"),
            _verdict("age", verdict="pass", reason="ok"),
            _verdict("measurement_threshold", reason="unit_mismatch"),
        ]
    )
    all_targets = [
        JudgeTarget(
            pair_id=record.case.pair_id,
            patient_id=record.case.patient_id,
            nct_id=record.case.nct_id,
            criterion_index=index,
            verdict=verdict,
        )
        for record in run.cases
        for index, verdict in enumerate(record.result.verdicts if record.result else [])
    ]
    report = _report([_judgment(all_targets[2])])

    selected = select_patient_evidence_targets(run, judge_report=report, limit=2)

    assert selected[0].criterion_index == 2
    assert {target.criterion_index for target in selected[1:]} <= {0, 2}


def test_select_patient_evidence_targets_filters_to_cardiometabolic_scope() -> None:
    run = _run([])
    run.cases = [
        CaseRecord(
            case=_case("oncology", slice="nsclc"),
            result=make_score_pair_result(verdicts=[_verdict("condition_present")]),
        ),
        CaseRecord(
            case=_case("diabetes", slice="t2dm-industry"),
            result=make_score_pair_result(verdicts=[_verdict("condition_present")]),
        ),
    ]

    selected = select_patient_evidence_targets(run, limit=10)

    assert [target.pair_id for target in selected] == ["diabetes"]


def test_patient_evidence_bucket_ignores_non_patient_evidence_judge_errors() -> None:
    age = JudgeTarget(
        pair_id="p1__T1",
        patient_id="p1",
        nct_id="T1",
        criterion_index=0,
        verdict=_verdict("age", verdict="pass", reason="ok"),
    )

    assert patient_evidence_bucket(age, _judgment(age)) is None


def test_patient_evidence_bucket_focuses_patient_side_cases() -> None:
    measurement = JudgeTarget(
        pair_id="p1__T1",
        patient_id="p1",
        nct_id="T1",
        criterion_index=0,
        verdict=_verdict("measurement_threshold", reason="unit_mismatch"),
    )
    age = JudgeTarget(
        pair_id="p1__T1",
        patient_id="p1",
        nct_id="T1",
        criterion_index=1,
        verdict=_verdict("age", verdict="pass", reason="ok"),
    )

    assert patient_evidence_bucket(measurement) == "measurement_or_unit"
    assert patient_evidence_bucket(age) is None


def test_build_patient_evidence_rows_attaches_source_row_ids_and_labels() -> None:
    target = JudgeTarget(
        pair_id="p1__T1",
        patient_id="p1",
        nct_id="T1",
        criterion_index=0,
        verdict=_verdict("condition_present", reason="unmapped_concept"),
    )
    context = LayerThreeSourceContext(
        patient=[
            LayerThreeSourceRecord(
                source="patient",
                kind="condition",
                label="Type 2 diabetes mellitus",
                value="Type 2 diabetes mellitus",
                code="44054006",
                system="http://snomed.info/sct",
            )
        ],
        trial=[
            LayerThreeSourceRecord(
                source="trial",
                kind="trial_field",
                label="Title",
                value="Test trial",
            )
        ],
    )

    rows = build_patient_evidence_rows(
        [target],
        source_contexts={"p1__T1": context},
        existing_labels=[
            PatientEvidenceHumanLabel(
                pair_id="p1__T1",
                criterion_index=0,
                label="supports_present",
                cited_source_row_ids=["patient:000"],
                expected_matcher_verdict="pass",
            )
        ],
    )

    assert rows[0].source_rows[0].row_id == "patient:000"
    assert rows[0].source_rows[1].row_id == "trial:000"
    assert rows[0].eval_slice == ""
    assert rows[0].matcher_assumption_mode == DEFAULT_MATCHER_ASSUMPTION_MODE
    assert rows[0].retrieved_source_row_ids == ["patient:000"]
    assert rows[0].retrieval_reasons["patient:000"]
    assert rows[0].existing_label is not None
    assert rows[0].existing_label.label == "supports_present"
    assert rows[0].existing_label.matcher_assumption_mode == DEFAULT_MATCHER_ASSUMPTION_MODE
    assert summarize_patient_evidence_rows(rows) == {"condition_present": 1}
