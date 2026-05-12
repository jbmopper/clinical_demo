from __future__ import annotations

import pytest

from clinical_demo.compiler import compile_compound_logic, compile_temporal_window
from clinical_demo.extractor.schema import (
    CompositeCriterionGroup,
    CompositeCriterionSubcheck,
    CompositeOperator,
    ConditionCriterion,
    ExtractedCriterion,
    FreeTextCriterion,
    TemporalWindowCriterion,
)
from clinical_demo.terminology.reviewed_registry import load_reviewed_mapping_registry


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


def _free_text(text: str = "compound parent") -> ExtractedCriterion:
    return ExtractedCriterion(
        kind="free_text",
        polarity="inclusion",
        source_text=text,
        negated=False,
        mood="actual",
        age=None,
        sex=None,
        condition=None,
        medication=None,
        measurement=None,
        temporal_window=None,
        free_text=FreeTextCriterion(note="compound"),
        mentions=[],
    )


def _temporal(
    *,
    event_text: str,
    window_days: int = 365,
    direction: str = "within_past",
) -> ExtractedCriterion:
    return ExtractedCriterion(
        kind="temporal_window",
        polarity="inclusion",
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
            direction=direction,  # type: ignore[arg-type]
        ),
        free_text=None,
        mentions=[],
    )


def _group(
    group_suffix: str,
    *,
    operator: CompositeOperator,
    subcheck_count: int = 2,
    subcheck_operator: CompositeOperator | None = None,
) -> CompositeCriterionGroup:
    group_id = f"criterion:0:group:{group_suffix}"
    return CompositeCriterionGroup(
        group_id=group_id,
        operator=operator,
        parent_criterion_index=0,
        parent_source_text="compound parent",
        subchecks=[
            CompositeCriterionSubcheck(
                subcheck_id=f"{group_id}:subcheck:{index + 1:03d}",
                operator=subcheck_operator or operator,
                source_text=f"subcheck {index + 1}",
                criterion=_condition(f"condition {index + 1}"),
            )
            for index in range(subcheck_count)
        ],
    )


def test_compound_no_groups_is_skipped() -> None:
    result = compile_compound_logic([], source_criterion_id="criterion:0")

    assert result.plan.status == "skipped"
    assert result.plan.operator == "none"
    assert result.plan.source_group_ids == []
    assert result.plan.subcheck_ids == []
    assert result.gaps == []
    assert result.diagnostics == []


@pytest.mark.parametrize("operator", ["any_of", "all_of"])
def test_compound_single_group_records_operator_and_subchecks(
    operator: CompositeOperator,
) -> None:
    group = _group("001", operator=operator)

    result = compile_compound_logic([group], source_criterion_id="criterion:0")

    assert result.plan.status == "resolved"
    assert result.plan.operator == operator
    assert result.plan.source_group_ids == ["criterion:0:group:001"]
    assert result.plan.subcheck_ids == [
        "criterion:0:group:001:subcheck:001",
        "criterion:0:group:001:subcheck:002",
    ]
    assert result.gaps == []


def test_compound_multiple_groups_keep_every_group_and_subcheck_id() -> None:
    first = _group("001", operator="all_of", subcheck_count=1)
    second = _group("002", operator="all_of", subcheck_count=2)

    result = compile_compound_logic([first, second], source_criterion_id="criterion:0")

    assert result.plan.status == "resolved"
    assert result.plan.source_group_ids == [
        "criterion:0:group:001",
        "criterion:0:group:002",
    ]
    assert result.plan.subcheck_ids == [
        "criterion:0:group:001:subcheck:001",
        "criterion:0:group:002:subcheck:001",
        "criterion:0:group:002:subcheck:002",
    ]


def test_compound_inconsistent_operators_are_ambiguous_with_gap() -> None:
    any_group = _group("001", operator="any_of")
    all_group = _group("002", operator="all_of")

    result = compile_compound_logic([any_group, all_group], source_criterion_id="criterion:0")

    assert result.plan.status == "ambiguous"
    assert result.plan.operator == "none"
    assert result.plan.source_group_ids == [
        "criterion:0:group:001",
        "criterion:0:group:002",
    ]
    assert result.plan.gap_ids == ["gap:criterion:0:compound_logic:operator_conflict"]
    assert result.gaps[0].kind == "unsupported_compound"
    assert result.gaps[0].domain == "compound"
    assert result.diagnostics[0].code == "compound_operator_conflict"


def test_compound_subcheck_operator_conflict_is_ambiguous_with_gap() -> None:
    group = _group("001", operator="any_of", subcheck_operator="all_of")

    result = compile_compound_logic([group], source_criterion_id="criterion:0")

    assert result.plan.status == "ambiguous"
    assert result.plan.gap_ids == ["gap:criterion:0:compound_logic:operator_conflict"]
    assert result.gaps[0].message.startswith("Composite groups for one parent")


def test_temporal_condition_event_mapped_to_condition_support() -> None:
    criterion = _temporal(event_text="type 2 diabetes", window_days=90)

    result = compile_temporal_window(criterion, source_criterion_id="criterion:4")

    assert result.event_surface == "type 2 diabetes"
    assert result.normalized_event_surface == "type 2 diabetes"
    assert result.window_days == 90
    assert result.direction == "within_past"
    assert result.event_resolved is True
    assert result.event_target_label == "Type 2 diabetes mellitus"
    assert result.supports[0].support_id == "support:criterion:4:temporal:event_condition"
    assert result.predicate.status == "resolved"
    assert result.predicate.expression == (
        "temporal_event(support:criterion:4:temporal:event_condition,within_past,90d)"
    )
    assert result.gaps == []


def test_temporal_diagnosis_surface_normalizes_to_condition_event() -> None:
    criterion = _temporal(event_text="recent T2D diagnosis", window_days=365)

    result = compile_temporal_window(criterion, source_criterion_id="criterion:4b")

    assert result.event_surface == "recent T2D diagnosis"
    assert result.normalized_event_surface == "recent t2d diagnosis"
    assert result.event_resolved is True
    assert result.event_target_label == "Type 2 diabetes mellitus"
    assert result.supports[0].surface == "type 2 diabetes"
    assert result.supports[0].normalized_surface == "type 2 diabetes"
    assert result.predicate.status == "resolved"
    assert result.diagnostics[0].code == "temporal_event_surface_normalized"
    assert result.diagnostics[0].facts[1].key == "lookup_surface"
    assert result.diagnostics[0].facts[1].value == "type 2 diabetes"


def test_temporal_diagnosis_prefix_normalizes_to_condition_event() -> None:
    criterion = _temporal(event_text="prior diagnosis of type 1 diabetes mellitus")

    result = compile_temporal_window(criterion, source_criterion_id="criterion:4c")

    assert result.event_resolved is True
    assert result.event_target_label == "Type 1 diabetes mellitus"
    assert result.supports[0].surface == "type 1 diabetes mellitus"
    assert result.diagnostics[0].code == "temporal_event_surface_normalized"


def test_temporal_unmapped_event_is_gap_not_executable() -> None:
    criterion = _temporal(event_text="liver transplant", window_days=365)

    result = compile_temporal_window(criterion, source_criterion_id="criterion:5")

    assert result.event_resolved is False
    assert result.supports == []
    assert result.predicate.status == "unresolved"
    assert result.predicate.expression is None
    assert result.gaps[0].gap_id == "gap:criterion:5:temporal:event_unmapped"
    assert result.gaps[0].kind == "unmapped_concept"
    assert result.gaps[0].stage == "concept_resolution"
    assert result.diagnostics[0].code == "temporal_window_not_executable"


def test_temporal_reviewed_nonmapped_event_is_typed_gap() -> None:
    criterion = _temporal(event_text="stable background therapy for PAH", window_days=90)

    result = compile_temporal_window(
        criterion,
        source_criterion_id="criterion:5b",
        reviewed_registry=load_reviewed_mapping_registry(),
    )

    assert result.event_resolved is False
    assert result.predicate.status == "unsupported"
    assert result.gaps[0].gap_id == "gap:criterion:5b:temporal:reviewed_composite_unhandled"
    assert result.gaps[0].kind == "unsupported_predicate"
    assert result.diagnostics[0].code == "temporal_event.reviewed.composite_unhandled"


def test_temporal_generic_event_surface_is_unsupported_gap() -> None:
    criterion = _temporal(event_text="screening", window_days=30)

    result = compile_temporal_window(criterion, source_criterion_id="criterion:6")

    assert result.event_resolved is False
    assert result.predicate.status == "unsupported"
    assert result.gaps[0].gap_id == "gap:criterion:6:temporal:generic_event"
    assert result.gaps[0].kind == "unsupported_predicate"


def test_temporal_generic_visit_surface_is_unsupported_gap() -> None:
    criterion = _temporal(event_text="screening visit", window_days=30)

    result = compile_temporal_window(criterion, source_criterion_id="criterion:6b")

    assert result.event_resolved is False
    assert result.predicate.status == "unsupported"
    assert result.gaps[0].gap_id == "gap:criterion:6b:temporal:generic_event"
    assert result.gaps[0].kind == "unsupported_predicate"


def test_temporal_future_direction_is_unsupported_even_when_event_maps() -> None:
    criterion = _temporal(event_text="type 2 diabetes", window_days=30, direction="within_future")

    result = compile_temporal_window(criterion, source_criterion_id="criterion:7")

    assert result.event_resolved is True
    assert result.supports
    assert result.predicate.status == "unsupported"
    assert result.predicate.expression is None
    assert [gap.gap_id for gap in result.gaps] == ["gap:criterion:7:temporal:unsupported_direction"]


def test_compound_and_temporal_ids_are_stable() -> None:
    groups = [_group("001", operator="any_of"), _group("002", operator="all_of")]
    criterion = _temporal(event_text="type 2 diabetes", window_days=180)

    first_compound = compile_compound_logic(groups, source_criterion_id="criterion:8")
    second_compound = compile_compound_logic(groups, source_criterion_id="criterion:8")
    first_temporal = compile_temporal_window(criterion, source_criterion_id="criterion:9")
    second_temporal = compile_temporal_window(criterion, source_criterion_id="criterion:9")

    assert first_compound.plan.gap_ids == second_compound.plan.gap_ids
    assert [gap.gap_id for gap in first_compound.gaps] == [
        gap.gap_id for gap in second_compound.gaps
    ]
    assert [support.support_id for support in first_temporal.supports] == [
        support.support_id for support in second_temporal.supports
    ]
    assert first_temporal.predicate.expression == second_temporal.predicate.expression


def test_non_temporal_input_returns_unsupported_gap() -> None:
    result = compile_temporal_window(_free_text(), source_criterion_id="criterion:10")

    assert result.event_resolved is False
    assert result.predicate.status == "unsupported"
    assert result.gaps[0].gap_id == "gap:criterion:10:temporal:not_temporal_window"
