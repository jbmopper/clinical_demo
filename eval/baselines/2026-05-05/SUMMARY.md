# 2026-05-05 Open Resolver Baseline Snapshot

Purpose: snapshot deterministic no-LLM scoring after the open terminology
resolver, closed-world rollup fix, and top-unmapped work queue work.

## Provenance

- Eval dataset: `data/curated/eval_seed.json`
- Binding strategy: `two_pass`
- Cases: 49
- Expected scoring errors: 2 deceased-patient refusals

## Mode Comparison

| Mode | Run ID | Case rollup | Criterion verdicts | `unmapped_concept` | Latency |
|---|---:|---:|---:|---:|---:|
| `open_world` / `none` | `17fc2bc0a9cd` | 18 fail / 29 indeterminate / 0 pass / 0 pass_pending_review | 21 fail / 963 indeterminate / 77 pass | 445 (41.9%) | 14.0s |
| `closed_world_eval` / `none` | `5a0e5717803c` | 22 fail / 25 indeterminate / 0 pass / 0 pass_pending_review | 32 fail / 919 indeterminate / 110 pass | 445 (41.9%) | 12.0s |
| `open_world` / `retrieval_only` | `d659d6ff19bb` | 18 fail / 29 indeterminate / 0 pass / 0 pass_pending_review | 21 fail / 963 indeterminate / 77 pass | 445 (41.9%) | 17.0s |

`retrieval_only` changed no verdicts by design; it attaches patient source-row
evidence to reviewer-facing indeterminates.

`closed_world_eval` moved 44 criteria from `no_data` to `ok` relative to
`open_world`, without changing terminology coverage. That is the intended
closed-world assumption toggle.

## Open-World Result

Compared with `eval/baselines/2026-05-04/patient_evidence_none_diagnostics.json`:

- `unmapped_concept`: 445/1061 (41.9%), down 106 criteria / 9.2 pp
- `indeterminate`: 963/1061 (90.8%), down 33 criteria / 1.7 pp
- Registered terminology surfaces: 21/21 resolved
- Unit mismatch: 1 criterion, down from 2

Case rollup remains conservative:

- fail: 18
- indeterminate: 29
- pass: 0
- pass_pending_review: 0

## Remaining Surface Queue

`open_resolver_surface_work_queue.json` classifies the current top unmapped
surfaces. The top queue is now mostly explicit non-mapping work:

- composites requiring split/review: PAH/PH group lists, pregnancy or
  breastfeeding, liver/kidney function tests, mitral/aortic regurgitation
- out of scope for current Synthea/profile model: pulmonary vascular
  resistance, pneumonectomy history, ECOG performance status
- ambiguous: generic blood pressure
- extractor bug: life expectancy as `measurement_threshold`

## Regression Gate

`resolved_surface_watchlist.json` records high-frequency surfaces that should
stay resolved:

- hemoglobin
- platelet count
- BMI / body mass index
- uncontrolled hypertension

Run:

```bash
uv run python scripts/check_terminology_regressions.py \
  --diagnostics eval/baselines/2026-05-05/open_resolver_none_diagnostics.json \
  --resolved-work-queue eval/baselines/2026-05-05/resolved_surface_watchlist.json
```

Expected output:

```text
No resolved terminology surface regressions.
```

The same gate also passes for `open_resolver_closed_world_eval_diagnostics.json`
and `open_resolver_retrieval_only_diagnostics.json`.

## Files

- `open_resolver_none_diagnostics.json`
- `open_resolver_closed_world_eval_diagnostics.json`
- `open_resolver_retrieval_only_diagnostics.json`
- `open_resolver_surface_work_queue.json`
- `resolved_surface_watchlist.json`
