"""Tests for the per-criterion routing decision and the fan-out edge."""

from __future__ import annotations

from langgraph.types import Send

from clinical_demo.extractor.extractor import ExtractionResult
from clinical_demo.extractor.schema import (
    CompositeCriterionGroup,
    CompositeCriterionSubcheck,
    ExtractedCriteria,
    ExtractedCriterion,
    ExtractionMetadata,
    ExtractorRunMeta,
)
from clinical_demo.graph.nodes.route import (
    DETERMINISTIC_NODE,
    LLM_NODE,
    ROLLUP_NODE,
    fan_out_criteria,
    route_by_kind,
)
from clinical_demo.graph.state import ScoringState
from clinical_demo.profile import PatientProfile
from tests.matcher._fixtures import (
    AS_OF,
    crit_age,
    crit_condition,
    crit_free_text,
    crit_measurement,
    crit_medication,
    crit_sex,
    crit_temporal_window,
    make_patient,
    make_trial,
)

# ---------- route_by_kind ----------


def test_free_text_routes_to_llm() -> None:
    assert route_by_kind(crit_free_text()) == LLM_NODE


def test_every_other_kind_routes_to_deterministic() -> None:
    """v0 contract: only free_text fires the LLM. Pin the others so
    that 2.2's dynamic fallback rule (which IS allowed to override
    this) doesn't accidentally regress the v0 baseline rule."""
    deterministic_builders = [
        crit_age(),
        crit_sex(),
        crit_condition(),
        crit_medication(),
        crit_measurement(),
        crit_temporal_window(),
    ]
    for c in deterministic_builders:
        assert route_by_kind(c) == DETERMINISTIC_NODE, c.kind


# ---------- fan_out_criteria ----------


def _state_with_extraction(
    criteria: list[ExtractedCriterion],
    *,
    composite_groups: list[CompositeCriterionGroup] | None = None,
) -> ScoringState:
    """Helper: build the minimal state the fan-out reads from."""
    extraction = ExtractionResult(
        extracted=ExtractedCriteria(
            criteria=criteria,
            composite_groups=composite_groups or [],
            metadata=ExtractionMetadata(notes="test"),
        ),
        meta=ExtractorRunMeta(
            model="m",
            prompt_version="v",
            input_tokens=0,
            output_tokens=0,
            cached_input_tokens=0,
            cost_usd=0.0,
            latency_ms=0.0,
        ),
    )
    return ScoringState(
        patient=make_patient(),
        trial=make_trial(),
        as_of=AS_OF,
        profile=PatientProfile(make_patient(), AS_OF),
        extraction=extraction,
    )


def test_fan_out_emits_one_send_per_criterion() -> None:
    state = _state_with_extraction([crit_age(), crit_free_text(), crit_age()])
    sends = fan_out_criteria(state)
    assert isinstance(sends, list)
    assert len(sends) == 3
    assert all(isinstance(s, Send) for s in sends)


def test_fan_out_routes_per_criterion() -> None:
    state = _state_with_extraction([crit_age(), crit_free_text()])
    sends = fan_out_criteria(state)
    assert isinstance(sends, list)
    targets = [s.node for s in sends]
    assert targets == [DETERMINISTIC_NODE, LLM_NODE]


def test_fan_out_routes_composite_parent_to_deterministic() -> None:
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
    state = _state_with_extraction([parent], composite_groups=[group])

    sends = fan_out_criteria(state)

    assert isinstance(sends, list)
    assert sends[0].node == DETERMINISTIC_NODE
    assert sends[0].arg["_composite_group"] == group


def test_fan_out_carries_index_and_branch_payload() -> None:
    state = _state_with_extraction([crit_age(), crit_free_text()])
    sends = fan_out_criteria(state)
    assert isinstance(sends, list)
    for i, send in enumerate(sends):
        payload = send.arg
        assert payload["_criterion_index"] == i
        for key in ("patient", "trial", "as_of", "profile", "extraction"):
            assert key in payload, f"missing {key} in branch payload"


def test_fan_out_with_zero_criteria_routes_to_rollup() -> None:
    """Empty Send lists leave the graph stuck after extract; the
    routing function returns the rollup node name in that case."""
    state = _state_with_extraction([])
    result = fan_out_criteria(state)
    assert result == ROLLUP_NODE


def test_fan_out_with_no_extraction_routes_to_rollup() -> None:
    state = ScoringState(
        patient=make_patient(),
        trial=make_trial(),
        as_of=AS_OF,
        profile=PatientProfile(make_patient(), AS_OF),
        extraction=None,
    )
    result = fan_out_criteria(state)
    assert result == ROLLUP_NODE
