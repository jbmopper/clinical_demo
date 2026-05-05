"""Tests for local TrialGPT/TREC-style benchmark scaffolding."""

from __future__ import annotations

from clinical_demo.domain.patient import (
    CodedConcept,
    Condition,
    LabObservation,
    Medication,
    Patient,
)
from clinical_demo.domain.trial import Trial
from clinical_demo.evals.patient_evidence import PatientEvidenceHumanLabel
from clinical_demo.evals.run import EvalCase
from clinical_demo.evals.trial_benchmark import (
    TrialRankingPrediction,
    build_trial_benchmark_dataset,
    patient_summary,
    score_trial_ranking,
)

from ._fixtures import AS_OF


def _patient(patient_id: str = "p1") -> Patient:
    return Patient(
        patient_id=patient_id,
        birth_date=AS_OF.replace(year=1980),
        sex="female",
        conditions=[
            Condition(
                concept=CodedConcept(
                    system="http://snomed.info/sct",
                    code="44054006",
                    display="Type 2 diabetes mellitus",
                )
            )
        ],
        observations=[
            LabObservation(
                concept=CodedConcept(system="http://loinc.org", code="4548-4", display="HbA1c"),
                value=7.2,
                unit="%",
                effective_date=AS_OF,
            )
        ],
        medications=[
            Medication(
                concept=CodedConcept(
                    system="http://www.nlm.nih.gov/research/umls/rxnorm",
                    code="6809",
                    display="Metformin",
                ),
                start_date=AS_OF.replace(year=2020),
            )
        ],
    )


def _trial(nct_id: str) -> Trial:
    return Trial(
        nct_id=nct_id,
        title=f"Trial {nct_id}",
        overall_status="RECRUITING",
        conditions=["Type 2 Diabetes"],
        sponsor_name="Example",
        sponsor_class="INDUSTRY",
        eligibility_text="Adults with type 2 diabetes.",
    )


def _case(pair_id: str, patient_id: str, nct_id: str) -> EvalCase:
    return EvalCase(
        pair_id=pair_id,
        patient_id=patient_id,
        nct_id=nct_id,
        as_of=AS_OF,
        slice="t2dm-industry",
    )


def test_patient_summary_is_deterministic_and_clinically_readable() -> None:
    summary = patient_summary(_patient(), AS_OF)

    assert "age 45" in summary
    assert "Type 2 diabetes mellitus" in summary
    assert "HbA1c 7.2 %" in summary
    assert "Metformin" in summary


def test_build_trial_benchmark_dataset_groups_seed_pairs_by_patient() -> None:
    patients = {"p1": _patient("p1")}
    trials = {"NCT1": _trial("NCT1"), "NCT2": _trial("NCT2")}

    dataset = build_trial_benchmark_dataset(
        [
            _case("p1__NCT2", "p1", "NCT2"),
            _case("p1__NCT1", "p1", "NCT1"),
        ],
        load_patient=patients.__getitem__,
        load_trial=trials.__getitem__,
        patient_evidence_labels=[
            PatientEvidenceHumanLabel(
                pair_id="p1__NCT1",
                criterion_index=3,
                expected_matcher_verdict="pass",
                cited_source_row_ids=["patient:000"],
            )
        ],
        relevance_by_pair={"p1__NCT1": "eligible"},
    )

    assert len(dataset.queries) == 1
    assert [candidate.nct_id for candidate in dataset.queries[0].candidates] == [
        "NCT1",
        "NCT2",
    ]
    assert dataset.queries[0].candidates[0].relevance == "eligible"
    assert dataset.criterion_cases[0].expected_matcher_verdict == "pass"


def test_score_trial_ranking_handles_unknown_and_empty_judgments() -> None:
    patients = {"p1": _patient("p1")}
    trials = {"NCT1": _trial("NCT1")}
    unknown_dataset = build_trial_benchmark_dataset(
        [_case("p1__NCT1", "p1", "NCT1")],
        load_patient=patients.__getitem__,
        load_trial=trials.__getitem__,
    )

    unknown_metrics = score_trial_ranking(
        unknown_dataset.queries,
        [TrialRankingPrediction(query_id="p1", ranked_nct_ids=["NCT1"])],
    )

    assert unknown_metrics.judged_queries == 0
    assert unknown_metrics.mrr is None
    judged_dataset = build_trial_benchmark_dataset(
        [_case("p1__NCT1", "p1", "NCT1")],
        load_patient=patients.__getitem__,
        load_trial=trials.__getitem__,
        relevance_by_pair={"p1__NCT1": "eligible"},
    )

    judged_metrics = score_trial_ranking(
        judged_dataset.queries,
        [TrialRankingPrediction(query_id="p1", ranked_nct_ids=["NCT1"])],
    )

    assert judged_metrics.judged_queries == 1
    assert judged_metrics.mrr == 1.0
    assert judged_metrics.recall_at_10 == 1.0
