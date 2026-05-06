from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "scripts" / "check_public_artifact_privacy.py"
SPEC = importlib.util.spec_from_file_location("check_public_artifact_privacy", MODULE_PATH)
assert SPEC is not None
gate = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = gate
SPEC.loader.exec_module(gate)


def test_eval_artifacts_require_public_safety_marker(tmp_path: Path) -> None:
    artifact = tmp_path / "eval" / "baselines" / "run.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text('{"patient_id": "P-1"}')

    findings = gate.scan_paths([artifact])

    assert [finding.reason for finding in findings] == ["missing artifact safety marker"]


def test_synthetic_marker_allows_patient_ids(tmp_path: Path) -> None:
    artifact = tmp_path / "eval" / "baselines" / "run.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text(
        """
        {
          "artifact_safety": {
            "public_export": "synthetic",
            "contains_real_patient_data": false
          },
          "rows": [{"patient_id": "synthetic-patient-1"}]
        }
        """
    )

    assert gate.scan_paths([artifact]) == []


def test_note_rows_are_blocked_even_when_marked_synthetic(tmp_path: Path) -> None:
    artifact = tmp_path / "eval" / "calibration" / "candidates.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text(
        """
        {
          "artifact_safety": {
            "public_export": "synthetic",
            "contains_real_patient_data": false
          },
          "rows": [{"kind": "note", "status": "note_id=doc-123"}]
        }
        """
    )

    reasons = [finding.detail for finding in gate.scan_paths([artifact])]

    assert any("clinical note row" in reason for reason in reasons)
    assert any("note identifier" in reason for reason in reasons)


def test_non_eval_files_are_ignored(tmp_path: Path) -> None:
    artifact = tmp_path / "scratch" / "run.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text('{"patient_id": "P-1"}')

    assert gate.scan_paths([artifact]) == []
