"""Offline candidate generation and confidence gating.

This module is deliberately network-free. It gives the compiler a small,
deterministic envelope for query variants and candidate ranking so later
resolver integrations can explain why a surface auto-mapped, stayed ambiguous,
or had no usable candidates.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CandidateSourceKind = Literal[
    "reviewed_registry",
    "surface_cache",
    "local_alias",
    "umls",
    "vsac",
    "rxnorm",
    "loinc",
    "fixture",
    "unknown",
]
CandidateRejectReason = Literal[
    "system_mismatch",
    "semantic_type_mismatch",
    "low_score",
    "inactive",
    "not_in_patient_vocabulary",
    "duplicate",
    "other",
]
ConfidenceBucket = Literal["high", "medium", "low", "rejected"]
CandidateGateVerdict = Literal["auto_map", "ambiguous", "no_candidates"]

HIGH_CONFIDENCE_MIN_SCORE = 0.90
MEDIUM_CONFIDENCE_MIN_SCORE = 0.70
AMBIGUITY_MARGIN = 0.05

_PARENTHETICAL_RE = re.compile(r"\([^()]*\)|\[[^\[\]]*\]|\{[^{}]*\}")
_PUNCTUATION_RE = re.compile(r"[\t\r\n\f\v\"'`.,;:!?/\\|()\[\]{}]+")
_HYPHEN_RE = re.compile(r"[-_]+")
_MULTISPACE_RE = re.compile(r"\s+")
_EXCLUSION_CLAUSE_RE = re.compile(r"\b(?:excluding|except|other than)\b.*$", re.IGNORECASE)
_TEMPORAL_WINDOW_RE = re.compile(
    r"\b(?:within|in|during|over)\s+(?:the\s+)?(?:past|last|previous)\s+\d+\s+"
    r"(?:day|days|week|weeks|month|months|year|years)\b",
    re.IGNORECASE,
)
_HISTORY_PREFIX_RE = re.compile(
    r"^(?:personal\s+)?(?:(?:past\s+)?medical\s+)?history\s+(?:of|for)\s+",
    re.IGNORECASE,
)
_DIAGNOSIS_PREFIX_RE = re.compile(r"^(?:diagnosis\s+of|diagnosed\s+with)\s+", re.IGNORECASE)
_QUALIFIER_PREFIX_RE = re.compile(
    r"^(?:known|documented|confirmed|current|active|prior|previous)\s+",
    re.IGNORECASE,
)

_UNINFLECTED_TOKENS = {
    "diabetes",
    "disease",
    "status",
    "mellitus",
    "analysis",
    "diagnosis",
}
_SOURCE_PRIORITY: dict[CandidateSourceKind, int] = {
    "reviewed_registry": 0,
    "surface_cache": 10,
    "local_alias": 20,
    "vsac": 30,
    "rxnorm": 30,
    "loinc": 30,
    "umls": 40,
    "fixture": 90,
    "unknown": 100,
}
_BUCKET_PRIORITY: dict[ConfidenceBucket, int] = {
    "high": 0,
    "medium": 1,
    "low": 2,
    "rejected": 3,
}


def normalize_candidate_surface(surface: str) -> str:
    """Normalize a trial-side surface for candidate search/ranking."""

    normalized = surface.strip().lower()
    normalized = normalized.replace("&", " and ")
    normalized = _HYPHEN_RE.sub(" ", normalized)
    normalized = _PUNCTUATION_RE.sub(" ", normalized)
    normalized = normalized.strip("()[]{}")
    return _MULTISPACE_RE.sub(" ", normalized).strip()


class QueryVariant(BaseModel):
    """One deterministic query variant derived from an extracted surface."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    raw_surface: str = Field(description="Original extracted surface.")
    variant: str = Field(description="Normalized variant to send to candidate sources.")
    transforms: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Ordered cleanup transforms used to produce this variant.",
    )

    @field_validator("raw_surface", "variant")
    @classmethod
    def _strip_nonblank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("surface strings must not be blank")
        return stripped


def generate_query_variants(surface: str) -> tuple[QueryVariant, ...]:
    """Return deterministic, conservative query variants for ``surface``.

    The generator intentionally removes context words only as alternate
    variants. The first variant is always the normalized original surface.
    """

    raw_surface = surface.strip()
    if not raw_surface:
        return ()

    states: list[tuple[str, tuple[str, ...]]] = []
    seen: set[str] = set()

    def add(candidate: str, transforms: tuple[str, ...]) -> None:
        variant = normalize_candidate_surface(candidate)
        if not variant or variant in seen:
            return
        seen.add(variant)
        states.append((candidate, transforms))

    add(raw_surface, ())

    transforms: tuple[tuple[str, Callable[[str], str]], ...] = (
        ("parenthetical_cleanup", _remove_parentheticals),
        ("history_of_stripped", _strip_history_prefix),
        ("diagnosis_prefix_stripped", _strip_diagnosis_prefix),
        ("qualifier_prefix_stripped", _strip_qualifier_prefix),
        ("temporal_window_stripped", _strip_temporal_window),
        ("exclusion_clause_stripped", _strip_exclusion_clause),
    )
    for transform_name, transform in transforms:
        for candidate, prior_transforms in tuple(states):
            add(transform(candidate), (*prior_transforms, transform_name))

    for candidate, prior_transforms in tuple(states):
        normalized = normalize_candidate_surface(candidate)
        singular = _singularize_last_token(normalized)
        if singular != normalized:
            add(singular, (*prior_transforms, "singularized_last_token"))
        plural = _pluralize_last_token(normalized)
        if plural != normalized:
            add(plural, (*prior_transforms, "pluralized_last_token"))

    return tuple(
        QueryVariant(
            raw_surface=raw_surface,
            variant=normalize_candidate_surface(variant),
            transforms=transform_steps,
        )
        for variant, transform_steps in states
    )


class CandidateSource(BaseModel):
    """Where a candidate came from, kept separate from the candidate target."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: CandidateSourceKind = "unknown"
    name: str = Field(description="Human-readable source name.")

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("source name must not be blank")
        return stripped


class TerminologyCandidate(BaseModel):
    """One ranked terminology candidate for a surface/variant pair."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: CandidateSource
    matched_surface: str = Field(description="Original or upstream matched surface.")
    matched_variant: str = Field(description="Query variant that produced this candidate.")
    code: str
    system: str
    name: str
    score: float = Field(ge=0.0, le=1.0)
    reject_reasons: tuple[CandidateRejectReason, ...] = Field(default_factory=tuple)
    confidence_bucket: ConfidenceBucket

    @model_validator(mode="before")
    @classmethod
    def _fill_confidence_bucket(cls, data: object) -> object:
        if not isinstance(data, dict) or data.get("confidence_bucket") is not None:
            return data
        return {
            **data,
            "confidence_bucket": bucket_for_score(
                float(data.get("score", 0.0)),
                data.get("reject_reasons", ()),
            ),
        }

    @field_validator("matched_surface", "matched_variant", "code", "system", "name")
    @classmethod
    def _strip_nonblank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("candidate strings must not be blank")
        return stripped

    @property
    def target_key(self) -> tuple[str, str]:
        """Stable identity of the coding target."""

        return (self.system, self.code)


class CandidateConfidencePolicy(BaseModel):
    """Simple deterministic thresholds for automatic mapping."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    auto_map_min_score: float = Field(default=HIGH_CONFIDENCE_MIN_SCORE, ge=0.0, le=1.0)
    medium_confidence_min_score: float = Field(
        default=MEDIUM_CONFIDENCE_MIN_SCORE,
        ge=0.0,
        le=1.0,
    )
    ambiguity_margin: float = Field(default=AMBIGUITY_MARGIN, ge=0.0, le=1.0)


class CandidateGateDecision(BaseModel):
    """Result of applying confidence gates to ranked candidates."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    verdict: CandidateGateVerdict
    selected: TerminologyCandidate | None = None
    ranked_candidates: tuple[TerminologyCandidate, ...] = Field(default_factory=tuple)
    policy: CandidateConfidencePolicy = Field(default_factory=CandidateConfidencePolicy)
    reason: str


def bucket_for_score(
    score: float,
    reject_reasons: Iterable[CandidateRejectReason | str] = (),
) -> ConfidenceBucket:
    """Classify a candidate into a coarse confidence bucket."""

    if tuple(reject_reasons):
        return "rejected"
    if score >= HIGH_CONFIDENCE_MIN_SCORE:
        return "high"
    if score >= MEDIUM_CONFIDENCE_MIN_SCORE:
        return "medium"
    return "low"


def rank_candidates(
    candidates: Iterable[TerminologyCandidate],
) -> tuple[TerminologyCandidate, ...]:
    """Return candidates in deterministic best-first order."""

    return tuple(sorted(candidates, key=_candidate_sort_key))


def gate_candidate_set(
    candidates: Iterable[TerminologyCandidate],
    policy: CandidateConfidencePolicy | None = None,
) -> CandidateGateDecision:
    """Apply offline confidence gates to a candidate set.

    Policy:
    - no non-rejected candidates -> ``no_candidates``
    - top candidate below high-confidence threshold -> ``ambiguous``
    - any distinct second candidate within ``ambiguity_margin`` -> ``ambiguous``
    - otherwise the top candidate may ``auto_map``
    """

    active_policy = policy or CandidateConfidencePolicy()
    ranked = rank_candidates(candidates)
    usable = tuple(candidate for candidate in ranked if not candidate.reject_reasons)
    if not usable:
        return CandidateGateDecision(
            verdict="no_candidates",
            ranked_candidates=ranked,
            policy=active_policy,
            reason="No non-rejected candidates were supplied.",
        )

    top = usable[0]
    if top.score < active_policy.auto_map_min_score or top.confidence_bucket != "high":
        return CandidateGateDecision(
            verdict="ambiguous",
            selected=top,
            ranked_candidates=ranked,
            policy=active_policy,
            reason=(
                "Top candidate did not meet the high-confidence auto-map "
                f"threshold of {active_policy.auto_map_min_score:.2f}."
            ),
        )

    distinct_runner_up = next(
        (candidate for candidate in usable[1:] if candidate.target_key != top.target_key),
        None,
    )
    if (
        distinct_runner_up is not None
        and top.score - distinct_runner_up.score <= active_policy.ambiguity_margin
    ):
        return CandidateGateDecision(
            verdict="ambiguous",
            selected=top,
            ranked_candidates=ranked,
            policy=active_policy,
            reason=(
                "Top candidate is within the ambiguity margin of another distinct coding target."
            ),
        )

    return CandidateGateDecision(
        verdict="auto_map",
        selected=top,
        ranked_candidates=ranked,
        policy=active_policy,
        reason="Top candidate met the high-confidence threshold with no close distinct target.",
    )


def _candidate_sort_key(
    candidate: TerminologyCandidate,
) -> tuple[bool, float, int, int, str, str, str, str]:
    return (
        bool(candidate.reject_reasons),
        -candidate.score,
        _BUCKET_PRIORITY[candidate.confidence_bucket],
        _SOURCE_PRIORITY[candidate.source.kind],
        normalize_candidate_surface(candidate.name),
        candidate.system,
        candidate.code,
        candidate.matched_variant,
    )


def _remove_parentheticals(surface: str) -> str:
    return _PARENTHETICAL_RE.sub(" ", surface)


def _strip_history_prefix(surface: str) -> str:
    return _HISTORY_PREFIX_RE.sub("", surface)


def _strip_diagnosis_prefix(surface: str) -> str:
    return _DIAGNOSIS_PREFIX_RE.sub("", surface)


def _strip_qualifier_prefix(surface: str) -> str:
    return _QUALIFIER_PREFIX_RE.sub("", surface)


def _strip_temporal_window(surface: str) -> str:
    return _TEMPORAL_WINDOW_RE.sub("", surface)


def _strip_exclusion_clause(surface: str) -> str:
    return _EXCLUSION_CLAUSE_RE.sub("", surface)


def _singularize_last_token(surface: str) -> str:
    tokens = surface.split()
    if not tokens:
        return surface
    singular = _singularize_token(tokens[-1])
    if singular == tokens[-1]:
        return surface
    return " ".join((*tokens[:-1], singular))


def _pluralize_last_token(surface: str) -> str:
    tokens = surface.split()
    if not tokens:
        return surface
    last = tokens[-1]
    if last in _UNINFLECTED_TOKENS or last.endswith("s"):
        return surface
    if last.endswith("y") and len(last) > 1 and last[-2] not in "aeiou":
        plural = f"{last[:-1]}ies"
    elif last.endswith(("ch", "sh", "x", "z")):
        plural = f"{last}es"
    else:
        plural = f"{last}s"
    return " ".join((*tokens[:-1], plural))


def _singularize_token(token: str) -> str:
    if token in _UNINFLECTED_TOKENS or len(token) <= 3:
        return token
    if token.endswith("ies") and len(token) > 4:
        return f"{token[:-3]}y"
    if token.endswith(("ches", "shes")) and len(token) > 5:
        return token[:-2]
    if token.endswith("ses") and not token.endswith("oses"):
        return token[:-2]
    if token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


__all__ = [
    "AMBIGUITY_MARGIN",
    "HIGH_CONFIDENCE_MIN_SCORE",
    "MEDIUM_CONFIDENCE_MIN_SCORE",
    "CandidateConfidencePolicy",
    "CandidateGateDecision",
    "CandidateGateVerdict",
    "CandidateRejectReason",
    "CandidateSource",
    "CandidateSourceKind",
    "ConfidenceBucket",
    "QueryVariant",
    "TerminologyCandidate",
    "bucket_for_score",
    "gate_candidate_set",
    "generate_query_variants",
    "normalize_candidate_surface",
    "rank_candidates",
]
