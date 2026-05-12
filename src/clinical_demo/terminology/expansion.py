"""Offline-safe concept expansion foundation.

The compiler can use this module to represent expansion policy decisions before
we wire live terminology graph/value-set expansion. Unsupported modes are
explicitly returned as typed results so downstream code cannot accidentally
treat an unimplemented expansion as complete.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from clinical_demo.profile import ConceptSet
from clinical_demo.terminology.reviewed_expansions import (
    ReviewedExpansionRegistry,
    load_reviewed_expansion_registry,
)
from clinical_demo.terminology.reviewed_registry import ExpansionPolicy as ConceptExpansionPolicy

ExpansionStatus = Literal["resolved", "unresolved", "unsupported"]
ExpansionUnsupportedReason = Literal[
    "descendants_not_available_offline",
    "value_set_oid_requires_resolver",
    "missing_patient_vocabulary",
    "empty_patient_vocabulary_closure",
]


class ConceptExpansionRequest(BaseModel):
    """Request envelope for expanding a matcher ``ConceptSet``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    concept_set: ConceptSet
    policy: ConceptExpansionPolicy
    patient_vocabulary_codes: frozenset[str] | None = None
    value_set_oid: str | None = None


class ConceptExpansionResult(BaseModel):
    """Typed result for one expansion policy application."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    policy: ConceptExpansionPolicy
    status: ExpansionStatus
    input_concept_set: ConceptSet
    expanded_concept_set: ConceptSet | None = None
    included_codes: frozenset[str] = Field(default_factory=frozenset)
    removed_codes: frozenset[str] = Field(default_factory=frozenset)
    unsupported_reason: ExpansionUnsupportedReason | None = None
    reason: str


def expand_concept_set(
    concept_set: ConceptSet,
    *,
    policy: ConceptExpansionPolicy,
    patient_vocabulary_codes: frozenset[str] | set[str] | None = None,
    value_set_oid: str | None = None,
) -> ConceptExpansionResult:
    """Apply an offline expansion policy to ``concept_set``.

    ``exact_code`` and ``reviewed_code_list`` keep the reviewed codes exactly.
    ``patient_vocabulary_closure`` intersects reviewed codes with observed
    patient vocabulary. ``descendants`` and ``value_set_oid`` use committed
    reviewed expansion closures when available; otherwise they remain explicit
    unsupported results until graph/value-set resolvers are available.
    """

    request = ConceptExpansionRequest(
        concept_set=concept_set,
        policy=policy,
        patient_vocabulary_codes=(
            None if patient_vocabulary_codes is None else frozenset(patient_vocabulary_codes)
        ),
        value_set_oid=value_set_oid,
    )
    if request.policy == "exact_code":
        return _resolved_copy(
            request,
            name_suffix=None,
            reason="Using exact ConceptSet codes without terminology expansion.",
        )
    if request.policy == "reviewed_code_list":
        return _resolved_copy(
            request,
            name_suffix="reviewed code list",
            reason="Using committed reviewed code list without terminology expansion.",
        )
    if request.policy == "patient_vocabulary_closure":
        return _patient_vocabulary_closure(request)
    if request.policy == "descendants":
        reviewed = _reviewed_expansion(request)
        if reviewed is not None:
            return reviewed
        return ConceptExpansionResult(
            policy=request.policy,
            status="unsupported",
            input_concept_set=request.concept_set,
            unsupported_reason="descendants_not_available_offline",
            reason=(
                "No reviewed offline SNOMED descendant expansion is committed "
                "for this ConceptSet; live graph expansion is not available in "
                "deterministic runs."
            ),
        )
    reviewed = _reviewed_expansion(request)
    if reviewed is not None:
        return reviewed
    return ConceptExpansionResult(
        policy=request.policy,
        status="unsupported",
        input_concept_set=request.concept_set,
        unsupported_reason="value_set_oid_requires_resolver",
        reason=(
            "No reviewed offline value-set expansion is committed for this "
            "ConceptSet/OID; live value-set expansion is not available in "
            "deterministic runs."
        ),
    )


def _resolved_copy(
    request: ConceptExpansionRequest,
    *,
    name_suffix: str | None,
    reason: str,
) -> ConceptExpansionResult:
    concept_set = request.concept_set
    name = concept_set.name if name_suffix is None else f"{concept_set.name} ({name_suffix})"
    expanded = ConceptSet(
        name=name,
        system=concept_set.system,
        codes=frozenset(concept_set.codes),
    )
    return ConceptExpansionResult(
        policy=request.policy,
        status="resolved",
        input_concept_set=concept_set,
        expanded_concept_set=expanded,
        included_codes=expanded.codes,
        reason=reason,
    )


def _patient_vocabulary_closure(request: ConceptExpansionRequest) -> ConceptExpansionResult:
    concept_set = request.concept_set
    if request.patient_vocabulary_codes is None:
        return ConceptExpansionResult(
            policy=request.policy,
            status="unresolved",
            input_concept_set=concept_set,
            unsupported_reason="missing_patient_vocabulary",
            reason="Patient vocabulary closure requires observed patient vocabulary codes.",
        )

    included = frozenset(concept_set.codes & request.patient_vocabulary_codes)
    removed = frozenset(concept_set.codes - included)
    if not included:
        return ConceptExpansionResult(
            policy=request.policy,
            status="unresolved",
            input_concept_set=concept_set,
            included_codes=included,
            removed_codes=removed,
            unsupported_reason="empty_patient_vocabulary_closure",
            reason="No reviewed ConceptSet codes were present in the patient vocabulary.",
        )

    expanded = ConceptSet(
        name=f"{concept_set.name} (patient vocabulary closure)",
        system=concept_set.system,
        codes=included,
    )
    return ConceptExpansionResult(
        policy=request.policy,
        status="resolved",
        input_concept_set=concept_set,
        expanded_concept_set=expanded,
        included_codes=included,
        removed_codes=removed,
        reason="Filtered reviewed ConceptSet codes to observed patient vocabulary.",
    )


def _reviewed_expansion(request: ConceptExpansionRequest) -> ConceptExpansionResult | None:
    entry = _reviewed_expansion_registry().lookup(
        concept_set=request.concept_set,
        policy=request.policy,
        value_set_oid=request.value_set_oid,
    )
    if entry is None:
        return None

    expanded = entry.to_concept_set()
    return ConceptExpansionResult(
        policy=request.policy,
        status="resolved",
        input_concept_set=request.concept_set,
        expanded_concept_set=expanded,
        included_codes=expanded.codes,
        reason=entry.reason,
    )


@lru_cache(maxsize=1)
def _reviewed_expansion_registry() -> ReviewedExpansionRegistry:
    return load_reviewed_expansion_registry()


__all__ = [
    "ConceptExpansionPolicy",
    "ConceptExpansionRequest",
    "ConceptExpansionResult",
    "ExpansionStatus",
    "ExpansionUnsupportedReason",
    "expand_concept_set",
]
