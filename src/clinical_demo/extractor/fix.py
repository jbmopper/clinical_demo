"""Deterministic criterion fixing between extraction and matching.

This is the first slice of PLAN 2.21. The extractor can produce a
matcher-shaped row that is still not quite matchable: a temporal row
whose event is really just a diagnosis, a measurement surface that
needs a conventional name, or a composite phrase that should not be
sent to the atomic terminology mapper.

The fixer is intentionally conservative. It preserves the original
`source_text`, rewrites only high-confidence cases, and routes unsafe
composites to `free_text` / human review instead of pretending they are
atomic concepts.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from .schema import (
    ConditionCriterion,
    CriterionGroupOperator,
    ExtractedCriteria,
    ExtractedCriterion,
    ExtractionMetadata,
    FreeTextCriterion,
    MeasurementCriterion,
)

CRITERION_FIX_NOTE_PREFIX = "criterion_fix"


@dataclass(frozen=True)
class _FixResult:
    criteria: list[ExtractedCriterion]
    note: str | None = None


def fix_extracted_criteria(extracted: ExtractedCriteria) -> ExtractedCriteria:
    """Return a matcher-friendlier extraction without mutating input."""

    fixed: list[ExtractedCriterion] = []
    notes: list[str] = []
    for index, criterion in enumerate(extracted.criteria):
        result = _fix_one(criterion)
        fixed.extend(result.criteria)
        if result.note:
            notes.append(f"criterion[{index}]: {result.note}")

    if not notes:
        return extracted

    return ExtractedCriteria(
        criteria=fixed,
        metadata=ExtractionMetadata(notes=_append_notes(extracted.metadata.notes, notes)),
    )


def _fix_one(criterion: ExtractedCriterion) -> _FixResult:
    decomposed = _decompose_compound_measurement_any_of(criterion)
    if decomposed is not None:
        return decomposed

    if _is_unsafe_composite(criterion):
        surface = _surface_text(criterion) or criterion.source_text
        return _FixResult(
            criteria=[
                _to_free_text(
                    criterion,
                    f"unsafe composite requires note/free-text evidence review; "
                    f"original_kind={criterion.kind}; surface={surface!r}",
                )
            ],
            note=f"routed unsafe composite {surface!r} to free_text",
        )

    if criterion.kind in {"condition_present", "condition_absent"} and criterion.condition:
        normalized = _normalize_surface(criterion.condition.condition_text)
        replacement = _CONDITION_SURFACE_FIXES.get(normalized)
        if replacement and replacement != criterion.condition.condition_text:
            return _FixResult(
                criteria=[
                    criterion.model_copy(
                        deep=True,
                        update={"condition": ConditionCriterion(condition_text=replacement)},
                    )
                ],
                note=(
                    f"normalized condition surface {criterion.condition.condition_text!r} "
                    f"to {replacement!r}"
                ),
            )

    if criterion.kind == "measurement_threshold" and criterion.measurement:
        fixed_measurement, note = _fix_measurement(criterion.measurement, criterion.source_text)
        if fixed_measurement is not None:
            return _FixResult(
                criteria=[
                    criterion.model_copy(
                        deep=True,
                        update={"measurement": fixed_measurement},
                    )
                ],
                note=note,
            )

    if criterion.kind == "temporal_window" and criterion.temporal_window:
        fixed_condition = _fix_temporal_window_to_condition(criterion)
        if fixed_condition is not None:
            return fixed_condition

    return _FixResult(criteria=[criterion])


def _decompose_compound_measurement_any_of(
    criterion: ExtractedCriterion,
) -> _FixResult | None:
    """Split common diagnostic OR measurement lists into an `any_of` group.

    This targets rows like ADA hyperglycemia criteria where the extractor
    often conservatively emits one `free_text` criterion even though most
    branches are structured thresholds. We only decompose inclusion,
    non-negated rows so grouped verdicts can be combined over final
    eligibility verdicts without needing raw predicate state.
    """

    if criterion.polarity != "inclusion" or criterion.negated:
        return None
    text = criterion.source_text
    normalized = _normalize_surface(text)
    if " or " not in f" {normalized} ":
        return None
    if not any(term in normalized for term in ("hba1c", "glucose", "glycosylated hemoglobin")):
        return None

    children: list[ExtractedCriterion] = []
    children.extend(
        _measurement_children(
            criterion,
            specs=[
                _MeasurementSpec(
                    name="hba1c",
                    unit="%",
                    pattern=(
                        r"(?:glycosylated\s+hemoglobin\s*\(\s*hba1c\s*\)|"
                        r"hba1c|glycosylated\s+hemoglobin)"
                        r"[^.;]*?(?:≥|>=)\s*(?P<value>\d+(?:\.\d+)?)\s*%"
                    ),
                ),
                _MeasurementSpec(
                    name="fasting plasma glucose",
                    unit="mg/dL",
                    pattern=(
                        r"fasting\s+plasma\s+glucose\s*(?:≥|>=)\s*"
                        r"(?P<value>\d+(?:\.\d+)?)\s*mg/dl"
                    ),
                ),
                _MeasurementSpec(
                    name="2-hour plasma glucose",
                    unit="mg/dL",
                    pattern=(
                        r"2[-\s]?hour\s+plasma\s+glucose\s*(?:≥|>=)\s*"
                        r"(?P<value>\d+(?:\.\d+)?)\s*mg/dl"
                    ),
                ),
            ],
        )
    )
    random_symptom_child = _random_glucose_symptom_child(criterion)
    if random_symptom_child is not None:
        children.append(random_symptom_child)

    if len(children) < 2:
        return None

    group_id = f"criterion_fix:any_of:{hashlib.sha1(text.encode('utf-8')).hexdigest()[:10]}"
    grouped = [_with_group(child, group_id=group_id, operator="any_of") for child in children]
    return _FixResult(
        criteria=grouped,
        note=f"decomposed compound measurement criterion into any_of group {group_id}",
    )


@dataclass(frozen=True)
class _MeasurementSpec:
    name: str
    unit: str
    pattern: str


def _measurement_children(
    criterion: ExtractedCriterion,
    *,
    specs: list[_MeasurementSpec],
) -> list[ExtractedCriterion]:
    children: list[ExtractedCriterion] = []
    for spec in specs:
        match = re.search(spec.pattern, criterion.source_text, flags=re.IGNORECASE)
        if match is None:
            continue
        source = _matched_clause(criterion.source_text, match.start(), match.end())
        children.append(
            _measurement_child(
                criterion,
                source_text=source,
                measurement_text=spec.name,
                value=float(match.group("value")),
                unit=spec.unit,
            )
        )
    return children


def _measurement_child(
    criterion: ExtractedCriterion,
    *,
    source_text: str,
    measurement_text: str,
    value: float,
    unit: str,
) -> ExtractedCriterion:
    return ExtractedCriterion(
        kind="measurement_threshold",
        polarity=criterion.polarity,
        source_text=source_text,
        negated=False,
        mood=criterion.mood,
        age=None,
        sex=None,
        condition=None,
        medication=None,
        measurement=MeasurementCriterion(
            measurement_text=measurement_text,
            operator=">=",
            value=value,
            value_low=None,
            value_high=None,
            unit=unit,
        ),
        temporal_window=None,
        free_text=None,
        mentions=criterion.mentions,
    )


def _random_glucose_symptom_child(criterion: ExtractedCriterion) -> ExtractedCriterion | None:
    match = re.search(
        r"(?:classic\s+symptoms|hyperglycemic\s+crisis)[^.]*?"
        r"random\s+plasma\s+glucose\s*(?:≥|>=)\s*(?P<value>\d+(?:\.\d+)?)\s*mg/dl",
        criterion.source_text,
        flags=re.IGNORECASE,
    )
    if match is None:
        return None
    source = _matched_clause(criterion.source_text, match.start(), match.end())
    return _to_free_text(
        criterion.model_copy(update={"source_text": source}),
        (
            "compound any_of residual requires combined note/free-text review: "
            "random plasma glucose threshold plus classic symptoms or hyperglycemic crisis"
        ),
    )


def _matched_clause(text: str, start: int, end: int) -> str:
    clause_start = max(text.rfind(";", 0, start), text.rfind(".", 0, start))
    clause_end_candidates = [pos for pos in (text.find(";", end), text.find(".", end)) if pos != -1]
    clause_end = min(clause_end_candidates) if clause_end_candidates else len(text)
    clause = text[clause_start + 1 : clause_end].strip()
    return re.sub(r"^(or|and)\s+", "", clause, flags=re.IGNORECASE).strip()


def _with_group(
    criterion: ExtractedCriterion,
    *,
    group_id: str,
    operator: CriterionGroupOperator,
) -> ExtractedCriterion:
    criterion._group_id = group_id
    criterion._group_operator = operator
    return criterion


def _fix_temporal_window_to_condition(criterion: ExtractedCriterion) -> _FixResult | None:
    temporal = criterion.temporal_window
    if temporal is None:
        return None
    normalized = _normalize_surface(temporal.event_text)
    replacement = _CONDITION_SURFACE_FIXES.get(normalized)
    if replacement is None:
        return None
    if temporal.window_days != 0 and "diagnosis" not in normalized:
        return None

    kind = "condition_absent" if criterion.negated else "condition_present"
    fixed = ExtractedCriterion(
        kind=kind,  # type: ignore[arg-type]
        polarity=criterion.polarity,
        source_text=criterion.source_text,
        negated=criterion.negated,
        mood="historical" if criterion.mood == "historical" else "actual",
        age=None,
        sex=None,
        condition=ConditionCriterion(condition_text=replacement),
        medication=None,
        measurement=None,
        temporal_window=None,
        free_text=None,
        mentions=criterion.mentions,
    )
    return _FixResult(
        criteria=[fixed],
        note=f"converted temporal event {temporal.event_text!r} to {kind} {replacement!r}",
    )


def _fix_measurement(
    measurement: MeasurementCriterion,
    source_text: str,
) -> tuple[MeasurementCriterion | None, str | None]:
    normalized = _normalize_surface(measurement.measurement_text)
    replacement = _MEASUREMENT_SURFACE_FIXES.get(normalized)
    if replacement is None and normalized in {"blood pressure", "bp"}:
        source = source_text.lower()
        if "systolic" in source:
            replacement = "systolic blood pressure"
        elif "diastolic" in source:
            replacement = "diastolic blood pressure"

    if replacement is None or replacement == measurement.measurement_text:
        return None, None

    fixed = measurement.model_copy(update={"measurement_text": replacement})
    return (
        fixed,
        f"normalized measurement surface {measurement.measurement_text!r} to {replacement!r}",
    )


def _to_free_text(criterion: ExtractedCriterion, reason: str) -> ExtractedCriterion:
    return ExtractedCriterion(
        kind="free_text",
        polarity=criterion.polarity,
        source_text=criterion.source_text,
        negated=criterion.negated,
        mood=criterion.mood,
        age=None,
        sex=None,
        condition=None,
        medication=None,
        measurement=None,
        temporal_window=None,
        free_text=FreeTextCriterion(note=f"{CRITERION_FIX_NOTE_PREFIX}: {reason}"),
        mentions=criterion.mentions,
    )


def _is_unsafe_composite(criterion: ExtractedCriterion) -> bool:
    if criterion.kind in {"age", "sex", "free_text"}:
        return False
    surface = _surface_text(criterion)
    if not surface:
        return False
    normalized = f" {_normalize_surface(surface)} "
    return any(token in normalized for token in (" and ", " or ", ",", ";", "/"))


def _surface_text(criterion: ExtractedCriterion) -> str | None:
    if criterion.condition is not None:
        return criterion.condition.condition_text
    if criterion.medication is not None:
        return criterion.medication.medication_text
    if criterion.measurement is not None:
        return criterion.measurement.measurement_text
    if criterion.temporal_window is not None:
        return criterion.temporal_window.event_text
    return None


def _normalize_surface(surface: str) -> str:
    return " ".join(surface.lower().strip(".,;:()[]{}\"'").split())


def _append_notes(existing: str, notes: list[str]) -> str:
    suffix = "; ".join(f"{CRITERION_FIX_NOTE_PREFIX}: {note}" for note in notes)
    if not existing:
        return suffix
    return f"{existing}; {suffix}"


_CONDITION_SURFACE_FIXES: dict[str, str] = {
    "mild to moderate hypertension": "hypertension",
    "poorly controlled hypertension": "hypertension",
    "t1d": "type 1 diabetes",
    "t1d diagnosis": "type 1 diabetes",
    "type 1 diabetes diagnosis": "type 1 diabetes",
    "uncontrolled hypertension": "hypertension",
}

_MEASUREMENT_SURFACE_FIXES: dict[str, str] = {
    "c peptide": "C-peptide",
    "c peptide concentration": "C-peptide",
    "c peptide concentrations": "C-peptide",
    "c-peptide concentration": "C-peptide",
    "c-peptide concentrations": "C-peptide",
}


__all__ = [
    "CRITERION_FIX_NOTE_PREFIX",
    "fix_extracted_criteria",
]
