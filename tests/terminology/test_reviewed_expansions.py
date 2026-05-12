from __future__ import annotations

import pytest

from clinical_demo.profile import ConceptSet
from clinical_demo.terminology.reviewed_expansions import (
    DuplicateReviewedExpansionError,
    ReviewedExpansionEntry,
    ReviewedExpansionRegistry,
    load_reviewed_expansion_registry,
)


def test_loads_committed_reviewed_expansion_registry() -> None:
    registry = load_reviewed_expansion_registry()

    entry = registry.lookup(
        concept_set=ConceptSet(
            name="psychiatric disorder",
            system="http://snomed.info/sct",
            codes=frozenset({"74732009"}),
        ),
        policy="descendants",
    )

    assert entry is not None
    assert entry.expanded_name == "Psychiatric disorder reviewed descendant closure"
    assert "74732009" in entry.expanded_code_values


def test_rejects_duplicate_reviewed_expansion_keys() -> None:
    payload = {
        "policy": "descendants",
        "source_system": "http://snomed.info/sct",
        "source_codes": ["123"],
        "source_display": "Parent",
        "expanded_name": "Parent closure",
        "expanded_codes": [{"code": "123", "display": "Parent", "reason": "Reviewed parent."}],
        "reason": "Reviewed closure.",
        "source": "unit test",
        "provenance": "unit test",
        "reviewer": "unit test",
        "reviewed_at": "2026-05-12",
        "resolver_version": "reviewed-expansion-registry-v1",
    }

    with pytest.raises(DuplicateReviewedExpansionError):
        ReviewedExpansionRegistry(
            [
                ReviewedExpansionEntry.model_validate(payload),
                ReviewedExpansionEntry.model_validate(payload),
            ]
        )
