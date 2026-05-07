"""Privacy boundary for outbound LLM and observability data.

Internal domain objects remain untouched. Callers pass prompt text,
trace payloads, or metadata through this module immediately before
crossing a non-HIPAA boundary.
"""

from .anonymization import (
    AnonymizationContext,
    AnonymizedText,
    EntityReplacement,
    PresidioPrivacyEngine,
    PrivacyEngine,
    PrivacyPolicy,
    anonymization_context,
    anonymize_text,
    current_anonymization_context,
    sanitize_for_metadata,
    sanitize_for_public_export,
    sanitize_for_trace,
)

__all__ = [
    "AnonymizationContext",
    "AnonymizedText",
    "EntityReplacement",
    "PresidioPrivacyEngine",
    "PrivacyEngine",
    "PrivacyPolicy",
    "anonymization_context",
    "anonymize_text",
    "current_anonymization_context",
    "sanitize_for_metadata",
    "sanitize_for_public_export",
    "sanitize_for_trace",
]
