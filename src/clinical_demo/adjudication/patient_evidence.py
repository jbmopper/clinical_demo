"""Bounded LLM adjudication over retrieved patient evidence.

This is the Phase 2.15 layer: it may improve an unresolved
deterministic verdict, but only by reading the criterion, the
deterministic verdict, trial context, and a small set of retrieved
patient source rows. It never receives the whole chart.
"""

from __future__ import annotations

import time
from datetime import date
from typing import Any, Literal, Protocol, cast

from openai import OpenAI
from openai.types.chat import ParsedChatCompletion
from pydantic import BaseModel, Field

from clinical_demo.cost_telemetry import LLMCallCost
from clinical_demo.extractor.extractor import (
    ExtractorError,
    ExtractorMissingParsedError,
    ExtractorRefusalError,
    _estimate_cost_usd,
)
from clinical_demo.extractor.schema import ExtractedCriterion
from clinical_demo.matcher import (
    MatcherAssumptionMode,
    MatchVerdict,
    RetrievedPatientRowEvidence,
    TrialFieldEvidence,
    Verdict,
)
from clinical_demo.matcher.matcher import _apply_polarity
from clinical_demo.matcher.verdict import Evidence, VerdictReason
from clinical_demo.observability import traced
from clinical_demo.retrieval import RetrievedPatientEvidence
from clinical_demo.settings import Settings, get_settings

PATIENT_EVIDENCE_ADJUDICATOR_VERSION = "patient-evidence-adjudicator-v0.1"
PATIENT_EVIDENCE_PROMPT_VERSION = "patient-evidence-adjudicator-prompt-v0.1"

PatientEvidenceAdjudicatorReason = Literal[
    "ok",
    "no_data",
    "human_review_required",
    "ambiguous_criterion",
]


class PatientEvidenceAdjudicatorOutput(BaseModel):
    """Strict structured-output payload from the adjudicator.

    `verdict` is the raw predicate verdict before trial polarity and
    negation are applied. The caller applies `_apply_polarity` so the
    same inversion rules are used everywhere else in the matcher.
    """

    verdict: Verdict
    reason: PatientEvidenceAdjudicatorReason
    cited_source_row_ids: list[str]
    rationale: str = Field(max_length=500)


class _ChatCompletionsParser(Protocol):
    def parse(self, **kwargs: Any) -> ParsedChatCompletion[PatientEvidenceAdjudicatorOutput]: ...


class _ChatGroup(Protocol):
    completions: _ChatCompletionsParser


class _ClientLike(Protocol):
    chat: _ChatGroup


PATIENT_EVIDENCE_SYSTEM_PROMPT = """\
You are a source-grounded clinical trial eligibility adjudicator.

You are given exactly one extracted eligibility criterion, one existing
deterministic matcher verdict, and a short list of retrieved patient
source rows. Decide whether the predicate of the criterion is satisfied
by the retrieved rows.

Return strict JSON:

  - verdict: "pass" if the retrieved rows clearly satisfy the criterion
             predicate, "fail" if they clearly contradict it,
             "indeterminate" if the rows do not contain enough support.
  - reason: "ok" for clean pass/fail, "no_data" when relevant evidence
            is absent from the rows, "human_review_required" when the
            criterion requires clinical judgment, "ambiguous_criterion"
            when the criterion itself is too underspecified.
  - cited_source_row_ids: stable row ids from the provided rows that
            support your answer. A decisive pass/fail MUST cite at
            least one patient row.
  - rationale: one concise sentence citing the source row labels/values.

Hard rules:

  - Use only the provided rows. Do not infer from missing rows unless
    the assumption mode says closed-world.
  - Under open_world, absence of a row is insufficient evidence, not
    proof of absence.
  - Do not perform arbitrary unit conversions. If units are not plainly
    comparable from the rows, return indeterminate.
  - Polarity and negation are applied by code after your raw predicate
    verdict. Do not invert for inclusion/exclusion.
"""


def adjudicate_patient_evidence(
    *,
    criterion: ExtractedCriterion,
    criterion_index: int,
    deterministic_verdict: MatchVerdict,
    retrieved: list[RetrievedPatientEvidence],
    trial_context: str,
    matcher_assumption_mode: MatcherAssumptionMode,
    client: _ClientLike | None = None,
    settings: Settings | None = None,
) -> tuple[MatchVerdict, LLMCallCost | None]:
    """Return a source-grounded verdict plus this call's LLM cost record.

    `criterion_index` is the 0-based position of this criterion in
    the extraction so the cost record can be joined back to the
    verdict it adjudicated. The cost record is `None` when the
    adjudicator was a no-op (no retrieved evidence) — callers can use
    that to distinguish "ran but free" from "ran and billed."
    """

    if not retrieved:
        return deterministic_verdict, None

    settings = settings or get_settings()
    if client is None:
        if settings.openai_api_key is None:
            raise ExtractorError(
                "OPENAI_API_KEY is not set; cannot construct an OpenAI client. "
                "Pass `client=` for tests or set the env var for production."
            )
        client = cast(
            _ClientLike,
            OpenAI(api_key=settings.openai_api_key.get_secret_value()),
        )

    user_message = _build_user_message(
        criterion=criterion,
        deterministic_verdict=deterministic_verdict,
        retrieved=retrieved,
        trial_context=trial_context,
        matcher_assumption_mode=matcher_assumption_mode,
    )
    messages = [
        {"role": "system", "content": PATIENT_EVIDENCE_SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    with traced(
        "patient_evidence_adjudicate",
        as_type="generation",
        model=settings.extractor_model,
        model_parameters={
            "temperature": settings.extractor_temperature,
            "max_tokens": settings.llm_matcher_max_output_tokens,
        },
        input=user_message,
        metadata={
            "prompt_version": PATIENT_EVIDENCE_PROMPT_VERSION,
            "criterion_kind": criterion.kind,
            "deterministic_reason": deterministic_verdict.reason,
            "retrieved_rows": str(len(retrieved)),
            "matcher_assumption_mode": matcher_assumption_mode,
        },
        version=PATIENT_EVIDENCE_ADJUDICATOR_VERSION,
    ) as span:
        started = time.monotonic()
        try:
            completion = client.chat.completions.parse(
                model=settings.extractor_model,
                messages=messages,
                response_format=PatientEvidenceAdjudicatorOutput,
                temperature=settings.extractor_temperature,
                max_tokens=settings.llm_matcher_max_output_tokens,
            )
        except Exception as exc:
            span.update(level="ERROR", status_message=f"{type(exc).__name__}: {exc}")
            raise

        latency_ms = (time.monotonic() - started) * 1000.0
        choice = completion.choices[0]
        usage = completion.usage
        input_tokens = usage.prompt_tokens if usage else None
        output_tokens = usage.completion_tokens if usage else None
        cost_usd = _estimate_cost_usd(settings.extractor_model, input_tokens, output_tokens)

        usage_details: dict[str, int] = {}
        if input_tokens is not None:
            usage_details["input"] = input_tokens
        if output_tokens is not None:
            usage_details["output"] = output_tokens

        if choice.message.refusal:
            span.update(
                level="WARNING",
                status_message=f"refusal: {choice.message.refusal}",
                output={"refusal": choice.message.refusal},
                usage_details=usage_details or None,
                cost_details={"total": cost_usd} if cost_usd is not None else None,
            )
            raise ExtractorRefusalError(choice.message.refusal, completion)

        parsed = choice.message.parsed
        if parsed is None:
            span.update(
                level="ERROR",
                status_message=f"missing parsed payload; finish_reason={choice.finish_reason!r}",
                usage_details=usage_details or None,
            )
            raise ExtractorMissingParsedError(
                f"completion had neither parsed payload nor refusal; "
                f"finish_reason={choice.finish_reason!r}"
            )

        parsed = _fail_closed_without_citations(parsed, retrieved)
        span.update(
            output=parsed.model_dump(mode="json"),
            usage_details=usage_details or None,
            cost_details={"total": cost_usd} if cost_usd is not None else None,
            metadata={
                "prompt_version": PATIENT_EVIDENCE_PROMPT_VERSION,
                "raw_verdict": parsed.verdict,
                "reason": parsed.reason,
                "latency_ms": str(round(latency_ms, 2)),
            },
        )

    final_verdict = _apply_polarity(parsed.verdict, criterion.polarity, criterion.negated)
    verdict = MatchVerdict(
        criterion=criterion,
        verdict=final_verdict,
        reason=_reason_for_output(parsed),
        rationale=parsed.rationale,
        evidence=_build_evidence(
            criterion=criterion,
            parsed=parsed,
            retrieved=retrieved,
        ),
        matcher_version=PATIENT_EVIDENCE_ADJUDICATOR_VERSION,
    )
    cost = LLMCallCost(
        stage="patient_evidence_adjudicator",
        criterion_index=criterion_index,
        model=settings.extractor_model,
        prompt_version=PATIENT_EVIDENCE_PROMPT_VERSION,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
        latency_ms=latency_ms,
    )
    return verdict, cost


def _build_user_message(
    *,
    criterion: ExtractedCriterion,
    deterministic_verdict: MatchVerdict,
    retrieved: list[RetrievedPatientEvidence],
    trial_context: str,
    matcher_assumption_mode: MatcherAssumptionMode,
) -> str:
    rows = "\n".join(_format_retrieved_row(item) for item in retrieved)
    return (
        f"ASSUMPTION MODE: {matcher_assumption_mode}\n"
        f"CRITERION KIND: {criterion.kind}\n"
        f"CRITERION POLARITY: {criterion.polarity}\n"
        f"CRITERION NEGATED: {criterion.negated}\n"
        f"CRITERION TEXT: {criterion.source_text!r}\n"
        f"TYPED CRITERION PAYLOAD: {criterion.model_dump_json()}\n"
        "\n"
        "DETERMINISTIC MATCHER VERDICT:\n"
        f"  verdict: {deterministic_verdict.verdict}\n"
        f"  reason: {deterministic_verdict.reason}\n"
        f"  rationale: {deterministic_verdict.rationale}\n"
        "\n"
        f"TRIAL CONTEXT: {trial_context}\n"
        "\n"
        "RETRIEVED PATIENT ROWS:\n"
        f"{rows}\n"
        "\n"
        "Decide the raw predicate verdict from the retrieved rows only. "
        "Return strict JSON."
    )


def _format_retrieved_row(item: RetrievedPatientEvidence) -> str:
    row = item.row
    pieces = [
        f"id={row.row_id}",
        f"kind={row.kind}",
        f"label={row.label!r}",
        f"value={row.value!r}",
    ]
    if row.date:
        pieces.append(f"date={row.date}")
    if row.code:
        pieces.append(f"code={row.system}:{row.code}")
    if row.status:
        pieces.append(f"status={row.status!r}")
    pieces.append(f"retrieval_score={item.score}")
    pieces.append(f"retrieval_reasons={item.reasons}")
    return "- " + "; ".join(pieces)


def _fail_closed_without_citations(
    parsed: PatientEvidenceAdjudicatorOutput,
    retrieved: list[RetrievedPatientEvidence],
) -> PatientEvidenceAdjudicatorOutput:
    valid_ids = {item.row.row_id for item in retrieved}
    cited = [row_id for row_id in parsed.cited_source_row_ids if row_id in valid_ids]
    if parsed.verdict == "indeterminate":
        return parsed.model_copy(update={"cited_source_row_ids": cited})
    if cited:
        return parsed.model_copy(update={"cited_source_row_ids": cited})
    return PatientEvidenceAdjudicatorOutput(
        verdict="indeterminate",
        reason="human_review_required",
        cited_source_row_ids=[],
        rationale="Adjudicator did not cite retrieved patient evidence for a decisive verdict.",
    )


def _reason_for_output(parsed: PatientEvidenceAdjudicatorOutput) -> VerdictReason:
    if parsed.verdict in {"pass", "fail"}:
        return "ok"
    return parsed.reason


def _build_evidence(
    *,
    criterion: ExtractedCriterion,
    parsed: PatientEvidenceAdjudicatorOutput,
    retrieved: list[RetrievedPatientEvidence],
) -> list[Evidence]:
    cited_ids = set(parsed.cited_source_row_ids)
    cited = [item for item in retrieved if item.row.row_id in cited_ids]
    if not cited and parsed.verdict == "indeterminate":
        cited = retrieved[:3]
    return [
        TrialFieldEvidence(
            kind="trial_field",
            field="eligibility_criterion",
            value=criterion.source_text,
            note=f"Patient-evidence adjudicator rationale: {parsed.rationale}",
        ),
        *[
            RetrievedPatientRowEvidence(
                kind="retrieved_patient_row",
                note=f"{item.row.label}: {item.row.value}",
                row_id=item.row.row_id,
                row_kind=item.row.kind,
                label=item.row.label,
                value=item.row.value,
                date=date.fromisoformat(item.row.date) if item.row.date else None,
                code=item.row.code,
                system=item.row.system,
                status=item.row.status,
                score=item.score,
                reasons=item.reasons,
            )
            for item in cited
        ],
    ]


__all__ = [
    "PATIENT_EVIDENCE_ADJUDICATOR_VERSION",
    "PatientEvidenceAdjudicatorOutput",
    "PatientEvidenceAdjudicatorReason",
    "adjudicate_patient_evidence",
]
