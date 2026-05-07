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
