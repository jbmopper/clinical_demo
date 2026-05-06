"""Tests for composite criterion boolean rollup semantics."""

from __future__ import annotations

import pytest

from clinical_demo.matcher import Verdict, roll_up_composite_verdict


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
