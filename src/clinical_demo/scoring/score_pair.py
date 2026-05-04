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

from pydantic import BaseModel

from ..adjudication.patient_evidence import _ClientLike as _PatientEvidenceClient
from ..adjudication.patient_evidence import adjudicate_patient_evidence
from ..domain.patient import Patient
from ..domain.trial import Trial
from ..extractor.enrich import enrich_with_structured_fields
from ..extractor.extractor import ExtractionResult, extract_criteria
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

EligibilityRollup = Literal["pass", "fail", "indeterminate"]


class ScoringSummary(BaseModel):
    """Counts derived from the per-criterion verdicts.

    Persisted alongside the verdicts so a regression dashboard can
    pivot on summary counts (e.g. "matcher's `unmapped_concept` rate
    on this slice jumped 30% after extractor-v0.2") without
    re-aggregating from raw verdict lists every time.
    """

    total_criteria: int
    by_verdict: dict[str, int]
    by_reason: dict[str, int]
    by_polarity: dict[str, int]


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
    """
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
        enriched_criteria = enrich_with_structured_fields(extraction.extracted, trial)

        profile = PatientProfile(patient, as_of)
        verdicts = match_extracted(enriched_criteria.criteria, profile, trial)
        verdicts = _apply_retrieval_only(
            verdicts,
            patient=patient,
            trial=trial,
            matcher_assumption_mode=matcher_assumption_mode,
            llm_use_level=llm_use_level,
            patient_evidence_client=patient_evidence_client,
        )
        summary = _summarize(verdicts)
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
    )


def _apply_retrieval_only(
    verdicts: list[MatchVerdict],
    *,
    patient: Patient,
    trial: Trial,
    matcher_assumption_mode: MatcherAssumptionMode = DEFAULT_MATCHER_ASSUMPTION_MODE,
    llm_use_level: LLMUseLevel,
    patient_evidence_client: _PatientEvidenceClient | None = None,
) -> list[MatchVerdict]:
    """Attach or adjudicate retrieved patient rows after deterministic matching."""

    if llm_use_level not in {"retrieval_only", "bounded_adjudication"}:
        return verdicts

    source_rows = structured_source_rows_for_pair(patient, trial)
    enriched: list[MatchVerdict] = []
    for verdict in verdicts:
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
            enriched.append(
                adjudicate_patient_evidence(
                    criterion=verdict.criterion,
                    deterministic_verdict=verdict,
                    retrieved=retrieved,
                    trial_context=_trial_context(trial),
                    matcher_assumption_mode=matcher_assumption_mode,
                    client=patient_evidence_client,
                )
            )
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
    return enriched


def _trial_context(trial: Trial) -> str:
    conditions = ", ".join(trial.conditions) if trial.conditions else "(none listed)"
    return (
        f"title={trial.title!r}; nct_id={trial.nct_id}; conditions={conditions}; "
        f"minimum_age={trial.minimum_age or '(not specified)'}; "
        f"maximum_age={trial.maximum_age or '(not specified)'}; sex={trial.sex}"
    )


def _rollup(verdicts: list[MatchVerdict]) -> EligibilityRollup:
    """Conservative top-level eligibility:
    any fail wins; else any indeterminate wins; else pass.

    Empty verdict lists collapse to `pass` — vacuously true, but
    callers should check for the empty case themselves before
    trusting that as a positive signal."""
    statuses = {v.verdict for v in verdicts}
    if "fail" in statuses:
        return "fail"
    if "indeterminate" in statuses:
        return "indeterminate"
    return "pass"


def _summarize(verdicts: list[MatchVerdict]) -> ScoringSummary:
    """Roll the per-criterion verdicts into the counts the dashboard
    and the CLI summary printer want."""
    # Cast the Counter keys to plain str on the way out so the
    # ScoringSummary's API doesn't leak the closed Literal types of
    # the upstream enums into every consumer's type signature.
    by_verdict: Counter[str] = Counter(str(v.verdict) for v in verdicts)
    by_reason: Counter[str] = Counter(str(v.reason) for v in verdicts)
    by_polarity: Counter[str] = Counter(str(v.criterion.polarity) for v in verdicts)
    return ScoringSummary(
        total_criteria=len(verdicts),
        by_verdict=dict(by_verdict),
        by_reason=dict(by_reason),
        by_polarity=dict(by_polarity),
    )


__all__ = [
    "EligibilityRollup",
    "ScorePairResult",
    "ScoringSummary",
    "score_pair",
]
