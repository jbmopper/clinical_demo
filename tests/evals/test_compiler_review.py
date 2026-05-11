from __future__ import annotations

import json
from datetime import datetime

from clinical_demo.compiler import compile_extracted_criteria
from clinical_demo.evals.compiler_review import (
    build_compiler_gap_review_groups,
    build_compiler_gap_review_rows,
    load_compiler_gap_review_groups,
    load_compiler_gap_review_rows,
    save_compiler_gap_review_groups,
    save_compiler_gap_review_rows,
    summarize_compiler_gap_review_groups,
    summarize_compiler_gap_review_rows,
)
from clinical_demo.evals.run import CaseRecord, EvalCase, RunResult
from clinical_demo.extractor.schema import (
    ConditionCriterion,
    ExtractedCriterion,
    MeasurementCriterion,
)
from tests.evals._fixtures import AS_OF, make_score_pair_result


def _condition(text: str) -> ExtractedCriterion:
    return ExtractedCriterion(
        kind="condition_present",
        polarity="inclusion",
        source_text=f"History of {text}",
        negated=False,
        mood="historical",
        age=None,
        sex=None,
        condition=ConditionCriterion(condition_text=text),
        medication=None,
        measurement=None,
        temporal_window=None,
        free_text=None,
        mentions=[],
    )


def _measurement(text: str, unit: str | None = None) -> ExtractedCriterion:
    return ExtractedCriterion(
        kind="measurement_threshold",
        polarity="inclusion",
        source_text=f"{text} >= 7{unit or ''}",
        negated=False,
        mood="actual",
        age=None,
        sex=None,
        condition=None,
        medication=None,
        measurement=MeasurementCriterion(
            measurement_text=text,
            operator=">=",
            value=7.0,
            value_low=None,
            value_high=None,
            unit=unit,
        ),
        temporal_window=None,
        free_text=None,
        mentions=[],
    )


def _case(pair_id: str, *, patient_id: str = "P-1", nct_id: str = "NCT00000001") -> EvalCase:
    return EvalCase(
        pair_id=pair_id,
        patient_id=patient_id,
        nct_id=nct_id,
        as_of=AS_OF,
        slice="compiler-fixture",
    )


def _run(records: list[CaseRecord]) -> RunResult:
    now = datetime(2025, 1, 1, 12, 0, 0)
    return RunResult(
        run_id="compiler-review-test",
        started_at=now,
        finished_at=now,
        dataset_path="memory://compiler-review",
        notes="compiler review fixture",
        cases=records,
    )


def _record(pair_id: str, criteria: list[ExtractedCriterion]) -> CaseRecord:
    case = _case(pair_id)
    result = make_score_pair_result(
        patient_id=case.patient_id,
        nct_id=case.nct_id,
    ).model_copy(update={"compilation": compile_extracted_criteria(criteria)})
    return CaseRecord(case=case, result=result)


def test_build_rows_projects_unmapped_condition_and_missing_unit() -> None:
    run = _run([_record("pair-1", [_condition("rare unknown syndrome"), _measurement("BNP")])])

    rows = build_compiler_gap_review_rows(run)

    assert [row.gap_kind for row in rows] == [
        "unmapped_concept",
        "unmapped_concept",
        "missing_unit",
    ]
    condition = rows[0]
    assert condition.row_id == f"pair-1:{condition.gap_id}"
    assert condition.pair_id == "pair-1"
    assert condition.patient_id == "P-1"
    assert condition.nct_id == "NCT00000001"
    assert condition.eval_slice == "compiler-fixture"
    assert condition.criterion_index == 0
    assert condition.source_index == 0
    assert condition.source_criterion_id == "criterion:0"
    assert condition.compiled_id == "compiled:criterion:0"
    assert condition.criterion_kind == "condition_present"
    assert condition.criterion_source_text == "History of rare unknown syndrome"
    assert condition.domain == "condition"
    assert condition.surface == "rare unknown syndrome"
    assert condition.recommended_action == "review_mapping"
    assert condition.priority == 20
    assert condition.severity == "high"

    missing_unit = rows[2]
    assert missing_unit.gap_kind == "missing_unit"
    assert missing_unit.domain == "unit"
    assert missing_unit.surface == "BNP"
    assert missing_unit.recommended_action == "add_unit_mapping"
    assert missing_unit.criterion_source_text == "BNP >= 7"


def test_build_rows_skips_missing_result_or_compilation() -> None:
    no_result = CaseRecord(case=_case("pair-error"), result=None, error="boom")
    no_compilation = CaseRecord(
        case=_case("pair-old"),
        result=make_score_pair_result(),
    )
    with_compilation = _record("pair-ok", [_condition("rare unknown syndrome")])

    rows = build_compiler_gap_review_rows(_run([no_result, no_compilation, with_compilation]))

    assert [row.pair_id for row in rows] == ["pair-ok"]


def test_build_rows_sort_by_priority_pair_source_index_gap_id() -> None:
    run = _run(
        [
            _record("pair-b", [_measurement("BNP")]),
            _record("pair-a", [_condition("rare unknown syndrome")]),
        ]
    )

    rows = build_compiler_gap_review_rows(run)

    assert [(row.priority, row.pair_id, row.source_index, row.gap_kind) for row in rows] == [
        (20, "pair-a", 0, "unmapped_concept"),
        (20, "pair-b", 0, "unmapped_concept"),
        (40, "pair-b", 0, "missing_unit"),
    ]


def test_json_round_trip_uses_stable_list_artifact(tmp_path) -> None:
    rows = build_compiler_gap_review_rows(
        _run([_record("pair-1", [_condition("rare unknown syndrome"), _measurement("BNP")])])
    )
    path = tmp_path / "compiler-review.json"

    save_compiler_gap_review_rows(list(reversed(rows)), path)

    assert load_compiler_gap_review_rows(path) == rows
    text = path.read_text()
    assert text.endswith("\n")
    payload = json.loads(text)
    assert payload["artifact_safety"]["public_export"] == "synthetic"
    assert [item["row_id"] for item in payload["rows"]] == [row.row_id for row in rows]


def test_summary_counts_actions_severity_and_gap_kind() -> None:
    rows = build_compiler_gap_review_rows(
        _run([_record("pair-1", [_condition("rare unknown syndrome"), _measurement("BNP")])])
    )

    summary = summarize_compiler_gap_review_rows(rows)

    assert summary.total_rows == 3
    assert summary.by_recommended_action == {
        "review_mapping": 2,
        "add_unit_mapping": 1,
    }
    assert summary.by_severity == {"high": 3}
    assert summary.by_gap_kind == {"unmapped_concept": 2, "missing_unit": 1}


def test_build_groups_dedupes_equivalent_surface_gaps() -> None:
    rows = build_compiler_gap_review_rows(
        _run(
            [
                _record("pair-1", [_condition("rare unknown syndrome")]),
                _record("pair-2", [_condition("rare unknown syndrome")]),
            ]
        )
    )

    groups = build_compiler_gap_review_groups(rows)

    assert len(rows) == 2
    assert len(groups) == 1
    group = groups[0]
    assert group.recommended_action == "review_mapping"
    assert group.gap_kind == "unmapped_concept"
    assert group.domain == "condition"
    assert group.surface == "rare unknown syndrome"
    assert group.normalized_surface == "rare unknown syndrome"
    assert group.occurrence_count == 2
    assert group.case_count == 2
    assert group.trial_count == 1
    assert group.criterion_kinds == ["condition_present"]
    assert [example.pair_id for example in group.example_rows] == ["pair-1", "pair-2"]


def test_group_json_round_trip_uses_stable_list_artifact(tmp_path) -> None:
    rows = build_compiler_gap_review_rows(
        _run(
            [
                _record("pair-1", [_condition("rare unknown syndrome")]),
                _record("pair-2", [_condition("rare unknown syndrome")]),
            ]
        )
    )
    groups = build_compiler_gap_review_groups(rows)
    path = tmp_path / "compiler-review-groups.json"

    save_compiler_gap_review_groups(groups, path)

    assert load_compiler_gap_review_groups(path) == groups
    text = path.read_text()
    assert text.endswith("\n")
    payload = json.loads(text)
    assert payload["artifact_safety"]["public_export"] == "synthetic"
    assert payload["groups"][0]["occurrence_count"] == 2


def test_group_summary_counts_groups_and_underlying_rows() -> None:
    rows = build_compiler_gap_review_rows(
        _run(
            [
                _record("pair-1", [_condition("rare unknown syndrome")]),
                _record("pair-2", [_condition("rare unknown syndrome")]),
                _record("pair-3", [_measurement("BNP")]),
            ]
        )
    )
    groups = build_compiler_gap_review_groups(rows)

    summary = summarize_compiler_gap_review_groups(groups)

    assert summary.total_rows == 4
    assert summary.total_groups == 3
    assert summary.by_recommended_action == {
        "add_unit_mapping": 1,
        "review_mapping": 2,
    }
    assert summary.by_domain == {"condition": 1, "measurement": 1, "unit": 1}
