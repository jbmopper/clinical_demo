"""Bounded source-grounded patient-evidence adjudication."""

from .patient_evidence import (
    PATIENT_EVIDENCE_ADJUDICATOR_VERSION,
    PatientEvidenceAdjudicatorOutput,
    PatientEvidenceAdjudicatorReason,
    adjudicate_patient_evidence,
)

__all__ = [
    "PATIENT_EVIDENCE_ADJUDICATOR_VERSION",
    "PatientEvidenceAdjudicatorOutput",
    "PatientEvidenceAdjudicatorReason",
    "adjudicate_patient_evidence",
]
