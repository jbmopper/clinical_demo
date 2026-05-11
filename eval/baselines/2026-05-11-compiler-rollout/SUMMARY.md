Public-Artifact-Safety: synthetic

# 2026-05-11 Compiler Rollout Eval Snapshot

Purpose: compare the legacy `matcher_inputs` execution path with opt-in
`compiled_predicates` after the compiler foundation, composite, temporal,
measurement, and medication hardening slices landed.

## Provenance

- Eval dataset: `data/curated/eval_seed.json`
- Binding strategy: `two_pass`
- Resolver execution policy: `cached_only`
- Matcher assumption mode: `closed_world_eval`
- LLM use level: `none`
- Cases: 49
- Scoring errors: 2 deceased-patient refusals
- Code changes in this slice: compiler-side correlatable free-text promotion,
  raw condition-surface lookup preservation, parenthetical measurement alias
  handling, and compiled matcher mood guard for hypothetical/planned criteria.

## Run Comparison

| Execution source | Run ID | Case rollup | Criterion verdicts | `unmapped_concept` | Latency |
|---|---:|---:|---:|---:|---:|
| `matcher_inputs` | `500e8f14fa5a` | 25 fail / 21 indeterminate / 0 pass / 1 pass_pending_review | 48 fail / 913 indeterminate / 115 pass | 316 (29.4%) | 17.9s |
| `compiled_predicates` | `4a3c127baebb` | 29 fail / 16 indeterminate / 0 pass / 2 pass_pending_review | 56 fail / 900 indeterminate / 120 pass | 223 (20.7%) | 16.7s |

The compiled path reduces criterion-level `unmapped_concept` by 93 rows
(-8.7 percentage points) and has no determinate-to-indeterminate criterion
regressions against the legacy path in this run. It adds 13
indeterminate-to-determinate criterion wins from more explicit compiler
execution of mapped condition/measurement/free-text/trial-exposure promotions.
The latest compiler guard also keeps unsafe composite free-text condition
mentions in human review instead of turning them into false closed-world passes.
This is progress, but the compiled path is still not default-ready because
closed-world validation still blocks 43 cases and the deduped compiler-review
queue is still large.

## Case Rollup Movement

Five case-level eligibility results changed:

| Pair | Legacy | Compiled |
|---|---:|---:|
| `060e72d3__NCT05713006` | indeterminate | fail |
| `3a364909__NCT07362459` | indeterminate | fail |
| `83f922a9__NCT05967689` | indeterminate | pass_pending_review |
| `9cbf47d8__NCT07362459` | indeterminate | fail |
| `e7d52393__NCT04040959` | indeterminate | fail |

Layer-1 structured field metrics are unchanged between paths: 89.0% agreement,
98.6% coverage, 8 min-age disagreements, and 1 max-age missing extraction.

## Compiler Readiness

Both runs compile the same 47 non-error cases:

- compiled criteria: 1076
- checkable predicates: 199
- unresolved compiler gaps: 462
- closed-world validation: 4 ok cases, 43 blocking cases
- validation findings: 1151 total, 537 blocking

Unresolved compiler gaps by recommended action:

| Action | Rows |
|---|---:|
| `review_mapping` | 297 |
| `choose_candidate` | 75 |
| `implement_compiler_logic` | 63 |
| `add_unit_mapping` | 17 |
| `review_gap` | 10 |

The compiler-review packet now also has a deduped group artifact. It collapses
462 raw rows to 232 distinct surface/action/policy work items:

| Action | Groups |
|---|---:|
| `review_mapping` | 161 |
| `implement_compiler_logic` | 40 |
| `choose_candidate` | 22 |
| `add_unit_mapping` | 8 |
| `review_gap` | 1 |

The current threshold gate passes only without `--require-compilation`, because
the 2 deceased-patient scorer refusals mean compilation is missing for those
cases before the compiler runs:

```bash
uv run python scripts/check_compiler_diagnostics.py \
  --diagnostics eval/baselines/2026-05-11-compiler-rollout/compiled_predicates_diagnostics.json \
  --max-unresolved-gaps 462 \
  --max-closed-world-blocking-cases 43 \
  --max-closed-world-blocking-findings 537
```

Top remaining unmapped surfaces are still dominated by measurement/event/data-
model gaps: pulmonary vascular resistance, stable background PAH therapy,
history of full pneumonectomy, generic blood pressure, life expectancy, ECOG
performance status, AST, corrected serum calcium, vitamin D3, ambulatory blood
pressure variants, uncontrolled severe arrhythmia, RAAS-inhibitor therapy, and
PH-ILD.

## Patient-Evidence Calibration

`eval/calibration/patient_evidence_labels.json` currently has 22/50 filled
labels, with only 5 labels comparable to this closed-world deterministic mode.

| Run | Comparable | Accuracy | Abstention | Mode skipped |
|---|---:|---:|---:|---:|
| `500e8f14fa5a` | 5/50 | 80.0% | 40.0% | 17 |
| `4a3c127baebb` | 5/50 | 80.0% | 40.0% | 17 |

Interpretation: defer broad human grading until the remaining decisive compiler
movements are reviewed and the compiler gap queue is reduced. The next human
pass should grade a deduped packet, not the raw 462-row compiler review export.

## Files

- `legacy_matcher_inputs_diagnostics.json`
- `compiled_predicates_diagnostics.json`
- `compiled_predicates_compiler_review.json`
- `compiled_predicates_compiler_review_groups.json`
- `patient_evidence_legacy_vs_compiled.json`
- `patient_evidence_legacy_vs_compiled.md`
