from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path

from tests.evals._fixtures import AS_OF, make_score_pair_result
from tests.matcher._fixtures import crit_condition

from clinical_demo.compiler import compile_extracted_criteria
from clinical_demo.evals.run import CaseRecord, EvalCase, RunResult
from clinical_demo.evals.store import open_store, save_run

MODULE_PATH = Path(__file__).parents[2] / "scripts" / "eval.py"
SPEC = importlib.util.spec_from_file_location("eval_cli", MODULE_PATH)
assert SPEC is not None
eval_cli = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = eval_cli
SPEC.loader.exec_module(eval_cli)


def test_compiler_review_command_writes_gap_artifact(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "runs.sqlite"
    output_path = tmp_path / "review" / "compiler_gaps.json"
    grouped_output_path = tmp_path / "review" / "compiler_gap_groups.json"
    case = EvalCase(
        pair_id="pair-1",
        patient_id="P-1",
        nct_id="NCT00000001",
        as_of=AS_OF,
        slice="compiler-fixture",
    )
    result = make_score_pair_result(
        patient_id=case.patient_id,
        nct_id=case.nct_id,
    ).model_copy(
        update={
            "compilation": compile_extracted_criteria(
                [crit_condition(text="definitely unmapped syndrome xyz")]
            )
        }
    )
    run = RunResult(
        run_id="compiler-review-run",
        started_at=datetime(2025, 1, 1, 0, 0, 0),
        finished_at=datetime(2025, 1, 1, 0, 0, 1),
        dataset_path="seed.json",
        notes="compiler review test",
        cases=[CaseRecord(case=case, result=result)],
    )
    with open_store(db_path) as conn:
        save_run(conn, run)

    rc = eval_cli._cmd_compiler_review(
        argparse.Namespace(
            db=db_path,
            run_id="compiler-review-run",
            output=output_path,
            grouped_output=grouped_output_path,
            format="text",
        )
    )

    assert rc == 0
    stdout = capsys.readouterr().out
    assert "compiler gap review rows for run compiler-review-run: 1" in stdout
    assert "deduped compiler gap groups: 1" in stdout
    assert "review_mapping: 1" in stdout
    payload = json.loads(output_path.read_text())
    assert payload["rows"][0]["pair_id"] == "pair-1"
    assert payload["rows"][0]["gap_kind"] == "unmapped_concept"
    group_payload = json.loads(grouped_output_path.read_text())
    assert group_payload["groups"][0]["occurrence_count"] == 1
    assert group_payload["groups"][0]["example_rows"][0]["pair_id"] == "pair-1"
