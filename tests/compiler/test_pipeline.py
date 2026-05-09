from __future__ import annotations

from clinical_demo.compiler import compile_extracted_criteria
from clinical_demo.extractor.schema import (
    CompositeCriterionGroup,
    CompositeCriterionSubcheck,
    ConditionCriterion,
    ExtractedCriteria,
    ExtractedCriterion,
    ExtractionMetadata,
    FreeTextCriterion,
    MeasurementCriterion,
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


def test_noop_pipeline_preserves_count_order_text_and_kind() -> None:
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


def test_compound_and_unit_placeholders_are_typed_without_changing_matcher_input() -> None:
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
    assert compiled.compound_logic.status == "not_attempted"
    assert compiled.compound_logic.operator == "any_of"
    assert compiled.compound_logic.source_group_ids == ["criterion:0:group:001"]
    assert compiled.compound_logic.subcheck_ids == ["criterion:0:group:001:subcheck:001"]
    assert compiled.unit_normalization.status == "skipped"
    assert compiled.predicate.status == "not_attempted"
    assert compiled.predicate.predicate_kind == "free_text_review"


def test_measurement_unit_placeholder_records_source_unit() -> None:
    criterion = _measurement("HbA1c", unit="%")

    result = compile_extracted_criteria([criterion])
    compiled = result.criteria[0]

    assert compiled.unit_normalization.status == "not_attempted"
    assert compiled.unit_normalization.measurement_surface == "HbA1c"
    assert compiled.unit_normalization.source_unit == "%"
    assert compiled.predicate.predicate_kind == "measurement_threshold"
