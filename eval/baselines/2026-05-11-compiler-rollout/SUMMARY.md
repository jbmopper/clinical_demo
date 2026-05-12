Public-Artifact-Safety: synthetic

# 2026-05-11 Compiler Rollout Eval Snapshot

Updated 2026-05-12 after the reviewed condition/event, medication
registry-closure, and cache-independent terminology-closure slices.

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
  handling, compiled matcher mood guard for hypothetical/planned criteria,
  reviewed measurement mapping/non-mapping/ambiguity decisions, reviewed
  condition/event non-mapping decisions, a CKD stage 3-or-4 reviewed
  ConceptSet, reviewed medication RxNorm patient-vocabulary anchors, reviewed
  lipid-lowering/bisphosphonate/RAAS class expansions, and reviewed nonmapped
  medication gap classifications in `data/terminology/`. The cache-independent
  closure pass also promotes 35 warmed-cache-only condition/medication surfaces
  into reviewed registry rows and lets reviewed rows carry inline code sets
  instead of requiring one Python constant per surface.

## Run Comparison

| Execution source | Run ID | Case rollup | Criterion verdicts | `unmapped_concept` | Latency |
|---|---:|---:|---:|---:|---:|
| `matcher_inputs` | `e8efb7bcce35` | 28 fail / 18 indeterminate / 0 pass / 1 pass_pending_review | 57 fail / 894 indeterminate / 125 pass | 317 (29.5%) | 18.1s |
| `compiled_predicates` | `752bd67507c6` | 30 fail / 15 indeterminate / 0 pass / 2 pass_pending_review | 60 fail / 887 indeterminate / 129 pass | 115 (10.7%) | 22.2s |

The compiled path reduces criterion-level `unmapped_concept` by 202 rows
(-18.8 percentage points) against the same-run legacy path and moves the
compiled snapshot from 122 to 115 `unmapped_concept` rows versus the previous
condition/event-only snapshot. It adds 12 indeterminate-to-determinate
criterion wins from more explicit compiler execution of mapped condition,
measurement, trial-exposure, and medication exposure promotions, including
RAAS, statin, and lipid-lowering criteria. It also introduces 5
determinate-to-indeterminate criterion movements where broad parent concepts
such as cardiovascular, endocrine, and psychiatric disease now require explicit
descendant expansion instead of trusting unsafe warmed-cache exact-code
matches. This is progress, but the compiled path is still not default-ready
because closed-world validation still blocks 43 cases and the deduped
compiler-review queue is still large.

## Case Rollup Movement

Three case-level eligibility results changed:

| Pair | Legacy | Compiled |
|---|---:|---:|
| `3a364909__NCT07362459` | indeterminate | fail |
| `83f922a9__NCT05967689` | indeterminate | pass_pending_review |
| `9cbf47d8__NCT07362459` | indeterminate | fail |

Layer-1 structured field metrics are unchanged between paths: 89.0% agreement,
98.6% coverage, 8 min-age disagreements, and 1 max-age missing extraction.

`legacy_vs_compiled_movement_review.json` and `.md` are the focused review
packet for these changes. They contain 17 decisive criterion movements and 225
reason-code-only changes. The decisive movements include medication-exposure
wins for RAAS blockers, stable lipid-lowering treatment, and reviewed class
closure, plus measurement and trial-exposure movements from earlier compiler
slices. Five decisive movements are safety-preserving
determinate-to-indeterminate changes for broad parent concepts that need
descendant expansion. Closed-world absence-dependent verdicts should still be
reviewed as a group so the absence-as-negative decisions match the validation
contract.

## Compiler Readiness

Both runs compile the same 47 non-error cases:

- compiled criteria: 1076
- checkable predicates: 216
- unresolved compiler gaps: 369
- closed-world validation: 4 ok cases, 43 blocking cases
- validation findings: 1121 total, 507 blocking

Unresolved compiler gaps by recommended action:

| Action | Rows |
|---|---:|
| `choose_candidate` | 13 |
| `implement_compiler_logic` | 193 |
| `review_gap` | 22 |
| `review_mapping` | 141 |

The compiler-review packet now also has a deduped group artifact. It collapses
369 raw rows to 198 distinct surface/action/policy work items:

| Action | Groups |
|---|---:|
| `choose_candidate` | 6 |
| `implement_compiler_logic` | 90 |
| `review_gap` | 4 |
| `review_mapping` | 98 |

The current threshold gate passes only without `--require-compilation`, because
the 2 deceased-patient scorer refusals mean compilation is missing for those
cases before the compiler runs:

```bash
uv run python scripts/check_compiler_diagnostics.py \
  --diagnostics eval/baselines/2026-05-11-compiler-rollout/compiled_predicates_diagnostics.json \
  --max-unresolved-gaps 369 \
  --max-closed-world-blocking-cases 43 \
  --max-closed-world-blocking-findings 507
```

Top remaining unmapped surfaces are now a thinner condition/event/medication
tail with frequency 2 at the top: uncontrolled severe arrhythmia, other
diseases requiring RAAS inhibitor therapy, PH-ILD variants, pulmonary
hypertension not otherwise considered to be PH-ILD, clinically significant
left-sided heart disease, current active malignancy, congenital heart disease,
concomitant disease with life expectancy under 6 months, liver dysfunction,
worse than mild untreated sleep apnea, severe hypoglycemia event counts,
primary renal glycosuria, illicit drug abuse, heavy alcohol use, and
study-requirement adherence phrases. The reviewed lab, condition/event, and
medication tranches removed the previous higher-frequency opaque buckets by
either mapping them or classifying them as explicit compiler gaps.

A pre-fix fresh-cache probe on 2026-05-12 regressed to 424 unresolved compiler
gaps and 156 compiled `unmapped_concept` rows. After promoting the 35
warmed-cache-only groups into reviewed artifacts, fresh-cache compiled
diagnostics now match the warmed-cache snapshot on opaque `unmapped_concept`
(115 rows) and case rollup (30 fail / 15 indeterminate / 2
pass_pending_review). The remaining gap delta is explicit: broad parent disease
concepts now produce typed descendant-expansion gaps rather than unsafe
cache-only exact matches.

## Patient-Evidence Calibration

`eval/calibration/patient_evidence_labels.json` currently has 22/50 filled
labels, with only 5 labels comparable to this closed-world deterministic mode.

| Run | Comparable | Accuracy | Abstention | Mode skipped |
|---|---:|---:|---:|---:|
| `e8efb7bcce35` | 5/50 | 80.0% | 40.0% | 17 |
| `752bd67507c6` | 5/50 | 80.0% | 40.0% | 17 |

Interpretation: defer broad human grading until the remaining decisive compiler
movements are reviewed and the compiler gap queue is reduced. The next human
pass should grade the 198-group deduped packet, not the raw 369-row compiler
review export.

## Files

- `legacy_matcher_inputs_diagnostics.json`
- `compiled_predicates_diagnostics.json`
- `compiled_predicates_compiler_review.json`
- `compiled_predicates_compiler_review_groups.json`
- `legacy_vs_compiled_movement_review.json`
- `legacy_vs_compiled_movement_review.md`
- `patient_evidence_legacy_vs_compiled.json`
- `patient_evidence_legacy_vs_compiled.md`
