from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

SUMMARY_MODULE_PATH = (
    Path(__file__).parents[1] / "scripts" / "export_patient_evidence_public_summary.py"
)
SUMMARY_SPEC = importlib.util.spec_from_file_location(
    "export_patient_evidence_public_summary", SUMMARY_MODULE_PATH
)
assert SUMMARY_SPEC is not None
summary_exporter = importlib.util.module_from_spec(SUMMARY_SPEC)
assert SUMMARY_SPEC.loader is not None
sys.modules[SUMMARY_SPEC.name] = summary_exporter
SUMMARY_SPEC.loader.exec_module(summary_exporter)

GATE_MODULE_PATH = Path(__file__).parents[1] / "scripts" / "check_public_artifact_privacy.py"
GATE_SPEC = importlib.util.spec_from_file_location(
    "check_public_artifact_privacy", GATE_MODULE_PATH
)
assert GATE_SPEC is not None
privacy_gate = importlib.util.module_from_spec(GATE_SPEC)
assert GATE_SPEC.loader is not None
sys.modules[GATE_SPEC.name] = privacy_gate
GATE_SPEC.loader.exec_module(privacy_gate)


def test_summary_export_omits_row_level_patient_fields_and_passes_privacy_gate(
    tmp_path: Path,
) -> None:
    candidates = tmp_path / "private_candidates.json"
    labels = tmp_path / "private_labels.json"
    diagnostics = tmp_path / "private_diagnostics.json"
    output = tmp_path / "eval" / "baselines" / "summary.json"

    candidates.write_text(
        json.dumps(
            [
                {
                    "pair_id": "patient-123__NCT00000000",
                    "patient_id": "patient-123",
                    "candidate_bucket": "free_text_patient_evidence",
                    "criterion_kind": "free_text",
                    "polarity": "inclusion",
                    "matcher_verdict": "indeterminate",
                    "matcher_reason": "human_review_required",
                    "matcher_assumption_mode": "none",
                    "judge_label": "incorrect",
                    "judge_error_categories": ["patient_evidence"],
                    "source_rows": [
                        {
                            "row_id": "patient:001",
                            "source": "patient",
                            "kind": "note",
                            "value": "Call 303-555-1212 about MRN: A12345",
                            "status": "note_id=abc",
                        }
                    ],
                    "retrieved_source_row_ids": ["patient:001"],
                    "retrieval_reasons": {
                        "patient:001": [
                            "composite:any_of",
                            "subcheck:criterion:0:group:001:subcheck:001",
                        ]
                    },
                    "concept_mappings": [{"slot": "condition", "mapped": False}],
                    "composite_groups": [
                        {
                            "operator": "any_of",
                            "subchecks": [{"operator": "any_of"}],
                        }
                    ],
                    "evidence_retrieval_state": "note_retrieved",
                    "free_text_review_hint": "note_evidence_retrieved",
                    "mapping_state": "some_unmapped",
                }
            ]
        )
    )
    labels.write_text(
        json.dumps(
            [
                {
                    "pair_id": "patient-123__NCT00000000",
                    "criterion_index": 0,
                    "label": "insufficient_evidence",
                    "cited_source_row_ids": ["patient:001"],
                    "expected_matcher_verdict": "indeterminate",
                    "matcher_assumption_mode": "none",
                    "reviewer": "Dr. Person",
                    "rationale": "Private row looked insufficient.",
                }
            ]
        )
    )
    diagnostics.write_text(
        json.dumps(
            {
                "run_id": "run-v06",
                "notes": "private free text omitted",
                "n_cases": 1,
                "n_errors": 0,
                "scored_cases": 1,
                "total_criteria": 1,
                "verdict_counts": {"indeterminate": 1},
                "reason_counts": {"human_review_required": 1},
                "kind_counts": {"free_text": 1},
                "unmapped_count": 0,
                "indeterminate_count": 1,
            }
        )
    )

    summary = summary_exporter.build_public_summary(
        candidates_spec=str(candidates),
        labels_spec=str(labels),
        diagnostics_spec=str(diagnostics),
    )
    output.parent.mkdir(parents=True)
    output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")

    rendered = output.read_text()
    assert "patient-123" not in rendered
    assert "303-555-1212" not in rendered
    assert "A12345" not in rendered
    assert "note_id=" not in rendered
    assert '"kind": "note"' not in rendered
    assert summary["calibration"]["source_row_counts"]["by_kind"] == {"note": 1}
    assert privacy_gate.scan_paths([output]) == []
