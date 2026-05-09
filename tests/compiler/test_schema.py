from __future__ import annotations

import pytest
from pydantic import ValidationError

from clinical_demo.compiler.schema import (
    CheckablePredicate,
    CheckablePredicatePlan,
    CompilerDiagnostic,
    DiagnosticFact,
    ExpansionPlan,
    ResolutionGap,
    ResolutionSupport,
    UnitNormalizationPlan,
)


def test_resolution_support_records_resolver_policy_and_target() -> None:
    support = ResolutionSupport(
        support_id="support:0",
        stage="concept_resolution",
        domain="condition",
        source_criterion_id="criterion:0",
        surface="bone fractures",
        normalized_surface="bone fractures",
        target_system="concept_set",
        target_id="FRACTURE",
        target_label="Fracture",
        resolver_policy="cached_only",
    )

    assert support.resolver_policy == "cached_only"
    assert support.target_id == "FRACTURE"


def test_gap_and_diagnostic_containers_are_typed() -> None:
    gap = ResolutionGap(
        gap_id="gap:0",
        stage="unit_normalization",
        domain="unit",
        kind="missing_unit",
        source_criterion_id="criterion:1",
        surface="albumin",
        message="No conventional unit is registered for this measurement.",
        resolver_policy="cached_only",
    )
    diagnostic = CompilerDiagnostic(
        severity="warning",
        code="unit.missing",
        message="Unit normalization could not run.",
        stage="unit_normalization",
        source_criterion_id="criterion:1",
        facts=[DiagnosticFact(key="gap_id", value=gap.gap_id)],
    )

    assert gap.kind == "missing_unit"
    assert diagnostic.facts[0].value == "gap:0"


def test_checkable_predicate_records_typed_execution_target() -> None:
    predicate = CheckablePredicate(
        predicate_id="predicate:0",
        predicate_kind="measurement_threshold",
        source_criterion_id="criterion:0",
        polarity="inclusion",
        negated=False,
        surface="HbA1c",
        target_system="http://loinc.org",
        target_codes=frozenset({"4548-4"}),
        operator=">=",
        value=7.0,
        value_low=None,
        value_high=None,
        unit="%",
        window_days=None,
        support_ids=["support:0"],
        gap_ids=[],
    )

    assert predicate.target_codes == frozenset({"4548-4"})
    assert predicate.operator == ">="
    assert predicate.support_ids == ["support:0"]


def test_future_stage_plan_objects_are_validation_checked() -> None:
    expansion = ExpansionPlan(
        status="not_attempted",
        domain="measurement",
        source_surface="HbA1c",
        strategy="none",
    )
    unit = UnitNormalizationPlan(
        status="not_attempted",
        measurement_surface="HbA1c",
        source_unit="%",
        canonical_unit=None,
        conventional_unit=None,
        conversion_factor=None,
    )
    predicate = CheckablePredicatePlan(
        status="not_attempted",
        predicate_kind="measurement_threshold",
        expression=None,
        input_refs=["criterion:0"],
    )

    assert expansion.strategy == "none"
    assert unit.source_unit == "%"
    assert predicate.input_refs == ["criterion:0"]

    with pytest.raises(ValidationError):
        ExpansionPlan.model_validate(
            {
                "status": "done-ish",
                "domain": "measurement",
                "source_surface": "HbA1c",
                "strategy": "none",
            }
        )
