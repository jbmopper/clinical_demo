# Patient evidence labeling guide

Human reviewers maintain a **JSON list** of labels aligned to eval seed **(pair id, criterion index)** targets. The calibration packet builder attaches **source rows** (indexed patient and trial snippets) and optional **retrieved** row ids. This guide matches the **Pydantic shapes and reporting code** that consume those files.

---

## 1. Label vocabulary (`label` field)

Each label is one of four strings (or empty / omitted while work is in progress):

| Value | Meaning for the patient chart relative to the criterion |
|--------|------------------------------------------------------------|
| **supports_present** | The cited rows show the patient **has** what the criterion asks for (e.g. condition or drug present, lab clearly on the qualifying side of the threshold once units and dates are considered). |
| **supports_absent** | The cited rows support **absence** of the requirement (e.g. no diagnosis of X in the window, or a negative screening result where that is what the criterion demands). |
| **supports_measurement_comparison** | The evidence needed is specifically a **numeric comparison** (lab vs threshold, correct units, as-of date within policy). Use when the disagreement is measurement-shaped rather than a binary diagnosis row. |
| **insufficient_evidence** | Even with the rows shown, the chart does **not** justify a decisive present/absent/meets call for this criterion under the active assumption mode. |

If any of `label`, `expected_matcher_verdict`, `cited_source_row_ids`, or `rationale` is filled, the row counts as “filled” for completeness stats; **usable for automated accuracy** requires `expected_matcher_verdict` to be set.

---

## 2. Expected matcher verdict (`expected_matcher_verdict`)

This is the **human ground truth** for what the system should conclude for that criterion after the full pipeline for the run configuration under test (same assumption mode you intend to measure).

- Use **`indeterminate`** when the correct outcome is honestly unknown, underspecified, or must stay in the “needs review” bucket.
- Align with the matcher’s **final** verdict vocabulary (`pass`, `fail`, `indeterminate`) — not the adjudicator’s pre-polarity raw predicate.

**Consistency check:** If you set `label` to **supports_present** but `expected_matcher_verdict` to **fail**, you should explain why in `rationale` (e.g. exclusion polarity, negation, or criterion wording that makes presence disqualifying).

---

## 3. Citation requirements (`cited_source_row_ids`)

- Values must be **stable row ids** exactly as shown on the calibration row (`patient:000` style for patient-derived rows, `trial:000` style for trial metadata rows in the same packet).
- For **decisive** expected verdicts (**pass** or **fail**), reviewers should cite **at least one** patient row that carries the clinical fact (trial-only rows are weak support for patient predicates).
- The automated **citation agreement** metric (patient-evidence report) only fires when:
  - `expected_matcher_verdict` is **not** `indeterminate`, **and**
  - the human cited at least one row.
  It then checks whether every human-cited id appears among verdict evidence rows tagged as **retrieved patient rows** on the persisted run being scored. Subset match counts as agreement.

---

## 4. Matcher assumption mode on the label row

Each human label may record which **assumption mode** the expectation applies to (defaults to open world). When comparing runs, ensure the scored run used the **same** mode; otherwise agreement numbers mix incompatible contracts.

---

## 5. Reviewer metadata

- **`reviewer`:** Free text who filled the label.
- **`rationale`:** Short prose for the next human or for adjudicating disagreements between judge and chart.

---

## 6. Common edge cases

| Situation | Guidance |
|-----------|----------|
| **Open world vs your intuition** | If the criterion is “no history of MI” and the chart simply has **no** MI condition row, open world says **not** evidence of absence — label **insufficient_evidence** or expected **indeterminate (no_data)** unless closed-world eval explicitly applies. |
| **Unit mismatch** | If labs exist but units cannot be reconciled to the trial threshold, deterministic path is indeterminate; human label should not claim **supports_measurement_comparison** unless units actually align or conversion is clinically obvious per project policy. |
| **Unmapped concept** | Terminology never bound the trial phrase to codes — expected verdict should stay **indeterminate (unmapped_concept)**; patient rows rarely “fix” that. |
| **Free-text criterion** | Often **human_review_required**; use **insufficient_evidence** or expected indeterminate unless retrieved note rows or composite subcheck rows provide citeable evidence. |
| **Composite OR/AND criterion** | Label the parent criterion, but inspect subcheck evidence separately. For `any_of`, one supported subcheck may support the parent; for `all_of`, every required subcheck must be supported. Until scorer wiring lands, expected matcher verdicts should stay aligned with the actual parent matcher output. |
| **Judge said “incorrect” but issue is age/sex** | The calibration packet builder **filters** those out of the patient-evidence slice — fix those in layer-1 / judge workflows instead of mixing them into patient-evidence rows. |
| **Oncology / NSCLC rows** | Default **cardiometabolic core** scope excludes them from the 60-row style packet unless you widen scope deliberately — labels on excluded rows will not drive the core packet metrics. |

---

## 7. Files and lifecycle

- **Labels file:** JSON list of label objects (sorted on save by pair id then criterion index).
- **Candidates file:** Larger JSON built from eval runs + source contexts + retrieval reasons; reviewers read from it and merge updates back into the labels file via tooling provided in the repo.

Related: `docs/matcher-assumption-modes.md`, `docs/patient-evidence-retrieval-architecture.md`, `docs/evaluation-layers-and-gates.md`.
