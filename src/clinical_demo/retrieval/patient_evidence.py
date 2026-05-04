"""Structured patient-evidence retrieval.

This is the retrieval-only layer for Phase 2.14. It does not decide
eligibility. It ranks patient source rows that a reviewer or bounded
adjudicator should inspect for one criterion. Terminology/code matches
are precision anchors when available; lexical overlap and row-kind
filters keep the layer useful when concept mapping is incomplete.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

from pydantic import BaseModel, Field

from clinical_demo.extractor.schema import ExtractedCriterion
from clinical_demo.matcher.concept_lookup import lookup_condition, lookup_lab, lookup_medication


class RetrievalSourceRow(BaseModel):
    """One patient or trial source row with a stable local id."""

    row_id: str
    source: str
    kind: str
    label: str
    value: str
    date: str | None = None
    code: str | None = None
    system: str | None = None
    status: str | None = None


class RetrievedPatientEvidence(BaseModel):
    """A ranked source row returned by structured retrieval."""

    row: RetrievalSourceRow
    score: int = Field(ge=1)
    reasons: list[str] = Field(default_factory=list)


_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "any",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "has",
        "have",
        "in",
        "is",
        "must",
        "no",
        "not",
        "of",
        "on",
        "or",
        "per",
        "prior",
        "the",
        "to",
        "with",
        "within",
    }
)


def retrieve_structured_patient_evidence(
    criterion: ExtractedCriterion,
    source_rows: Sequence[RetrievalSourceRow],
    *,
    limit: int = 12,
) -> list[RetrievedPatientEvidence]:
    """Rank structured patient rows relevant to one criterion.

    Returns patient rows only; trial rows remain criterion context and
    should be passed separately to any adjudicator.
    """

    if limit < 1:
        raise ValueError("limit must be positive")

    query_terms = _criterion_terms(criterion)
    preferred_kinds = _preferred_patient_kinds(criterion)
    anchored_codes = _anchored_codes(criterion)

    retrieved: list[RetrievedPatientEvidence] = []
    for row in source_rows:
        if row.source != "patient":
            continue
        score, reasons = _score_row(
            row,
            query_terms=query_terms,
            preferred_kinds=preferred_kinds,
            anchored_codes=anchored_codes,
        )
        if score > 0:
            retrieved.append(RetrievedPatientEvidence(row=row, score=score, reasons=reasons))

    retrieved.sort(key=lambda item: (-item.score, item.row.row_id))
    return retrieved[:limit]


def _score_row(
    row: RetrievalSourceRow,
    *,
    query_terms: set[str],
    preferred_kinds: set[str],
    anchored_codes: set[str],
) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []

    if row.code and row.code in anchored_codes:
        score += 20
        reasons.append(f"code:{row.code}")

    row_terms = _tokens(" ".join(_row_text_parts(row)))
    overlaps = sorted(query_terms & row_terms)
    if overlaps:
        score += 2 * len(overlaps)
        reasons.extend(f"term:{term}" for term in overlaps[:5])

    normalized_kind = row.kind.lower()
    if score > 0 and normalized_kind in preferred_kinds:
        score += 3
        reasons.insert(0, f"kind:{normalized_kind}")

    return score, reasons


def _criterion_terms(criterion: ExtractedCriterion) -> set[str]:
    parts = [criterion.source_text]
    if criterion.condition is not None:
        parts.append(criterion.condition.condition_text)
    if criterion.medication is not None:
        parts.append(criterion.medication.medication_text)
    if criterion.measurement is not None:
        parts.append(criterion.measurement.measurement_text)
        if criterion.measurement.unit:
            parts.append(criterion.measurement.unit)
    if criterion.temporal_window is not None:
        parts.append(criterion.temporal_window.event_text)
    if criterion.free_text is not None:
        parts.append(criterion.free_text.note)
    parts.extend(mention.text for mention in criterion.mentions)
    return _tokens(" ".join(parts))


def _preferred_patient_kinds(criterion: ExtractedCriterion) -> set[str]:
    if criterion.kind in {"condition_present", "condition_absent", "temporal_window"}:
        return {"condition"}
    if criterion.kind in {"medication_present", "medication_absent"}:
        return {"medication"}
    if criterion.kind == "measurement_threshold":
        return {"observation"}
    if criterion.kind in {"age", "sex"}:
        return {"demographics"}
    return {"condition", "medication", "observation"}


def _anchored_codes(criterion: ExtractedCriterion) -> set[str]:
    concept_sets = []
    if criterion.condition is not None:
        concept_sets.append(lookup_condition(criterion.condition.condition_text))
    if criterion.medication is not None:
        concept_sets.append(lookup_medication(criterion.medication.medication_text))
    if criterion.measurement is not None:
        concept_sets.append(lookup_lab(criterion.measurement.measurement_text))
    return {
        code
        for concept_set in concept_sets
        if concept_set is not None
        for code in concept_set.codes
    }


def _row_text_parts(row: RetrievalSourceRow) -> Iterable[str]:
    yield row.kind
    yield row.label
    yield row.value
    if row.code:
        yield row.code
    if row.status:
        yield row.status


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in _TOKEN_RE.findall(text.lower())
        if token not in _STOPWORDS and not token.isdigit()
    }


__all__ = [
    "RetrievalSourceRow",
    "RetrievedPatientEvidence",
    "retrieve_structured_patient_evidence",
]
