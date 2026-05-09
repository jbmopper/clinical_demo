from __future__ import annotations

from clinical_demo.terminology.candidates import (
    CandidateSource,
    TerminologyCandidate,
    gate_candidate_set,
    generate_query_variants,
    normalize_candidate_surface,
    rank_candidates,
)


def _candidate(
    *,
    code: str,
    name: str,
    score: float,
    source_kind: str = "umls",
    reject_reasons: tuple[str, ...] = (),
) -> TerminologyCandidate:
    return TerminologyCandidate.model_validate(
        {
            "source": {"kind": source_kind, "name": source_kind},
            "matched_surface": "Bone fractures",
            "matched_variant": "bone fractures",
            "code": code,
            "system": "http://snomed.info/sct",
            "name": name,
            "score": score,
            "reject_reasons": reject_reasons,
        }
    )


def test_normalize_candidate_surface_cleans_punctuation_and_spacing() -> None:
    assert normalize_candidate_surface("  LDL-cholesterol / fasting!!  ") == (
        "ldl cholesterol fasting"
    )


def test_generate_query_variants_cleans_parentheticals_temporal_and_plural() -> None:
    variants = {
        variant.variant: variant.transforms
        for variant in generate_query_variants(
            "Bone fractures (excluding skull, facial bones) within the past 12 months"
        )
    }

    assert "bone fractures excluding skull facial bones within the past 12 months" in variants
    assert variants["bone fractures"] == (
        "parenthetical_cleanup",
        "temporal_window_stripped",
    )
    assert variants["bone fracture"] == (
        "parenthetical_cleanup",
        "temporal_window_stripped",
        "singularized_last_token",
    )


def test_generate_query_variants_strips_history_and_qualifier_prefixes() -> None:
    variants = {variant.variant for variant in generate_query_variants("History of prior fracture")}

    assert "history of prior fracture" in variants
    assert "prior fracture" in variants
    assert "fracture" in variants
    assert "fractures" in variants


def test_rank_candidates_is_deterministic_for_score_ties() -> None:
    zeta = _candidate(code="222", name="Zeta disorder", score=0.94)
    alpha_later_code = _candidate(code="333", name="Alpha disorder", score=0.94)
    alpha_first_code = _candidate(code="111", name="Alpha disorder", score=0.94)

    ranked = rank_candidates([zeta, alpha_later_code, alpha_first_code])

    assert [candidate.code for candidate in ranked] == ["111", "333", "222"]


def test_gate_candidate_set_auto_maps_clear_high_confidence_candidate() -> None:
    decision = gate_candidate_set(
        [
            _candidate(code="111", name="Bone fracture", score=0.96),
            _candidate(code="222", name="Bone contusion", score=0.75),
        ]
    )

    assert decision.verdict == "auto_map"
    assert decision.selected is not None
    assert decision.selected.code == "111"


def test_gate_candidate_set_marks_close_targets_ambiguous() -> None:
    decision = gate_candidate_set(
        [
            _candidate(code="111", name="Bone fracture", score=0.96),
            _candidate(code="222", name="Pathologic fracture", score=0.93),
        ]
    )

    assert decision.verdict == "ambiguous"
    assert "ambiguity margin" in decision.reason


def test_gate_candidate_set_marks_medium_confidence_ambiguous() -> None:
    decision = gate_candidate_set([_candidate(code="111", name="Bone fracture", score=0.82)])

    assert decision.verdict == "ambiguous"
    assert decision.selected is not None
    assert decision.selected.confidence_bucket == "medium"


def test_gate_candidate_set_reports_no_candidates_when_all_rejected() -> None:
    decision = gate_candidate_set(
        [
            _candidate(
                code="111",
                name="Bone fracture",
                score=0.98,
                reject_reasons=("semantic_type_mismatch",),
            )
        ]
    )

    assert decision.verdict == "no_candidates"
    assert decision.selected is None
    assert decision.ranked_candidates[0].confidence_bucket == "rejected"


def test_candidate_source_model_is_exportable_for_parent_compiler() -> None:
    source = CandidateSource(kind="reviewed_registry", name="committed reviewed mappings")

    assert source.kind == "reviewed_registry"
