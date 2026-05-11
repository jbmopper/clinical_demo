"""Parity reports for legacy matcher vs compiled-predicate execution."""

from __future__ import annotations

from collections import Counter
from typing import Final, Literal

from pydantic import BaseModel, Field

from clinical_demo.domain.trial import Trial
from clinical_demo.matcher import (
    DEFAULT_MATCHER_ASSUMPTION_MODE,
    MatcherAssumptionMode,
    MatchVerdict,
    match_extracted,
)
from clinical_demo.matcher.verdict import Verdict, VerdictReason
from clinical_demo.profile import PatientProfile

from .predicate_matcher import match_compiled_criteria
from .schema import CriterionCompilationResult

ParityClassification = Literal["same", "compiled_improved", "compiled_regressed", "changed"]
PARITY_CLASSIFICATIONS: Final[tuple[ParityClassification, ...]] = (
    "same",
    "compiled_improved",
    "compiled_regressed",
    "changed",
)


class CriterionParityComparison(BaseModel):
    """Per-criterion comparison between legacy and compiled execution."""

    compiled_id: str = Field(description="Stable compiled criterion id.")
    source_criterion_id: str = Field(description="Stable source criterion id.")
    source_index: int = Field(description="Zero-based source criterion index.")
    source_text: str = Field(description="Original criterion text.")
    legacy_verdict: Verdict = Field(description="Legacy matcher verdict.")
    legacy_reason: VerdictReason = Field(description="Legacy matcher reason code.")
    compiled_verdict: Verdict = Field(description="Compiled-predicate verdict.")
    compiled_reason: VerdictReason = Field(description="Compiled-predicate reason code.")
    classification: ParityClassification = Field(description="Conservative parity classification.")
    rationale: str = Field(description="Short explanation of the classification.")


class ParityReport(BaseModel):
    """Whole-run parity report for one compiled criteria set."""

    matcher_assumption_mode: MatcherAssumptionMode = Field(
        description="Matcher assumption mode used by both paths."
    )
    criteria: list[CriterionParityComparison] = Field(
        description="Per-criterion parity comparisons in source order."
    )
    summary_counts: dict[ParityClassification, int] = Field(
        description="Counts by parity classification."
    )

    @property
    def total_criteria(self) -> int:
        """Number of criteria compared."""

        return len(self.criteria)


def compare_compilation_parity(
    compilation: CriterionCompilationResult,
    profile: PatientProfile,
    trial: Trial,
    *,
    matcher_assumption_mode: MatcherAssumptionMode = DEFAULT_MATCHER_ASSUMPTION_MODE,
) -> ParityReport:
    """Compare legacy matcher execution with compiled-predicate execution."""

    legacy_verdicts = match_extracted(
        compilation.matcher_inputs,
        profile,
        trial,
        matcher_assumption_mode=matcher_assumption_mode,
    )
    compiled_verdicts = match_compiled_criteria(
        compilation,
        profile,
        trial,
        matcher_assumption_mode=matcher_assumption_mode,
    )

    comparisons = [
        _compare_criterion(
            compiled_id=compiled.compiled_id,
            source_criterion_id=compiled.source_criterion_id,
            source_index=compiled.source_index,
            source_text=compiled.source_text,
            legacy=legacy,
            compiled=compiled_verdict,
        )
        for compiled, legacy, compiled_verdict in zip(
            compilation.criteria,
            legacy_verdicts,
            compiled_verdicts,
            strict=True,
        )
    ]
    counts = Counter(comparison.classification for comparison in comparisons)
    return ParityReport(
        matcher_assumption_mode=matcher_assumption_mode,
        criteria=comparisons,
        summary_counts={
            classification: counts[classification] for classification in PARITY_CLASSIFICATIONS
        },
    )


def _compare_criterion(
    *,
    compiled_id: str,
    source_criterion_id: str,
    source_index: int,
    source_text: str,
    legacy: MatchVerdict,
    compiled: MatchVerdict,
) -> CriterionParityComparison:
    classification, rationale = _classify(
        legacy_verdict=legacy.verdict,
        legacy_reason=legacy.reason,
        compiled_verdict=compiled.verdict,
        compiled_reason=compiled.reason,
    )
    return CriterionParityComparison(
        compiled_id=compiled_id,
        source_criterion_id=source_criterion_id,
        source_index=source_index,
        source_text=source_text,
        legacy_verdict=legacy.verdict,
        legacy_reason=legacy.reason,
        compiled_verdict=compiled.verdict,
        compiled_reason=compiled.reason,
        classification=classification,
        rationale=rationale,
    )


def _classify(
    *,
    legacy_verdict: Verdict,
    legacy_reason: VerdictReason,
    compiled_verdict: Verdict,
    compiled_reason: VerdictReason,
) -> tuple[ParityClassification, str]:
    if legacy_verdict == compiled_verdict and legacy_reason == compiled_reason:
        return "same", "Compiled predicate matched the legacy verdict and reason."

    legacy_determinate = _is_determinate(legacy_verdict)
    compiled_determinate = _is_determinate(compiled_verdict)
    if not legacy_determinate and compiled_determinate:
        return (
            "compiled_improved",
            "Compiled predicate resolved a legacy indeterminate verdict.",
        )
    if legacy_determinate and not compiled_determinate:
        return (
            "compiled_regressed",
            "Compiled predicate became indeterminate where legacy was determinate.",
        )
    if legacy_determinate and compiled_determinate and legacy_verdict != compiled_verdict:
        return (
            "compiled_regressed",
            "Compiled predicate changed a determinate legacy verdict.",
        )
    return "changed", "Compiled predicate changed the verdict reason without a clear win/loss."


def _is_determinate(verdict: Verdict) -> bool:
    return verdict in {"pass", "fail"}


__all__ = [
    "CriterionParityComparison",
    "ParityClassification",
    "ParityReport",
    "compare_compilation_parity",
]
