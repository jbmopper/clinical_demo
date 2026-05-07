"""Tests for the outbound privacy boundary."""

from __future__ import annotations

from clinical_demo.privacy import (
    AnonymizationContext,
    PresidioPrivacyEngine,
    PrivacyPolicy,
    anonymize_text,
    sanitize_for_metadata,
    sanitize_for_trace,
)


def test_placeholders_are_stable_within_one_context() -> None:
    context = AnonymizationContext()
    engine = PresidioPrivacyEngine()

    first = anonymize_text(
        "patient_id=abc123 called 303-555-1212; patient_id=abc123 returned.",
        context=context,
        policy=PrivacyPolicy.llm_prompt(),
        engine=engine,
    )
    second = anonymize_text(
        "Follow-up for patient_id=abc123.",
        context=context,
        policy=PrivacyPolicy.llm_prompt(),
        engine=engine,
    )

    patient_replacements = [
        r.replacement for r in first.replacements if r.entity_type == "PATIENT_ID"
    ]
    assert len(set(patient_replacements)) == 1
    assert patient_replacements[0] in second.text
    assert "abc123" not in first.text
    assert "303-555-1212" not in first.text


def test_placeholders_do_not_persist_across_contexts() -> None:
    engine = PresidioPrivacyEngine()
    first = anonymize_text(
        "patient_id=abc123",
        context=AnonymizationContext(),
        policy=PrivacyPolicy.llm_prompt(),
        engine=engine,
    ).text
    second = anonymize_text(
        "patient_id=abc123",
        context=AnonymizationContext(),
        policy=PrivacyPolicy.llm_prompt(),
        engine=engine,
    ).text

    assert first != second


def test_trace_sanitizer_preserves_source_row_ids_but_removes_identifiers() -> None:
    context = AnonymizationContext()
    payload = {
        "row_id": "patient:004",
        "value": "MRN: A12345. Jane called 303-555-1212 on 2024-12-01.",
        "date": "2024-12-01",
    }

    sanitized = sanitize_for_trace(payload, context=context)

    assert sanitized["row_id"] == "patient:004"
    assert "A12345" not in sanitized["value"]
    assert "303-555-1212" not in sanitized["value"]
    assert sanitized["date"].startswith("<DATE_")


def test_metadata_sanitizer_only_pseudonymizes_sensitive_keys() -> None:
    context = AnonymizationContext()
    metadata = {
        "patient_id": "P-test",
        "nct_id": "NCT00000000",
        "prompt_version": "v1",
    }

    sanitized = sanitize_for_metadata(metadata, context=context)

    assert sanitized is not None
    assert sanitized["patient_id"] != "P-test"
    assert sanitized["nct_id"] == "NCT00000000"
    assert sanitized["prompt_version"] == "v1"
