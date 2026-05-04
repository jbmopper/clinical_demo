"""Deterministic per-criterion matcher.

Consumes `ExtractedCriterion` rows from the LLM extractor (see
`clinical_demo.extractor`) and produces `MatchVerdict` rows the
aggregator and reviewer UI consume.
"""

from .concept_lookup import lookup_condition, lookup_lab, lookup_medication
from .matcher import MATCHER_VERSION, match_criterion, match_extracted
from .modes import (
    DEFAULT_LLM_USE_LEVEL,
    DEFAULT_MATCHER_ASSUMPTION_MODE,
    LLMUseLevel,
    MatcherAssumptionMode,
)
from .verdict import (
    ConditionEvidence,
    DemographicsEvidence,
    Evidence,
    EvidenceKind,
    LabEvidence,
    MatchVerdict,
    MedicationEvidence,
    MissingEvidence,
    TrialFieldEvidence,
    Verdict,
    VerdictReason,
)

__all__ = [
    "DEFAULT_LLM_USE_LEVEL",
    "DEFAULT_MATCHER_ASSUMPTION_MODE",
    "MATCHER_VERSION",
    "ConditionEvidence",
    "DemographicsEvidence",
    "Evidence",
    "EvidenceKind",
    "LLMUseLevel",
    "LabEvidence",
    "MatchVerdict",
    "MatcherAssumptionMode",
    "MedicationEvidence",
    "MissingEvidence",
    "TrialFieldEvidence",
    "Verdict",
    "VerdictReason",
    "lookup_condition",
    "lookup_lab",
    "lookup_medication",
    "match_criterion",
    "match_extracted",
]
