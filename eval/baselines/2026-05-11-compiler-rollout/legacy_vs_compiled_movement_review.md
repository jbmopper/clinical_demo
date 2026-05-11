Public-Artifact-Safety: synthetic

# Run Movement Review

- baseline: `500e8f14fa5a`
- comparison: `c467039ca2aa`
- changed cases: 5/49
- changed criteria: 24/1076
- criterion directions: indeterminate_to_determinate=24

## Case Movements

| Pair | Slice | Baseline | Comparison |
|---|---|---:|---:|
| `060e72d3__NCT05713006` | nsclc | indeterminate | fail |
| `3a364909__NCT07362459` | nsclc | indeterminate | fail |
| `83f922a9__NCT05967689` | nsclc | indeterminate | pass_pending_review |
| `9cbf47d8__NCT07362459` | nsclc | indeterminate | fail |
| `e7d52393__NCT04040959` | ckd | indeterminate | fail |

## Criterion Movements

| Pair | # | Kind | Movement | Direction | Compiled predicate | Source |
|---|---:|---|---|---|---|---|
| `060e72d3__NCT05713006` | 17 | condition_absent | indeterminate->fail | indeterminate_to_determinate | condition_presence | Previous malignancies except for any carcinoma in-situ |
| `1293efbb__NCT06964087` | 10 | measurement_threshold | indeterminate->pass | indeterminate_to_determinate | measurement_threshold | Has chronic kidney disease of Stage 2 or higher with eGFR of <90 mL/min/1.73m2. |
| `28db1c55__NCT07297797` | 3 | measurement_threshold | indeterminate->fail | indeterminate_to_determinate | measurement_threshold | At the Screening and Baseline periods, the mean sitting office systolic blood pressure is > 130 m... |
| `38f38890__NCT06217302` | 2 | measurement_threshold | indeterminate->fail | indeterminate_to_determinate | measurement_threshold | eGFR based on serum creatinine and cystatin c (2021 serum creatinine-cystatin C CKD-EPI equation)... |
| `38f38890__NCT06217302` | 27 | condition_absent | indeterminate->fail | indeterminate_to_determinate | trial_exposure | Participation in another interventional clinical research study within 30 days of screening; |
| `38f38890__NCT07489209` | 2 | measurement_threshold | indeterminate->pass | indeterminate_to_determinate | measurement_threshold | Fasting serum LDL-C ≥2.6 mmol/L. |
| `3a364909__NCT07362459` | 32 | condition_absent | indeterminate->fail | indeterminate_to_determinate | trial_exposure | Current participation in another clinical trial, with the exception of observational (non-interve... |
| `3beee40e__NCT06143566` | 3 | measurement_threshold | indeterminate->pass | indeterminate_to_determinate | measurement_threshold | eGFR < 25 |
| `3beee40e__NCT06143566` | 8 | measurement_threshold | indeterminate->pass | indeterminate_to_determinate | measurement_threshold | Creatinine >2.0mg/dL in men and >1.8mg/dL in women |
| `3beee40e__NCT07394114` | 13 | measurement_threshold | indeterminate->pass | indeterminate_to_determinate | measurement_threshold | FPG ≥13.9 mmol/L. |
| `3beee40e__NCT07394114` | 16 | measurement_threshold | indeterminate->pass | indeterminate_to_determinate | measurement_threshold | Fasting triglyceride (TG) >5.6 mmol/L (500 mg/dL). |
| `407ef75b__NCT07297797` | 3 | measurement_threshold | indeterminate->pass | indeterminate_to_determinate | measurement_threshold | At the Screening and Baseline periods, the mean sitting office systolic blood pressure is > 130 m... |
| `9cbf47d8__NCT07362459` | 32 | condition_absent | indeterminate->fail | indeterminate_to_determinate | trial_exposure | Current participation in another clinical trial, with the exception of observational (non-interve... |
| `9e84e569__NCT04602754` | 12 | measurement_threshold | indeterminate->pass | indeterminate_to_determinate | measurement_threshold | Fasting blood glucose > 300 mg/dL; |
| `c2786fee__NCT06217302` | 2 | measurement_threshold | indeterminate->fail | indeterminate_to_determinate | measurement_threshold | eGFR based on serum creatinine and cystatin c (2021 serum creatinine-cystatin C CKD-EPI equation)... |
| `c2786fee__NCT06217302` | 27 | condition_absent | indeterminate->fail | indeterminate_to_determinate | trial_exposure | Participation in another interventional clinical research study within 30 days of screening; |
| `c2786fee__NCT06597006` | 2 | measurement_threshold | indeterminate->fail | indeterminate_to_determinate | measurement_threshold | Fasting LDL-C >130 mg/dL (3.4 mmol/L) at screening |
| `c2786fee__NCT06597006` | 13 | condition_present | indeterminate->pass | indeterminate_to_determinate | condition_presence | Active liver disease defined as any known current infectious, neoplastic, or metabolic pathology... |
| `d02b2ca5__NCT07489209` | 2 | measurement_threshold | indeterminate->fail | indeterminate_to_determinate | measurement_threshold | Fasting serum LDL-C ≥2.6 mmol/L. |
| `d57e867e__NCT06143566` | 3 | measurement_threshold | indeterminate->pass | indeterminate_to_determinate | measurement_threshold | eGFR < 25 |
| `d57e867e__NCT06143566` | 8 | measurement_threshold | indeterminate->fail | indeterminate_to_determinate | measurement_threshold | Creatinine >2.0mg/dL in men and >1.8mg/dL in women |
| `e7d52393__NCT04040959` | 13 | condition_absent | indeterminate->fail | indeterminate_to_determinate | condition_presence | Known malignancy |
| `e7d52393__NCT06568471` | 8 | measurement_threshold | indeterminate->pass | indeterminate_to_determinate | measurement_threshold | Estimated glomerular filtration rate (eGFR)<30 mL/min/1.73m2; |
| `e7d52393__NCT06568471` | 11 | measurement_threshold | indeterminate->pass | indeterminate_to_determinate | measurement_threshold | Poorly controlled Type 1 or Type 2 diabetes mellitus defined as fasting blood glucose ≥11.0 mmol/... |
