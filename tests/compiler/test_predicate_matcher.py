from __future__ import annotations

from datetime import timedelta
from typing import Literal

from tests.matcher._fixtures import (
    AS_OF,
    crit_condition,
    crit_free_text,
    crit_measurement,
    crit_medication,
    crit_temporal_window,
    make_condition,
    make_lab,
    make_medication,
    make_procedure,
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


def test_compiled_condition_predicate_executes_reviewed_descendant_expansion() -> None:
    criterion = crit_condition(text="cardiovascular disease")
    profile = make_profile(
        conditions=[
            make_condition(
                code="84114007",
                display="Heart failure",
                onset=AS_OF.replace(year=AS_OF.year - 1),
            )
        ]
    )

    compilation = compile_extracted_criteria([criterion])
    verdicts = match_compiled_criteria(compilation, profile, make_trial())

    assert compilation.criteria[0].expansion.strategy == "descendants"
    assert compilation.criteria[0].predicate.status == "resolved"
    assert verdicts[0].verdict == "pass"
    assert verdicts[0].reason == "ok"
    assert verdicts[0].evidence[0].kind == "condition"


def test_compiled_cardiovascular_event_phrase_executes_reviewed_promotion() -> None:
    criterion = crit_condition(text="major adverse cardiovascular events", polarity="exclusion")
    profile = make_profile(
        conditions=[
            make_condition(
                code="22298006",
                display="Myocardial infarction",
                onset=AS_OF.replace(year=AS_OF.year - 1),
            )
        ]
    )

    compilation = compile_extracted_criteria([criterion])
    verdicts = match_compiled_criteria(compilation, profile, make_trial())

    assert compilation.criteria[0].predicate.status == "resolved"
    assert compilation.criteria[0].resolved_supports[0].surface == "cardiovascular disease"
    assert verdicts[0].verdict == "fail"
    assert verdicts[0].reason == "ok"
    assert verdicts[0].evidence[0].kind == "condition"


def test_compiled_procedure_history_predicate_executes_reviewed_mapping() -> None:
    criterion = crit_condition(text="history of full pneumonectomy")
    profile = make_profile(procedures=[make_procedure(code="49795001")])

    compilation = compile_extracted_criteria([criterion])
    verdicts = match_compiled_criteria(compilation, profile, make_trial())

    assert compilation.checkable_predicates[0].predicate_kind == "procedure_history"
    assert verdicts[0].verdict == "pass"
    assert verdicts[0].reason == "ok"
    assert verdicts[0].evidence[0].kind == "procedure"


def test_compiled_procedure_history_preserves_open_and_closed_world_absence() -> None:
    criterion = crit_condition(text="history of full pneumonectomy")
    compilation = compile_extracted_criteria([criterion])
    profile = make_profile(procedures=[])

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


def test_compiled_procedure_history_exclusion_fails_when_present() -> None:
    criterion = crit_condition(text="history of full pneumonectomy", polarity="exclusion")
    profile = make_profile(procedures=[make_procedure(code="232647000")])

    compilation = compile_extracted_criteria([criterion])
    verdict = match_compiled_criteria(compilation, profile, make_trial())[0]

    assert verdict.verdict == "fail"
    assert verdict.reason == "ok"
    assert verdict.evidence[0].kind == "procedure"


def test_compiled_procedure_history_applies_source_window() -> None:
    criterion = crit_condition(text="history of full pneumonectomy").model_copy(
        update={"source_text": "History of full pneumonectomy within 30 days"}
    )
    profile = make_profile(
        procedures=[make_procedure(code="49795001", performed=AS_OF - timedelta(days=60))]
    )

    compilation = compile_extracted_criteria([criterion])
    verdict = match_compiled_criteria(
        compilation,
        profile,
        make_trial(),
        matcher_assumption_mode="closed_world_eval",
    )[0]

    assert compilation.checkable_predicates[0].window_days == 30
    assert verdict.verdict == "fail"
    assert verdict.reason == "ok"


def test_compiled_all_of_mixed_condition_and_procedure_history_requires_both() -> None:
    criterion = crit_condition(text="advanced CKD requiring chronic dialysis")
    compilation = compile_extracted_criteria([criterion], resolver_policy="cached_only")
    full_profile = make_profile(
        conditions=[make_condition(code="431856006", display="Chronic kidney disease stage 2")],
        procedures=[make_procedure(code="265764009", display="Renal dialysis")],
    )
    missing_condition_profile = make_profile(
        conditions=[],
        procedures=[make_procedure(code="265764009", display="Renal dialysis")],
    )

    full_verdict = match_compiled_criteria(compilation, full_profile, make_trial())[0]
    missing_condition_verdict = match_compiled_criteria(
        compilation,
        missing_condition_profile,
        make_trial(),
        matcher_assumption_mode="closed_world_eval",
    )[0]

    assert compilation.criteria[0].predicate.predicate_kind == "compound"
    assert [predicate.predicate_kind for predicate in compilation.checkable_predicates] == [
        "condition_presence",
        "procedure_history",
    ]
    assert full_verdict.verdict == "pass"
    assert full_verdict.reason == "ok"
    assert {evidence.kind for evidence in full_verdict.evidence} == {"condition", "procedure"}
    assert missing_condition_verdict.verdict == "fail"
    assert missing_condition_verdict.reason == "ok"


def test_compiled_mixed_renal_dialysis_exclusion_polarity_applies_after_rollup() -> None:
    criterion = crit_condition(text="end-stage renal failure on dialysis", polarity="exclusion")
    profile = make_profile(
        conditions=[make_condition(code="46177005", display="End-stage renal disease")],
        procedures=[make_procedure(code="302497006", display="Hemodialysis")],
    )

    compilation = compile_extracted_criteria([criterion], resolver_policy="cached_only")
    verdict = match_compiled_criteria(compilation, profile, make_trial())[0]

    assert compilation.criteria[0].compound_logic.operator == "all_of"
    assert verdict.verdict == "fail"
    assert verdict.reason == "ok"
    assert {evidence.kind for evidence in verdict.evidence} == {"condition", "procedure"}


def test_compiled_medication_exposure_applies_source_window() -> None:
    criterion = crit_medication(text="metformin").model_copy(
        update={"source_text": "Use of metformin in the previous 2 months"}
    )
    profile = make_profile(
        medications=[
            make_medication(
                code="860975",
                start=AS_OF - timedelta(days=300),
                end=AS_OF - timedelta(days=30),
            )
        ]
    )

    compilation = compile_extracted_criteria([criterion])
    verdict = match_compiled_criteria(compilation, profile, make_trial())[0]

    assert compilation.checkable_predicates[0].window_days == 60
    assert verdict.verdict == "pass"
    assert verdict.reason == "ok"
    assert "overlaps" in verdict.evidence[0].note


def test_compiled_medication_exposure_requires_minimum_duration() -> None:
    criterion = crit_medication(text="metformin").model_copy(
        update={"source_text": "On a stable dose of metformin for at least 30 days"}
    )
    compilation = compile_extracted_criteria([criterion])

    short_profile = make_profile(
        medications=[make_medication(code="860975", start=AS_OF - timedelta(days=10))]
    )
    long_profile = make_profile(
        medications=[make_medication(code="860975", start=AS_OF - timedelta(days=45))]
    )

    short_verdict = match_compiled_criteria(
        compilation,
        short_profile,
        make_trial(),
        matcher_assumption_mode="closed_world_eval",
    )[0]
    long_verdict = match_compiled_criteria(compilation, long_profile, make_trial())[0]

    assert compilation.checkable_predicates[0].min_duration_days == 30
    assert short_verdict.verdict == "fail"
    assert long_verdict.verdict == "pass"
    assert "required duration >= 30 days" in long_verdict.evidence[0].note


def test_compiled_measurement_predicate_executes_threshold() -> None:
    criterion = crit_measurement(text="HbA1c", operator=">=", value=7.0, unit="%")
    profile = make_profile(observations=[make_lab(loinc="4548-4", value=7.4, unit="%")])

    compilation = compile_extracted_criteria([criterion])
    verdicts = match_compiled_criteria(compilation, profile, make_trial())

    assert compilation.checkable_predicates[0].predicate_kind == "measurement_threshold"
    assert verdicts[0].verdict == "pass"
    assert verdicts[0].reason == "ok"
    assert verdicts[0].evidence[0].kind == "lab"


def test_compiled_sex_specific_uln_measurement_uses_patient_sex_threshold() -> None:
    criterion = crit_measurement(
        text="hemoglobin",
        operator=">",
        value=None,
        unit="gender-specific ULN",
        polarity="exclusion",
    ).model_copy(update={"source_text": "Hemoglobin at screening above gender-specific ULN"})
    female_profile = make_profile(
        sex="female",
        observations=[make_lab(loinc="718-7", value=16.0, unit="g/dL")],
    )
    male_profile = make_profile(
        sex="male",
        observations=[make_lab(loinc="718-7", value=16.0, unit="g/dL")],
    )

    compilation = compile_extracted_criteria([criterion])
    female_verdict = match_compiled_criteria(compilation, female_profile, make_trial())[0]
    male_verdict = match_compiled_criteria(compilation, male_profile, make_trial())[0]

    assert compilation.checkable_predicates[0].value_by_sex == {"FEMALE": 15.5, "MALE": 17.5}
    assert female_verdict.verdict == "fail"
    assert female_verdict.reason == "ok"
    assert male_verdict.verdict == "pass"
    assert male_verdict.reason == "ok"


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


def test_compiled_structured_free_text_review_condition_stays_human_review() -> None:
    criterion = crit_condition(text="structured exercise program")

    compilation = compile_extracted_criteria([criterion])
    verdict = match_compiled_criteria(
        compilation,
        make_profile(),
        make_trial(),
        matcher_assumption_mode="closed_world_eval",
    )[0]

    assert compilation.criteria[0].predicate.predicate_kind == "free_text_review"
    assert verdict.verdict == "indeterminate"
    assert verdict.reason == "human_review_required"
    assert verdict.evidence[0].kind == "missing"
    assert "human-review/free-text criterion" in verdict.evidence[0].note


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


def test_compiled_temporal_drug_event_executes_medication_duration() -> None:
    criterion = crit_temporal_window(
        event_text="lipid-lowering therapies", window_days=30
    ).model_copy(
        update={
            "source_text": (
                "Participants on lipid-lowering therapies must be on a stable dose "
                "for ≥30 days before screening"
            ),
            "mentions": [
                EntityMention(text="lipid-lowering therapies", type="Drug"),
                EntityMention(text="≥30 days before screening", type="Temporal"),
            ],
        }
    )
    profile = make_profile(
        medications=[make_medication(code="259255", start=AS_OF - timedelta(days=45))]
    )

    compilation = compile_extracted_criteria([criterion])
    verdict = match_compiled_criteria(compilation, profile, make_trial())[0]

    assert compilation.checkable_predicates[0].predicate_kind == "medication_exposure"
    assert compilation.checkable_predicates[0].min_duration_days == 30
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
