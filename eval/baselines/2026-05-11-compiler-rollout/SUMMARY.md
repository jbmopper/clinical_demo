Public-Artifact-Safety: synthetic

# 2026-05-11 Compiler Rollout Eval Snapshot

Updated 2026-05-12 after the reviewed condition/event, medication
registry-closure, cache-independent terminology-closure, reviewed
descendant-expansion, condition/event decomposition, qualifier/top-gap review,
final opaque-unmapped registry slices, and blood-pressure threshold
decomposition.

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
  instead of requiring one Python constant per surface. The descendant-expansion
  pass adds `reviewed_expansions.json` so broad endocrine, psychiatric, and
  cardiovascular parent concepts expand without warmed-cache exact parent hits.
  The condition/event decomposition pass adds PH-ILD, cardiovascular event-list,
  congenital heart disease, HoFH, and long-tail reviewed non-mapping decisions.
  The qualifier/top-gap pass adds generic typed gaps for contraindication,
  life-expectancy, study-compliance, qualified arrhythmia, and NYHA functional
  class phrases, plus reviewed rows for type 2 DM and high-frequency procedure,
  genomic, oncology, and cpcPH non-atomic surfaces. The final opaque-gap pass
  adds GLP-1/semaglutide, amylin, calcitonin, diabetes/HF/pregnancy variants,
  and singleton oncology/genomic/procedure/status classifications so the
  compiler-review queue no longer has `review_mapping` groups. The BP
  threshold pass decomposes explicit systolic/diastolic phrases and generic
  `BP >160/100` / `BP <140/90` shorthand, including `SBP`/`DBP` pairs, into
  systolic and diastolic LOINC-backed measurement predicates.

## Run Comparison

| Execution source | Run ID | Case rollup | Criterion verdicts | `unmapped_concept` | Latency |
|---|---:|---:|---:|---:|---:|
| `matcher_inputs` | `e8efb7bcce35` | 28 fail / 18 indeterminate / 0 pass / 1 pass_pending_review | 57 fail / 894 indeterminate / 125 pass | 317 (29.5%) | 18.1s |
| `compiled_predicates` | `3d05a47d0af3` | 36 fail / 9 indeterminate / 0 pass / 2 pass_pending_review | 78 fail / 840 indeterminate / 158 pass | 0 (0.0%) | 23.0s |

The compiled path reduces criterion-level `unmapped_concept` by 317 rows
(-29.5 percentage points) against the same-run legacy path and moves the
compiled snapshot from 37 to 0 `unmapped_concept` rows versus the previous
qualifier/top-gap snapshot. It adds 54 indeterminate-to-determinate
criterion wins from more explicit compiler execution of mapped condition,
measurement, trial-exposure, medication exposure, PH-ILD, HoFH, congenital heart
disease, cardiovascular event-list promotions, GLP-1 class closure, and
diabetes/HF/pregnancy variant mapping, plus blood-pressure threshold
decomposition. The prior broad-parent
determinate-to-indeterminate movements are gone:
endocrine, psychiatric, and cardiovascular parent mappings now expand through
committed reviewed closures instead of warmed-cache exact-code behavior. This is
progress, but the compiled path is still not default-ready because closed-world
validation still blocks 43 cases and the deduped compiler-review queue is still
large.

## Case Rollup Movement

Nine case-level eligibility results changed:

| Pair | Legacy | Compiled |
|---|---:|---:|
| `2e555528__NCT06475781` | indeterminate | fail |
| `3a364909__NCT07362459` | indeterminate | fail |
| `407ef75b__NCT06941441` | indeterminate | fail |
| `56cfe6a5__NCT06475781` | indeterminate | fail |
| `56cfe6a5__NCT06941441` | indeterminate | fail |
| `83f922a9__NCT05967689` | indeterminate | pass_pending_review |
| `9cbf47d8__NCT07362459` | indeterminate | fail |
| `a06bce31__NCT06941441` | indeterminate | fail |
| `e7d52393__NCT06568471` | indeterminate | fail |

Layer-1 structured field metrics are unchanged between paths: 89.0% agreement,
98.6% coverage, 8 min-age disagreements, and 1 max-age missing extraction.

`legacy_vs_compiled_movement_review.json` and `.md` are the focused review
packet for these changes. They contain 55 decisive criterion movements and 306
reason-code-only changes. The decisive movements include medication-exposure
wins for RAAS blockers, stable lipid-lowering treatment, and reviewed class
closure, plus GLP-1 member closure, diabetes/HF/pregnancy variants,
measurement, trial-exposure, PH-ILD, cardiovascular event-list, congenital heart
disease, HoFH, and BP threshold movements. Closed-world absence-dependent
verdicts should still be reviewed as a group so the absence-as-negative
decisions match the validation contract.

## Compiler Readiness

Both runs compile the same 47 non-error cases:

- compiled criteria: 1076
- checkable predicates: 311
- unresolved compiler gaps: 342
- closed-world validation: 4 ok cases, 43 blocking cases
- validation findings: 1046 total, 449 blocking

Unresolved compiler gaps by recommended action:

| Action | Rows |
|---|---:|
| `choose_candidate` | 8 |
| `implement_compiler_logic` | 312 |
| `review_gap` | 22 |

The compiler-review packet now also has a deduped group artifact. It collapses
342 raw rows to 184 distinct surface/action/policy work items:

| Action | Groups |
|---|---:|
| `choose_candidate` | 5 |
| `implement_compiler_logic` | 175 |
| `review_gap` | 4 |

The current threshold gate passes only without `--require-compilation`, because
the 2 deceased-patient scorer refusals mean compilation is missing for those
cases before the compiler runs:

```bash
uv run python scripts/check_compiler_diagnostics.py \
  --diagnostics eval/baselines/2026-05-11-compiler-rollout/compiled_predicates_diagnostics.json \
  --max-unresolved-gaps 342 \
  --max-closed-world-blocking-cases 43 \
  --max-closed-world-blocking-findings 449 \
  --max-gap-kind unmapped_concept=0 \
  --max-gap-kind unsupported_predicate=312 \
  --max-gap-kind ambiguous_mapping=8 \
  --max-gap-kind insufficient_source=22
```

There are no remaining `review_mapping` groups. The remaining queue is compiler
work: unsupported predicate translation, ambiguous candidate choice, and
insufficient-source review. Formerly opaque singleton concepts (NSCLC,
curative-intent treatment, ALK rearrangements, measurable disease, pregnancy
test variants, active hepatitis/HIV/TB infection, breastfeeding, other diabetes
types, xenotransplant logistics/crossmatch phrases, anticoagulation therapy,
psychiatric disorder variants, hepatic function, pancreatic disease/insulin
deficiency, and similar long-tail surfaces) now map or emit explicit
`unsupported_predicate` classifications.

A pre-fix fresh-cache probe on 2026-05-12 regressed to 424 unresolved compiler
gaps and 156 compiled `unmapped_concept` rows. After promoting the 35
warmed-cache-only groups into reviewed artifacts, fresh-cache compiled
diagnostics matched the warmed-cache snapshot on opaque `unmapped_concept`
(115 rows) and case rollup (30 fail / 15 indeterminate / 2
pass_pending_review). The reviewed descendant-expansion slice then removed the
five explicit broad-parent expansion gaps for endocrine, psychiatric, and
cardiovascular disease while preserving the same case rollup. The
condition/event decomposition and long-tail terminology slice then moved the
compiled snapshot to 79 opaque `unmapped_concept` rows, 354 unresolved compiler
gaps, and a 33 fail / 12 indeterminate / 2 pass_pending_review case rollup. The
qualifier/top-gap slice then moved opaque `unmapped_concept` to 37 rows while
preserving the same case rollup; unresolved compiler gaps are now 365 because
more rows are explicitly typed as unsupported compiler work instead of unknown
terminology. The final opaque-gap registry pass then moved
`unmapped_concept` to 0, reduced unresolved compiler gaps to 354, preserved the
same case rollup, and converted the deduped queue to compiler implementation
work with no `review_mapping` groups. The BP threshold-decomposition slice then
moved explicit/generic BP clauses into executable measurement compounds,
reduced unresolved compiler gaps to 342, increased checkable predicates to 311,
and moved the case rollup to 36 fail / 9 indeterminate / 2
pass_pending_review.

## Patient-Evidence Calibration

`eval/calibration/patient_evidence_labels.json` currently has 22/50 filled
labels, with only 5 labels comparable to this closed-world deterministic mode.

| Run | Comparable | Accuracy | Abstention | Mode skipped |
|---|---:|---:|---:|---:|
| `e8efb7bcce35` | 5/50 | 80.0% | 40.0% | 17 |
| `3d05a47d0af3` | 5/50 | 80.0% | 40.0% | 17 |

Interpretation: defer broad human grading until the remaining decisive compiler
movements are reviewed and the compiler gap queue is reduced. The next human
pass should grade targeted decisive movements plus the highest-priority
compiler-logic groups, not a raw terminology-mapping packet.

## Files

- `legacy_matcher_inputs_diagnostics.json`
- `compiled_predicates_diagnostics.json`
- `compiled_predicates_compiler_review.json`
- `compiled_predicates_compiler_review_groups.json`
- `legacy_vs_compiled_movement_review.json`
- `legacy_vs_compiled_movement_review.md`
- `patient_evidence_legacy_vs_compiled.json`
- `patient_evidence_legacy_vs_compiled.md`
