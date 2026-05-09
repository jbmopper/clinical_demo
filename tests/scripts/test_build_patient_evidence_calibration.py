from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).parents[2] / "scripts" / "build_patient_evidence_calibration.py"
SPEC = importlib.util.spec_from_file_location("build_patient_evidence_calibration", MODULE_PATH)
assert SPEC is not None
builder = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = builder
SPEC.loader.exec_module(builder)


def test_public_summary_export_command_points_to_safe_exporter() -> None:
    command = builder.public_summary_export_command(
        candidates=Path("eval/calibration/patient_evidence_candidates.json"),
        labels=Path("eval/calibration/patient_evidence_labels.json"),
        diagnostics=Path("eval/baselines/2026-05-06/composite_v06_none_diagnostics.json"),
        output=Path("eval/baselines/2026-05-06/composite_v06_public_summary.json"),
    )

    assert command == (
        "uv run python scripts/export_patient_evidence_public_summary.py "
        "--candidates eval/calibration/patient_evidence_candidates.json "
        "--labels eval/calibration/patient_evidence_labels.json "
        "--diagnostics eval/baselines/2026-05-06/composite_v06_none_diagnostics.json "
        "--output eval/baselines/2026-05-06/composite_v06_public_summary.json"
    )


def test_reviewed_label_keys_ignore_empty_templates_and_keep_user_work() -> None:
    labels = [
        builder.PatientEvidenceHumanLabel(pair_id="empty", criterion_index=0),
        builder.PatientEvidenceHumanLabel(
            pair_id="labeled",
            criterion_index=1,
            expected_matcher_verdict="pass",
        ),
        builder.PatientEvidenceHumanLabel(
            pair_id="assumption",
            criterion_index=2,
            matcher_assumption_mode="closed_world_eval",
        ),
    ]

    assert builder._reviewed_label_keys(labels) == {
        ("labeled", 1),
        ("assumption", 2),
    }


def test_builder_defaults_to_resolver_backed_binding_strategy() -> None:
    assert builder.DEFAULT_BINDING_STRATEGY == "two_pass"


def test_apply_binding_strategy_clears_settings_cache(monkeypatch) -> None:
    from clinical_demo.settings import get_settings
    from clinical_demo.terminology.resolver import get_resolver

    monkeypatch.setenv("BINDING_STRATEGY", "alias")
    get_settings.cache_clear()
    get_resolver.cache_clear()

    try:
        builder._apply_binding_strategy("two_pass")

        assert get_settings().binding_strategy == "two_pass"
    finally:
        get_settings.cache_clear()
        get_resolver.cache_clear()
