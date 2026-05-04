"""Tests for bounded patient-evidence adjudication."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

from openai.types.chat import ParsedChatCompletion
from pydantic import SecretStr
from tests.matcher._fixtures import crit_condition

from clinical_demo.adjudication import (
    PATIENT_EVIDENCE_ADJUDICATOR_VERSION,
    PatientEvidenceAdjudicatorOutput,
    adjudicate_patient_evidence,
)
from clinical_demo.adjudication.patient_evidence import (
    _ChatCompletionsParser,
    _ChatGroup,
    _ClientLike,
)
from clinical_demo.matcher.matcher import _build
from clinical_demo.retrieval import RetrievalSourceRow, RetrievedPatientEvidence
from clinical_demo.settings import Settings


class _StubCompletions(_ChatCompletionsParser):
    def __init__(self, parsed: PatientEvidenceAdjudicatorOutput) -> None:
        self.parsed = parsed
        self.captured: dict[str, Any] | None = None

    def parse(self, **kwargs: Any) -> ParsedChatCompletion[PatientEvidenceAdjudicatorOutput]:
        self.captured = kwargs
        completion = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    finish_reason="stop",
                    message=SimpleNamespace(refusal=None, parsed=self.parsed),
                )
            ],
            usage=None,
        )
        return cast(ParsedChatCompletion[PatientEvidenceAdjudicatorOutput], completion)


class _StubChat(_ChatGroup):
    def __init__(self, completions: _StubCompletions) -> None:
        self.completions: _ChatCompletionsParser = completions


class _StubClient(_ClientLike):
    def __init__(self, parsed: PatientEvidenceAdjudicatorOutput) -> None:
        self._completions = _StubCompletions(parsed)
        self.chat: _ChatGroup = _StubChat(self._completions)

    @property
    def captured(self) -> dict[str, Any] | None:
        return self._completions.captured


def _settings() -> Settings:
    return Settings(openai_api_key=SecretStr("sk-test"))


def _retrieved() -> list[RetrievedPatientEvidence]:
    return [
        RetrievedPatientEvidence(
            row=RetrievalSourceRow(
                row_id="patient:002",
                source="patient",
                kind="condition",
                label="Smoking history",
                value="Smoking history",
                code="custom-smoking",
                system="http://example.test",
                status="active or unresolved",
            ),
            score=7,
            reasons=["kind:condition", "term:smoking", "term:history"],
        )
    ]


def _deterministic_verdict():
    return _build(
        crit_condition(text="smoking history"),
        verdict="indeterminate",
        reason="unmapped_concept",
        rationale="No ConceptSet mapping.",
        evidence=[],
    )


def test_adjudicator_returns_cited_verdict() -> None:
    parsed = PatientEvidenceAdjudicatorOutput(
        verdict="pass",
        reason="ok",
        cited_source_row_ids=["patient:002"],
        rationale="patient:002 records smoking history.",
    )
    client = _StubClient(parsed)

    verdict, cost = adjudicate_patient_evidence(
        criterion=_deterministic_verdict().criterion,
        criterion_index=3,
        deterministic_verdict=_deterministic_verdict(),
        retrieved=_retrieved(),
        trial_context="test trial",
        matcher_assumption_mode="open_world",
        client=client,
        settings=_settings(),
    )

    assert verdict.matcher_version == PATIENT_EVIDENCE_ADJUDICATOR_VERSION
    assert verdict.verdict == "pass"
    assert verdict.reason == "ok"
    assert verdict.evidence[1].kind == "retrieved_patient_row"
    assert verdict.evidence[1].row_id == "patient:002"
    assert client.captured is not None
    assert client.captured["response_format"] is PatientEvidenceAdjudicatorOutput
    assert "RETRIEVED PATIENT ROWS" in client.captured["messages"][1]["content"]
    assert cost is not None
    assert cost.stage == "patient_evidence_adjudicator"
    assert cost.criterion_index == 3
    assert cost.prompt_version  # the pinned prompt version, non-empty
    # Stub client has no usage payload, so token / cost fields are
    # nullable; latency_ms is observed from the Python clock and is
    # always populated.
    assert cost.input_tokens is None
    assert cost.output_tokens is None
    assert cost.cost_usd is None
    assert cost.latency_ms is not None and cost.latency_ms >= 0.0


def test_adjudicator_fails_closed_when_decisive_verdict_has_no_valid_citation() -> None:
    parsed = PatientEvidenceAdjudicatorOutput(
        verdict="pass",
        reason="ok",
        cited_source_row_ids=["not-real"],
        rationale="unsupported decisive answer",
    )

    verdict, cost = adjudicate_patient_evidence(
        criterion=_deterministic_verdict().criterion,
        criterion_index=0,
        deterministic_verdict=_deterministic_verdict(),
        retrieved=_retrieved(),
        trial_context="test trial",
        matcher_assumption_mode="open_world",
        client=_StubClient(parsed),
        settings=_settings(),
    )

    assert verdict.verdict == "indeterminate"
    assert verdict.reason == "human_review_required"
    assert "did not cite" in verdict.rationale
    # Even fail-closed adjudications still incur the LLM call, so
    # the cost record must be returned for billing accounting.
    assert cost is not None
    assert cost.stage == "patient_evidence_adjudicator"


def test_adjudicator_no_retrieved_evidence_returns_no_cost() -> None:
    """No-op path returns the deterministic verdict and a None cost record.

    The caller distinguishes "ran but free" (None) from "ran and
    billed" (an `LLMCallCost`) so we don't accidentally double-bill
    by counting a no-op as a zero-USD adjudication."""
    parsed = PatientEvidenceAdjudicatorOutput(
        verdict="pass",
        reason="ok",
        cited_source_row_ids=[],
        rationale="unused",
    )
    deterministic = _deterministic_verdict()
    verdict, cost = adjudicate_patient_evidence(
        criterion=deterministic.criterion,
        criterion_index=0,
        deterministic_verdict=deterministic,
        retrieved=[],
        trial_context="test trial",
        matcher_assumption_mode="open_world",
        client=_StubClient(parsed),
        settings=_settings(),
    )

    assert verdict is deterministic
    assert cost is None
