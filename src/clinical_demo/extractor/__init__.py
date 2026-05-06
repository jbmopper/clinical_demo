"""LLM-driven extraction of structured eligibility criteria from trial text."""

from .composite import (
    CompositeCriterionGroup,
    CompositeCriterionSubcheck,
    CompositeOperator,
    build_composite_criterion_groups,
)
from .enrich import INJECTED_SOURCE_PREFIX, enrich_with_structured_fields
from .extractor import (
    ExtractionResult,
    ExtractorError,
    ExtractorMissingParsedError,
    ExtractorRefusalError,
    extract_criteria,
)
from .fix import CRITERION_FIX_NOTE_PREFIX, fix_extracted_criteria
from .prompt import PROMPT_VERSION, SYSTEM_PROMPT, build_messages
from .schema import (
    CRITERION_KINDS,
    AgeCriterion,
    ConditionCriterion,
    CriterionKind,
    EntityMention,
    EntityType,
    ExtractedCriteria,
    ExtractedCriterion,
    ExtractionMetadata,
    ExtractorRunMeta,
    FreeTextCriterion,
    MeasurementCriterion,
    MedicationCriterion,
    Polarity,
    SexCriterion,
    TemporalWindowCriterion,
    ThresholdOperator,
)

__all__ = [
    "CRITERION_FIX_NOTE_PREFIX",
    "CRITERION_KINDS",
    "INJECTED_SOURCE_PREFIX",
    "PROMPT_VERSION",
    "SYSTEM_PROMPT",
    "AgeCriterion",
    "CompositeCriterionGroup",
    "CompositeCriterionSubcheck",
    "CompositeOperator",
    "ConditionCriterion",
    "CriterionKind",
    "EntityMention",
    "EntityType",
    "ExtractedCriteria",
    "ExtractedCriterion",
    "ExtractionMetadata",
    "ExtractionResult",
    "ExtractorError",
    "ExtractorMissingParsedError",
    "ExtractorRefusalError",
    "ExtractorRunMeta",
    "FreeTextCriterion",
    "MeasurementCriterion",
    "MedicationCriterion",
    "Polarity",
    "SexCriterion",
    "TemporalWindowCriterion",
    "ThresholdOperator",
    "build_composite_criterion_groups",
    "build_messages",
    "enrich_with_structured_fields",
    "extract_criteria",
    "fix_extracted_criteria",
]
