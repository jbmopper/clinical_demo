"""Closed-world validation for compiler outputs.

This module is intentionally reporting-only. It inspects compiler IR for
closed-world readiness without changing predicate generation or scoring.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from clinical_demo.extractor.schema import CriterionKind

from .schema import CompiledCriterion, CriterionCompilationResult

ValidationSeverity = Literal["info", "warning", "error"]
ClosedWorldFindingCode = Literal[
    "allowed_non_executable",
    "structured_unresolved_gaps",
    "structured_missing_executable",
]
AllowedNonExecutableClass = Literal["free_text_review"]

STRUCTURED_CRITERION_KINDS: frozenset[CriterionKind] = frozenset(
    {
        "age",
        "sex",
        "condition_present",
        "condition_absent",
        "medication_present",
        "medication_absent",
        "measurement_threshold",
        "temporal_window",
    }
)


class ClosedWorldValidationFinding(BaseModel):
    """Reviewer-facing validation finding for one compiled criterion."""

    code: ClosedWorldFindingCode = Field(description="Stable closed-world finding code.")
    severity: ValidationSeverity = Field(description="Reviewer-facing severity.")
    blocking: bool = Field(description="Whether this finding blocks closed-world execution.")
    source_criterion_id: str = Field(description="Source criterion id for the finding.")
    compiled_id: str = Field(description="Compiled criterion id for the finding.")
    criterion_kind: CriterionKind = Field(description="Extractor criterion kind.")
    gap_ids: list[str] = Field(
        default_factory=list,
        description="Resolution gap ids contributing to this finding.",
    )
    allowed_non_executable_class: AllowedNonExecutableClass | None = Field(
        default=None,
        description="Typed non-executable class allowed in closed-world validation.",
    )
    message: str = Field(description="Reviewer-facing validation message.")


class ClosedWorldValidationSummary(BaseModel):
    """Deterministic aggregate counts for closed-world validation."""

    criteria_count: int = Field(description="Total compiled criteria checked.")
    structured_criteria_count: int = Field(description="Structured criteria checked.")
    executable_criteria_count: int = Field(
        description="Criteria with at least one executable checkable predicate."
    )
    review_criteria_count: int = Field(description="Criteria allowed as non-executable review.")
    finding_count: int = Field(description="Total validation findings.")
    blocking_count: int = Field(description="Blocking validation findings.")
    non_blocking_count: int = Field(description="Non-blocking validation findings.")
    info_count: int = Field(description="Info findings.")
    warning_count: int = Field(description="Warning findings.")
    error_count: int = Field(description="Error findings.")


class ClosedWorldValidationResult(BaseModel):
    """Aggregate closed-world validation result for a compilation."""

    ok: bool = Field(description="True when no blocking findings were emitted.")
    findings: list[ClosedWorldValidationFinding] = Field(
        default_factory=list,
        description="Validation findings in source criterion order.",
    )
    summary: ClosedWorldValidationSummary = Field(
        description="Deterministic summary counts for the validation pass."
    )


def validate_compiled_criterion_for_closed_world(
    compiled: CompiledCriterion,
) -> list[ClosedWorldValidationFinding]:
    """Validate one compiled criterion for closed-world readiness."""

    if compiled.criterion_kind == "free_text" and not compiled.checkable_predicates:
        return [
            ClosedWorldValidationFinding(
                code="allowed_non_executable",
                severity="info",
                blocking=False,
                source_criterion_id=compiled.source_criterion_id,
                compiled_id=compiled.compiled_id,
                criterion_kind=compiled.criterion_kind,
                allowed_non_executable_class="free_text_review",
                message=(
                    "Free-text criterion is allowed as a non-executable human-review item "
                    "in closed-world validation."
                ),
            )
        ]

    findings: list[ClosedWorldValidationFinding] = []
    gap_ids = [gap.gap_id for gap in compiled.unresolved_gaps]
    if gap_ids:
        findings.append(
            ClosedWorldValidationFinding(
                code="structured_unresolved_gaps",
                severity="error",
                blocking=True,
                source_criterion_id=compiled.source_criterion_id,
                compiled_id=compiled.compiled_id,
                criterion_kind=compiled.criterion_kind,
                gap_ids=gap_ids,
                message=_gap_message(compiled),
            )
        )

    if not compiled.checkable_predicates:
        findings.append(
            ClosedWorldValidationFinding(
                code="structured_missing_executable",
                severity="error",
                blocking=True,
                source_criterion_id=compiled.source_criterion_id,
                compiled_id=compiled.compiled_id,
                criterion_kind=compiled.criterion_kind,
                gap_ids=gap_ids,
                message=(
                    f"Structured {compiled.criterion_kind!r} criterion does not have an "
                    "executable CheckablePredicate and is not an allowed non-executable class."
                ),
            )
        )

    return findings


def validate_compilation_for_closed_world(
    compilation: CriterionCompilationResult,
) -> ClosedWorldValidationResult:
    """Validate a compiled result for closed-world execution readiness."""

    findings: list[ClosedWorldValidationFinding] = []
    for compiled in compilation.criteria:
        findings.extend(validate_compiled_criterion_for_closed_world(compiled))

    blocking_count = sum(1 for finding in findings if finding.blocking)
    summary = ClosedWorldValidationSummary(
        criteria_count=len(compilation.criteria),
        structured_criteria_count=sum(
            1 for compiled in compilation.criteria if _is_structured(compiled)
        ),
        executable_criteria_count=sum(
            1 for compiled in compilation.criteria if compiled.checkable_predicates
        ),
        review_criteria_count=sum(
            1 for finding in findings if finding.allowed_non_executable_class == "free_text_review"
        ),
        finding_count=len(findings),
        blocking_count=blocking_count,
        non_blocking_count=len(findings) - blocking_count,
        info_count=sum(1 for finding in findings if finding.severity == "info"),
        warning_count=sum(1 for finding in findings if finding.severity == "warning"),
        error_count=sum(1 for finding in findings if finding.severity == "error"),
    )
    return ClosedWorldValidationResult(
        ok=blocking_count == 0,
        findings=findings,
        summary=summary,
    )


def _is_structured(compiled: CompiledCriterion) -> bool:
    return compiled.criterion_kind in STRUCTURED_CRITERION_KINDS


def _gap_message(compiled: CompiledCriterion) -> str:
    gap_ids = ", ".join(gap.gap_id for gap in compiled.unresolved_gaps)
    gap_messages = "; ".join(gap.message for gap in compiled.unresolved_gaps)
    return (
        f"Structured {compiled.criterion_kind!r} criterion has unresolved compiler gaps "
        f"blocking closed-world execution ({gap_ids}): {gap_messages}"
    )


__all__ = [
    "STRUCTURED_CRITERION_KINDS",
    "AllowedNonExecutableClass",
    "ClosedWorldValidationFinding",
    "ClosedWorldValidationResult",
    "ClosedWorldValidationSummary",
    "ValidationSeverity",
    "validate_compilation_for_closed_world",
    "validate_compiled_criterion_for_closed_world",
]
