Public-Artifact-Safety: synthetic

# Patient Evidence Calibration Report

## Labels

- path: `eval/calibration/patient_evidence_labels.json`
- filled: 22/50
- usable for verdict metrics: 22/50

## Runs

| Run | LLM use | Comparable | Accuracy | Abstention | Citation agreement | Mode skipped | Retrieved rows | Decisive citations | Eligibility | Adjudicator |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `6a88853d0199` | `none` | 5/50 | 80.0% | 40.0% | 0.0% (0/1) | 17 | (none) | (none) | fail=26 / indeterminate=20 / pass_pending_review=1 | 0 calls / $0.0000 |
| `697521739b59` | `none` | 5/50 | 80.0% | 40.0% | 0.0% (0/1) | 17 | (none) | (none) | fail=30 / indeterminate=15 / pass_pending_review=2 | 0 calls / $0.0000 |

## Case Rollup Movement

| Baseline | Comparison | Changed cases | Movements |
|---|---|---:|---|
| `6a88853d0199` | `697521739b59` | 5 | indeterminate->fail=4 / indeterminate->pass_pending_review=1 |
