"""Matcher output types: MatchVerdict + typed Evidence.

`MatchVerdict` is the matcher's per-criterion answer for an
`ExtractedCriterion` (the LLM-derived shape from
`clinical_demo.extractor`). It complements but does NOT replace the
`evals.seed.CriterionVerdict`, which lives on the eval-seed side and
carries the structured `StructuredCriterion` shape used for hand-
labelling.

Both share the top-level `Verdict` enum
(`pass | fail | indeterminate`); the eval harness reconciles them
later.

Design notes
------------
- `reason` is a closed `Literal` so an analyst can pivot a regression
  by reason code without parsing free-text rationales. `rationale` is
  the one-line human-readable explanation that goes into the
  reviewer UI's verdict pill tooltip.
- Evidence is a list of `Evidence` items, each a discriminated union
  by `kind`. The matcher emits the records it actually consulted —
  including a `MissingEvidence` row when the answer was driven by
  an *absence* (no lab on file, no matching condition). Citing the
  absence makes the audit trail honest; "no MI in patient record"
  is information.
- `matcher_version` mirrors the extractor's `prompt_version` so an
  eval regression can be attributed to a specific matcher revision
  without git archaeology.
"""

from __future__ import annotations

from datetime import date as Date
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from ..domain.patient import CodedConcept
from ..extractor.schema import ExtractedCriterion
from .modes import MatcherAssumptionMode

Verdict = Literal["pass", "fail", "indeterminate"]
"""Top-level eligibility outcome for one criterion. Mirrors
`evals.seed.Verdict` exactly so eval consumers can compare matcher
output and ground-truth labels apples-to-apples."""

VerdictReason = Literal[
    # pass / fail reasons
    "ok",
    # indeterminate reasons
    "no_data",
    "stale_data",
    "unit_mismatch",
    "unmapped_concept",
    "unsupported_kind",
    "unsupported_mood",
    "human_review_required",
    "ambiguous_criterion",
    "extractor_invariant_violation",
]
"""Closed enum for *why* the matcher returned the verdict it did.

`ok` is the only reason for `pass` / `fail`; everything else maps to
`indeterminate`. Keeping these as machine-comparable codes (rather
than string-pattern-matching `rationale`) is what lets us pivot
regression analyses on "matcher's `no_data` rate jumped 30%
between revisions."
"""

EvidenceKind = Literal[
    "lab",
    "condition",
    "medication",
    "demographics",
    "trial_field",
    "missing",
    "retrieved_patient_row",
]


class _BaseEvidence(BaseModel):
    """Common fields on every evidence row.

    Concrete subclasses set their own `kind` discriminator. The
    `note` is a short clinician-readable description ("HbA1c 7.4% on
    2024-03-12") rendered in the reviewer UI."""

    kind: EvidenceKind
    note: str


class LabEvidence(_BaseEvidence):
    """A lab value that informed the verdict."""

    kind: Literal["lab"] = "lab"
    concept: CodedConcept
    value: float
    unit: str
    effective_date: Date


class ConditionEvidence(_BaseEvidence):
    """A patient condition record that informed the verdict."""

    kind: Literal["condition"] = "condition"
    concept: CodedConcept
    onset_date: Date | None
    abatement_date: Date | None


class MedicationEvidence(_BaseEvidence):
    """A patient medication record that informed the verdict."""

    kind: Literal["medication"] = "medication"
    concept: CodedConcept
    start_date: Date
    end_date: Date | None


class DemographicsEvidence(_BaseEvidence):
    """A patient demographic field (age, sex) that informed the verdict."""

    kind: Literal["demographics"] = "demographics"
    field: Literal["age_years", "sex"]
    value: str


class TrialFieldEvidence(_BaseEvidence):
    """A trial-side structured field cited as auxiliary corroboration.

    Used when the extractor restated a CT.gov-structured field (age,
    sex) in the eligibility text — citing both lets the reviewer see
    the agreement (or, more interestingly, the disagreement)."""

    kind: Literal["trial_field"] = "trial_field"
    field: str
    value: str


class MissingEvidence(_BaseEvidence):
    """A record we *looked for* but did not find.

    Carrying explicit absences in the audit trail prevents
    indeterminate verdicts from looking like the matcher just gave
    up; "no HbA1c lab on or before 2025-01-01" is itself a useful
    answer for the reviewer."""

    kind: Literal["missing"] = "missing"
    looked_for: str


class RetrievedPatientRowEvidence(_BaseEvidence):
    """A patient source row retrieved for review/adjudication.

    Retrieval-only mode uses these rows to show what the system would
    inspect next. They are intentionally evidence candidates, not
    proof that the criterion is satisfied.
    """

    kind: Literal["retrieved_patient_row"] = "retrieved_patient_row"
    row_id: str
    row_kind: str
    label: str
    value: str
    date: Date | None = None
    code: str | None = None
    system: str | None = None
    status: str | None = None
    score: int
    reasons: list[str] = Field(default_factory=list)


Evidence = Annotated[
    LabEvidence
    | ConditionEvidence
    | MedicationEvidence
    | DemographicsEvidence
    | TrialFieldEvidence
    | MissingEvidence
    | RetrievedPatientRowEvidence,
    Field(discriminator="kind"),
]


class MatchVerdict(BaseModel):
    """One matcher verdict for one ExtractedCriterion.

    `assumption` records the `MatcherAssumptionMode` the verdict was
    produced under so audit trails (and any downstream LLM
    adjudicator that looks at the deterministic verdict) can see
    whether absence-as-negative evidence was in play. `None` is
    legacy/test-only.

    `evidence_under_assumption` is `True` only when the closed-world
    assumption *changed* the answer relative to what `open_world`
    would have produced — in practice, when a resolved-but-absent
    condition / medication / temporal event triggered a hard
    `pass`/`fail` instead of `indeterminate(no_data)`. Reviewers can
    pivot on this flag to see exactly which verdicts depend on the
    closed-world contract holding (D-73 / PLAN 2.19 guardrail).
    """

    criterion: ExtractedCriterion
    verdict: Verdict
    reason: VerdictReason
    rationale: str
    evidence: list[Evidence] = Field(default_factory=list)
    matcher_version: str
    assumption: MatcherAssumptionMode | None = None
    evidence_under_assumption: bool = False


__all__ = [
    "ConditionEvidence",
    "DemographicsEvidence",
    "Evidence",
    "EvidenceKind",
    "LabEvidence",
    "MatchVerdict",
    "MedicationEvidence",
    "MissingEvidence",
    "RetrievedPatientRowEvidence",
    "TrialFieldEvidence",
    "Verdict",
    "VerdictReason",
]
