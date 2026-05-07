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

from clinical_demo.domain.patient import ClinicalNote, LabObservation, Medication, Patient
from clinical_demo.domain.trial import Trial
from clinical_demo.extractor.composite import build_composite_criterion_groups
from clinical_demo.extractor.schema import (
    ConditionCriterion,
    ExtractedCriterion,
    MeasurementCriterion,
    MedicationCriterion,
)
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


def structured_source_rows_for_pair(
    patient: Patient,
    trial: Trial,
    *,
    max_conditions: int = 40,
    max_observations: int = 40,
    max_medications: int = 30,
    max_note_snippets: int = 30,
) -> list[RetrievalSourceRow]:
    """Build compact patient/trial source rows with stable local IDs."""

    patient_rows = [
        RetrievalSourceRow(
            row_id="patient:000",
            source="patient",
            kind="demographics",
            label="Sex",
            value=patient.sex,
        ),
        RetrievalSourceRow(
            row_id="patient:001",
            source="patient",
            kind="demographics",
            label="Birth date",
            value=patient.birth_date.isoformat(),
        ),
        *_patient_condition_rows(patient, start_index=2, limit=max_conditions),
    ]
    observation_start = len(patient_rows)
    patient_rows.extend(
        _patient_observation_rows(patient, start_index=observation_start, limit=max_observations)
    )
    medication_start = len(patient_rows)
    patient_rows.extend(
        _patient_medication_rows(patient, start_index=medication_start, limit=max_medications)
    )
    note_start = len(patient_rows)
    patient_rows.extend(
        _patient_note_rows(patient, start_index=note_start, limit=max_note_snippets)
    )

    trial_rows = [
        RetrievalSourceRow(
            row_id="trial:000",
            source="trial",
            kind="trial_field",
            label="Title",
            value=trial.title,
        ),
        RetrievalSourceRow(
            row_id="trial:001",
            source="trial",
            kind="trial_field",
            label="Conditions",
            value=", ".join(trial.conditions) if trial.conditions else "(none listed)",
        ),
        RetrievalSourceRow(
            row_id="trial:002",
            source="trial",
            kind="trial_field",
            label="Minimum age",
            value=trial.minimum_age or "(not specified)",
        ),
        RetrievalSourceRow(
            row_id="trial:003",
            source="trial",
            kind="trial_field",
            label="Maximum age",
            value=trial.maximum_age or "(not specified)",
        ),
        RetrievalSourceRow(
            row_id="trial:004",
            source="trial",
            kind="trial_field",
            label="Sex",
            value=trial.sex,
        ),
    ]
    return [*patient_rows, *trial_rows]


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

    merged: dict[str, RetrievedPatientEvidence] = {}
    for item in _retrieve_structured_patient_evidence_direct(
        criterion,
        source_rows,
        limit=limit,
    ):
        _merge_retrieved_item(merged, item)

    for surrogate in _correlatable_free_text_surrogates(criterion):
        for item in _retrieve_structured_patient_evidence_direct(
            surrogate,
            source_rows,
            limit=limit,
        ):
            _merge_retrieved_item(
                merged,
                item.model_copy(
                    update={
                        "reasons": [
                            f"correlatable_free_text:{surrogate.kind}",
                            *item.reasons,
                        ]
                    }
                ),
            )

    retrieved = list(merged.values())
    retrieved.sort(key=lambda item: (-item.score, item.row.row_id))
    return retrieved[:limit]


def _retrieve_structured_patient_evidence_direct(
    criterion: ExtractedCriterion,
    source_rows: Sequence[RetrievalSourceRow],
    *,
    limit: int,
) -> list[RetrievedPatientEvidence]:
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


def _correlatable_free_text_surrogates(
    criterion: ExtractedCriterion,
) -> list[ExtractedCriterion]:
    """Build retrieval-only typed queries from free-text audit mentions.

    The returned criteria are never matched directly. They only let retrieval
    reuse the existing terminology/code anchors for free-text rows that contain
    typed clinical surfaces such as a condition, medication, or measurement.
    """

    if criterion.kind != "free_text":
        return []

    surrogates: list[ExtractedCriterion] = []
    seen: set[tuple[str, str]] = set()
    for mention in criterion.mentions:
        mention_text = mention.text.strip()
        if not mention_text:
            continue
        mention_type = mention.type
        if mention_type == "Condition":
            key = ("condition_present", _normalized_surface(mention_text))
            if key in seen:
                continue
            seen.add(key)
            surrogates.append(
                _criterion_like(
                    criterion,
                    kind="condition_present",
                    condition=ConditionCriterion(condition_text=mention_text),
                )
            )
        elif mention_type == "Drug":
            key = ("medication_present", _normalized_surface(mention_text))
            if key in seen:
                continue
            seen.add(key)
            surrogates.append(
                _criterion_like(
                    criterion,
                    kind="medication_present",
                    medication=MedicationCriterion(medication_text=mention_text),
                )
            )
        elif mention_type in {"Measurement", "Observation"}:
            key = ("measurement_threshold", _normalized_surface(mention_text))
            if key in seen:
                continue
            seen.add(key)
            surrogates.append(
                _criterion_like(
                    criterion,
                    kind="measurement_threshold",
                    measurement=MeasurementCriterion(
                        measurement_text=mention_text,
                        operator="=",
                        value=None,
                        value_low=None,
                        value_high=None,
                        unit=None,
                    ),
                )
            )
    return surrogates


def _criterion_like(
    criterion: ExtractedCriterion,
    *,
    kind: str,
    condition: ConditionCriterion | None = None,
    medication: MedicationCriterion | None = None,
    measurement: MeasurementCriterion | None = None,
) -> ExtractedCriterion:
    return ExtractedCriterion(
        kind=kind,  # type: ignore[arg-type]
        polarity=criterion.polarity,
        source_text=criterion.source_text,
        negated=criterion.negated,
        mood=criterion.mood,
        age=None,
        sex=None,
        condition=condition,
        medication=medication,
        measurement=measurement,
        temporal_window=None,
        free_text=None,
        mentions=criterion.mentions,
    )


def _normalized_surface(text: str) -> str:
    return " ".join(text.lower().split())


def retrieve_patient_evidence_with_composite_subchecks(
    criterion: ExtractedCriterion,
    source_rows: Sequence[RetrievalSourceRow],
    *,
    criterion_index: int,
    limit: int = 12,
    subcheck_limit: int = 5,
) -> list[RetrievedPatientEvidence]:
    """Rank parent criterion evidence plus evidence from composite subchecks.

    This widens retrieval context for review/adjudication without deciding the
    parent composite or changing deterministic matcher rollup.
    """

    merged: dict[str, RetrievedPatientEvidence] = {}
    for item in retrieve_structured_patient_evidence(criterion, source_rows, limit=limit):
        _merge_retrieved_item(merged, item)

    for group in build_composite_criterion_groups(criterion, criterion_index=criterion_index):
        for subcheck in group.subchecks:
            for item in retrieve_structured_patient_evidence(
                subcheck.criterion,
                source_rows,
                limit=subcheck_limit,
            ):
                _merge_retrieved_item(
                    merged,
                    item.model_copy(
                        update={
                            "reasons": [
                                f"composite:{group.operator}",
                                f"subcheck:{subcheck.subcheck_id}",
                                *item.reasons,
                            ]
                        }
                    ),
                )

    retrieved = list(merged.values())
    retrieved.sort(key=lambda item: (-item.score, item.row.row_id))
    return retrieved[:limit]


def _merge_retrieved_item(
    merged: dict[str, RetrievedPatientEvidence],
    item: RetrievedPatientEvidence,
) -> None:
    current = merged.get(item.row.row_id)
    if current is None:
        merged[item.row.row_id] = item
        return

    reasons = [*current.reasons]
    reasons.extend(reason for reason in item.reasons if reason not in reasons)
    merged[item.row.row_id] = current.model_copy(
        update={
            "score": max(current.score, item.score),
            "reasons": reasons,
        }
    )


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
        return {"condition", "note"}
    if criterion.kind in {"medication_present", "medication_absent"}:
        return {"medication", "note"}
    if criterion.kind == "measurement_threshold":
        return {"observation", "note"}
    if criterion.kind in {"age", "sex"}:
        return {"demographics"}
    return {"condition", "medication", "observation", "note"}


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


def _patient_condition_rows(
    patient: Patient,
    *,
    start_index: int,
    limit: int,
) -> list[RetrievalSourceRow]:
    conditions = sorted(
        patient.conditions,
        key=lambda c: (c.onset_date is not None, c.onset_date),
        reverse=True,
    )
    return [
        RetrievalSourceRow(
            row_id=f"patient:{start_index + index:03d}",
            source="patient",
            kind="condition",
            label=c.concept.display or c.concept.code or "Condition",
            value=c.concept.display or c.concept.code or "",
            date=c.onset_date.isoformat() if c.onset_date else None,
            code=c.concept.code or None,
            system=c.concept.system or None,
            status=_condition_status(c),
        )
        for index, c in enumerate(conditions[:limit])
    ]


def _patient_observation_rows(
    patient: Patient,
    *,
    start_index: int,
    limit: int,
) -> list[RetrievalSourceRow]:
    latest_by_code: dict[str, LabObservation] = {}
    for obs in patient.observations:
        existing = latest_by_code.get(obs.concept.code)
        if existing is None or obs.effective_date > existing.effective_date:
            latest_by_code[obs.concept.code] = obs
    observations = sorted(
        latest_by_code.values(),
        key=lambda obs: (obs.concept.display or obs.concept.code, obs.effective_date),
    )
    return [
        RetrievalSourceRow(
            row_id=f"patient:{start_index + index:03d}",
            source="patient",
            kind="observation",
            label=obs.concept.display or obs.concept.code or "Observation",
            value=f"{obs.value:g} {obs.unit}".strip(),
            date=obs.effective_date.isoformat(),
            code=obs.concept.code or None,
            system=obs.concept.system or None,
        )
        for index, obs in enumerate(observations[:limit])
    ]


def _patient_medication_rows(
    patient: Patient,
    *,
    start_index: int,
    limit: int,
) -> list[RetrievalSourceRow]:
    medications = sorted(patient.medications, key=_medication_sort_key, reverse=True)
    return [
        RetrievalSourceRow(
            row_id=f"patient:{start_index + index:03d}",
            source="patient",
            kind="medication",
            label=m.concept.display or m.concept.code or "Medication",
            value=m.concept.display or m.concept.code or "",
            date=m.start_date.isoformat(),
            code=m.concept.code or None,
            system=m.concept.system or None,
            status="active" if m.end_date is None else f"ended {m.end_date.isoformat()}",
        )
        for index, m in enumerate(medications[:limit])
    ]


def _patient_note_rows(
    patient: Patient,
    *,
    start_index: int,
    limit: int,
) -> list[RetrievalSourceRow]:
    rows: list[RetrievalSourceRow] = []
    for note in sorted(patient.notes, key=_note_sort_key, reverse=True):
        for snippet in _note_snippets(note):
            rows.append(
                RetrievalSourceRow(
                    row_id=f"patient:{start_index + len(rows):03d}",
                    source="patient",
                    kind="note",
                    label=note.title or "Clinical note",
                    value=snippet,
                    date=note.date.isoformat() if note.date else None,
                    status=f"note_id={note.note_id}",
                )
            )
            if len(rows) >= limit:
                return rows
    return rows


def _condition_status(condition: object) -> str:
    if not getattr(condition, "is_clinical", False):
        return "non-clinical"
    abatement_date = getattr(condition, "abatement_date", None)
    if abatement_date is None:
        return "active or unresolved"
    return f"ended {abatement_date.isoformat()}"


def _medication_sort_key(medication: Medication) -> tuple:
    return (
        medication.end_date is None,
        medication.start_date,
        medication.concept.display or medication.concept.code or "",
    )


def _note_sort_key(note: ClinicalNote) -> tuple:
    return (
        note.date is not None,
        note.date,
        note.note_id,
    )


def _note_snippets(note: ClinicalNote, *, max_chars: int = 420) -> list[str]:
    snippets: list[str] = []
    chunks = [chunk.strip() for chunk in re.split(r"(?<=[.!?])\s+|\n+", note.text) if chunk.strip()]
    current = ""
    for chunk in chunks:
        if len(chunk) > max_chars:
            if current:
                snippets.append(current)
                current = ""
            snippets.extend(_chunk_text(chunk, max_chars=max_chars))
            continue
        if not current:
            current = chunk
            continue
        if len(current) + 1 + len(chunk) <= max_chars:
            current = f"{current} {chunk}"
            continue
        snippets.append(current)
        current = chunk
    if current:
        snippets.append(current)
    return snippets


def _chunk_text(text: str, *, max_chars: int) -> list[str]:
    return [text[index : index + max_chars].strip() for index in range(0, len(text), max_chars)]


__all__ = [
    "RetrievalSourceRow",
    "RetrievedPatientEvidence",
    "retrieve_structured_patient_evidence",
    "structured_source_rows_for_pair",
]
