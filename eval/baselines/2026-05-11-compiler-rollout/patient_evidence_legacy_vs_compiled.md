Public-Artifact-Safety: synthetic

# Patient Evidence Calibration Report

## Labels

- path: `eval/calibration/patient_evidence_labels.json`
- filled: 22/50
- usable for verdict metrics: 22/50

## Runs

| Run | LLM use | Comparable | Accuracy | Abstention | Citation agreement | Mode skipped | Retrieved rows | Decisive citations | Eligibility | Adjudicator |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `e8efb7bcce35` | `none` | 5/50 | 80.0% | 40.0% | 0.0% (0/1) | 17 | (none) | (none) | fail=28 / indeterminate=18 / pass_pending_review=1 | 0 calls / $0.0000 |
| `a53dea7638dc` | `none` | 5/50 | 80.0% | 40.0% | 0.0% (0/1) | 17 | (none) | (none) | fail=40 / indeterminate=5 / pass_pending_review=2 | 0 calls / $0.0000 |

## Case Rollup Movement

| Baseline | Comparison | Changed cases | Movements |
|---|---|---:|---|
| `e8efb7bcce35` | `a53dea7638dc` | 13 | indeterminate->fail=12 / indeterminate->pass_pending_review=1 |
