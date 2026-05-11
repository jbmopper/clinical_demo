from __future__ import annotations

from typing import Literal

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
from clinical_demo.extractor.schema import (
    CompositeCriterionGroup,
    CompositeCriterionSubcheck,
    EntityMention,
    ExtractedCriteria,
    ExtractedCriterion,
    ExtractionMetadata,
)


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


def test_compiled_predicate_preserves_unsupported_hypothetical_mood() -> None:
    criterion = crit_condition(text="type 2 diabetes", mood="hypothetical")
    compilation = compile_extracted_criteria([criterion])

    verdict = match_compiled_criteria(
        compilation,
        make_profile(),
        make_trial(),
        matcher_assumption_mode="closed_world_eval",
    )[0]

    assert compilation.criteria[0].predicate.status == "resolved"
    assert verdict.verdict == "indeterminate"
    assert verdict.reason == "unsupported_mood"
    assert verdict.evidence_under_assumption is False


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


def test_compiled_free_text_condition_promotion_executes() -> None:
    criterion = crit_free_text(
        polarity="exclusion",
        source_text="Bone fractures within the past 12 months",
        mentions=[
            EntityMention(text="Bone fractures", type="Condition"),
            EntityMention(text="12 months", type="Temporal"),
        ],
    )
    profile = make_profile()

    compilation = compile_extracted_criteria([criterion])
    verdict = match_compiled_criteria(
        compilation,
        profile,
        make_trial(),
        matcher_assumption_mode="closed_world_eval",
    )[0]

    assert compilation.criteria[0].predicate.predicate_kind == "condition_presence"
    assert verdict.verdict == "pass"
    assert verdict.reason == "ok"
    assert verdict.evidence_under_assumption is True


def test_compiled_free_text_composite_condition_mention_stays_human_review() -> None:
    criterion = crit_free_text(
        polarity="exclusion",
        source_text="Pregnant or breastfeeding females",
        mentions=[EntityMention(text="Pregnant or breastfeeding females", type="Condition")],
    )

    compilation = compile_extracted_criteria([criterion])
    verdict = match_compiled_criteria(
        compilation,
        make_profile(),
        make_trial(),
        matcher_assumption_mode="closed_world_eval",
    )[0]

    assert compilation.criteria[0].predicate.status == "not_attempted"
    assert verdict.verdict == "indeterminate"
    assert verdict.reason == "human_review_required"


def test_compiled_free_text_trial_exposure_promotion_executes() -> None:
    criterion = crit_free_text(
        polarity="exclusion",
        source_text="Use of other investigational agents within 3 months of enrollment",
        mentions=[
            EntityMention(text="other investigational agents", type="Drug"),
            EntityMention(text="3 months", type="Temporal"),
        ],
    )

    compilation = compile_extracted_criteria([criterion])
    verdict = match_compiled_criteria(
        compilation,
        make_profile(),
        make_trial(),
        matcher_assumption_mode="closed_world_eval",
    )[0]

    assert compilation.criteria[0].predicate.predicate_kind == "trial_exposure"
    assert verdict.verdict == "pass"
    assert verdict.reason == "ok"
    assert verdict.evidence_under_assumption is True


def test_compiled_condition_shaped_trial_exposure_promotion_executes() -> None:
    criterion = crit_condition(
        text="Currently enrolled in or have completed any other investigational product study",
        polarity="exclusion",
    )

    compilation = compile_extracted_criteria([criterion])
    verdict = match_compiled_criteria(
        compilation,
        make_profile(),
        make_trial(),
        matcher_assumption_mode="closed_world_eval",
    )[0]

    assert compilation.criteria[0].predicate.predicate_kind == "trial_exposure"
    assert verdict.verdict == "pass"
    assert verdict.reason == "ok"
    assert verdict.evidence_under_assumption is True


def test_compiled_parenthetical_bmi_surface_executes_threshold() -> None:
    criterion = crit_measurement(
        text="body mass index (bmi)",
        operator=">",
        value=45.0,
        unit="kg/m2",
    )
    profile = make_profile(observations=[make_lab(loinc="39156-5", value=46.0, unit="kg/m2")])

    compilation = compile_extracted_criteria([criterion])
    verdict = match_compiled_criteria(compilation, profile, make_trial())[0]

    assert compilation.criteria[0].predicate.status == "resolved"
    assert verdict.verdict == "pass"
    assert verdict.reason == "ok"


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


def test_compiled_temporal_diagnosis_variant_executes_window() -> None:
    criterion = crit_temporal_window(event_text="recent T2D diagnosis", window_days=90)
    profile = make_profile(
        conditions=[make_condition(code="44054006", display="T2DM", onset=AS_OF.replace(day=1))]
    )
    compilation = compile_extracted_criteria([criterion])

    verdict = match_compiled_criteria(compilation, profile, make_trial())[0]

    assert compilation.criteria[0].resolved_supports[0].surface == "type 2 diabetes"
    assert compilation.checkable_predicates[0].predicate_kind == "temporal_event"
    assert verdict.verdict == "pass"
    assert verdict.reason == "ok"


def test_compiled_composite_any_of_rolls_up_subcheck_predicates() -> None:
    parent = crit_free_text()
    first = crit_measurement(text="hba1c", operator=">=", value=6.5, unit="%")
    second = crit_measurement(text="hba1c", operator="<=", value=6.0, unit="%")
    extraction = _extraction_with_group(parent, [first, second], operator="any_of")
    profile = make_profile(observations=[make_lab(value=7.2, unit="%")])

    compilation = compile_extracted_criteria(extraction)
    verdict = match_compiled_criteria(compilation, profile, make_trial())[0]

    assert compilation.criteria[0].predicate.predicate_kind == "compound"
    assert [predicate.source_criterion_id for predicate in compilation.checkable_predicates] == [
        "criterion:0:group:001:subcheck:001",
        "criterion:0:group:001:subcheck:002",
    ]
    assert verdict.verdict == "pass"
    assert verdict.reason == "ok"
    assert "Compiled composite any_of group" in verdict.rationale


def test_compiled_composite_exclusion_polarity_applies_after_rollup() -> None:
    parent = crit_free_text(polarity="exclusion")
    first = crit_measurement(text="hba1c", operator=">=", value=6.5, unit="%")
    second = crit_measurement(text="hba1c", operator="<=", value=6.0, unit="%")
    extraction = _extraction_with_group(parent, [first, second], operator="any_of")
    profile = make_profile(observations=[make_lab(value=7.2, unit="%")])

    compilation = compile_extracted_criteria(extraction)
    verdict = match_compiled_criteria(compilation, profile, make_trial())[0]

    assert verdict.verdict == "fail"
    assert verdict.reason == "ok"
    assert "Compiled composite any_of group" in verdict.rationale


def test_compiled_composite_any_of_can_decide_with_one_unresolved_subcheck() -> None:
    parent = crit_free_text()
    mapped = crit_measurement(text="hba1c", operator=">=", value=6.5, unit="%")
    unmapped = crit_measurement(text="BNP", operator=">=", value=50.0, unit="pg/mL")
    extraction = _extraction_with_group(parent, [mapped, unmapped], operator="any_of")
    profile = make_profile(observations=[make_lab(value=7.2, unit="%")])

    compilation = compile_extracted_criteria(extraction)
    verdict = match_compiled_criteria(compilation, profile, make_trial())[0]

    assert compilation.criteria[0].predicate.status == "unresolved"
    assert compilation.criteria[0].unresolved_gaps
    assert verdict.verdict == "pass"
    assert verdict.reason == "ok"
    assert any(evidence.kind == "missing" for evidence in verdict.evidence)


def _extraction_with_group(
    parent: ExtractedCriterion,
    subchecks: list[ExtractedCriterion],
    *,
    operator: Literal["any_of", "all_of"],
) -> ExtractedCriteria:
    return ExtractedCriteria(
        criteria=[parent],
        composite_groups=[
            CompositeCriterionGroup(
                group_id="criterion:0:group:001",
                operator=operator,
                parent_criterion_index=0,
                parent_source_text=parent.source_text,
                subchecks=[
                    CompositeCriterionSubcheck(
                        subcheck_id=f"criterion:0:group:001:subcheck:{index:03d}",
                        operator=operator,
                        source_text=subcheck.source_text,
                        criterion=subcheck,
                    )
                    for index, subcheck in enumerate(subchecks, start=1)
                ],
            )
        ],
        metadata=ExtractionMetadata(notes=""),
    )
