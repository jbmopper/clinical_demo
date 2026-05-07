# Patient evidence retrieval architecture

How **structured patient and trial facts** plus v0 note snippets become **citeable rows**, how **retrieval ranks** them per criterion, and where composite / vector retrieval plugs in next.

---

## 1. Source row inventory (pair-level)

For a given patient + trial, the system materializes a **flat list** of **source rows**:

**Patient side (in order):**

- Demographics: sex, birth date (stable synthetic ids like `patient:000`, `patient:001`).
- **Conditions** up to a cap — each row carries kind, label, value text, optional onset/abatement dates, code, system, clinical flag.
- **Observations (labs/vitals)** up to a cap — each numeric observation becomes its own row with LOINC (or other) code, value, unit, date.
- **Medications** up to a cap — drug concept, dates when present.
- **Clinical note snippets** from `DocumentReference.content.attachment.data` — each row carries `kind="note"`, title, snippet text, document date when present, and `note_id=...` status.

**Trial side:**

- Title, condition list, min/max age, sex — each as a small metadata row (`trial:000` …).

These rows are the **only** substrate for lexical retrieval today. They are also serialized into **layer-3 / calibration** contexts so humans and judges share the same ids.

---

## 2. What counts as a “source row”

Each row is: **stable id**, **source** (`patient` vs `trial`), **kind** (demographics, condition, observation, medication, note, trial_field), **label**, **value** string, optional **date**, optional **code/system**, optional **status**.

Rows are **not** full FHIR resources — they are **projections** chosen for eligibility screening. Anything not projected (procedures, encounters, imaging reports, non-inline note URLs) is **invisible** to retrieval until adapters add new projections.

---

## 3. Retrieval scoring (per criterion)

Given one **extracted criterion** and the full row list:

1. **Patient rows only** are candidates (trial rows are context elsewhere, e.g. adjudicator prompt).
2. Build **query tokens** from criterion source text, typed payload fields (condition phrase, med phrase, lab text + unit, temporal event text, free-text note), and all **mention** surfaces.
3. Compute **anchored codes**: resolve condition / medication / lab strings to `ConceptSet`s when possible; collect all member codes — a row whose code matches any anchored code receives a **large** score bump and a `code:…` reason tag.
4. Token overlap: each overlapping non-stopword token between query and row text adds a smaller bump; reasons list individual `term:…` tags (capped for readability).
5. **Kind preference:** if the criterion is condition-shaped, medication-shaped, lab-shaped, or demographic, matching row kinds receive an extra bump when overlap already exists.

Rows with score ≤ 0 are dropped. The remainder sort by **descending score**, then stable row id, and truncate to a **limit** (tighter limit on live scoring than on the 60-row calibration builder).

---

## 4. Outputs of retrieval

Each kept row becomes a **retrieved evidence** object carrying: the row snapshot, integer score, and string **reasons** list explaining why it surfaced.

- **Retrieval-only mode:** these attach to the existing **indeterminate** verdict as extra evidence without flipping the verdict.
- **Bounded adjudication:** the top set is passed into the adjudicator prompt; citations must reference these ids.

---

## 5. Composite subcheck retrieval

The extractor/fixer now emits native representational composite groups, and
legacy paths can still backfill the same shape from explicit punctuation:

- `composite_groups[]` contains a parent `any_of` / `all_of` group with stable subcheck ids.
- The flat `criteria[]` list remains the parent view for matcher compatibility.
- Each subcheck carries a matcher-shaped criterion payload where safely inferable, otherwise a `free_text` subcheck.
- Retrieval runs per subcheck, so reviewers can see evidence for “HbA1c threshold” separately from “fasting glucose threshold.”
- Scoring retrieval now unions parent-criterion hits and composite-subcheck hits for `retrieval_only` and `bounded_adjudication`, tagging subcheck-derived rows with `composite:...` and `subcheck:...` reasons.

The deterministic matcher now consumes flat native groups in both the imperative
and LangGraph paths: subchecks are matched as raw predicates, the group is
rolled up under `any_of` / `all_of`, then the parent criterion's polarity and
negation are applied once. Nested groups and richer clinical event extraction
remain future work.

---

## 6. Future: vector retrieval

The structured layer is intentionally **lexical + code-anchored** so it is cheap, inspectable, and deterministic aside from resolver caches.

**Planned extension surface:**

- Add an **optional embedding ranker** behind an interface so lexical scores can be reordered or blended without changing downstream adjudicator contracts.

Anything only stated outside projected rows will continue to land in **no data** / **human_review_required** paths.

---

## 7. Correlatable free text status

The first patient-evidence pilot labels showed that `retrieval_only` can attach rows without improving verdicts when the parent criterion remains `free_text`, `human_review_required`, or `unmapped_concept`. Some of those rows are genuinely note-only or underspecified, but others are **correlatable**:

- investigational drug or trial exposure within a time window;
- prior/concurrent medication use expressed without a clean medication slot;
- condition history phrased as prose rather than a structured condition criterion;
- lab or vital constraints embedded in free-text wording;
- composite subchecks where one subcheck is typed and another remains free text.

The current deterministic matcher now includes a narrow normalization pass before bounded adjudication:

1. detect free-text criteria with exactly one promotable typed clinical surface;
2. map/search that surface through the same terminology front door used by typed criteria;
3. parse simple symbolic measurement thresholds such as `BMI > 32 kg/m2`;
4. preserve subcheck ids, row ids, codes, units, numeric values, and citation reasons;
5. handle investigational-agent / clinical-trial exposure as a trial-exposure predicate rather than an RxNorm medication;
6. leave multi-surface, note-only, negation-ambiguous, and unsupported semantics as bounded adjudication or human review.

This pass does not turn `retrieval_only` into an adjudicator. Its purpose is to make the deterministic and retrieval substrate less blind before any LLM decides. Closed-world trial-exposure absence is allowed only under the explicit matcher assumption contract; open-world remains `indeterminate(no_data)`.

## 8. Next target: normal-range criteria

The remaining labeled misses include criteria such as "serum calcium within normal limits." These should not be guessed from prose alone. The conservative implementation target is:

1. detect normal-range/reference-interval wording for measurement criteria;
2. compare only when the patient observation carries a trustworthy reference range or the trial text provides an explicit numeric threshold;
3. preserve units and source row ids;
4. otherwise keep the verdict indeterminate and send the row to human review or bounded adjudication.

Related: `docs/fhir-patient-processing.md`, `docs/matcher-assumption-modes.md`, `docs/free-text-note-evidence-design.md`.
