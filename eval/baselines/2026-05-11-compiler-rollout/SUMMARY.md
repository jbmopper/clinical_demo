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
  handling, compiled matcher mood guard for hypothetical/planned criteria, and
  reviewed measurement non-mapping/ambiguity decisions in
  `data/terminology/reviewed_mappings.json`.

## Run Comparison

| Execution source | Run ID | Case rollup | Criterion verdicts | `unmapped_concept` | Latency |
|---|---:|---:|---:|---:|---:|
| `matcher_inputs` | `500e8f14fa5a` | 25 fail / 21 indeterminate / 0 pass / 1 pass_pending_review | 48 fail / 913 indeterminate / 115 pass | 316 (29.4%) | 17.9s |
| `compiled_predicates` | `6f857bb7c7bd` | 29 fail / 16 indeterminate / 0 pass / 2 pass_pending_review | 56 fail / 900 indeterminate / 120 pass | 202 (18.8%) | 17.2s |

The compiled path reduces criterion-level `unmapped_concept` by 114 rows
(-10.6 percentage points) and has no determinate-to-indeterminate criterion
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

`legacy_vs_compiled_movement_review.json` and `.md` are the focused review
packet for these changes. They contain 13 decisive criterion movements:
6 measurement thresholds, 4 trial-exposure predicates, and 3 condition
predicates. Seven of the 13 comparison verdicts rely on closed-world absence
(`evidence_under_assumption=true`), so the next reviewer pass should confirm
that those absence-as-negative decisions match the validation contract before
broad grading resumes.

## Compiler Readiness

Both runs compile the same 47 non-error cases:

- compiled criteria: 1076
- checkable predicates: 199
- unresolved compiler gaps: 441
- closed-world validation: 4 ok cases, 43 blocking cases
- validation findings: 1151 total, 537 blocking

Unresolved compiler gaps by recommended action:

| Action | Rows |
|---|---:|
| `review_mapping` | 276 |
| `implement_compiler_logic` | 79 |
| `choose_candidate` | 64 |
| `add_unit_mapping` | 12 |
| `review_gap` | 10 |

The compiler-review packet now also has a deduped group artifact. It collapses
441 raw rows to 229 distinct surface/action/policy work items:

| Action | Groups |
|---|---:|
| `review_mapping` | 157 |
| `implement_compiler_logic` | 43 |
| `choose_candidate` | 21 |
| `add_unit_mapping` | 7 |
| `review_gap` | 1 |

The current threshold gate passes only without `--require-compilation`, because
the 2 deceased-patient scorer refusals mean compilation is missing for those
cases before the compiler runs:

```bash
uv run python scripts/check_compiler_diagnostics.py \
  --diagnostics eval/baselines/2026-05-11-compiler-rollout/compiled_predicates_diagnostics.json \
  --max-unresolved-gaps 441 \
  --max-closed-world-blocking-cases 43 \
  --max-closed-world-blocking-findings 537
```

Top remaining unmapped surfaces are now dominated by event/data-model gaps and
unreviewed measurement variants: stable background PAH therapy, history of full
pneumonectomy, AST, corrected serum calcium, vitamin D3, office/ambulatory
systolic blood-pressure variants, PH-ILD, 6-minute walk distance, oxygen
supplementation, uncontrolled arrhythmia, and RAAS-inhibitor therapy. The
standalone PVR, ECOG, life-expectancy, and generic blood-pressure measurement
surfaces are no longer opaque top-unmapped rows; reviewed registry decisions now
classify them as out-of-scope, extractor-bug, or ambiguous compiler gaps.

## Patient-Evidence Calibration

`eval/calibration/patient_evidence_labels.json` currently has 22/50 filled
labels, with only 5 labels comparable to this closed-world deterministic mode.

| Run | Comparable | Accuracy | Abstention | Mode skipped |
|---|---:|---:|---:|---:|
| `500e8f14fa5a` | 5/50 | 80.0% | 40.0% | 17 |
| `6f857bb7c7bd` | 5/50 | 80.0% | 40.0% | 17 |

Interpretation: defer broad human grading until the remaining decisive compiler
movements are reviewed and the compiler gap queue is reduced. The next human
pass should grade a deduped packet, not the raw 441-row compiler review export.

## Files

- `legacy_matcher_inputs_diagnostics.json`
- `compiled_predicates_diagnostics.json`
- `compiled_predicates_compiler_review.json`
- `compiled_predicates_compiler_review_groups.json`
- `legacy_vs_compiled_movement_review.json`
- `legacy_vs_compiled_movement_review.md`
- `patient_evidence_legacy_vs_compiled.json`
- `patient_evidence_legacy_vs_compiled.md`
