# 2026-05-04-2.19 — PLAN 2.19 closed-world matcher semantics + open-world bug fix

Two side-by-side runs against the same eval seed, post matcher
v0.2 (PLAN 2.19). The two runs differ only in
`matcher_assumption_mode`; everything else is identical.

| Run | Mode | Notes |
|---|---|---|
| `7ad02d2ce814` | `open_world` | post bug fix; honest absence semantics |
| `505d88763f00` | `closed_world_eval` | absence-as-negative for cond / med / temporal |

Dataset: `data/curated/eval_seed.json` (49 cases, 2 deceased-patient
refusals). Criteria: 1061. `binding_strategy=two_pass`,
`llm_use_level=none`, no critic. Baselines were captured immediately
after the matcher was bumped to v0.2; the previous open-world
baseline (`43c765d1dbcc`, 2026-05-04-umls) was produced by matcher
v0.1 and the silent-flip bug — it is no longer comparable for
verdict mix and should not be used as a regression target.

## Verdict mix (criterion-level, n=1061)

| Verdict / Reason | open_world | closed_world_eval |
|---|---:|---:|
| `pass` | 77 | 110 |
| `fail` | 21 | 32 |
| `indeterminate` | 963 (90.8%) | 919 (86.6%) |
| `unmapped_concept` | 445 (41.9%) | 445 (41.9%) |
| `human_review_required` | 413 | 413 |
| `ok` | 98 | 142 |
| `no_data` | 62 | 18 |
| `ambiguous_criterion` | 18 | 18 |
| `unsupported_mood` | 16 | 16 |
| `unit_mismatch` | 1 | 1 |
| `extractor_invariant_violation` | 8 | 8 |

The 44-criterion swing (`no_data` 62 → 18 in closed-world; `ok` 98 →
142) is exactly the resolved-but-absent condition / medication /
temporal verdicts: open-world surfaces them as
`indeterminate(no_data)`, closed-world commits them to `pass` /
`fail` via polarity. Lab `no_data` rows are stable across modes
(labs are deliberately not on the closed-world whitelist —
clinically a missing observation is not the same as a normal one).

## Eligibility rollup (case-level, n=47 scored / 2 deceased)

| Rollup | open_world | closed_world_eval |
|---|---:|---:|
| `fail` | 18 | 22 |
| `indeterminate` | 29 | 25 |
| `pass_pending_review` | 0 | 0 |
| `pass` | 0 | 0 |

`pass_pending_review` is a new state (PLAN 2.19): "no fails, every
non-pass criterion is `human_review_required`." It does not fire on
the current eval seed because every case has at least one
non-free-text indeterminate (typically `unmapped_concept` on a
composite phrase, or `no_data` on a missing lab observation). It
will start firing once we either (a) push the unmapped-concept
floor below the per-case-presence threshold (Phase 3 LLM-assisted
disambiguation) or (b) round-trip free-text criteria through an
LLM classifier (also Phase 3 in the user's "calibration phases"
framing).

## What changed vs the previous baseline

The 2026-05-04-umls baseline (matcher v0.1) cannot be diffed
directly — it conflated two behaviors (closed-world semantics +
silent polarity-flip on raw `fail`). The closed-world v0.2 numbers
above match the v0.1 numbers exactly (`pass`=110, `fail`=32,
`indeterminate`=919), confirming that v0.2 closed-world is a
faithful re-implementation of the prior implicit behavior. The new
open-world numbers are the honest mode; we will use them as the
default review-friendly baseline going forward.

## Note on case-level pass rate

Both modes still show 0 case-level `pass`. With 1061 criteria
spread across 47 cases (~22.6 / case) and 41.9% of criteria still
landing on `unmapped_concept`, every case has at least one
unresolved structured criterion. Closing the unmapped-concept gap
is the Phase 3 conversation: introduce LLM disambiguation /
research helpers in measured phases per the user's
calibration-scaffold plan, score each phase, and write up the
economic curve.
