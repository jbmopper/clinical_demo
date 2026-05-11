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
from .parity import (
    CriterionParityComparison,
    ParityClassification,
    ParityReport,
    compare_compilation_parity,
)
from .pipeline import compile_extracted_criteria, compiled_criterion_id, source_criterion_id
from .predicate_matcher import (
    COMPILED_PREDICATE_MATCHER_VERSION,
    match_compiled_criteria,
    match_compiled_criterion,
)
from .reviewer_queue import (
    CompilerGapQueue,
    CompilerGapQueueItem,
    RecommendedAction,
    Severity,
    compiler_gap_queue,
    compiler_gap_queue_object,
)
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
from .validation import (
    STRUCTURED_CRITERION_KINDS,
    AllowedNonExecutableClass,
    ClosedWorldValidationFinding,
    ClosedWorldValidationResult,
    ClosedWorldValidationSummary,
    ValidationSeverity,
    validate_compilation_for_closed_world,
    validate_compiled_criterion_for_closed_world,
)

__all__ = [
    "COMPILED_PREDICATE_MATCHER_VERSION",
    "COMPILER_VERSION",
    "STRUCTURED_CRITERION_KINDS",
    "AllowedNonExecutableClass",
    "CheckablePredicate",
    "CheckablePredicatePlan",
    "ClosedWorldValidationFinding",
    "ClosedWorldValidationResult",
    "ClosedWorldValidationSummary",
    "CompiledCriterion",
    "CompilerDiagnostic",
    "CompilerGapQueue",
    "CompilerGapQueueItem",
    "CompoundLogicCompilation",
    "CompoundLogicPlan",
    "CriterionCompilationResult",
    "CriterionParityComparison",
    "DiagnosticFact",
    "ExpansionPlan",
    "MeasurementResolutionResult",
    "MedicationAspectPlan",
    "MedicationCompilationResult",
    "ParityClassification",
    "ParityReport",
    "RecommendedAction",
    "ResolutionGap",
    "ResolutionSupport",
    "Severity",
    "TemporalWindowCompilation",
    "UnitNormalizationPlan",
    "ValidationSeverity",
    "compare_compilation_parity",
    "compile_compound_logic",
    "compile_extracted_criteria",
    "compile_measurement_resolution",
    "compile_medication_resolution",
    "compile_temporal_window",
    "compiled_criterion_id",
    "compiler_gap_queue",
    "compiler_gap_queue_object",
    "match_compiled_criteria",
    "match_compiled_criterion",
    "normalize_medication_surface",
    "source_criterion_id",
    "validate_compilation_for_closed_world",
    "validate_compiled_criterion_for_closed_world",
]
