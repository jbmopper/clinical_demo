"""Export the curated seed as a local TrialGPT/TREC-style benchmark scaffold."""

from __future__ import annotations

import argparse
from pathlib import Path

from clinical_demo.api.loaders import load_patient, load_trial
from clinical_demo.evals.patient_evidence import load_patient_evidence_labels_if_exists
from clinical_demo.evals.run import load_dataset
from clinical_demo.evals.trial_benchmark import build_trial_benchmark_dataset

DEFAULT_SEED = Path("data/curated/eval_seed.json")
DEFAULT_LABELS = Path("eval/calibration/patient_evidence_labels.json")
DEFAULT_OUTPUT = Path("eval/benchmarks/local_trialgpt_trec_seed.json")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_SEED)
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    cases = load_dataset(args.dataset)
    labels = load_patient_evidence_labels_if_exists(args.labels)
    benchmark = build_trial_benchmark_dataset(
        cases,
        load_patient=load_patient,
        load_trial=load_trial,
        patient_evidence_labels=labels,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(benchmark.model_dump_json(indent=2) + "\n")
    print(
        f"wrote {len(benchmark.queries)} patient query/queries and "
        f"{sum(len(query.candidates) for query in benchmark.queries)} candidate trial(s) "
        f"to {args.output}"
    )
    print(f"criterion cases: {len(benchmark.criterion_cases)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
