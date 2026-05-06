"""End-to-end scoring entry: extractor + matcher → per-criterion verdicts.

`score_pair(patient, trial, as_of)` is the seam the CLI script and
the eventual web/API surface both call. It does the smallest useful
amount of orchestration — extract criteria, match each one, roll up
to a top-level eligibility — and returns a structured envelope that
the caller renders / persists / sends downstream.

Why a top-level rollup at all?
------------------------------
The matcher emits per-criterion verdicts. Reviewers (and any caller
that wants a single answer) need a "what's the bottom line" signal.
v0 uses a deliberately conservative rule (D-38):

  - Any `fail` criterion → eligibility = `fail`.
  - Otherwise, any `indeterminate` → eligibility = `indeterminate`.
  - Otherwise → `pass`.

This mirrors the clinical screening reality (one missed exclusion is
disqualifying) and is exactly the surface a Phase-2 critic loop will
refine ("override an unmapped-concept indeterminate with a
high-confidence textual match," etc.).

Why ScorePairResult is a single envelope, not a tuple
-----------------------------------------------------
Every consumer wants the verdicts plus the run metadata: the CLI
needs cost to print, the eval harness needs prompt+matcher version
to attribute regressions, the reviewer UI needs the trial+patient
ids to render headers. Bundling them in one Pydantic model means
each consumer picks what it needs without an ad-hoc tuple unpacking
contract.
"""

from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from ..adjudication.patient_evidence import _ClientLike as _PatientEvidenceClient
from ..adjudication.patient_evidence import adjudicate_patient_evidence
from ..cost_telemetry import LLMCallCost
from ..domain.patient import Patient
from ..domain.trial import Trial
from ..extractor.enrich import enrich_with_structured_fields
from ..extractor.extractor import ExtractionResult, extract_criteria
from ..extractor.fix import fix_extracted_criteria
from ..extractor.schema import ExtractedCriteria, ExtractorRunMeta
from ..matcher import (
    DEFAULT_LLM_USE_LEVEL,
    DEFAULT_MATCHER_ASSUMPTION_MODE,
    MATCHER_VERSION,
    LLMUseLevel,
    MatcherAssumptionMode,
    MatchVerdict,
    RetrievedPatientRowEvidence,
    match_extracted,
)
from ..observability import traced
from ..profile import PatientProfile
from ..retrieval import retrieve_structured_patient_evidence, structured_source_rows_for_pair

EligibilityRollup = Literal["pass", "fail", "indeterminate", "pass_pending_review"]
"""Top-level eligibility rollup. v0 uses three states; v0.2 (PLAN
2.19) adds `pass_pending_review` for the "at least one structured
criterion passes; only `human_review_required` indeterminates remain" case so
reviewer dashboards can distinguish "the system can't decide" from
"the system says yes for everything it could decide and only
free-text remains for human review." Useful in any mode but
especially under closed-world demo runs where the structured
verdicts are the whole point."""


class PatientDeceasedError(ValueError):
    """Raised when scoring is asked to evaluate a deceased patient.

    Refusal is deterministic and source-cited: we know from
    `Patient.deceasedDateTime` (FHIR R4) that the patient was deceased
    on or before the evaluation `as_of`, so any extracted criterion
    we'd score against — current age, current labs, active
    medications — is by construction stale. The matcher could happily
    return a structurally valid verdict; the *clinical* contract says
    we should not. Eval harness already records errors per case; the
    API maps this to a 422 so the reviewer sees the refusal reason
    instead of a 500.

    Attrs are exposed so callers can build structured error payloads
    without re-parsing the message."""

    def __init__(self, patient_id: str, deceased_date: date, as_of: date) -> None:
        self.patient_id = patient_id
        self.deceased_date = deceased_date
        self.as_of = as_of
        super().__init__(
            f"patient {patient_id!r} is deceased as of "
            f"FHIR Patient.deceasedDateTime={deceased_date.isoformat()}; "
            f"refusing to score against as_of={as_of.isoformat()}"
        )


class ScoringSummary(BaseModel):
    """Counts derived from the per-criterion verdicts.

    Persisted alongside the verdicts so a regression dashboard can
    pivot on summary counts (e.g. "matcher's `unmapped_concept` rate
    on this slice jumped 30% after extractor-v0.2") without
    re-aggregating from raw verdict lists every time.

    Adjudicator cost aggregates surface here (sum / call count) so the
    SQLite store can persist them as flat columns for fast pivots in
    the cost-quality dashboard. Per-call detail still lives on
    `ScorePairResult.llm_calls` for fine-grained routing analyses.
    """

    total_criteria: int
    by_verdict: dict[str, int]
    by_reason: dict[str, int]
    by_polarity: dict[str, int]
    adjudicator_calls: int = 0
    adjudicator_input_tokens: int | None = None
    adjudicator_output_tokens: int | None = None
    adjudicator_cost_usd: float | None = None


class ScorePairResult(BaseModel):
    """The full result of scoring one (patient, trial) pair."""

    patient_id: str
    nct_id: str
    as_of: date
    matcher_assumption_mode: MatcherAssumptionMode = DEFAULT_MATCHER_ASSUMPTION_MODE
    llm_use_level: LLMUseLevel = DEFAULT_LLM_USE_LEVEL
    extraction: ExtractedCriteria
    extraction_meta: ExtractorRunMeta
    verdicts: list[MatchVerdict]
    summary: ScoringSummary
    eligibility: EligibilityRollup
    llm_calls: list[LLMCallCost] = Field(default_factory=list)


def score_pair(
    patient: Patient,
    trial: Trial,
    as_of: date,
    *,
    extraction: ExtractionResult | None = None,
    matcher_assumption_mode: MatcherAssumptionMode = DEFAULT_MATCHER_ASSUMPTION_MODE,
    llm_use_level: LLMUseLevel = DEFAULT_LLM_USE_LEVEL,
    patient_evidence_client: _PatientEvidenceClient | None = None,
) -> ScorePairResult:
    """Score one patient against one trial end-to-end.

    Parameters
    ----------
    patient : Patient
        Domain patient (loaded via `data.synthea.load_bundle` or
        equivalent).
    trial : Trial
        Domain trial (loaded via `data.clinicaltrials.trial_from_raw`).
    as_of : date
        The date the eligibility decision is being evaluated against.
        Drives age, lab freshness, condition activity, etc.
    extraction : ExtractionResult, optional
        Pre-computed extraction. If provided, skip the LLM call —
        useful for replay / caching, evals, and offline tests. If
        None, calls `extract_criteria(trial.eligibility_text)`.

    Raises
    ------
    PatientDeceasedError
        If the patient's FHIR `deceasedDateTime` is on or before
        `as_of`. Scoring refuses rather than producing a verdict
        that would inevitably be misleading.
    """
    if patient.deceased_date is not None and patient.deceased_date <= as_of:
        raise PatientDeceasedError(patient.patient_id, patient.deceased_date, as_of)
    # One parent span per (patient, trial) pair. The extractor's
    # `generation` observation nests under it automatically because
    # `traced(...)` uses `start_as_current_observation`. Tags
    # (patient_id, nct_id, eligibility, verdict counts) live in
    # `metadata` so the Langfuse UI can pivot on them without us
    # leaning on session/user-id semantics that don't fit a batch
    # eligibility tool. We pass `input` ahead of the LLM call and
    # `update(...)` with the resolved output at the end so the span
    # is well-formed even if the extractor raises.
    with traced(
        "score_pair",
        as_type="span",
        input={
            "patient_id": patient.patient_id,
            "nct_id": trial.nct_id,
            "as_of": as_of.isoformat(),
            "eligibility_text_chars": len(trial.eligibility_text or ""),
        },
        metadata={
            "patient_id": patient.patient_id,
            "nct_id": trial.nct_id,
            "matcher_version": MATCHER_VERSION,
            "matcher_assumption_mode": matcher_assumption_mode,
            "llm_use_level": llm_use_level,
        },
    ) as span:
        if extraction is None:
            extraction = extract_criteria(trial.eligibility_text)

        # Backfill `kind="age"` / `kind="sex"` from the trial's
        # CT.gov structured fields when the extractor didn't emit
        # one (the eligibility text often doesn't restate them but
        # the matcher can score against the patient profile
        # trivially). Cheap, deterministic, leaves the cached
        # `extraction` envelope untouched -- we only enrich the
        # in-memory copy used for matching, so the D-66 extractor
        # cache stays valid across CT.gov metadata updates.
        enriched_criteria = fix_extracted_criteria(
            enrich_with_structured_fields(extraction.extracted, trial)
        )

        profile = PatientProfile(patient, as_of)
        verdicts = match_extracted(
            enriched_criteria.criteria,
            profile,
            trial,
            matcher_assumption_mode=matcher_assumption_mode,
        )
        verdicts, llm_calls = _apply_retrieval_only(
            verdicts,
            patient=patient,
            trial=trial,
            matcher_assumption_mode=matcher_assumption_mode,
            llm_use_level=llm_use_level,
            patient_evidence_client=patient_evidence_client,
        )
        summary = _summarize(verdicts, llm_calls)
        eligibility = _rollup(verdicts)

        # Stringify count dicts because Langfuse v4 propagated
        # metadata is `dict[str, str]`. The structured verdict /
        # summary objects are still surfaced via `output` for the
        # full record.
        span.update(
            output={
                "eligibility": eligibility,
                "total_criteria": summary.total_criteria,
                "by_verdict": summary.by_verdict,
                "by_reason": summary.by_reason,
                "by_polarity": summary.by_polarity,
            },
            metadata={
                "patient_id": patient.patient_id,
                "nct_id": trial.nct_id,
                "matcher_version": MATCHER_VERSION,
                "matcher_assumption_mode": matcher_assumption_mode,
                "llm_use_level": llm_use_level,
                "eligibility": eligibility,
                "total_criteria": str(summary.total_criteria),
                "fail_count": str(summary.by_verdict.get("fail", 0)),
                "pass_count": str(summary.by_verdict.get("pass", 0)),
                "indeterminate_count": str(summary.by_verdict.get("indeterminate", 0)),
            },
        )

    return ScorePairResult(
        patient_id=patient.patient_id,
        nct_id=trial.nct_id,
        as_of=as_of,
        matcher_assumption_mode=matcher_assumption_mode,
        llm_use_level=llm_use_level,
        # Persist the enriched view so eval-side and reviewer-UI
        # consumers see the same criterion set the matcher saw;
        # provenance of injected rows is inspectable via
        # `INJECTED_SOURCE_PREFIX` in `source_text`.
        extraction=enriched_criteria,
        extraction_meta=extraction.meta,
        verdicts=verdicts,
        summary=summary,
        eligibility=eligibility,
        llm_calls=llm_calls,
    )


def _apply_retrieval_only(
    verdicts: list[MatchVerdict],
    *,
    patient: Patient,
    trial: Trial,
    matcher_assumption_mode: MatcherAssumptionMode = DEFAULT_MATCHER_ASSUMPTION_MODE,
    llm_use_level: LLMUseLevel,
    patient_evidence_client: _PatientEvidenceClient | None = None,
) -> tuple[list[MatchVerdict], list[LLMCallCost]]:
    """Attach or adjudicate retrieved patient rows after deterministic matching.

    Returns the (possibly enriched) verdict list plus an ordered list
    of `LLMCallCost` records for any LLM-backed adjudications that
    fired. Empty list when `llm_use_level` is `none` or
    `retrieval_only` (deterministic-only retrieval doesn't bill)."""

    if llm_use_level not in {"retrieval_only", "bounded_adjudication"}:
        return verdicts, []

    source_rows = structured_source_rows_for_pair(patient, trial)
    enriched: list[MatchVerdict] = []
    llm_calls: list[LLMCallCost] = []
    for criterion_index, verdict in enumerate(verdicts):
        if verdict.verdict != "indeterminate":
            enriched.append(verdict)
            continue

        retrieved = retrieve_structured_patient_evidence(
            verdict.criterion,
            source_rows,
            limit=5,
        )
        if not retrieved:
            enriched.append(verdict)
            continue

        if llm_use_level == "bounded_adjudication":
            adjudicated, cost = adjudicate_patient_evidence(
                criterion=verdict.criterion,
                criterion_index=criterion_index,
                deterministic_verdict=verdict,
                retrieved=retrieved,
                trial_context=_trial_context(trial),
                matcher_assumption_mode=matcher_assumption_mode,
                client=patient_evidence_client,
            )
            enriched.append(adjudicated)
            if cost is not None:
                llm_calls.append(cost)
            continue

        retrieval_evidence = [
            RetrievedPatientRowEvidence(
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
            for item in retrieved
        ]
        enriched.append(
            verdict.model_copy(
                update={"evidence": [*verdict.evidence, *retrieval_evidence]},
            )
        )
    return enriched, llm_calls


def _trial_context(trial: Trial) -> str:
    conditions = ", ".join(trial.conditions) if trial.conditions else "(none listed)"
    return (
        f"title={trial.title!r}; nct_id={trial.nct_id}; conditions={conditions}; "
        f"minimum_age={trial.minimum_age or '(not specified)'}; "
        f"maximum_age={trial.maximum_age or '(not specified)'}; sex={trial.sex}"
    )


def _rollup(verdicts: list[MatchVerdict]) -> EligibilityRollup:
    """Conservative top-level eligibility (D-38, with PLAN 2.19
    refinement):

      - Any `fail` criterion → eligibility = `fail`.
      - All criteria `pass` → `pass`.
      - At least one criterion `pass` and all remaining non-`pass`
        criteria are indeterminate with reason `human_review_required`
        → `pass_pending_review`. The structured matcher said yes for
        at least one criterion and did not find a structured blocker;
        what's left is free-text criteria a clinician needs to eyeball.
      - Any other indeterminate (`unmapped_concept`, `no_data`,
        `unit_mismatch`, ...) → `indeterminate`.

    Empty verdict lists collapse to `pass` — vacuously true, but
    callers should check for the empty case themselves before
    trusting that as a positive signal."""
    has_fail = False
    has_pass = False
    has_indeterminate = False
    has_non_review_indeterminate = False
    for v in verdicts:
        if v.verdict == "fail":
            has_fail = True
        elif v.verdict == "pass":
            has_pass = True
        elif v.verdict == "indeterminate":
            has_indeterminate = True
            if v.reason != "human_review_required":
                has_non_review_indeterminate = True
    if has_fail:
        return "fail"
    if has_non_review_indeterminate:
        return "indeterminate"
    if has_indeterminate and has_pass:
        return "pass_pending_review"
    if has_indeterminate:
        return "indeterminate"
    return "pass"


def _summarize(
    verdicts: list[MatchVerdict],
    llm_calls: list[LLMCallCost] | None = None,
) -> ScoringSummary:
    """Roll the per-criterion verdicts into the counts the dashboard
    and the CLI summary printer want.

    `llm_calls` is the list of LLM cost records gathered during
    scoring; the adjudicator subtotal is computed from the entries
    whose `stage == "patient_evidence_adjudicator"` so future stages
    can be added without re-shaping the summary."""
    # Cast the Counter keys to plain str on the way out so the
    # ScoringSummary's API doesn't leak the closed Literal types of
    # the upstream enums into every consumer's type signature.
    by_verdict: Counter[str] = Counter(str(v.verdict) for v in verdicts)
    by_reason: Counter[str] = Counter(str(v.reason) for v in verdicts)
    by_polarity: Counter[str] = Counter(str(v.criterion.polarity) for v in verdicts)

    adjudicator_calls = 0
    adjudicator_in: int | None = None
    adjudicator_out: int | None = None
    adjudicator_cost: float | None = None
    for call in llm_calls or []:
        if call.stage != "patient_evidence_adjudicator":
            continue
        adjudicator_calls += 1
        if call.input_tokens is not None:
            adjudicator_in = (adjudicator_in or 0) + call.input_tokens
        if call.output_tokens is not None:
            adjudicator_out = (adjudicator_out or 0) + call.output_tokens
        if call.cost_usd is not None:
            adjudicator_cost = (adjudicator_cost or 0.0) + call.cost_usd

    return ScoringSummary(
        total_criteria=len(verdicts),
        by_verdict=dict(by_verdict),
        by_reason=dict(by_reason),
        by_polarity=dict(by_polarity),
        adjudicator_calls=adjudicator_calls,
        adjudicator_input_tokens=adjudicator_in,
        adjudicator_output_tokens=adjudicator_out,
        adjudicator_cost_usd=adjudicator_cost,
    )


__all__ = [
    "EligibilityRollup",
    "ScorePairResult",
    "ScoringSummary",
    "score_pair",
]
