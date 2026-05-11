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
  reviewed measurement mapping/non-mapping/ambiguity decisions in
  `data/terminology/reviewed_mappings.json`.

## Run Comparison

| Execution source | Run ID | Case rollup | Criterion verdicts | `unmapped_concept` | Latency |
|---|---:|---:|---:|---:|---:|
| `matcher_inputs` | `500e8f14fa5a` | 25 fail / 21 indeterminate / 0 pass / 1 pass_pending_review | 48 fail / 913 indeterminate / 115 pass | 316 (29.4%) | 17.9s |
| `compiled_predicates` | `dba692258184` | 29 fail / 16 indeterminate / 0 pass / 2 pass_pending_review | 60 fail / 889 indeterminate / 127 pass | 164 (15.2%) | 17.4s |

The compiled path reduces criterion-level `unmapped_concept` by 152 rows
(-14.2 percentage points) and has no determinate-to-indeterminate criterion
regressions against the legacy path in this run. It adds 24
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
packet for these changes. They contain 24 decisive criterion movements:
17 measurement thresholds, 4 trial-exposure predicates, and 3 condition
predicates. Seven of the 24 comparison verdicts rely on closed-world absence
(`evidence_under_assumption=true`), so the next reviewer pass should confirm
that those absence-as-negative decisions match the validation contract. The 11
additional measurement movements from the reviewed lab tranche should be
reviewed as a group, especially where extracted prose had fasting/modality or
sex-specific threshold details that are not independently modeled yet.

## Compiler Readiness

Both runs compile the same 47 non-error cases:

- compiled criteria: 1076
- checkable predicates: 212
- unresolved compiler gaps: 398
- closed-world validation: 4 ok cases, 43 blocking cases
- validation findings: 1125 total, 511 blocking

Unresolved compiler gaps by recommended action:

| Action | Rows |
|---|---:|
| `review_mapping` | 238 |
| `implement_compiler_logic` | 100 |
| `choose_candidate` | 35 |
| `review_gap` | 22 |
| `add_unit_mapping` | 3 |

The compiler-review packet now also has a deduped group artifact. It collapses
398 raw rows to 211 distinct surface/action/policy work items:

| Action | Groups |
|---|---:|
| `review_mapping` | 136 |
| `implement_compiler_logic` | 54 |
| `choose_candidate` | 15 |
| `review_gap` | 4 |
| `add_unit_mapping` | 2 |

The current threshold gate passes only without `--require-compilation`, because
the 2 deceased-patient scorer refusals mean compilation is missing for those
cases before the compiler runs:

```bash
uv run python scripts/check_compiler_diagnostics.py \
  --diagnostics eval/baselines/2026-05-11-compiler-rollout/compiled_predicates_diagnostics.json \
  --max-unresolved-gaps 398 \
  --max-closed-world-blocking-cases 43 \
  --max-closed-world-blocking-findings 511
```

Top remaining unmapped surfaces are now dominated by event/data-model gaps and
a smaller measurement tail: stable background PAH therapy, history of full
pneumonectomy, PH-ILD variants, severe hypoglycemia event counts, beta-
hydroxybutyrate surfaces, uncontrolled arrhythmia, RAAS-inhibitor therapy, and
oncology/cardiopulmonary history concepts. The reviewed lab tranche removed AST,
corrected calcium, vitamin D3, systolic-BP variants, 6-minute walk distance,
oxygen supplementation, creatinine, glucose/FPG, LDL-C, triglycerides, ANC, and
bilirubin from the opaque top-unmapped bucket by either mapping them or
classifying them as explicit compiler gaps.

## Patient-Evidence Calibration

`eval/calibration/patient_evidence_labels.json` currently has 22/50 filled
labels, with only 5 labels comparable to this closed-world deterministic mode.

| Run | Comparable | Accuracy | Abstention | Mode skipped |
|---|---:|---:|---:|---:|
| `500e8f14fa5a` | 5/50 | 80.0% | 40.0% | 17 |
| `dba692258184` | 5/50 | 80.0% | 40.0% | 17 |

Interpretation: defer broad human grading until the remaining decisive compiler
movements are reviewed and the compiler gap queue is reduced. The next human
pass should grade a deduped packet, not the raw 398-row compiler review export.

## Files

- `legacy_matcher_inputs_diagnostics.json`
- `compiled_predicates_diagnostics.json`
- `compiled_predicates_compiler_review.json`
- `compiled_predicates_compiler_review_groups.json`
- `legacy_vs_compiled_movement_review.json`
- `legacy_vs_compiled_movement_review.md`
- `patient_evidence_legacy_vs_compiled.json`
- `patient_evidence_legacy_vs_compiled.md`
