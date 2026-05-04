# 2026-05-04-umls — Open terminology resolver with UMLS/LOINC search

**Run:** `43c765d1dbcc`
**Notes:** `d73-umls-open-search-smoke; binding_strategy=two_pass; matcher_assumption_mode=open_world; llm_use_level=none`
**Cases:** 49 (2 skipped: deceased-patient safety guards).
**Criteria:** 1061.

## Delta vs `2026-05-04/patient_evidence_none_diagnostics.json`

| Metric | Baseline (8e718e87c3fa) | This run (43c765d1dbcc) | Δ |
|---|---:|---:|---:|
| `unmapped_concept` | 551 (51.2%) | **445 (41.9%)** | **−106 (−9.2 pp)** |
| `indeterminate` | 996 (92.5%) | 919 (86.6%) | −77 (−5.9 pp) |
| `pass` verdicts | 58 | 110 | **+52** |
| `fail` verdicts | 23 | 32 | +9 |
| `ok` reason | 81 | 142 | +61 |
| `no_data` reason | 2 | 18 | +16 |

## What changed

- `TerminologyResolver` now calls `UMLSSearchClient` on open condition /
  lab surfaces when the hand-curated alias tables miss.
- SNOMED conditions use `searchType=exact`; LOINC labs use `words` with
  a Parts-filter regex (`^\d+-\d+$`) so `LP*` / `LA*` / `MTHU*`
  component atoms do not pollute the resolved ConceptSet.
- Composite phrases (containing ` and `, ` or `, `,`, `;`, `/`) short-
  circuit before the API call and cache as `composite_unhandled`.
- Work queue applies hand-curated `extractor_bug` / `out_of_scope`
  classifications **before** consulting the resolver, so surfaces
  like `life expectancy` and `ECOG performance status` get the
  right triage label even though UMLS has LOINC hits for them.
- Hand-coded alias tables still take precedence for the known-hot
  surfaces (`hemoglobin`, `platelet count`, `bmi`, `uncontrolled
  hypertension`, `blood pressure` ambiguous).

## Residual top-unmapped surfaces (all non-atomic)

All 15 remaining rows in `top_unmapped_surfaces` are legitimately
non-mappable with exact-match terminology:

- Composites (`pregnant or breastfeeding`, `PH WHO Groups 2, 3, 4, or 5`,
  `liver and kidney function tests`, `mitral regurgitation or aortic
  regurgitation`, etc.)
- Out-of-scope for Synthea (`pulmonary vascular resistance`,
  `history of full pneumonectomy`, `ECOG performance status`)
- Extractor bug (`life expectancy`)
- Ambiguous (`blood pressure` → systolic vs diastolic)
- Condition-specific phrases that would need composite splitting
  (`symptomatic pulmonary hypertension (PH) classified as WHO FC II or III`,
  `stable background therapy for PAH`)

This satisfies the 2.17 exit criterion: "remaining unmapped rows
are true misses, composites, extractor errors, or out-of-scope
concepts with explicit labels."
