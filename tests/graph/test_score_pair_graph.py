"""End-to-end tests for `score_pair_graph`.

These exercise the full graph wiring: extract → fan-out → mixed
matchers → join → rollup → public envelope. Two stub clients
(one for the extractor, one for the LLM matcher) mean no network.
"""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from clinical_demo.extractor.schema import (
    CompositeCriterionGroup,
    CompositeCriterionSubcheck,
    ExtractedCriteria,
    ExtractionMetadata,
)
from clinical_demo.graph import score_pair_graph
from clinical_demo.graph.nodes.llm_match import (
    LLM_MATCHER_VERSION,
    _LLMMatcherOutput,
)
from clinical_demo.matcher import MATCHER_VERSION
from clinical_demo.scoring import PatientDeceasedError
from clinical_demo.scoring.score_pair import ScorePairResult
from clinical_demo.settings import Settings
from tests.extractor.test_extractor import (
    _make_completion as _make_extractor_completion,
)
from tests.extractor.test_extractor import (
    _StubClient as ExtractorStubClient,
)
from tests.graph._fixtures import (
    LLMMatcherStubClient,
    make_llm_matcher_completion,
)
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


def _settings() -> Settings:
    return Settings(
        openai_api_key=SecretStr("sk-test"),
        extractor_model="gpt-4o-mini-2024-07-18",
        extractor_temperature=0.0,
        extractor_max_output_tokens=4096,
    )


def _extractor_stub(
    criteria: list,
    *,
    composite_groups: list[CompositeCriterionGroup] | None = None,
) -> ExtractorStubClient:
    parsed = ExtractedCriteria(
        criteria=criteria,
        composite_groups=composite_groups or [],
        metadata=ExtractionMetadata(notes="test"),
    )
    return ExtractorStubClient(_make_extractor_completion(parsed=parsed))


def _llm_matcher_stub(
    *,
    verdict: str = "indeterminate",
    reason: str = "no_data",
    rationale: str = "Snapshot lacks the relevant fact.",
) -> LLMMatcherStubClient:
    parsed = _LLMMatcherOutput(
        verdict=verdict,  # type: ignore[arg-type]
        reason=reason,  # type: ignore[arg-type]
        rationale=rationale,
    )
    return LLMMatcherStubClient(make_llm_matcher_completion(parsed=parsed))


# ---------- result envelope ----------


def test_returns_score_pair_result_envelope() -> None:
    """Same return type as the imperative score_pair — non-negotiable
    so consumers don't branch on which orchestrator produced it."""
    result = score_pair_graph(
        make_patient(),
        make_trial(eligibility_text="Age >= 18."),
        AS_OF,
        extractor_client=_extractor_stub([crit_age(minimum_years=18.0)]),
        llm_matcher_client=_llm_matcher_stub(),
        settings=_settings(),
    )
    assert isinstance(result, ScorePairResult)
    assert result.summary.total_criteria == 1
    assert result.eligibility in ("pass", "fail", "indeterminate")
    assert result.compiler_validation is not None
    assert result.compiler_validation.ok is True
    assert result.compiler_gap_queue is not None
    assert result.compiler_gap_queue.items == []


def test_score_pair_graph_exposes_blocking_compiler_audit_for_unmapped_structured_criterion() -> (
    None
):
    result = score_pair_graph(
        make_patient(),
        make_trial(eligibility_text="History of rare unknown syndrome."),
        AS_OF,
        extractor_client=_extractor_stub([crit_condition(text="definitely unmapped syndrome xyz")]),
        llm_matcher_client=_llm_matcher_stub(),
        settings=_settings(),
    )

    assert result.compiler_validation is not None
    assert result.compiler_validation.ok is False
    assert result.compiler_validation.summary.blocking_count == 2
    assert result.compiler_gap_queue is not None
    assert [item.gap_kind for item in result.compiler_gap_queue.items] == ["unmapped_concept"]


def test_score_pair_graph_refuses_deceased_patient() -> None:
    """Mirror the imperative orchestrator's deceased-patient guard so
    operators cannot accidentally pick an orchestrator that quietly
    drops the safety check."""
    from datetime import date as _date

    deceased = make_patient(deceased_date=_date(2024, 6, 1))
    with pytest.raises(PatientDeceasedError):
        score_pair_graph(
            deceased,
            make_trial(eligibility_text="Age >= 18."),
            AS_OF,
            extractor_client=_extractor_stub([crit_age(minimum_years=18.0)]),
            llm_matcher_client=_llm_matcher_stub(),
            settings=_settings(),
        )


# ---------- routing ----------


def test_mixed_criteria_run_through_correct_matchers() -> None:
    """Age → deterministic; free_text → LLM. Verdicts carry the
    source matcher_version so we can pin which path each took."""
    result = score_pair_graph(
        make_patient(),
        make_trial(eligibility_text="Age >= 18. Subject must be ambulatory."),
        AS_OF,
        extractor_client=_extractor_stub([crit_age(minimum_years=18.0), crit_free_text()]),
        llm_matcher_client=_llm_matcher_stub(verdict="indeterminate", reason="no_data"),
        settings=_settings(),
    )

    assert result.summary.total_criteria == 2
    by_kind = {v.criterion.kind: v for v in result.verdicts}
    assert by_kind["age"].matcher_version == MATCHER_VERSION
    assert by_kind["free_text"].matcher_version == LLM_MATCHER_VERSION


def test_extraction_order_preserved_across_parallel_fan_in() -> None:
    """Parallel matcher branches fan in via `operator.add`; without
    the rollup's sort, the verdict order would be arrival order
    (nondeterministic). Pin extraction order so eval / replay are
    deterministic."""
    criteria = [
        crit_age(minimum_years=18.0),
        crit_free_text(),
        crit_condition(),
        crit_free_text(polarity="exclusion"),
        crit_age(minimum_years=21.0),
    ]
    result = score_pair_graph(
        make_patient(),
        make_trial(eligibility_text="x"),
        AS_OF,
        extractor_client=_extractor_stub(criteria),
        llm_matcher_client=_llm_matcher_stub(),
        settings=_settings(),
    )
    assert [v.criterion.kind for v in result.verdicts] == [
        "age",
        "free_text",
        "condition_present",
        "free_text",
        "age",
    ]


def test_score_pair_graph_applies_criterion_fixing_before_fanout() -> None:
    result = score_pair_graph(
        make_patient(
            conditions=[
                make_condition(
                    code="46635009",
                    display="Type 1 diabetes mellitus",
                )
            ]
        ),
        make_trial(eligibility_text="Documented T1D diagnosis."),
        AS_OF,
        extractor_client=_extractor_stub(
            [crit_temporal_window(event_text="T1D diagnosis", window_days=0)]
        ),
        llm_matcher_client=_llm_matcher_stub(),
        settings=_settings(),
    )

    assert result.extraction.criteria[0].kind == "condition_present"
    assert result.verdicts[0].verdict == "pass"


def test_score_pair_graph_matches_native_composite_parent_deterministically() -> None:
    parent = crit_free_text()
    subcheck = crit_measurement(text="hba1c", operator=">=", value=6.5, unit="%")
    group = CompositeCriterionGroup(
        group_id="criterion:0:group:001",
        operator="any_of",
        parent_criterion_index=0,
        parent_source_text=parent.source_text,
        subchecks=[
            CompositeCriterionSubcheck(
                subcheck_id="criterion:0:group:001:subcheck:001",
                operator="any_of",
                source_text=subcheck.source_text,
                criterion=subcheck,
            )
        ],
    )

    result = score_pair_graph(
        make_patient(observations=[make_lab(value=7.2, unit="%")]),
        make_trial(eligibility_text="HbA1c >= 6.5%"),
        AS_OF,
        extractor_client=_extractor_stub([parent], composite_groups=[group]),
        llm_matcher_client=_llm_matcher_stub(verdict="fail", reason="ok"),
        settings=_settings(),
    )

    assert result.verdicts[0].matcher_version == MATCHER_VERSION
    assert result.verdicts[0].verdict == "pass"
    assert "Composite any_of group" in result.verdicts[0].rationale


# ---------- pre-supplied extraction ----------


def test_supplied_extraction_short_circuits_extractor_call() -> None:
    """If the caller passes `extraction=...`, the extract node must
    NOT call the LLM. Pin it: a stub that would error out, never
    invoked, is the proof."""
    parsed = ExtractedCriteria(
        criteria=[crit_age(minimum_years=18.0)],
        metadata=ExtractionMetadata(notes="test"),
    )
    from clinical_demo.extractor import extract_criteria

    extraction = extract_criteria(
        "Age >= 18.",
        client=_extractor_stub([crit_age(minimum_years=18.0)]),
        settings=_settings(),
    )

    _ = parsed

    class _BoomClient:
        @property
        def chat(self) -> object:
            raise AssertionError("extract should not have been called")

    result = score_pair_graph(
        make_patient(),
        make_trial(eligibility_text="Age >= 18."),
        AS_OF,
        extraction=extraction,
        extractor_client=_BoomClient(),
        llm_matcher_client=_llm_matcher_stub(),
        settings=_settings(),
    )
    assert result.summary.total_criteria == 1


# ---------- rollup edge case ----------


def test_zero_criteria_extraction_runs_clean_to_rollup() -> None:
    """A trial with no extractable criteria has to traverse the
    graph without getting stuck at fan-out — the routing function
    short-circuits to rollup. Eligibility itself is whatever the
    `_rollup` helper returns for an empty list (currently `pass`,
    same as the imperative path); we pin the *graph completion*,
    not the rollup's vacuous-truth policy."""
    result = score_pair_graph(
        make_patient(),
        make_trial(eligibility_text=""),
        AS_OF,
        extractor_client=_extractor_stub([]),
        llm_matcher_client=_llm_matcher_stub(),
        settings=_settings(),
    )
    assert result.summary.total_criteria == 0
    assert result.verdicts == []


def test_any_fail_dominates_rollup() -> None:
    """An exclusion criterion the patient SATISFIES (model raw=pass)
    inverts to FAIL after polarity, and any FAIL drives the rollup
    to FAIL — same conservative rule the imperative path applies."""
    result = score_pair_graph(
        make_patient(),
        make_trial(eligibility_text="x"),
        AS_OF,
        extractor_client=_extractor_stub(
            [crit_age(minimum_years=18.0), crit_free_text(polarity="exclusion")]
        ),
        llm_matcher_client=_llm_matcher_stub(verdict="pass", reason="ok"),
        settings=_settings(),
    )
    assert result.eligibility == "fail"


def test_no_fails_with_indeterminates_yields_indeterminate() -> None:
    result = score_pair_graph(
        make_patient(),
        make_trial(eligibility_text="x"),
        AS_OF,
        extractor_client=_extractor_stub([crit_age(minimum_years=18.0), crit_free_text()]),
        llm_matcher_client=_llm_matcher_stub(verdict="indeterminate", reason="no_data"),
        settings=_settings(),
    )
    assert result.eligibility == "indeterminate"


def test_all_pass_yields_pass() -> None:
    result = score_pair_graph(
        make_patient(),
        make_trial(eligibility_text="x"),
        AS_OF,
        extractor_client=_extractor_stub([crit_age(minimum_years=18.0), crit_free_text()]),
        llm_matcher_client=_llm_matcher_stub(verdict="pass", reason="ok"),
        settings=_settings(),
    )
    assert result.eligibility == "pass"


_ = pytest  # silence unused import if all tests run without a marker
