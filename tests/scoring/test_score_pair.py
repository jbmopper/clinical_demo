"""Tests for `score_pair` and the rollup / summary helpers.

The library entry stitches the extractor and matcher together; we
test it with an injected `ExtractionResult` so no LLM call is made.
The aggregation rules (rollup, summary counts) are small but
load-bearing — the rollup is the single signal a non-clinician
consumer of the system gets, and getting it wrong silently inverts
the demo.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest

from clinical_demo.adjudication import PatientEvidenceAdjudicatorOutput
from clinical_demo.domain import ClinicalNote
from clinical_demo.extractor.extractor import ExtractionResult
from clinical_demo.extractor.schema import (
    ExtractedCriteria,
    ExtractedCriterion,
    ExtractionMetadata,
    ExtractorRunMeta,
)
from clinical_demo.scoring import PatientDeceasedError
from clinical_demo.scoring.score_pair import _rollup, _summarize, score_pair
from tests.matcher._fixtures import (
    AS_OF,
    crit_age,
    crit_condition,
    crit_free_text,
    crit_measurement,
    crit_temporal_window,
    make_condition,
    make_lab,
    make_patient,
    make_trial,
)


def _make_extraction(criteria: list[ExtractedCriterion]) -> ExtractionResult:
    """Bundle a list of criteria into the same envelope the extractor
    would have produced. Uses zero costs so summary numbers don't
    drift across test runs."""
    return ExtractionResult(
        extracted=ExtractedCriteria(
            criteria=criteria,
            metadata=ExtractionMetadata(notes="test fixture"),
        ),
        meta=ExtractorRunMeta(
            model="test-model",
            prompt_version="extractor-test",
            input_tokens=0,
            output_tokens=0,
            cached_input_tokens=0,
            cost_usd=0.0,
            latency_ms=0.0,
        ),
    )


# ---------- patient safety: deceased ----------


def test_score_pair_refuses_deceased_patient_before_as_of() -> None:
    """A patient who died on or before `as_of` cannot be scored.

    Refusal is structured (typed exception with citation attrs) so
    the API can map it to a clean 422 and the eval harness records
    the per-case error rather than producing a misleading verdict
    against a patient who could not consent."""
    deceased = make_patient(
        birth=date(1950, 1, 1),
        deceased_date=date(2024, 6, 1),
    )
    extraction = _make_extraction([crit_age(minimum_years=18.0)])
    with pytest.raises(PatientDeceasedError) as excinfo:
        score_pair(deceased, make_trial(), AS_OF, extraction=extraction)
    assert excinfo.value.patient_id == "P-test"
    assert excinfo.value.deceased_date == date(2024, 6, 1)
    assert excinfo.value.as_of == AS_OF
    assert "Patient.deceasedDateTime" in str(excinfo.value)


def test_score_pair_refuses_when_deceased_on_as_of_exactly() -> None:
    """Equality boundary is closed: died on `as_of` is still deceased.

    The clinical-screening contract is that we evaluate eligibility
    on a date the patient is alive; same-day death means the chart
    is by definition stale for any forward-looking decision."""
    same_day = make_patient(birth=date(1950, 1, 1), deceased_date=AS_OF)
    extraction = _make_extraction([crit_age(minimum_years=18.0)])
    with pytest.raises(PatientDeceasedError):
        score_pair(same_day, make_trial(), AS_OF, extraction=extraction)


def test_score_pair_allows_patient_who_died_after_as_of() -> None:
    """Retrospective eligibility replays at a historical `as_of` date
    must still work even if the patient later died — that's the
    whole point of carrying a date rather than a boolean."""
    later_deceased = make_patient(
        birth=date(1990, 1, 1),
        deceased_date=date(AS_OF.year + 10, 1, 1),
        conditions=[make_condition(code="44054006")],
    )
    extraction = _make_extraction(
        [crit_age(minimum_years=18.0), crit_condition(text="type 2 diabetes")]
    )
    result = score_pair(later_deceased, make_trial(), AS_OF, extraction=extraction)
    assert result.eligibility == "pass"


# ---------- rollup ----------


def test_rollup_pass_when_all_criteria_pass() -> None:
    """All `pass` criteria → top-level pass."""
    profile_p = make_patient(
        birth=date(1990, 1, 1),
        conditions=[make_condition(code="44054006")],
    )
    extraction = _make_extraction(
        [
            crit_age(minimum_years=18.0),
            crit_condition(text="type 2 diabetes"),
        ]
    )
    result = score_pair(profile_p, make_trial(), AS_OF, extraction=extraction)
    assert result.eligibility == "pass"


def test_rollup_fail_when_any_fail_overrides_passes_and_indeterminates() -> None:
    """Conservative rule: any single `fail` flips the whole rollup
    to `fail`, even when other criteria pass or are indeterminate."""
    patient = make_patient(birth=date(2010, 1, 1))  # underage
    extraction = _make_extraction(
        [
            crit_age(minimum_years=18.0),  # fails (underage)
            crit_free_text(),  # indeterminate
        ]
    )
    result = score_pair(patient, make_trial(), AS_OF, extraction=extraction)
    assert result.eligibility == "fail"


def test_rollup_pass_pending_review_when_only_free_text_indeterminate() -> None:
    """No fails + ≥1 indeterminate but every indeterminate is
    `human_review_required` → `pass_pending_review` (PLAN 2.19).
    The structured matcher said yes for everything it could decide;
    only free-text remains for a human eye."""
    patient = make_patient(birth=date(1990, 1, 1))
    extraction = _make_extraction(
        [
            crit_age(minimum_years=18.0),  # passes
            crit_free_text(),  # indeterminate(human_review_required)
        ]
    )
    result = score_pair(patient, make_trial(), AS_OF, extraction=extraction)
    assert result.eligibility == "pass_pending_review"


def test_rollup_indeterminate_when_human_review_required_without_any_pass() -> None:
    """`pass_pending_review` still needs at least one positive
    structured decision. A trial made only of free-text review items
    has no structured support for a possible match yet."""
    patient = make_patient(birth=date(1990, 1, 1))
    extraction = _make_extraction([crit_free_text()])
    result = score_pair(patient, make_trial(), AS_OF, extraction=extraction)
    assert result.eligibility == "indeterminate"


def test_rollup_indeterminate_when_no_fail_but_a_non_review_indeterminate() -> None:
    """No fails + a non-`human_review_required` indeterminate (e.g.
    `unmapped_concept`, `no_data`) still rolls up to plain
    `indeterminate`: the system is genuinely undecided, not just
    waiting on a clinician."""
    patient = make_patient(birth=date(1990, 1, 1))
    extraction = _make_extraction(
        [
            crit_age(minimum_years=18.0),  # passes
            crit_condition(text="rare unknown disease"),  # indeterminate(unmapped_concept)
        ]
    )
    result = score_pair(patient, make_trial(), AS_OF, extraction=extraction)
    assert result.eligibility == "indeterminate"


def test_retrieval_only_attaches_patient_rows_without_changing_verdict() -> None:
    """Retrieval-only mode should make indeterminates inspectable, not decisive."""
    patient = make_patient(
        conditions=[
            make_condition(
                code="custom-smoking",
                display="Smoking history",
            )
        ]
    )
    extraction = _make_extraction([crit_condition(text="smoking history")])

    result = score_pair(
        patient,
        make_trial(),
        AS_OF,
        extraction=extraction,
        llm_use_level="retrieval_only",
    )

    assert result.llm_use_level == "retrieval_only"
    assert result.eligibility == "indeterminate"
    assert result.verdicts[0].reason == "unmapped_concept"
    retrieved = [e for e in result.verdicts[0].evidence if e.kind == "retrieved_patient_row"]
    assert len(retrieved) == 1
    assert retrieved[0].label == "Smoking history"
    assert "term:smoking" in retrieved[0].reasons


def test_bounded_adjudication_can_replace_indeterminate_with_cited_verdict() -> None:
    """Bounded adjudication may decide, but only through retrieved evidence."""

    class _StubCompletions:
        captured: dict[str, Any] | None = None

        def parse(self, **kwargs: Any) -> Any:
            self.captured = kwargs
            parsed = PatientEvidenceAdjudicatorOutput(
                verdict="pass",
                reason="ok",
                cited_source_row_ids=["patient:002"],
                rationale="patient:002 records smoking history.",
            )
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        finish_reason="stop",
                        message=SimpleNamespace(refusal=None, parsed=parsed),
                    )
                ],
                usage=None,
            )

    completions = _StubCompletions()
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    patient = make_patient(
        conditions=[
            make_condition(
                code="custom-smoking",
                display="Smoking history",
            )
        ]
    )
    extraction = _make_extraction([crit_condition(text="smoking history")])

    result = score_pair(
        patient,
        make_trial(),
        AS_OF,
        extraction=extraction,
        llm_use_level="bounded_adjudication",
        patient_evidence_client=client,
    )

    assert result.llm_use_level == "bounded_adjudication"
    assert result.eligibility == "pass"
    assert result.verdicts[0].matcher_version == "patient-evidence-adjudicator-v0.1"
    assert result.verdicts[0].evidence[1].kind == "retrieved_patient_row"
    assert completions.captured is not None
    # Cost telemetry is captured per LLM call so the eval store can
    # persist adjudicator spend without re-walking verdict evidence.
    assert len(result.llm_calls) == 1
    assert result.llm_calls[0].stage == "patient_evidence_adjudicator"
    assert result.llm_calls[0].criterion_index == 0
    assert result.summary.adjudicator_calls == 1
    # Stub usage payload is None, so the rolled-up tokens / cost are
    # left as None (we deliberately don't synthesize zeroes — the
    # documented "no usage data" sentinel is None).
    assert result.summary.adjudicator_input_tokens is None
    assert result.summary.adjudicator_cost_usd is None


def test_bounded_adjudication_uses_note_evidence_for_unmapped_concept() -> None:
    """Free-text note snippets enter through the same bounded citation gate."""

    class _StubCompletions:
        captured: dict[str, Any] | None = None

        def parse(self, **kwargs: Any) -> Any:
            self.captured = kwargs
            parsed = PatientEvidenceAdjudicatorOutput(
                verdict="pass",
                reason="ok",
                cited_source_row_ids=["patient:002"],
                rationale="patient:002 notes uncontrolled hypertension.",
            )
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        finish_reason="stop",
                        message=SimpleNamespace(refusal=None, parsed=parsed),
                    )
                ],
                usage=None,
            )

    completions = _StubCompletions()
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    patient = make_patient(
        notes=[
            ClinicalNote(
                note_id="doc-hypertension",
                title="Cardiology note",
                date=date(2024, 12, 1),
                text="Patient has uncontrolled hypertension despite therapy.",
            )
        ]
    )
    extraction = _make_extraction([crit_condition(text="uncontrolled hypertension")])

    result = score_pair(
        patient,
        make_trial(),
        AS_OF,
        extraction=extraction,
        llm_use_level="bounded_adjudication",
        patient_evidence_client=client,
    )

    assert result.eligibility == "pass"
    retrieved = [e for e in result.verdicts[0].evidence if e.kind == "retrieved_patient_row"]
    assert retrieved[0].row_kind == "note"
    assert retrieved[0].label == "Cardiology note"
    assert completions.captured is not None


def test_rollup_pass_on_empty_verdicts_documents_vacuous_truth() -> None:
    """Empty extraction → vacuously `pass`. This is intentional and
    documented; callers should check `summary.total_criteria == 0`
    before trusting the rollup as a positive signal."""
    extraction = _make_extraction([])
    result = score_pair(make_patient(), make_trial(), AS_OF, extraction=extraction)
    assert result.eligibility == "pass"
    assert result.summary.total_criteria == 0


def test_rollup_helper_matches_truth_table() -> None:
    """Direct unit test of the helper, mirroring the integration
    cases above so we know which layer broke when something fails.

    Reason matters in v0.2: `pass_pending_review` only fires when
    every non-pass criterion is indeterminate with reason
    `human_review_required` (typical free-text path)."""
    from clinical_demo.matcher.matcher import _build
    from clinical_demo.matcher.verdict import MatchVerdict, VerdictReason

    def vd(status: str, reason: VerdictReason = "ok") -> MatchVerdict:
        crit = crit_free_text()
        return _build(
            crit,
            verdict=status,  # type: ignore[arg-type]
            reason=reason,
            rationale="",
            evidence=[],
            assumption="open_world",
            evidence_under_assumption=False,
        )

    assert _rollup([vd("pass")]) == "pass"
    assert (
        _rollup([vd("pass"), vd("indeterminate", "human_review_required")]) == "pass_pending_review"
    )
    assert _rollup([vd("indeterminate", "human_review_required")]) == "indeterminate"
    assert _rollup([vd("pass"), vd("indeterminate", "no_data")]) == "indeterminate"
    assert _rollup([vd("pass"), vd("indeterminate", "human_review_required"), vd("fail")]) == "fail"
    assert _rollup([vd("indeterminate", "no_data"), vd("fail")]) == "fail"
    assert _rollup([]) == "pass"


# ---------- summary ----------


def test_summary_counts_match_verdicts() -> None:
    patient = make_patient(
        birth=date(1990, 1, 1),
        conditions=[make_condition(code="44054006")],
        observations=[make_lab(value=8.0, unit="%")],
    )
    extraction = _make_extraction(
        [
            crit_age(minimum_years=18.0),
            crit_condition(text="type 2 diabetes"),
            crit_measurement(text="hba1c", operator=">=", value=7.0, unit="%"),
            crit_free_text(),
        ]
    )
    result = score_pair(patient, make_trial(), AS_OF, extraction=extraction)
    assert result.summary.total_criteria == 4
    assert result.summary.by_verdict.get("pass") == 3
    assert result.summary.by_verdict.get("indeterminate") == 1
    assert result.summary.by_polarity.get("inclusion") == 4


def test_summarize_helper_emits_expected_shape() -> None:
    """Directly probe the helper so a regression in the keys (verdict
    name change, etc.) breaks here too, not just in integration tests."""
    from clinical_demo.matcher.matcher import _build

    crit_inc = crit_age(minimum_years=18.0, polarity="inclusion")
    crit_exc = crit_age(minimum_years=18.0, polarity="exclusion")
    verdicts = [
        _build(
            crit_inc,
            verdict="pass",
            reason="ok",
            rationale="",
            evidence=[],
            assumption="open_world",
            evidence_under_assumption=False,
        ),
        _build(
            crit_exc,
            verdict="indeterminate",
            reason="no_data",
            rationale="",
            evidence=[],
            assumption="open_world",
            evidence_under_assumption=False,
        ),
    ]
    summary = _summarize(verdicts)
    assert summary.total_criteria == 2
    assert summary.by_verdict == {"pass": 1, "indeterminate": 1}
    assert summary.by_reason == {"ok": 1, "no_data": 1}
    assert summary.by_polarity == {"inclusion": 1, "exclusion": 1}


# ---------- score_pair plumbing ----------


def test_score_pair_uses_injected_extraction_when_provided() -> None:
    """No LLM call should be made when an `extraction=` argument is
    passed. The presence of any network call would be a leak — we
    verify by passing the extraction and asserting the run meta
    survives unmodified."""
    extraction = _make_extraction([crit_age(minimum_years=18.0)])
    result = score_pair(
        make_patient(birth=date(1990, 1, 1)),
        make_trial(),
        AS_OF,
        extraction=extraction,
    )
    assert result.extraction_meta.model == "test-model"
    assert result.extraction_meta.prompt_version == "extractor-test"


def test_score_pair_carries_top_level_identifiers() -> None:
    """The returned envelope must carry `patient_id`, `nct_id`, and
    `as_of` so a downstream persister doesn't have to re-derive them."""
    patient = make_patient(birth=date(1990, 1, 1))
    trial = make_trial(nct_id="NCT99999999")
    result = score_pair(
        patient,
        trial,
        AS_OF,
        extraction=_make_extraction([crit_age(minimum_years=18.0)]),
    )
    assert result.patient_id == patient.patient_id
    assert result.nct_id == "NCT99999999"
    assert result.as_of == AS_OF


def test_score_pair_enriches_age_sex_from_ctgov_when_extractor_silent() -> None:
    """End-to-end: when a trial has CT.gov-structured age and sex
    bounds but the extractor produced neither (the eligibility text
    didn't restate them), `score_pair` must inject `kind='age'` /
    `kind='sex'` rows so the matcher actually scores those cells.
    Pre-enrichment this returned an empty verdict list and rolled
    up to vacuous `pass`; post-enrichment we expect two
    matcher-evaluated rows.

    This pins the layer-1 coverage lift mentioned in the D-68
    INDETERMINACY.md follow-up: 55% -> ~95% by removing the
    extractor's blind spot on structured fields."""
    from clinical_demo.extractor.enrich import INJECTED_SOURCE_PREFIX

    patient = make_patient(birth=date(1990, 1, 1), sex="female")
    trial = make_trial(
        minimum_age="18 Years",
        maximum_age="65 Years",
        sex="FEMALE",
        eligibility_text="See structured fields.",
    )
    extraction = _make_extraction([])  # extractor saw nothing

    result = score_pair(patient, trial, AS_OF, extraction=extraction)

    # Two synthetic criteria injected and matched.
    assert len(result.verdicts) == 2
    kinds = {v.criterion.kind for v in result.verdicts}
    assert kinds == {"age", "sex"}
    # Both should pass: 36-year-old female meets 18-65 / FEMALE.
    assert all(v.verdict == "pass" for v in result.verdicts)
    # Persisted extraction reflects the enriched view (two rows
    # both flagged with the CT.gov-injection sentinel) so eval
    # consumers see the same criterion set as the matcher did.
    assert len(result.extraction.criteria) == 2
    assert all(c.source_text.startswith(INJECTED_SOURCE_PREFIX) for c in result.extraction.criteria)


def test_score_pair_does_not_override_extracted_age_sex() -> None:
    """If the extractor *did* emit `kind='age'` / `kind='sex'`,
    enrichment leaves them alone -- the LLM saw the eligibility
    text and may have nuanced bounds beyond what the structured
    field carries. Verifies the no-override branch flows through
    `score_pair` end-to-end."""
    patient = make_patient(birth=date(1990, 1, 1), sex="female")
    # Trial says 18-65 / FEMALE; extractor extracted 21-50 / ALL
    # ish-equivalent. After enrichment, the extracted bound
    # should win (no second age/sex row injected).
    trial = make_trial(minimum_age="18 Years", maximum_age="65 Years", sex="FEMALE")
    extraction = _make_extraction(
        [
            crit_age(minimum_years=21.0, maximum_years=50.0),
        ]
    )

    result = score_pair(patient, trial, AS_OF, extraction=extraction)
    age_rows = [c for c in result.extraction.criteria if c.kind == "age"]
    assert len(age_rows) == 1
    assert age_rows[0].age is not None
    # Extractor's tighter bound preserved.
    assert age_rows[0].age.minimum_years == 21.0
    assert age_rows[0].age.maximum_years == 50.0
    # Sex was missing from the extraction AND trial says FEMALE
    # (constraining), so it *should* be injected.
    sex_rows = [c for c in result.extraction.criteria if c.kind == "sex"]
    assert len(sex_rows) == 1
    assert sex_rows[0].sex is not None
    assert sex_rows[0].sex.sex == "FEMALE"


def test_score_pair_applies_criterion_fixing_before_matching() -> None:
    patient = make_patient(
        conditions=[
            make_condition(
                code="46635009",
                display="Type 1 diabetes mellitus",
            )
        ]
    )
    trial = make_trial(eligibility_text="Documented T1D diagnosis.")
    extraction = _make_extraction([crit_temporal_window(event_text="T1D diagnosis", window_days=0)])

    result = score_pair(patient, trial, AS_OF, extraction=extraction)

    assert result.extraction.criteria[0].kind == "condition_present"
    assert result.extraction.criteria[0].condition is not None
    assert result.extraction.criteria[0].condition.condition_text == "type 1 diabetes"
    assert result.verdicts[0].verdict == "pass"
