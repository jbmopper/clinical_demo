"""Tests for composite criterion boolean rollup semantics."""

from __future__ import annotations

from typing import Literal

import pytest

from clinical_demo.extractor.schema import (
    CompositeCriterionGroup,
    CompositeCriterionSubcheck,
    ExtractedCriterion,
)
from clinical_demo.matcher import Verdict, match_extracted, roll_up_composite_verdict
from tests.matcher._fixtures import (
    crit_free_text,
    crit_measurement,
    make_lab,
    make_profile,
    make_trial,
)


@pytest.mark.parametrize(
    ("subchecks", "expected"),
    [
        (["pass", "fail"], "pass"),
        (["pass", "indeterminate"], "pass"),
        (["fail", "fail"], "fail"),
        (["fail", "indeterminate"], "indeterminate"),
        (["indeterminate", "indeterminate"], "indeterminate"),
        ([], "indeterminate"),
    ],
)
def test_any_of_composite_rollup(subchecks: list[Verdict], expected: Verdict) -> None:
    result = roll_up_composite_verdict("any_of", subchecks)

    assert result.verdict == expected
    if expected in {"pass", "fail"}:
        assert result.reason == "ok"
    elif subchecks:
        assert result.reason == "human_review_required"
    assert "operator=any_of" in result.rationale or not subchecks


@pytest.mark.parametrize(
    ("subchecks", "expected"),
    [
        (["pass", "pass"], "pass"),
        (["pass", "fail"], "fail"),
        (["fail", "indeterminate"], "fail"),
        (["pass", "indeterminate"], "indeterminate"),
        (["indeterminate", "indeterminate"], "indeterminate"),
        ([], "indeterminate"),
    ],
)
def test_all_of_composite_rollup(subchecks: list[Verdict], expected: Verdict) -> None:
    result = roll_up_composite_verdict("all_of", subchecks)

    assert result.verdict == expected
    if expected in {"pass", "fail"}:
        assert result.reason == "ok"
    elif subchecks:
        assert result.reason == "human_review_required"
    assert "operator=all_of" in result.rationale or not subchecks


def test_empty_composite_is_ambiguous() -> None:
    result = roll_up_composite_verdict("any_of", [])

    assert result.verdict == "indeterminate"
    assert result.reason == "ambiguous_criterion"


def test_match_extracted_consumes_any_of_composite_group() -> None:
    parent = crit_free_text()
    group = _composite_group(
        parent=parent,
        subchecks=[
            crit_measurement(text="hba1c", operator=">=", value=6.5, unit="%"),
            crit_measurement(text="hba1c", operator="<=", value=6.0, unit="%"),
        ],
    )
    profile = make_profile(observations=[make_lab(value=7.2, unit="%")])

    verdicts = match_extracted(
        [parent],
        profile,
        make_trial(),
        composite_groups=[group],
    )

    assert len(verdicts) == 1
    assert verdicts[0].criterion == parent
    assert verdicts[0].verdict == "pass"
    assert verdicts[0].reason == "ok"
    assert "Composite any_of group" in verdicts[0].rationale


def test_match_extracted_applies_exclusion_polarity_after_composite_rollup() -> None:
    parent = crit_free_text(polarity="exclusion")
    group = _composite_group(
        parent=parent,
        subchecks=[
            crit_measurement(text="hba1c", operator=">=", value=6.5, unit="%"),
            crit_measurement(text="hba1c", operator="<=", value=6.0, unit="%"),
        ],
    )
    profile = make_profile(observations=[make_lab(value=7.2, unit="%")])

    verdicts = match_extracted(
        [parent],
        profile,
        make_trial(),
        composite_groups=[group],
    )

    assert verdicts[0].verdict == "fail"
    assert verdicts[0].reason == "ok"


def _composite_group(
    *,
    parent: ExtractedCriterion,
    subchecks: list[ExtractedCriterion],
    operator: Literal["any_of", "all_of"] = "any_of",
) -> CompositeCriterionGroup:
    return CompositeCriterionGroup(
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
