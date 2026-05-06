"""Tests for internal composite criterion group construction."""

from __future__ import annotations

from clinical_demo.extractor.composite import build_composite_criterion_groups
from tests.matcher._fixtures import crit_free_text


def test_build_composite_groups_for_explicit_or_bundle() -> None:
    criterion = crit_free_text().model_copy(
        update={
            "source_text": (
                "Hyperglycemia (HbA1c >= 6.5%; OR fasting plasma glucose >= "
                "126 mg/dL; OR random plasma glucose >= 200 mg/dL)"
            )
        }
    )

    groups = build_composite_criterion_groups(criterion, criterion_index=2)

    assert len(groups) == 1
    group = groups[0]
    assert group.group_id == "criterion:2:group:001"
    assert group.operator == "any_of"
    assert [subcheck.subcheck_id for subcheck in group.subchecks] == [
        "criterion:2:group:001:subcheck:001",
        "criterion:2:group:001:subcheck:002",
        "criterion:2:group:001:subcheck:003",
    ]
    assert group.subchecks[0].criterion.kind == "measurement_threshold"
    assert group.subchecks[0].criterion.measurement is not None
    assert group.subchecks[0].criterion.measurement.measurement_text == "HbA1c"
    assert group.subchecks[0].criterion.measurement.operator == ">="
    assert group.subchecks[0].criterion.measurement.value == 6.5
    assert group.subchecks[1].criterion.kind == "free_text"


def test_build_composite_groups_for_explicit_and_bundle() -> None:
    criterion = crit_free_text().model_copy(update={"source_text": "HbA1c >= 7%; AND HbA1c <= 10%"})

    groups = build_composite_criterion_groups(criterion, criterion_index=3)

    assert len(groups) == 1
    assert groups[0].operator == "all_of"
    assert [subcheck.criterion.kind for subcheck in groups[0].subchecks] == [
        "measurement_threshold",
        "measurement_threshold",
    ]


def test_build_composite_groups_ignores_non_explicit_bundle() -> None:
    criterion = crit_free_text().model_copy(update={"source_text": "Willing to follow protocol"})

    assert build_composite_criterion_groups(criterion, criterion_index=0) == []
