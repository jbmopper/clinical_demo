"""Patient-side FHIR evidence calibration set helpers.

Chia gives us trial-text extraction gold labels. This module is the
patient-side analogue for matcher adjudication: small reviewed rows that
say whether the patient source records support presence, absence, a
measurement comparison, or insufficient evidence for one trial criterion.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from clinical_demo.evals.layer_three import (
    JudgeTarget,
    LayerThreeJudgment,
    LayerThreeReport,
    LayerThreeSourceContext,
    LayerThreeSourceRecord,
    select_judge_targets,
)
from clinical_demo.evals.run import RunResult
from clinical_demo.matcher import Verdict

PatientEvidenceLabel = Literal[
    "supports_present",
    "supports_absent",
    "supports_measurement_comparison",
    "insufficient_evidence",
]


class PatientEvidenceHumanLabel(BaseModel):
    """Human label for one patient-side evidence calibration row."""

    pair_id: str
    criterion_index: int
    label: PatientEvidenceLabel | None = None
    cited_source_row_ids: list[str] = Field(default_factory=list)
    expected_matcher_verdict: Verdict | None = None
    reviewer: str | None = None
    rationale: str = ""


class PatientEvidenceSourceRow(LayerThreeSourceRecord):
    """A source row with a stable local id for reviewer citation."""

    row_id: str


class PatientEvidenceCalibrationRow(BaseModel):
    """Reviewer-facing candidate row for patient-side evidence labeling."""

    pair_id: str
    patient_id: str
    nct_id: str
    criterion_index: int
    candidate_bucket: str
    criterion_kind: str
    criterion_source_text: str
    polarity: str
    negated: bool
    mood: str
    matcher_verdict: str
    matcher_reason: str
    matcher_rationale: str
    matcher_evidence: list[dict] = Field(default_factory=list)
    judge_label: str | None = None
    judge_error_categories: list[str] = Field(default_factory=list)
    judge_rationale: str | None = None
    source_rows: list[PatientEvidenceSourceRow] = Field(default_factory=list)
    existing_label: PatientEvidenceHumanLabel | None = None


def load_patient_evidence_labels(path: Path | str) -> list[PatientEvidenceHumanLabel]:
    """Load a JSON list of patient-side evidence labels."""

    raw = json.loads(Path(path).read_text())
    return [PatientEvidenceHumanLabel.model_validate(item) for item in raw]


def load_patient_evidence_labels_if_exists(
    path: Path | str,
) -> list[PatientEvidenceHumanLabel]:
    """Load labels when present; otherwise return an empty list."""

    label_path = Path(path)
    if not label_path.exists():
        return []
    return load_patient_evidence_labels(label_path)


def save_patient_evidence_labels(
    path: Path | str,
    labels: list[PatientEvidenceHumanLabel],
) -> None:
    """Persist patient-side evidence labels as reviewer-editable JSON."""

    label_path = Path(path)
    label_path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(labels, key=lambda label: (label.pair_id, label.criterion_index))
    label_path.write_text(
        json.dumps([label.model_dump(mode="json") for label in ordered], indent=2) + "\n"
    )


def save_patient_evidence_rows(
    path: Path | str,
    rows: list[PatientEvidenceCalibrationRow],
) -> None:
    """Persist reviewer rows as stable, manually editable JSON."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(rows, key=lambda row: (row.pair_id, row.criterion_index))
    output_path.write_text(
        json.dumps([row.model_dump(mode="json") for row in ordered], indent=2) + "\n"
    )


def load_layer_three_report(path: Path | str) -> LayerThreeReport:
    """Load a persisted Layer-3 judge report."""

    return LayerThreeReport.model_validate_json(Path(path).read_text())


def select_patient_evidence_targets(
    run: RunResult,
    *,
    judge_report: LayerThreeReport | None = None,
    limit: int = 60,
) -> list[JudgeTarget]:
    """Select a deterministic, evidence-focused calibration packet.

    Judge-incorrect rows are included first because they are the most
    actionable. The remaining slots round-robin across patient-evidence
    buckets so the packet does not become 50 copies of the same
    `unmapped_concept` failure.
    """

    if limit < 1:
        raise ValueError("limit must be positive")

    targets = select_judge_targets(run)
    judgments = _judgments_by_key(judge_report)
    selected: list[JudgeTarget] = []
    selected_keys: set[tuple[str, int]] = set()

    for target in targets:
        key = (target.pair_id, target.criterion_index)
        judgment = judgments.get(key)
        if judgment is None or judgment.judge_label != "incorrect":
            continue
        selected.append(target)
        selected_keys.add(key)
        if len(selected) >= limit:
            return selected

    buckets: dict[str, list[JudgeTarget]] = {}
    for target in targets:
        key = (target.pair_id, target.criterion_index)
        if key in selected_keys:
            continue
        bucket = patient_evidence_bucket(target, judgments.get(key))
        if bucket is None:
            continue
        buckets.setdefault(bucket, []).append(target)

    bucket_names = sorted(buckets)
    while len(selected) < limit and bucket_names:
        next_bucket_names: list[str] = []
        for bucket in bucket_names:
            bucket_targets = buckets[bucket]
            if bucket_targets:
                target = bucket_targets.pop(0)
                selected.append(target)
                if len(selected) >= limit:
                    break
            if bucket_targets:
                next_bucket_names.append(bucket)
        bucket_names = next_bucket_names

    return selected


def build_patient_evidence_rows(
    targets: list[JudgeTarget],
    *,
    source_contexts: dict[str, LayerThreeSourceContext],
    judge_report: LayerThreeReport | None = None,
    existing_labels: list[PatientEvidenceHumanLabel] | None = None,
) -> list[PatientEvidenceCalibrationRow]:
    """Convert selected targets into reviewer-facing evidence rows."""

    judgments = _judgments_by_key(judge_report)
    labels = {(label.pair_id, label.criterion_index): label for label in existing_labels or []}
    rows: list[PatientEvidenceCalibrationRow] = []
    for target in targets:
        criterion = target.verdict.criterion
        key = (target.pair_id, target.criterion_index)
        judgment = judgments.get(key)
        source_context = source_contexts[target.pair_id]
        rows.append(
            PatientEvidenceCalibrationRow(
                pair_id=target.pair_id,
                patient_id=target.patient_id,
                nct_id=target.nct_id,
                criterion_index=target.criterion_index,
                candidate_bucket=patient_evidence_bucket(target, judgment) or "other",
                criterion_kind=criterion.kind,
                criterion_source_text=criterion.source_text,
                polarity=criterion.polarity,
                negated=criterion.negated,
                mood=criterion.mood,
                matcher_verdict=target.verdict.verdict,
                matcher_reason=target.verdict.reason,
                matcher_rationale=target.verdict.rationale,
                matcher_evidence=[e.model_dump(mode="json") for e in target.verdict.evidence],
                judge_label=judgment.judge_label if judgment else None,
                judge_error_categories=list(judgment.error_categories) if judgment else [],
                judge_rationale=judgment.rationale if judgment else None,
                source_rows=_indexed_source_rows(source_context),
                existing_label=labels.get(key),
            )
        )
    return rows


def patient_evidence_bucket(
    target: JudgeTarget,
    judgment: LayerThreeJudgment | None = None,
) -> str | None:
    """Classify a target for patient-side evidence review."""

    if judgment is not None and judgment.judge_label == "incorrect":
        categories = ",".join(judgment.error_categories) or "uncategorized"
        return f"judge_incorrect:{categories}"

    kind = target.verdict.criterion.kind
    reason = target.verdict.reason
    text = target.verdict.criterion.source_text.lower()

    if reason in {"unit_mismatch", "ambiguous_criterion"} or kind == "measurement_threshold":
        return "measurement_or_unit"
    if kind in {"condition_present", "condition_absent"}:
        return kind
    if kind in {"medication_present", "medication_absent"}:
        return kind
    if reason == "no_data":
        return "no_data"
    if reason == "unmapped_concept":
        return "unmapped_concept"
    if reason == "extractor_invariant_violation":
        return "extractor_invariant_violation"
    if reason == "human_review_required" and _looks_patient_evidence_relevant(text):
        return "free_text_patient_evidence"
    return None


def summarize_patient_evidence_rows(
    rows: list[PatientEvidenceCalibrationRow],
) -> dict[str, int]:
    """Return bucket counts for CLI progress output."""

    return dict(sorted(Counter(row.candidate_bucket for row in rows).items()))


def _looks_patient_evidence_relevant(text: str) -> bool:
    needles = (
        "diagnos",
        "history",
        "use of",
        "tobacco",
        "nicotine",
        "marijuana",
        "alcohol",
        "drug",
        "medication",
        "therapy",
        "treatment",
        "laboratory",
        "lab",
        "hba1c",
        "glucose",
        "egfr",
        "blood pressure",
        "ldl",
    )
    return any(needle in text for needle in needles)


def _judgments_by_key(
    report: LayerThreeReport | None,
) -> dict[tuple[str, int], LayerThreeJudgment]:
    if report is None:
        return {}
    return {(j.pair_id, j.criterion_index): j for j in report.judgments}


def _indexed_source_rows(
    context: LayerThreeSourceContext,
) -> list[PatientEvidenceSourceRow]:
    rows: list[PatientEvidenceSourceRow] = []
    for index, record in enumerate(context.patient):
        rows.append(_source_row_with_id(record, row_id=f"patient:{index:03d}"))
    for index, record in enumerate(context.trial):
        if record.kind == "trial_field" and record.label == "Eligibility text":
            continue
        rows.append(_source_row_with_id(record, row_id=f"trial:{index:03d}"))
    return rows


def _source_row_with_id(
    record: LayerThreeSourceRecord,
    *,
    row_id: str,
) -> PatientEvidenceSourceRow:
    return PatientEvidenceSourceRow(
        row_id=row_id,
        source=record.source,
        kind=record.kind,
        label=record.label,
        value=record.value,
        date=record.date,
        code=record.code,
        system=record.system,
        status=record.status,
    )


__all__ = [
    "PatientEvidenceCalibrationRow",
    "PatientEvidenceHumanLabel",
    "PatientEvidenceLabel",
    "PatientEvidenceSourceRow",
    "build_patient_evidence_rows",
    "load_layer_three_report",
    "load_patient_evidence_labels",
    "load_patient_evidence_labels_if_exists",
    "patient_evidence_bucket",
    "save_patient_evidence_labels",
    "save_patient_evidence_rows",
    "select_patient_evidence_targets",
    "summarize_patient_evidence_rows",
]
