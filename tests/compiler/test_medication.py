from __future__ import annotations

from pathlib import Path

from clinical_demo.compiler import compile_medication_resolution
from clinical_demo.extractor.schema import ExtractedCriterion, MedicationCriterion
from clinical_demo.profile import ConceptSet
from clinical_demo.terminology import TerminologyCache, TerminologyResolver
from clinical_demo.terminology.reviewed_registry import (
    REVIEWED_REGISTRY_VERSION,
    ReviewedMappingEntry,
    ReviewedMappingRegistry,
)

METFORMIN = ConceptSet(
    name="metformin",
    system="http://www.nlm.nih.gov/research/umls/rxnorm",
    codes=frozenset({"860975"}),
)
ATORVASTATIN = ConceptSet(
    name="atorvastatin",
    system="http://www.nlm.nih.gov/research/umls/rxnorm",
    codes=frozenset({"259255"}),
)
SIMVASTATIN = ConceptSet(
    name="simvastatin",
    system="http://www.nlm.nih.gov/research/umls/rxnorm",
    codes=frozenset({"312961"}),
)


class StubMedicationResolver:
    def __init__(
        self,
        mapping: dict[str, ConceptSet | None],
        *,
        execution_policy: str = "cached_only",
    ) -> None:
        self.mapping = mapping
        self.execution_policy = execution_policy
        self.calls: list[str] = []

    def resolve_medication(self, surface: str) -> ConceptSet | None:
        self.calls.append(surface)
        return self.mapping.get(surface)


def _criterion(text: str, *, kind: str = "medication_present") -> ExtractedCriterion:
    return ExtractedCriterion(
        kind=kind,  # type: ignore[arg-type]
        polarity="inclusion",
        source_text=f"{text} use",
        negated=kind == "medication_absent",
        mood="actual",
        age=None,
        sex=None,
        condition=None,
        medication=MedicationCriterion(medication_text=text),
        measurement=None,
        temporal_window=None,
        free_text=None,
        mentions=[],
    )


def test_mapped_injected_resolver_emits_medication_exposure_support() -> None:
    resolver = StubMedicationResolver({"metformin": METFORMIN})

    result = compile_medication_resolution(
        _criterion("metformin"),
        source_criterion_id="criterion:0",
        resolver=resolver,
    )

    assert resolver.calls == ["metformin"]
    assert result.concept_set == METFORMIN
    assert result.supports[0].domain == "medication"
    assert result.supports[0].target_id == "metformin"
    assert result.predicate.status == "resolved"
    assert result.predicate.predicate_kind == "medication_exposure"
    assert result.predicate.support_ids == [result.supports[0].support_id]
    assert result.ingredient.status == "resolved"
    assert result.medication_class.status == "skipped"
    assert result.gaps == []


def test_route_prefixed_medication_resolves_stripped_ingredient_surface() -> None:
    resolver = StubMedicationResolver({"metformin": METFORMIN, "oral metformin": None})

    result = compile_medication_resolution(
        _criterion("oral metformin"),
        source_criterion_id="criterion:oral",
        resolver=resolver,
    )

    assert resolver.calls == ["metformin"]
    assert result.surface == "oral metformin"
    assert result.normalized_surface == "oral metformin"
    assert result.route.status == "resolved"
    assert result.route.normalized_surface == "oral"
    assert result.ingredient.status == "resolved"
    assert result.ingredient.surface == "metformin"
    assert result.ingredient.normalized_surface == "metformin"
    assert result.concept_set == METFORMIN
    assert result.supports[0].surface == "metformin"
    assert result.supports[0].normalized_surface == "metformin"
    assert result.gaps == []


def test_route_only_surface_is_insufficient_without_resolver_call() -> None:
    resolver = StubMedicationResolver({"oral": METFORMIN})

    result = compile_medication_resolution(
        _criterion("oral"),
        source_criterion_id="criterion:route-only",
        resolver=resolver,
    )

    assert resolver.calls == []
    assert result.surface == "oral"
    assert result.normalized_surface == "oral"
    assert result.route.status == "resolved"
    assert result.route.normalized_surface == "oral"
    assert result.ingredient.status == "unresolved"
    assert result.ingredient.surface is None
    assert result.gaps[0].kind == "insufficient_source"
    assert result.predicate.status == "unresolved"
    assert result.supports == []


def test_unmapped_medication_emits_unmapped_concept_gap() -> None:
    resolver = StubMedicationResolver({"warfarin": None})

    result = compile_medication_resolution(
        _criterion("warfarin"),
        source_criterion_id="criterion:1",
        resolver=resolver,
    )

    assert resolver.calls == ["warfarin"]
    assert result.supports == []
    assert result.gaps[0].kind == "unmapped_concept"
    assert result.gaps[0].domain == "medication"
    assert result.predicate.status == "unresolved"
    assert result.predicate.gap_ids == [result.gaps[0].gap_id]
    assert result.ingredient.status == "unresolved"


def test_composite_list_medication_emits_ambiguous_gap_without_resolving() -> None:
    resolver = StubMedicationResolver({"insulin or metformin": METFORMIN})

    result = compile_medication_resolution(
        _criterion("insulin or metformin"),
        source_criterion_id="criterion:2",
        resolver=resolver,
    )

    assert resolver.calls == []
    assert result.gaps[0].kind == "ambiguous_mapping"
    assert "multiple drugs" in result.gaps[0].message
    assert result.medication_class.status == "ambiguous"
    assert result.predicate.status == "ambiguous"
    assert result.supports == []


def test_reviewed_medication_class_expands_to_member_code_union() -> None:
    resolver = StubMedicationResolver({"atorvastatin": ATORVASTATIN, "simvastatin": SIMVASTATIN})

    result = compile_medication_resolution(
        _criterion("statins"),
        source_criterion_id="criterion:3",
        resolver=resolver,
    )

    assert resolver.calls == ["atorvastatin", "simvastatin"]
    assert result.concept_set is not None
    assert result.concept_set.name == "Statins"
    assert result.concept_set.codes == frozenset({"259255", "312961"})
    assert result.medication_class.status == "resolved"
    assert result.medication_class.surface == "statins"
    assert result.ingredient.status == "skipped"
    assert result.predicate.status == "resolved"
    assert result.predicate.support_ids == [
        "criterion:3:medication:support:class-expansion",
        "criterion:3:medication:support:class-member-001",
        "criterion:3:medication:support:class-member-002",
    ]
    assert [support.stage for support in result.supports] == [
        "expansion",
        "concept_resolution",
        "concept_resolution",
    ]
    assert result.gaps == []


def test_committed_lipid_lowering_class_expands_without_rxnorm_cache(tmp_path: Path) -> None:
    resolver = TerminologyResolver(
        TerminologyCache(tmp_path),
        execution_policy="cached_only",
    )

    result = compile_medication_resolution(
        _criterion("lipid-lowering oral drugs"),
        source_criterion_id="criterion:lipid",
        resolver=resolver,
    )

    assert result.gaps == []
    assert result.concept_set is not None
    assert result.concept_set.name == "Lipid-lowering therapy (current patient vocabulary)"
    assert result.concept_set.codes == frozenset({"259255", "314231", "312961"})
    assert result.medication_class.status == "resolved"
    assert [support.surface for support in result.supports] == [
        "lipid-lowering oral drugs",
        "atorvastatin",
        "simvastatin",
    ]


def test_committed_blood_pressure_affecting_class_expands_without_rxnorm_cache(
    tmp_path: Path,
) -> None:
    resolver = TerminologyResolver(
        TerminologyCache(tmp_path),
        execution_policy="cached_only",
    )

    result = compile_medication_resolution(
        _criterion("medication affecting blood pressure"),
        source_criterion_id="criterion:bp-meds",
        resolver=resolver,
    )

    assert result.gaps == []
    assert result.concept_set is not None
    assert result.concept_set.name == (
        "Blood-pressure-affecting medications (current patient vocabulary)"
    )
    assert result.concept_set.codes == frozenset(
        {"308136", "313988", "1719286", "310798", "314076", "314077", "979492"}
    )
    assert result.medication_class.status == "resolved"
    assert [support.surface for support in result.supports] == [
        "medication affecting blood pressure",
        "amlodipine",
        "furosemide",
        "hydrochlorothiazide",
        "lisinopril",
        "losartan",
    ]


def test_committed_glp1_class_expands_without_rxnorm_cache(tmp_path: Path) -> None:
    resolver = TerminologyResolver(
        TerminologyCache(tmp_path),
        execution_policy="cached_only",
    )

    result = compile_medication_resolution(
        _criterion("GLP-1 agonists"),
        source_criterion_id="criterion:glp1",
        resolver=resolver,
    )

    assert result.gaps == []
    assert result.concept_set is not None
    assert result.concept_set.name == "GLP-1 receptor agonists"
    assert len(result.concept_set.codes) == 40
    assert "1991306" in result.concept_set.codes
    assert "2739771" in result.concept_set.codes
    assert result.medication_class.status == "resolved"
    assert [support.surface for support in result.supports] == [
        "GLP-1 agonists",
        "semaglutide",
    ]


def test_committed_sglt_variant_class_expands_without_rxnorm_cache(tmp_path: Path) -> None:
    resolver = TerminologyResolver(
        TerminologyCache(tmp_path),
        execution_policy="cached_only",
    )

    result = compile_medication_resolution(
        _criterion("SGLT inhibitor"),
        source_criterion_id="criterion:sglt",
        resolver=resolver,
    )

    assert result.gaps == []
    assert result.concept_set is not None
    assert result.concept_set.name == "SGLT2 inhibitors"
    assert len(result.concept_set.codes) == 18
    assert "1486977" in result.concept_set.codes
    assert "2169276" in result.concept_set.codes
    assert result.medication_class.status == "resolved"
    assert [support.surface for support in result.supports] == [
        "SGLT inhibitor",
        "dapagliflozin",
    ]


def test_committed_non_insulin_antidiabetic_class_expands_without_rxnorm_cache(
    tmp_path: Path,
) -> None:
    resolver = TerminologyResolver(
        TerminologyCache(tmp_path),
        execution_policy="cached_only",
    )

    result = compile_medication_resolution(
        _criterion("diabetes medications other than insulin"),
        source_criterion_id="criterion:non-insulin-antidiabetic",
        resolver=resolver,
    )

    assert result.gaps == []
    assert result.concept_set is not None
    assert (
        result.concept_set.name
        == "Non-insulin antidiabetic medications (current patient vocabulary)"
    )
    assert "860975" in result.concept_set.codes
    assert "1991306" in result.concept_set.codes
    assert "1486977" in result.concept_set.codes
    assert "106892" not in result.concept_set.codes
    assert result.medication_class.status == "resolved"
    assert [support.surface for support in result.supports] == [
        "diabetes medications other than insulin",
        "metformin",
        "semaglutide",
        "dapagliflozin",
    ]


def test_reviewed_class_surface_can_override_list_like_text() -> None:
    resolver = StubMedicationResolver({"atorvastatin": ATORVASTATIN, "simvastatin": SIMVASTATIN})

    result = compile_medication_resolution(
        _criterion("low or moderate-intensity statins"),
        source_criterion_id="criterion:list-like-class",
        resolver=resolver,
    )

    assert resolver.calls == ["atorvastatin", "simvastatin"]
    assert result.medication_class.status == "resolved"
    assert result.predicate.status == "resolved"
    assert result.gaps == []


def test_reviewed_medication_class_requires_every_member_to_resolve() -> None:
    resolver = StubMedicationResolver({"atorvastatin": ATORVASTATIN, "simvastatin": None})

    result = compile_medication_resolution(
        _criterion("statins"),
        source_criterion_id="criterion:class-gap",
        resolver=resolver,
    )

    assert resolver.calls == ["atorvastatin", "simvastatin"]
    assert result.concept_set is None
    assert result.gaps[0].kind == "unmapped_concept"
    assert "simvastatin" in result.gaps[0].message
    assert result.medication_class.status == "unresolved"
    assert result.predicate.status == "unresolved"
    assert result.diagnostics[0].code == "medication.class_member_unmapped"


def test_reviewed_nonmapped_medication_emits_typed_gap_without_resolving() -> None:
    resolver = StubMedicationResolver({"marijuana": METFORMIN})
    registry = ReviewedMappingRegistry(
        [
            ReviewedMappingEntry.model_validate(
                {
                    "kind": "medication",
                    "surface": "marijuana",
                    "status": "out_of_scope",
                    "concept_set": None,
                    "reason": "substance-use history is not structured medication evidence",
                    "source": "unit test",
                    "provenance": "unit test",
                    "reviewer": "unit-test",
                    "reviewed_at": "2026-05-12",
                    "resolver_version": REVIEWED_REGISTRY_VERSION,
                    "expansion_policy": "exact_code",
                }
            )
        ]
    )

    result = compile_medication_resolution(
        _criterion("marijuana"),
        source_criterion_id="criterion:reviewed-med-gap",
        resolver=resolver,
        reviewed_registry=registry,
    )

    assert resolver.calls == []
    assert result.gaps[0].kind == "unsupported_predicate"
    assert result.predicate.status == "unsupported"
    assert result.ingredient.status == "unsupported"
    assert result.diagnostics[0].code == "medication.reviewed.out_of_scope"


def test_unreviewed_class_like_medication_emits_unsupported_gap_without_false_mapping() -> None:
    resolver = StubMedicationResolver({"DPP-4 inhibitors": METFORMIN})

    result = compile_medication_resolution(
        _criterion("DPP-4 inhibitors"),
        source_criterion_id="criterion:3",
        resolver=resolver,
    )

    assert resolver.calls == []
    assert result.gaps[0].kind == "unsupported_predicate"
    assert "medication class" in result.gaps[0].message
    assert result.medication_class.status == "unsupported"
    assert result.predicate.status == "unsupported"
    assert result.diagnostics[0].code == "medication.medication_class"


def test_present_and_absent_polarity_preserve_medication_exposure_kind() -> None:
    resolver = StubMedicationResolver({"metformin": METFORMIN})

    present = compile_medication_resolution(
        _criterion("metformin", kind="medication_present"),
        source_criterion_id="criterion:4",
        resolver=resolver,
    )
    absent = compile_medication_resolution(
        _criterion("metformin", kind="medication_absent"),
        source_criterion_id="criterion:5",
        resolver=resolver,
    )

    assert present.required_presence == "present"
    assert absent.required_presence == "absent"
    assert present.predicate.predicate_kind == "medication_exposure"
    assert absent.predicate.predicate_kind == "medication_exposure"
    assert "required=present" in (present.predicate.expression or "")
    assert "required=absent" in (absent.predicate.expression or "")


def test_non_cached_policy_does_not_call_resolver() -> None:
    resolver = StubMedicationResolver({"metformin": METFORMIN}, execution_policy="live_allowed")

    result = compile_medication_resolution(
        _criterion("metformin"),
        source_criterion_id="criterion:6",
        resolver_policy="live_allowed",
        resolver=resolver,
    )

    assert resolver.calls == []
    assert result.concept_set is None
    assert result.gaps[0].kind == "unmapped_concept"
    assert result.diagnostics[0].code == "medication.resolver_policy_not_cached_only"
