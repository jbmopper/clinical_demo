from __future__ import annotations

from tests.matcher._fixtures import (
    AS_OF,
    crit_condition,
    crit_measurement,
    make_condition,
    make_lab,
    make_profile,
    make_trial,
)

from clinical_demo.compiler.parity import compare_compilation_parity
from clinical_demo.compiler.pipeline import compile_extracted_criteria
from clinical_demo.compiler.schema import ResolutionGap


def test_parity_reports_same_for_simple_mapped_criteria() -> None:
    criteria = [
        crit_condition(text="type 2 diabetes"),
        crit_measurement(text="HbA1c", operator=">=", value=7.0, unit="%"),
    ]
    profile = make_profile(
        conditions=[make_condition(code="44054006", display="T2DM")],
        observations=[make_lab(loinc="4548-4", value=7.4, unit="%")],
    )

    report = compare_compilation_parity(
        compile_extracted_criteria(criteria),
        profile,
        make_trial(),
    )

    assert report.total_criteria == 2
    assert [comparison.classification for comparison in report.criteria] == ["same", "same"]
    assert report.summary_counts == {
        "same": 2,
        "compiled_improved": 0,
        "compiled_regressed": 0,
        "changed": 0,
    }
    assert report.criteria[0].source_criterion_id == "criterion:0"
    assert report.criteria[0].source_index == 0
    assert report.criteria[0].legacy_verdict == "pass"
    assert report.criteria[0].compiled_verdict == "pass"


def test_parity_classifies_reviewed_fracture_variant_as_compiled_improved() -> None:
    criterion = crit_condition(
        text=(
            "Bone fractures (excluding skull, facial bones, metacarpals, fingers, toes "
            "and spontaneous fractures associated with severe trauma) within the past 12 months"
        )
    )
    profile = make_profile(
        conditions=[
            make_condition(
                code="263102004",
                display="Fracture subluxation of wrist",
                onset=AS_OF.replace(year=AS_OF.year - 1),
            )
        ]
    )

    report = compare_compilation_parity(
        compile_extracted_criteria([criterion]),
        profile,
        make_trial(),
    )

    comparison = report.criteria[0]
    assert comparison.classification == "compiled_improved"
    assert comparison.legacy_verdict == "indeterminate"
    assert comparison.legacy_reason == "unmapped_concept"
    assert comparison.compiled_verdict == "pass"
    assert comparison.compiled_reason == "ok"
    assert report.summary_counts["compiled_improved"] == 1


def test_parity_classifies_missing_compiled_predicate_as_regression() -> None:
    criterion = crit_condition(text="type 2 diabetes")
    compilation = compile_extracted_criteria([criterion])
    gap = ResolutionGap(
        gap_id="criterion:0:gap:predicate",
        stage="predicate_translation",
        domain="predicate",
        kind="unsupported_predicate",
        source_criterion_id="criterion:0",
        surface=criterion.source_text,
        message="Injected test gap.",
        resolver_policy="cached_only",
    )
    broken_compiled = compilation.criteria[0].model_copy(
        update={"checkable_predicates": [], "unresolved_gaps": [gap]}
    )
    broken_compilation = compilation.model_copy(
        update={
            "criteria": [broken_compiled],
            "checkable_predicates": [],
            "unresolved_gaps": [gap],
        }
    )
    profile = make_profile(conditions=[make_condition(code="44054006", display="T2DM")])

    report = compare_compilation_parity(broken_compilation, profile, make_trial())

    comparison = report.criteria[0]
    assert comparison.classification == "compiled_regressed"
    assert comparison.legacy_verdict == "pass"
    assert comparison.legacy_reason == "ok"
    assert comparison.compiled_verdict == "indeterminate"
    assert comparison.compiled_reason == "unsupported_kind"
    assert report.summary_counts["compiled_regressed"] == 1
