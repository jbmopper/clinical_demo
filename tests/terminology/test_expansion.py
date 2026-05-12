from __future__ import annotations

from clinical_demo.profile import ConceptSet
from clinical_demo.terminology.expansion import expand_concept_set


def _concept_set() -> ConceptSet:
    return ConceptSet(
        name="Bone fracture",
        system="http://snomed.info/sct",
        codes=frozenset({"111", "222", "333"}),
    )


def _cardiovascular_parent() -> ConceptSet:
    return ConceptSet(
        name="cardiovascular disease",
        system="http://snomed.info/sct",
        codes=frozenset({"49601007"}),
    )


def test_exact_code_expansion_preserves_concept_set_codes() -> None:
    result = expand_concept_set(_concept_set(), policy="exact_code")

    assert result.status == "resolved"
    assert result.expanded_concept_set is not None
    assert result.expanded_concept_set.codes == frozenset({"111", "222", "333"})
    assert result.removed_codes == frozenset()


def test_reviewed_code_list_expansion_preserves_reviewed_codes() -> None:
    result = expand_concept_set(_concept_set(), policy="reviewed_code_list")

    assert result.status == "resolved"
    assert result.expanded_concept_set is not None
    assert result.expanded_concept_set.name == "Bone fracture (reviewed code list)"
    assert result.included_codes == frozenset({"111", "222", "333"})


def test_patient_vocabulary_closure_filters_to_observed_codes() -> None:
    result = expand_concept_set(
        _concept_set(),
        policy="patient_vocabulary_closure",
        patient_vocabulary_codes=frozenset({"222", "999"}),
    )

    assert result.status == "resolved"
    assert result.expanded_concept_set is not None
    assert result.expanded_concept_set.codes == frozenset({"222"})
    assert result.included_codes == frozenset({"222"})
    assert result.removed_codes == frozenset({"111", "333"})


def test_patient_vocabulary_closure_without_vocabulary_is_unresolved() -> None:
    result = expand_concept_set(_concept_set(), policy="patient_vocabulary_closure")

    assert result.status == "unresolved"
    assert result.expanded_concept_set is None
    assert result.unsupported_reason == "missing_patient_vocabulary"


def test_patient_vocabulary_closure_without_overlap_is_unresolved() -> None:
    result = expand_concept_set(
        _concept_set(),
        policy="patient_vocabulary_closure",
        patient_vocabulary_codes=frozenset({"999"}),
    )

    assert result.status == "unresolved"
    assert result.expanded_concept_set is None
    assert result.unsupported_reason == "empty_patient_vocabulary_closure"
    assert result.removed_codes == frozenset({"111", "222", "333"})


def test_descendants_policy_is_explicitly_unsupported_offline() -> None:
    result = expand_concept_set(_concept_set(), policy="descendants")

    assert result.status == "unsupported"
    assert result.expanded_concept_set is None
    assert result.unsupported_reason == "descendants_not_available_offline"


def test_descendants_policy_uses_reviewed_offline_expansion_when_available() -> None:
    result = expand_concept_set(_cardiovascular_parent(), policy="descendants")

    assert result.status == "resolved"
    assert result.expanded_concept_set is not None
    assert result.expanded_concept_set.name == "Cardiovascular disease reviewed descendant closure"
    assert "49601007" in result.included_codes
    assert "84114007" in result.included_codes
    assert "22298006" in result.included_codes


def test_value_set_oid_policy_is_explicitly_unsupported_offline() -> None:
    result = expand_concept_set(
        _concept_set(),
        policy="value_set_oid",
        value_set_oid="2.16.840.1.113883.3.464.1003.113.12.1001",
    )

    assert result.status == "unsupported"
    assert result.expanded_concept_set is None
    assert result.unsupported_reason == "value_set_oid_requires_resolver"
