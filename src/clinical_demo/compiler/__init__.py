"""Criterion compiler/resolution-layer public API."""

from .compound_time import (
    CompoundLogicCompilation,
    TemporalWindowCompilation,
    compile_compound_logic,
    compile_temporal_window,
)
from .measurement import MeasurementResolutionResult, compile_measurement_resolution
from .medication import (
    MedicationAspectPlan,
    MedicationCompilationResult,
    compile_medication_resolution,
    normalize_medication_surface,
)
from .pipeline import compile_extracted_criteria, compiled_criterion_id, source_criterion_id
from .schema import (
    COMPILER_VERSION,
    CheckablePredicate,
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
    "CheckablePredicate",
    "CheckablePredicatePlan",
    "CompiledCriterion",
    "CompilerDiagnostic",
    "CompoundLogicCompilation",
    "CompoundLogicPlan",
    "CriterionCompilationResult",
    "DiagnosticFact",
    "ExpansionPlan",
    "MeasurementResolutionResult",
    "MedicationAspectPlan",
    "MedicationCompilationResult",
    "ResolutionGap",
    "ResolutionSupport",
    "TemporalWindowCompilation",
    "UnitNormalizationPlan",
    "compile_compound_logic",
    "compile_extracted_criteria",
    "compile_measurement_resolution",
    "compile_medication_resolution",
    "compile_temporal_window",
    "compiled_criterion_id",
    "normalize_medication_surface",
    "source_criterion_id",
]
