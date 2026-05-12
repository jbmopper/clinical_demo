Public-Artifact-Safety: synthetic

# Patient Evidence Calibration Report

## Labels

- path: `eval/calibration/patient_evidence_labels.json`
- filled: 22/50
- usable for verdict metrics: 22/50

## Runs

| Run | LLM use | Comparable | Accuracy | Abstention | Citation agreement | Mode skipped | Retrieved rows | Decisive citations | Eligibility | Adjudicator |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `500e8f14fa5a` | `none` | 5/50 | 80.0% | 40.0% | 0.0% (0/1) | 17 | (none) | (none) | fail=25 / indeterminate=21 / pass_pending_review=1 | 0 calls / $0.0000 |
| `2802063cfb09` | `none` | 5/50 | 80.0% | 40.0% | 0.0% (0/1) | 17 | (none) | (none) | fail=30 / indeterminate=15 / pass_pending_review=2 | 0 calls / $0.0000 |

## Case Rollup Movement

| Baseline | Comparison | Changed cases | Movements |
|---|---|---:|---|
| `500e8f14fa5a` | `2802063cfb09` | 6 | indeterminate->fail=5 / indeterminate->pass_pending_review=1 |
