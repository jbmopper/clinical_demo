"""Criterion compiler/resolution-layer public API."""

from .pipeline import compile_extracted_criteria, compiled_criterion_id, source_criterion_id
from .schema import (
    COMPILER_VERSION,
    CheckablePredicatePlan,
    CompiledCriterion,
    CompilerDiagnostic,
    CompoundLogicPlan,
    CriterionCompilationResult,
    DiagnosticFact,
    ExpansionPlan,
    ResolutionGap,
    ResolutionSupport,
    UnitNormalizationPlan,
)

__all__ = [
    "COMPILER_VERSION",
    "CheckablePredicatePlan",
    "CompiledCriterion",
    "CompilerDiagnostic",
    "CompoundLogicPlan",
    "CriterionCompilationResult",
    "DiagnosticFact",
    "ExpansionPlan",
    "ResolutionGap",
    "ResolutionSupport",
    "UnitNormalizationPlan",
    "compile_extracted_criteria",
    "compiled_criterion_id",
    "source_criterion_id",
]
