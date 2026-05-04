# 2026-05-04 Patient Evidence Mode Rerun

Purpose: compare `llm_use_level` modes after the PLAN 2.15 bounded
patient-evidence adjudicator and PLAN 2.16 deterministic unit pass.

## Provenance

- Extractor cache refresh: `uv run python scripts/extract_criteria.py --limit 0 --force`
- Extractor prompt/model: extractor-v0.5 / `gpt-4o-mini-2024-07-18`
- Refreshed curated trials: 30
- Extracted criteria: 641
- Extractor cost: `$0.0870`
- Extractor wall time: 2109.6s
- Eval dataset: `data/curated/eval_seed.json`
- Binding strategy: `two_pass`
- Matcher assumption mode: `open_world`

## Mode Comparison

| Mode | Run ID | Case rollup | Criterion verdicts | Retrieval effect | Latency |
|---|---|---:|---:|---:|---:|
| `none` | `8e718e87c3fa` | 18 fail / 31 indeterminate / 0 pass | 23 fail / 996 indeterminate / 58 pass | no retrieved rows | 25.5s total |
| `retrieval_only` | `dd8a939ea584` | 18 fail / 31 indeterminate / 0 pass | 23 fail / 996 indeterminate / 58 pass | 627 unresolved verdicts gained retrieved source-row evidence | 20.7s total |
| `bounded_adjudication` | `4458ecd2199a` | 27 fail / 22 indeterminate / 0 pass | 38 fail / 942 indeterminate / 97 pass | 627 unresolved verdicts adjudicated over retrieved rows | 827.7s total |

`retrieval_only` changed no verdicts by design. It is the cheap reviewer
evidence mode.

`bounded_adjudication` changed 624 criterion-level verdict/reason pairs
relative to deterministic-only. Most of that movement clarified conservative
indeterminates into `no_data`; decisive movement was 39 criteria from
indeterminate -> pass and 15 criteria from indeterminate -> fail. Top-level
movement was 9 cases from indeterminate -> fail and 0 cases -> pass.

## Calibration Status

`eval/calibration/patient_evidence_labels.json` has 60 rows and 0 filled
labels. Therefore this snapshot is an empirical mode comparison, not a
calibrated quality result. Phase 3 routing economics should wait for:

- filled patient-evidence labels,
- adjudicator token/cost metadata persisted into eval rows,
- a calibrated quality score that distinguishes useful resolved cases from
  merely defensible conservative indeterminates.

## Files

- `patient_evidence_none_report.json`
- `patient_evidence_none_diagnostics.json`
- `patient_evidence_retrieval_only_report.json`
- `patient_evidence_retrieval_only_diagnostics.json`
- `patient_evidence_bounded_adjudication_report.json`
- `patient_evidence_bounded_adjudication_diagnostics.json`
- `patient_evidence_modes_summary.json`
