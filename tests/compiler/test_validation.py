from __future__ import annotations

from clinical_demo.compiler.pipeline import compile_extracted_criteria
from clinical_demo.compiler.validation import (
    validate_compilation_for_closed_world,
    validate_compiled_criterion_for_closed_world,
)
from clinical_demo.extractor.schema import (
    AgeCriterion,
    CompositeCriterionGroup,
    CompositeCriterionSubcheck,
    ConditionCriterion,
    ExtractedCriteria,
    ExtractedCriterion,
    ExtractionMetadata,
    FreeTextCriterion,
    MeasurementCriterion,
    ThresholdOperator,
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


def _measurement(
    text: str,
    *,
    operator: ThresholdOperator = ">=",
    value: float | None = 7.0,
    unit: str | None = "%",
) -> ExtractedCriterion:
    return ExtractedCriterion(
        kind="measurement_threshold",
        polarity="inclusion",
        source_text=f"{text} {operator} {value or ''}{unit or ''}",
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


def _free_text(text: str = "Investigator discretion") -> ExtractedCriterion:
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
        free_text=FreeTextCriterion(note="requires review"),
        mentions=[],
    )


def test_compiled_age_condition_and_measurement_predicates_pass_validation() -> None:
    compilation = compile_extracted_criteria(
        [
            _age(),
            _condition(
                "Bone fractures (excluding skull, facial bones, metacarpals, fingers, "
                "toes and spontaneous fractures associated with severe trauma) within "
                "the past 12 months"
            ),
            _measurement("HbA1c", unit="%"),
        ],
        resolver_policy="cached_only",
    )

    result = validate_compilation_for_closed_world(compilation)

    assert result.ok is True
    assert result.findings == []
    assert result.summary.criteria_count == 3
    assert result.summary.structured_criteria_count == 3
    assert result.summary.executable_criteria_count == 3
    assert result.summary.blocking_count == 0


def test_free_text_without_predicate_is_allowed_review_not_blocking() -> None:
    compilation = compile_extracted_criteria([_free_text()])
    compiled = compilation.criteria[0]

    findings = validate_compiled_criterion_for_closed_world(compiled)
    result = validate_compilation_for_closed_world(compilation)

    assert findings[0].code == "allowed_non_executable"
    assert findings[0].blocking is False
    assert findings[0].severity == "info"
    assert findings[0].allowed_non_executable_class == "free_text_review"
    assert findings[0].gap_ids == []
    assert result.ok is True
    assert result.summary.review_criteria_count == 1
    assert result.summary.non_blocking_count == 1


def test_free_text_composite_with_executable_subchecks_is_not_review_only() -> None:
    parent = _free_text("HbA1c >= 7% or HbA1c <= 6%")
    first = _measurement("HbA1c", operator=">=", value=7.0, unit="%")
    second = _measurement("HbA1c", operator="<=", value=6.0, unit="%")
    extraction = ExtractedCriteria(
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
                        source_text=first.source_text,
                        criterion=first,
                    ),
                    CompositeCriterionSubcheck(
                        subcheck_id="criterion:0:group:001:subcheck:002",
                        operator="any_of",
                        source_text=second.source_text,
                        criterion=second,
                    ),
                ],
            )
        ],
        metadata=ExtractionMetadata(notes=""),
    )

    compilation = compile_extracted_criteria(extraction)
    result = validate_compilation_for_closed_world(compilation)

    assert compilation.criteria[0].predicate.predicate_kind == "compound"
    assert compilation.criteria[0].checkable_predicates
    assert result.ok is True
    assert result.findings == []
    assert result.summary.review_criteria_count == 0


def test_unmapped_structured_condition_fails_validation_with_gap_ids() -> None:
    compilation = compile_extracted_criteria([_condition("definitely unmapped syndrome xyz")])

    result = validate_compilation_for_closed_world(compilation)

    assert result.ok is False
    assert [finding.code for finding in result.findings] == [
        "structured_unresolved_gaps",
        "structured_missing_executable",
    ]
    gap_finding = result.findings[0]
    assert gap_finding.source_criterion_id == "criterion:0"
    assert gap_finding.criterion_kind == "condition_present"
    assert gap_finding.blocking is True
    assert gap_finding.severity == "error"
    assert gap_finding.gap_ids == ["criterion:0:condition:gap:no_candidates"]
    assert "No non-rejected candidates were supplied" in gap_finding.message


def test_measurement_missing_or_unsupported_unit_fails_validation() -> None:
    compilation = compile_extracted_criteria([_measurement("BNP", unit=None)])

    result = validate_compilation_for_closed_world(compilation)

    assert result.ok is False
    assert [finding.code for finding in result.findings] == [
        "structured_unresolved_gaps",
        "structured_missing_executable",
    ]
    assert result.findings[0].criterion_kind == "measurement_threshold"
    assert result.findings[0].gap_ids == [
        "criterion:0:measurement:gap:unmapped",
        "criterion:0:unit:gap:missing_unit",
    ]
    assert result.findings[1].gap_ids == result.findings[0].gap_ids


def test_summary_counts_are_deterministic() -> None:
    compilation = compile_extracted_criteria(
        [
            _age(),
            _free_text(),
            _condition("definitely unmapped syndrome xyz"),
            _measurement("BNP", unit=None),
        ]
    )

    result = validate_compilation_for_closed_world(compilation)

    assert result.summary.model_dump() == {
        "criteria_count": 4,
        "structured_criteria_count": 3,
        "executable_criteria_count": 1,
        "review_criteria_count": 1,
        "finding_count": 5,
        "blocking_count": 4,
        "non_blocking_count": 1,
        "info_count": 1,
        "warning_count": 0,
        "error_count": 4,
    }
