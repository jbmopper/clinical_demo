# Patient evidence retrieval architecture

How **structured patient and trial facts** become **citeable rows**, how **retrieval ranks** them per criterion, and where **future** note or vector retrieval is expected to plug in.

---

## 1. Source row inventory (pair-level)

For a given patient + trial, the system materializes a **flat list** of **source rows**:

**Patient side (in order):**

- Demographics: sex, birth date (stable synthetic ids like `patient:000`, `patient:001`).
- **Conditions** up to a cap — each row carries kind, label, value text, optional onset/abatement dates, code, system, clinical flag.
- **Observations (labs/vitals)** up to a cap — each numeric observation becomes its own row with LOINC (or other) code, value, unit, date.
- **Medications** up to a cap — drug concept, dates when present.

**Trial side:**

- Title, condition list, min/max age, sex — each as a small metadata row (`trial:000` …).

These rows are the **only** substrate for lexical retrieval today. They are also serialized into **layer-3 / calibration** contexts so humans and judges share the same ids.

---

## 2. What counts as a “source row”

Each row is: **stable id**, **source** (`patient` vs `trial`), **kind** (demographics, condition, observation, medication, trial_field), **label**, **value** string, optional **date**, optional **code/system**, optional **status**.

Rows are **not** full FHIR resources — they are **projections** chosen for eligibility screening. Anything not projected (procedures, encounters, notes, imaging reports) is **invisible** to structured retrieval until adapters add new projections.

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

## 5. Future: vector and clinical note retrieval

The structured layer is intentionally **lexical + code-anchored** so it is cheap, inspectable, and deterministic aside from resolver caches.

**Planned extension surface (not yet in code):**

- Add **note-derived rows** (e.g. from `DocumentReference` attachments) into the same `RetrievalSourceRow` shape so ranking and adjudication reuse the same citation machinery.
- Add an **optional embedding ranker** behind an interface so lexical scores can be reordered or blended without changing downstream adjudicator contracts.

Until those adapters exist, anything only stated in clinical narrative **outside** projected rows will continue to land in **no data** / **human_review_required** paths.

Related: `docs/fhir-patient-processing.md`, `docs/matcher-assumption-modes.md`, `docs/free-text-note-evidence-design.md`.
