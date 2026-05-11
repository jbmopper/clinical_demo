from __future__ import annotations

from clinical_demo.compiler import compile_extracted_criteria
from clinical_demo.extractor.schema import (
    AgeCriterion,
    CompositeCriterionGroup,
    CompositeCriterionSubcheck,
    ConditionCriterion,
    EntityMention,
    ExtractedCriteria,
    ExtractedCriterion,
    ExtractionMetadata,
    FreeTextCriterion,
    MeasurementCriterion,
    TemporalWindowCriterion,
    ThresholdOperator,
)


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


def _measurement(text: str, unit: str | None = "%") -> ExtractedCriterion:
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


def _measurement_with_value(
    text: str,
    *,
    operator: ThresholdOperator = ">=",
    value: float | None,
    unit: str | None,
) -> ExtractedCriterion:
    return ExtractedCriterion(
        kind="measurement_threshold",
        polarity="inclusion",
        source_text=f"{text} {operator} {value if value is not None else ''}{unit or ''}",
        negated=False,
        mood="actual",
        age=None,
        sex=None,
        condition=None,
        medication=None,
        measurement=MeasurementCriterion(
            measurement_text=text,
            operator=operator,
            value=value,
            value_low=None,
            value_high=None,
            unit=unit,
        ),
        temporal_window=None,
        free_text=None,
        mentions=[],
    )


def _free_text(text: str) -> ExtractedCriterion:
    return ExtractedCriterion(
        kind="free_text",
        polarity="exclusion",
        source_text=text,
        negated=False,
        mood="actual",
        age=None,
        sex=None,
        condition=None,
        medication=None,
        measurement=None,
        temporal_window=None,
        free_text=FreeTextCriterion(note="not structured yet"),
        mentions=[],
    )


def _age(minimum_years: float = 18.0) -> ExtractedCriterion:
    return ExtractedCriterion(
        kind="age",
        polarity="inclusion",
        source_text=f"Age >= {minimum_years:g} years",
        negated=False,
        mood="actual",
        age=AgeCriterion(minimum_years=minimum_years, maximum_years=None),
        sex=None,
        condition=None,
        medication=None,
        measurement=None,
        temporal_window=None,
        free_text=None,
        mentions=[],
    )


def _temporal(event_text: str, window_days: int = 365) -> ExtractedCriterion:
    return ExtractedCriterion(
        kind="temporal_window",
        polarity="exclusion",
        source_text=f"{event_text} within {window_days} days",
        negated=False,
        mood="historical",
        age=None,
        sex=None,
        condition=None,
        medication=None,
        measurement=None,
        temporal_window=TemporalWindowCriterion(
            event_text=event_text,
            window_days=window_days,
            direction="within_past",
        ),
        free_text=None,
        mentions=[],
    )


def test_pipeline_preserves_count_order_text_kind_and_matcher_inputs() -> None:
    criteria = [_condition("type 2 diabetes"), _measurement("HbA1c"), _free_text("Unable")]
    extracted = ExtractedCriteria(criteria=criteria, metadata=ExtractionMetadata(notes=""))

    result = compile_extracted_criteria(extracted)

    assert result.source_criteria_count == 3
    assert result.matcher_inputs == criteria
    assert [item.source_text for item in result.criteria] == [item.source_text for item in criteria]
    assert [item.criterion_kind for item in result.criteria] == [item.kind for item in criteria]


def test_pipeline_assigns_stable_ids() -> None:
    criteria = [_condition("type 2 diabetes"), _measurement("HbA1c")]

    first = compile_extracted_criteria(criteria, resolver_policy="cached_only")
    second = compile_extracted_criteria(criteria, resolver_policy="cached_only")

    assert [item.source_criterion_id for item in first.criteria] == ["criterion:0", "criterion:1"]
    assert [item.compiled_id for item in first.criteria] == [
        "compiled:criterion:0",
        "compiled:criterion:1",
    ]
    assert [item.compiled_id for item in first.criteria] == [
        item.compiled_id for item in second.criteria
    ]


def test_empty_input_compiles_to_empty_result() -> None:
    result = compile_extracted_criteria(
        ExtractedCriteria(criteria=[], metadata=ExtractionMetadata(notes="empty"))
    )

    assert result.source_criteria_count == 0
    assert result.criteria == []
    assert result.matcher_inputs == []
    assert result.unresolved_gaps == []
    assert result.diagnostics == []


def test_compound_logic_compiles_without_changing_matcher_input() -> None:
    parent = _free_text("HbA1c >= 7% or fasting glucose >= 126 mg/dL")
    subcheck = _measurement("HbA1c", unit="%")
    extracted = ExtractedCriteria(
        criteria=[parent],
        composite_groups=[
            CompositeCriterionGroup(
                group_id="criterion:0:group:001",
                operator="any_of",
                parent_criterion_index=0,
                parent_source_text=parent.source_text,
                subchecks=[
                    CompositeCriterionSubcheck(
                        subcheck_id="criterion:0:group:001:subcheck:001",
                        operator="any_of",
                        source_text=subcheck.source_text,
                        criterion=subcheck,
                    )
                ],
            )
        ],
        metadata=ExtractionMetadata(notes=""),
    )

    result = compile_extracted_criteria(extracted, resolver_policy="live_allowed")
    compiled = result.criteria[0]

    assert result.matcher_inputs == [parent]
    assert compiled.resolver_policy == "live_allowed"
    assert compiled.compound_logic.status == "resolved"
    assert compiled.compound_logic.operator == "any_of"
    assert compiled.compound_logic.source_group_ids == ["criterion:0:group:001"]
    assert compiled.compound_logic.subcheck_ids == ["criterion:0:group:001:subcheck:001"]
    assert compiled.unit_normalization.status == "skipped"
    assert compiled.predicate.status == "resolved"
    assert compiled.predicate.predicate_kind == "compound"
    assert compiled.predicate.predicate_ids == [
        "criterion:0:group:001:subcheck:001:predicate:measurement"
    ]
    assert compiled.checkable_predicates[0].source_criterion_id == (
        "criterion:0:group:001:subcheck:001"
    )
    assert compiled.checkable_predicates[0].predicate_kind == "measurement_threshold"


def test_measurement_unit_resolution_builds_checkable_predicate() -> None:
    criterion = _measurement("HbA1c", unit="%")

    result = compile_extracted_criteria([criterion])
    compiled = result.criteria[0]

    assert compiled.unit_normalization.status == "resolved"
    assert compiled.unit_normalization.measurement_surface == "HbA1c"
    assert compiled.unit_normalization.source_unit == "%"
    assert compiled.unit_normalization.conventional_unit == "%"
    assert compiled.predicate.predicate_kind == "measurement_threshold"
    assert compiled.predicate.status == "resolved"
    assert compiled.predicate.predicate_ids == ["criterion:0:predicate:measurement"]
    assert [predicate.predicate_id for predicate in result.checkable_predicates] == [
        "criterion:0:predicate:measurement"
    ]
    predicate = compiled.checkable_predicates[0]
    assert predicate.target_system == "http://loinc.org"
    assert predicate.target_codes == frozenset({"4548-4"})
    assert predicate.operator == ">="
    assert predicate.value == 7.0
    assert predicate.unit == "%"
    assert result.resolved_supports == compiled.resolved_supports


def test_measurement_missing_threshold_value_blocks_checkable_predicate() -> None:
    criterion = _measurement_with_value(
        "aspartate aminotransferase",
        operator="<=",
        value=None,
        unit=None,
    )

    result = compile_extracted_criteria([criterion])
    compiled = result.criteria[0]

    assert compiled.unit_normalization.status == "resolved"
    assert compiled.predicate.status == "unresolved"
    assert compiled.checkable_predicates == []
    assert [gap.kind for gap in compiled.unresolved_gaps] == ["insufficient_source"]
    assert compiled.unresolved_gaps[0].stage == "predicate_translation"


def test_condition_compiler_maps_reviewed_fracture_surface_after_variant_cleanup() -> None:
    criterion = _condition(
        "Bone fractures (excluding skull, facial bones, metacarpals, fingers, toes "
        "and spontaneous fractures associated with severe trauma) within the past 12 months"
    )

    result = compile_extracted_criteria([criterion], resolver_policy="cached_only")
    compiled = result.criteria[0]

    assert result.matcher_inputs == [criterion]
    assert compiled.expansion.status == "resolved"
    assert compiled.expansion.strategy == "reviewed_code_list"
    assert compiled.predicate.status == "resolved"
    assert compiled.predicate.predicate_ids == ["criterion:0:predicate:condition"]
    assert compiled.checkable_predicates[0].predicate_kind == "condition_presence"
    assert "263102004" in compiled.checkable_predicates[0].target_codes
    assert compiled.resolved_supports[0].normalized_surface == "bone fractures"
    assert {support.stage for support in compiled.resolved_supports} == {
        "concept_resolution",
        "expansion",
    }
    assert result.checkable_predicates == compiled.checkable_predicates
    assert result.unresolved_gaps == []


def test_condition_compiler_preserves_raw_hyphenated_lookup_surface() -> None:
    criterion = _condition("end-stage renal disease")

    result = compile_extracted_criteria([criterion], resolver_policy="cached_only")
    compiled = result.criteria[0]

    assert compiled.predicate.status == "resolved"
    assert compiled.resolved_supports[0].normalized_surface == "end-stage renal disease"
    assert compiled.checkable_predicates[0].target_codes == frozenset({"46177005"})


def test_free_text_condition_mention_compiles_to_condition_predicate() -> None:
    criterion = _free_text("Bone fractures within the past 12 months").model_copy(
        update={
            "mentions": [
                EntityMention(text="Bone fractures", type="Condition"),
                EntityMention(text="12 months", type="Temporal"),
            ]
        }
    )

    result = compile_extracted_criteria([criterion], resolver_policy="cached_only")
    compiled = result.criteria[0]

    assert compiled.criterion_kind == "free_text"
    assert compiled.predicate.status == "resolved"
    assert compiled.predicate.predicate_kind == "condition_presence"
    assert compiled.checkable_predicates[0].predicate_kind == "condition_presence"
    assert compiled.diagnostics[0].code == "free_text.promoted.condition"


def test_free_text_composite_condition_mention_stays_human_review() -> None:
    criterion = _free_text("Pregnant or breastfeeding females").model_copy(
        update={
            "mentions": [EntityMention(text="Pregnant or breastfeeding females", type="Condition")]
        }
    )

    result = compile_extracted_criteria([criterion], resolver_policy="cached_only")
    compiled = result.criteria[0]

    assert compiled.criterion_kind == "free_text"
    assert compiled.predicate.status == "not_attempted"
    assert compiled.checkable_predicates == []
    assert result.unresolved_gaps == []


def test_free_text_trial_exposure_compiles_to_internal_predicate() -> None:
    criterion = _free_text("Use of other investigational agents within 3 months").model_copy(
        update={
            "mentions": [
                EntityMention(text="other investigational agents", type="Drug"),
                EntityMention(text="3 months", type="Temporal"),
            ]
        }
    )

    result = compile_extracted_criteria([criterion], resolver_policy="cached_only")
    compiled = result.criteria[0]

    assert compiled.predicate.status == "resolved"
    assert compiled.predicate.predicate_kind == "trial_exposure"
    assert compiled.checkable_predicates[0].window_days == 90
    assert compiled.diagnostics[0].code == "free_text.promoted.trial-exposure"


def test_condition_shaped_trial_exposure_compiles_to_internal_predicate() -> None:
    criterion = _condition(
        "Currently enrolled in or have completed any other investigational product study"
    )

    result = compile_extracted_criteria([criterion], resolver_policy="cached_only")
    compiled = result.criteria[0]

    assert compiled.criterion_kind == "condition_present"
    assert compiled.predicate.status == "resolved"
    assert compiled.predicate.predicate_kind == "trial_exposure"
    assert compiled.checkable_predicates[0].predicate_kind == "trial_exposure"
    assert compiled.resolved_supports[0].domain == "condition"
    assert compiled.diagnostics[0].code == "condition.promoted.trial-exposure"
    assert result.unresolved_gaps == []


def test_demographic_and_temporal_predicates_are_aggregated() -> None:
    criteria = [_age(), _temporal("type 2 diabetes", window_days=90)]

    result = compile_extracted_criteria(criteria)

    assert result.matcher_inputs == criteria
    assert [criterion.predicate.status for criterion in result.criteria] == [
        "resolved",
        "resolved",
    ]
    assert [predicate.predicate_kind for predicate in result.checkable_predicates] == [
        "demographic",
        "temporal_event",
    ]
    assert result.checkable_predicates[1].window_days == 90
