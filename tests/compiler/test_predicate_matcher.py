from __future__ import annotations

from tests.matcher._fixtures import (
    AS_OF,
    crit_condition,
    crit_free_text,
    crit_measurement,
    crit_temporal_window,
    make_condition,
    make_lab,
    make_profile,
    make_trial,
)

from clinical_demo.compiler import compile_extracted_criteria, match_compiled_criteria


def test_compiled_condition_predicate_executes_reviewed_fracture_mapping() -> None:
    criterion = crit_condition(
        text=(
            "Bone fractures (excluding skull, facial bones, metacarpals, fingers, toes "
            "and spontaneous fractures associated with severe trauma) within the past 12 months"
        )
    )
    profile = make_profile(
        conditions=[
            make_condition(
                code="263102004",
                display="Fracture subluxation of wrist",
                onset=AS_OF.replace(year=AS_OF.year - 1),
            )
        ]
    )

    compilation = compile_extracted_criteria([criterion])
    verdicts = match_compiled_criteria(compilation, profile, make_trial())

    assert compilation.criteria[0].predicate.status == "resolved"
    assert verdicts[0].verdict == "pass"
    assert verdicts[0].reason == "ok"
    assert verdicts[0].evidence[0].kind == "condition"


def test_compiled_measurement_predicate_executes_threshold() -> None:
    criterion = crit_measurement(text="HbA1c", operator=">=", value=7.0, unit="%")
    profile = make_profile(observations=[make_lab(loinc="4548-4", value=7.4, unit="%")])

    compilation = compile_extracted_criteria([criterion])
    verdicts = match_compiled_criteria(compilation, profile, make_trial())

    assert compilation.checkable_predicates[0].predicate_kind == "measurement_threshold"
    assert verdicts[0].verdict == "pass"
    assert verdicts[0].reason == "ok"
    assert verdicts[0].evidence[0].kind == "lab"


def test_compiled_condition_predicate_preserves_open_and_closed_world_absence() -> None:
    criterion = crit_condition(text="type 2 diabetes")
    compilation = compile_extracted_criteria([criterion])
    profile = make_profile(conditions=[])

    open_world = match_compiled_criteria(compilation, profile, make_trial())[0]
    closed_world = match_compiled_criteria(
        compilation,
        profile,
        make_trial(),
        matcher_assumption_mode="closed_world_eval",
    )[0]

    assert open_world.verdict == "indeterminate"
    assert open_world.reason == "no_data"
    assert open_world.evidence_under_assumption is False
    assert closed_world.verdict == "fail"
    assert closed_world.reason == "ok"
    assert closed_world.evidence_under_assumption is True


def test_compiled_unmapped_gap_becomes_unmapped_indeterminate() -> None:
    criterion = crit_condition(text="rare unknown disease")
    compilation = compile_extracted_criteria([criterion])

    verdict = match_compiled_criteria(compilation, make_profile(), make_trial())[0]

    assert compilation.criteria[0].predicate.status == "unresolved"
    assert verdict.verdict == "indeterminate"
    assert verdict.reason == "unmapped_concept"
    assert verdict.evidence[0].kind == "missing"


def test_compiled_free_text_without_predicate_stays_human_review() -> None:
    criterion = crit_free_text()
    compilation = compile_extracted_criteria([criterion])

    verdict = match_compiled_criteria(compilation, make_profile(), make_trial())[0]

    assert verdict.verdict == "indeterminate"
    assert verdict.reason == "human_review_required"


def test_compiled_temporal_predicate_executes_window() -> None:
    criterion = crit_temporal_window(event_text="type 2 diabetes", window_days=90)
    profile = make_profile(
        conditions=[make_condition(code="44054006", display="T2DM", onset=AS_OF.replace(day=1))]
    )
    compilation = compile_extracted_criteria([criterion])

    verdict = match_compiled_criteria(compilation, profile, make_trial())[0]

    assert compilation.checkable_predicates[0].predicate_kind == "temporal_event"
    assert verdict.verdict == "pass"
    assert verdict.reason == "ok"
