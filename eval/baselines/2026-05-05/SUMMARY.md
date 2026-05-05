# 2026-05-05 Open Resolver Baseline Snapshot

Purpose: snapshot deterministic no-LLM scoring after the open terminology
resolver, closed-world rollup fix, and top-unmapped work queue work.

## Provenance

- Run ID: `17fc2bc0a9cd`
- Command: `uv run python scripts/eval.py run --no-llm --binding-strategy two_pass --matcher-assumption-mode open_world --llm-use-level none --notes "open resolver baseline snapshot; no llm"`
- Eval dataset: `data/curated/eval_seed.json`
- Binding strategy: `two_pass`
- Matcher assumption mode: `open_world`
- LLM use level: `none`
- Cases: 49
- Expected scoring errors: 2 deceased-patient refusals

## Result

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

## Files

- `open_resolver_none_diagnostics.json`
- `open_resolver_surface_work_queue.json`
