from __future__ import annotations

from clinical_demo.compiler import compile_medication_resolution
from clinical_demo.extractor.schema import ExtractedCriterion, MedicationCriterion
from clinical_demo.profile import ConceptSet

METFORMIN = ConceptSet(
    name="metformin",
    system="http://www.nlm.nih.gov/research/umls/rxnorm",
    codes=frozenset({"860975"}),
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


def test_class_like_medication_emits_unsupported_gap_without_false_mapping() -> None:
    resolver = StubMedicationResolver({"GLP-1 receptor agonists": METFORMIN})

    result = compile_medication_resolution(
        _criterion("GLP-1 receptor agonists"),
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
