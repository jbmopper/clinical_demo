"""Build a patient-side FHIR evidence calibration packet.

This creates the project-specific analogue to Chia for matcher
adjudication. Rows are candidates for human review: each contains one
criterion, matcher output, optional Layer-3 judge output, and stable
patient/trial source-row ids that reviewers can cite in labels.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from clinical_demo.api.loaders import load_patient, load_trial
from clinical_demo.evals.layer_three import JudgeTarget, build_source_context
from clinical_demo.evals.patient_evidence import (
    PatientEvidenceHumanLabel,
    PatientEvidenceScope,
    build_patient_evidence_rows,
    load_layer_three_report,
    load_patient_evidence_labels_if_exists,
    save_patient_evidence_labels,
    save_patient_evidence_rows,
    select_patient_evidence_targets,
    summarize_patient_evidence_rows,
)
from clinical_demo.evals.store import load_run, open_store
from clinical_demo.matcher import DEFAULT_MATCHER_ASSUMPTION_MODE

DEFAULT_DB = Path("eval/runs.sqlite")
DEFAULT_JUDGE_REPORT = Path("eval/baselines/2026-04-30/layer3_judge_calibrated.json")
DEFAULT_LABELS = Path("eval/calibration/patient_evidence_labels.json")
DEFAULT_OUTPUT = Path("eval/calibration/patient_evidence_candidates.json")
DEFAULT_PUBLIC_SUMMARY_OUTPUT = Path("eval/baselines/YYYY-MM-DD/composite_v06_public_summary.json")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--judge-report", type=Path, default=DEFAULT_JUDGE_REPORT)
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int, default=60)
    parser.add_argument(
        "--scope",
        choices=["cardiometabolic_core", "all"],
        default="cardiometabolic_core",
        help="Filter candidate targets before packet selection.",
    )
    parser.add_argument(
        "--prune-labels",
        action="store_true",
        help="Rewrite the label template to exactly the selected targets, preserving matching labels.",
    )
    args = parser.parse_args()
    scope: PatientEvidenceScope = args.scope

    with open_store(args.db) as store:
        run = load_run(store, args.run_id)
    judge_report = load_layer_three_report(args.judge_report)
    existing_labels = load_patient_evidence_labels_if_exists(args.labels)

    targets = select_patient_evidence_targets(
        run,
        judge_report=judge_report,
        limit=args.limit,
        scope=scope,
        preserve_keys=_reviewed_label_keys(existing_labels),
    )
    labels = _labels_for_targets(targets, existing_labels)
    if args.prune_labels or not existing_labels:
        save_patient_evidence_labels(args.labels, labels)

    source_contexts = {}
    for target in targets:
        if target.pair_id in source_contexts:
            continue
        source_contexts[target.pair_id] = build_source_context(
            load_patient(target.patient_id),
            load_trial(target.nct_id),
            max_conditions=12,
            max_observations=15,
            max_medications=8,
        )

    rows = build_patient_evidence_rows(
        targets,
        source_contexts=source_contexts,
        judge_report=judge_report,
        existing_labels=labels,
    )
    save_patient_evidence_rows(args.output, rows)

    print(
        f"wrote {len(rows)} patient-evidence calibration rows to {args.output} (scope={args.scope})"
    )
    print(f"label template: {args.labels}")
    print("private calibration packets are local-only unless exported as a public summary.")
    print("safe public summary command:")
    print(
        "  "
        + public_summary_export_command(
            candidates=args.output,
            labels=args.labels,
            diagnostics=None,
            output=DEFAULT_PUBLIC_SUMMARY_OUTPUT,
        )
    )
    print(json.dumps(summarize_patient_evidence_rows(rows), indent=2, sort_keys=True))


def _labels_for_targets(
    targets: list[JudgeTarget],
    existing_labels: list[PatientEvidenceHumanLabel],
) -> list[PatientEvidenceHumanLabel]:
    existing = {(label.pair_id, label.criterion_index): label for label in existing_labels}
    labels = []
    for target in targets:
        labels.append(
            existing.get(
                (target.pair_id, target.criterion_index),
                PatientEvidenceHumanLabel(
                    pair_id=target.pair_id,
                    criterion_index=target.criterion_index,
                ),
            )
        )
    return labels


def _reviewed_label_keys(
    labels: list[PatientEvidenceHumanLabel],
) -> set[tuple[str, int]]:
    return {(label.pair_id, label.criterion_index) for label in labels if _label_has_review(label)}


def _label_has_review(label: PatientEvidenceHumanLabel) -> bool:
    return (
        label.label is not None
        or label.expected_matcher_verdict is not None
        or bool(label.cited_source_row_ids)
        or bool(label.rationale.strip())
        or label.reviewer is not None
        or label.matcher_assumption_mode != DEFAULT_MATCHER_ASSUMPTION_MODE
    )


def public_summary_export_command(
    *,
    candidates: Path,
    labels: Path,
    diagnostics: Path | None,
    output: Path,
) -> str:
    """Return the reproducible public-summary export command for a private packet."""

    parts = [
        "uv",
        "run",
        "python",
        "scripts/export_patient_evidence_public_summary.py",
        "--candidates",
        str(candidates),
        "--labels",
        str(labels),
    ]
    if diagnostics is not None:
        parts.extend(["--diagnostics", str(diagnostics)])
    parts.extend(["--output", str(output)])
    return " ".join(parts)


if __name__ == "__main__":
    main()
