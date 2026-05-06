"""Boolean rollup helpers for composite criteria.

`match_extracted` uses these truth tables for flat native composite
groups. The scorer still keeps the top-level criterion list as an AND:
one parent composite row contributes one rolled-up verdict.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from .verdict import Verdict, VerdictReason

CompositeOperator = Literal["any_of", "all_of"]


@dataclass(frozen=True)
class CompositeRollup:
    """Result of rolling up subcheck verdicts under one boolean operator."""

    verdict: Verdict
    reason: VerdictReason
    rationale: str


def roll_up_composite_verdict(
    operator: CompositeOperator,
    subcheck_verdicts: Sequence[Verdict],
) -> CompositeRollup:
    """Apply boolean `any_of` / `all_of` semantics to subcheck verdicts.

    Indeterminate subchecks preserve uncertainty unless the operator
    can already decide the parent: one pass decides `any_of`, and one
    fail decides `all_of`.
    """

    counts = Counter(subcheck_verdicts)
    if not subcheck_verdicts:
        return CompositeRollup(
            verdict="indeterminate",
            reason="ambiguous_criterion",
            rationale="Composite criterion has no subchecks to roll up.",
        )

    if operator == "any_of":
        if counts["pass"]:
            return _decisive(
                "pass",
                operator=operator,
                counts=counts,
                rationale="At least one subcheck passed an any_of composite.",
            )
        if counts["fail"] == len(subcheck_verdicts):
            return _decisive(
                "fail",
                operator=operator,
                counts=counts,
                rationale="Every subcheck failed an any_of composite.",
            )
        return _indeterminate(operator=operator, counts=counts)

    if counts["fail"]:
        return _decisive(
            "fail",
            operator=operator,
            counts=counts,
            rationale="At least one subcheck failed an all_of composite.",
        )
    if counts["pass"] == len(subcheck_verdicts):
        return _decisive(
            "pass",
            operator=operator,
            counts=counts,
            rationale="Every subcheck passed an all_of composite.",
        )
    return _indeterminate(operator=operator, counts=counts)


def _decisive(
    verdict: Literal["pass", "fail"],
    *,
    operator: CompositeOperator,
    counts: Counter[Verdict],
    rationale: str,
) -> CompositeRollup:
    return CompositeRollup(
        verdict=verdict,
        reason="ok",
        rationale=f"{rationale} ({_count_summary(operator, counts)})",
    )


def _indeterminate(*, operator: CompositeOperator, counts: Counter[Verdict]) -> CompositeRollup:
    return CompositeRollup(
        verdict="indeterminate",
        reason="human_review_required",
        rationale=(
            "Composite criterion cannot be decided while at least one needed "
            f"subcheck is indeterminate. ({_count_summary(operator, counts)})"
        ),
    )


def _count_summary(operator: CompositeOperator, counts: Counter[Verdict]) -> str:
    return (
        f"operator={operator}; pass={counts['pass']}; fail={counts['fail']}; "
        f"indeterminate={counts['indeterminate']}"
    )


__all__ = [
    "CompositeOperator",
    "CompositeRollup",
    "roll_up_composite_verdict",
]
