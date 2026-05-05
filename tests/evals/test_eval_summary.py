"""Tests for the eval CLI summary renderer."""

from __future__ import annotations

from datetime import datetime

from scripts.eval import _summarize

from clinical_demo.evals.run import CaseRecord, EvalCase, RunResult

from ._fixtures import AS_OF, make_score_pair_result


def test_eval_summary_includes_zero_pass_pending_review_bucket() -> None:
    run = RunResult(
        started_at=datetime(2026, 5, 1, 0, 0, 0),
        finished_at=datetime(2026, 5, 1, 0, 0, 1),
        dataset_path="seed.json",
        notes="summary test",
        cases=[
            CaseRecord(
                case=EvalCase(
                    pair_id="p1__T1",
                    patient_id="p1",
                    nct_id="T1",
                    as_of=AS_OF,
                    slice="slice-a",
                ),
                result=make_score_pair_result(eligibility="pass"),
                scoring_latency_ms=1.0,
            )
        ],
    )

    out = _summarize(run)

    assert "eligibility: fail=0  indeterminate=0  pass=1  pass_pending_review=0" in out
