"""Local TrialGPT/TREC-style benchmark scaffolding.

This is not official TREC ingestion. It gives our curated eval seed a
portable shape that mirrors the useful external framing: a patient summary,
candidate trials to rank, and optional criterion-level judgments.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from clinical_demo.domain.patient import Patient
from clinical_demo.domain.trial import Trial
from clinical_demo.evals.patient_evidence import PatientEvidenceHumanLabel
from clinical_demo.evals.run import EvalCase

TrialRelevance = Literal["eligible", "ineligible", "unknown"]


class TrialRankingCandidate(BaseModel):
    """One candidate trial for one patient-summary query."""

    pair_id: str
    nct_id: str
    title: str
    conditions: list[str] = Field(default_factory=list)
    slice: str = ""
    relevance: TrialRelevance = "unknown"


class TrialRankingQuery(BaseModel):
    """A TREC-like patient-summary query with candidate trials."""

    query_id: str
    patient_id: str
    as_of: date
    patient_summary: str
    candidates: list[TrialRankingCandidate]


class CriterionMatchingCase(BaseModel):
    """One criterion-level matching target, keyed to a seed pair."""

    pair_id: str
    patient_id: str
    nct_id: str
    criterion_index: int
    expected_matcher_verdict: str | None = None
    cited_source_row_ids: list[str] = Field(default_factory=list)


class TrialBenchmarkDataset(BaseModel):
    """Local benchmark export for ranking and criterion-level matching."""

    version: str = "trial-benchmark-v0.1"
    framing: str = (
        "Local TrialGPT/TREC-style scaffold: patient-summary retrieval, "
        "criterion matching, and trial ranking."
    )
    queries: list[TrialRankingQuery]
    criterion_cases: list[CriterionMatchingCase] = Field(default_factory=list)


class TrialRankingPrediction(BaseModel):
    """One model/system ranking for a patient query."""

    query_id: str
    ranked_nct_ids: list[str]


class TrialRankingMetrics(BaseModel):
    """Simple ranking metrics over judged candidates only."""

    queries: int
    judged_queries: int
    relevant_candidates: int
    mrr: float | None = None
    recall_at_10: float | None = None


def build_trial_benchmark_dataset(
    cases: Iterable[EvalCase],
    *,
    load_patient: Callable[[str], Patient],
    load_trial: Callable[[str], Trial],
    patient_evidence_labels: Sequence[PatientEvidenceHumanLabel] = (),
    relevance_by_pair: dict[str, TrialRelevance] | None = None,
) -> TrialBenchmarkDataset:
    """Export the curated seed into a local benchmark dataset."""

    relevance_by_pair = relevance_by_pair or {}
    cases_by_patient: dict[str, list[EvalCase]] = defaultdict(list)
    for case in cases:
        cases_by_patient[case.patient_id].append(case)

    queries = []
    for patient_id, patient_cases in sorted(cases_by_patient.items()):
        patient = load_patient(patient_id)
        as_of = patient_cases[0].as_of
        candidates = []
        for case in sorted(patient_cases, key=lambda item: (item.nct_id, item.pair_id)):
            trial = load_trial(case.nct_id)
            candidates.append(
                TrialRankingCandidate(
                    pair_id=case.pair_id,
                    nct_id=trial.nct_id,
                    title=trial.title,
                    conditions=list(trial.conditions),
                    slice=case.slice,
                    relevance=relevance_by_pair.get(case.pair_id, "unknown"),
                )
            )
        queries.append(
            TrialRankingQuery(
                query_id=patient_id,
                patient_id=patient_id,
                as_of=as_of,
                patient_summary=patient_summary(patient, as_of),
                candidates=candidates,
            )
        )

    criterion_cases = [
        CriterionMatchingCase(
            pair_id=label.pair_id,
            patient_id=_patient_id_from_pair(label.pair_id),
            nct_id=_nct_id_from_pair(label.pair_id),
            criterion_index=label.criterion_index,
            expected_matcher_verdict=label.expected_matcher_verdict,
            cited_source_row_ids=list(label.cited_source_row_ids),
        )
        for label in sorted(
            patient_evidence_labels, key=lambda item: (item.pair_id, item.criterion_index)
        )
    ]
    return TrialBenchmarkDataset(queries=queries, criterion_cases=criterion_cases)


def patient_summary(patient: Patient, as_of: date) -> str:
    """Build a compact deterministic patient summary for benchmark queries."""

    active_conditions = [
        condition.concept.display or condition.concept.code
        for condition in patient.active_conditions(as_of)[:8]
    ]
    latest_observations = sorted(
        [obs for obs in patient.observations if obs.effective_date <= as_of],
        key=lambda obs: obs.effective_date,
        reverse=True,
    )[:8]
    active_meds = [
        medication.concept.display or medication.concept.code
        for medication in patient.active_medications(as_of)[:8]
    ]
    pieces = [
        f"Patient {patient.patient_id}",
        f"age {patient.age_years(as_of)}",
        f"sex {patient.sex}",
    ]
    if active_conditions:
        pieces.append("active conditions: " + "; ".join(active_conditions))
    if latest_observations:
        pieces.append(
            "recent observations: "
            + "; ".join(
                f"{obs.concept.display or obs.concept.code} {obs.value:g} {obs.unit} "
                f"on {obs.effective_date.isoformat()}"
                for obs in latest_observations
            )
        )
    if active_meds:
        pieces.append("active medications: " + "; ".join(active_meds))
    return ". ".join(pieces) + "."


def score_trial_ranking(
    queries: Sequence[TrialRankingQuery],
    predictions: Sequence[TrialRankingPrediction],
) -> TrialRankingMetrics:
    """Compute simple ranking metrics, ignoring unknown judgments."""

    predictions_by_query = {
        prediction.query_id: prediction.ranked_nct_ids for prediction in predictions
    }
    reciprocal_ranks = []
    recall_values = []
    relevant_total = 0
    for query in queries:
        relevant = {
            candidate.nct_id for candidate in query.candidates if candidate.relevance == "eligible"
        }
        if not relevant:
            continue
        relevant_total += len(relevant)
        ranking = predictions_by_query.get(query.query_id, [])
        first_rank = next(
            (index + 1 for index, nct_id in enumerate(ranking) if nct_id in relevant),
            None,
        )
        reciprocal_ranks.append(0.0 if first_rank is None else 1.0 / first_rank)
        top_10 = set(ranking[:10])
        recall_values.append(len(relevant & top_10) / len(relevant))

    judged_queries = len(reciprocal_ranks)
    return TrialRankingMetrics(
        queries=len(queries),
        judged_queries=judged_queries,
        relevant_candidates=relevant_total,
        mrr=_mean(reciprocal_ranks),
        recall_at_10=_mean(recall_values),
    )


def _mean(values: Sequence[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _patient_id_from_pair(pair_id: str) -> str:
    return pair_id.split("__", 1)[0]


def _nct_id_from_pair(pair_id: str) -> str:
    parts = pair_id.split("__", 1)
    return parts[1] if len(parts) == 2 else ""


__all__ = [
    "CriterionMatchingCase",
    "TrialBenchmarkDataset",
    "TrialRankingCandidate",
    "TrialRankingMetrics",
    "TrialRankingPrediction",
    "TrialRankingQuery",
    "TrialRelevance",
    "build_trial_benchmark_dataset",
    "patient_summary",
    "score_trial_ranking",
]
