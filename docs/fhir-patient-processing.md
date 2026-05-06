# FHIR (Synthea) patient processing: shapes, use, and validation

This note describes how **patient-side FHIR** is ingested, what **internal record shape** the system keeps, how that record feeds **eligibility scoring**, and how it ties into **evaluation**—in the same spirit as `docs/extractor-chia-validation.md`: behavior and schemas, not implementation identifiers.

The code path today assumes **Synthea’s FHIR R4 sample**: one JSON **transaction bundle** per patient file, with resources linked by UUID references inside the bundle. Other FHIR feeds would need the same logical fields (or an adapter) to populate the same internal model.

---

## 1. Ingestion: from bundle file to a patient record

### 1.1 What is read from the bundle

The loader walks bundle entries and builds one **patient record** from:

| FHIR resource kind | What becomes of it |
|--------------------|---------------------|
| **Patient** | Stable id, birth date, administrative gender (mapped to an internal sex enum), and optional **death date** when present. |
| **Condition** | Each becomes an internal **diagnosis row**: primary code (system + code + display text), optional onset and abatement dates, and a flag distinguishing **clinical** vs **explicitly social-history–category** rows (so downstream logic can prefer clinical problems). |
| **Observation** | Numeric labs and vitals only in the supported path: a value, a unit, an effective date, and a coded concept (e.g. LOINC). **Panel observations** (e.g. blood pressure wrappers with no single top-level value) are **split** into one row per **component** that carries its own code and value, so downstream code can ask for systolic vs diastolic by code. Observations without a usable numeric value and date are **dropped**. |
| **MedicationRequest** | Each becomes an **order row**: coded drug concept, start date, and end date when the source supplies it; inline medication coding and references to a sibling Medication resource are both handled so a single concept emerges when possible. Unresolvable medication concepts are skipped. |

Resources that exist in real FHIR charts but are **not** in this ingestion list are simply **ignored** for v0—they do not appear on the internal patient record.

### 1.2 Normalization and lossy choices (intentional)

- **Death:** If the patient has a documented death on or before the evaluation date, **end-to-end scoring refuses** to produce eligibility verdicts for that pair. The rationale coded in the product is: once the patient is deceased, “current” eligibility primitives (age as of date, active conditions, fresh labs) are not a meaningful screening target.

- **Clinical vs social conditions:** Only category metadata that explicitly marks **social history** is used to downgrade a Condition to non-clinical. Other social-style findings that happen to sit in encounter-diagnosis categories remain marked clinical—so this is a **partial** hygiene filter, not a complete ontology of “social determinants.”

- **Race, ethnicity, narrative notes:** Not promoted into the v0 patient record shape, even if present in FHIR—so criteria that depended on those fields could not be matched from this slice alone.

- **Medication end dates:** The sample path often leaves end open when the source does not record a stop—**active medication** is then inferred from start ≤ as-of and no end before as-of.

---

## 2. Internal patient schema (conceptual)

After ingestion, a **patient** is not “raw FHIR.” It is a compact, longitudinal object:

| Area | Contents |
|------|-----------|
| **Identity & demographics** | Id, birth date, sex, optional deceased date. |
| **Problems** | List of coded conditions with activity interval and clinical flag. |
| **Measurements** | List of coded numeric observations with value, unit, and effective date. |
| **Medications** | List of coded medication orders with start/end for activity as-of logic. |

Every downstream consumer is expected to use an **as-of date** when asking “what was true on the day we’re screening?” Age, active conditions, active medications, and “latest lab before as-of” all respect that anchor.

---

## 3. The profile layer: how the matcher sees the patient

Matching trial criteria against raw lists would duplicate policy everywhere. Instead, the system wraps the patient in an **as-of profile**—a thin view that exposes only the **primitives the matcher needs**:

| Primitive family | Behavior (conceptual) |
|------------------|----------------------|
| **Presence / absence of conditions** | “Does the patient have any **active clinical** condition whose code matches this trial-side concept set (with system URI discipline so SNOMED and ICD codes never collide by accident)?” Also exposes which rows matched for evidence display. |
| **Medications** | Same pattern for **active** medication orders vs trial-side code sets. |
| **Numeric thresholds** | “Given a LOINC, an operator, a threshold value, a unit string, and an optional freshness window: does the **latest on-or-before-as-of** observation support a decisive comparison?” Outcomes are explicitly **tri-valued**: meets, does not meet, **no data**, **stale** (exists but outside freshness), or **unit mismatch** (cannot normalize safely). |

### 3.1 Units and conversions

For a small set of high-impact measures, the profile defines **canonical unit strings** per LOINC and a **whitelist of numeric conversions** (e.g. LDL mmol/L vs mg/dL). If the chart unit and the trial criterion unit cannot be aligned through that table, the threshold path returns **unit mismatch** rather than silently comparing incompatible numbers.

---

## 4. How the patient record is used in the product path

1. **Load** the bundle → internal **patient** object.
2. **Choose an as-of date** (eval case, API request, or CLI).
3. **Build the profile** for (patient, as-of).
4. **Match** each extracted trial criterion against that profile (and against trial metadata where relevant), producing per-criterion pass / fail / indeterminate with reasons and evidence pointers.
5. **Optional retrieval / adjudication modes:** For some indeterminate outcomes, the system can materialize **ranked source rows**—compact snapshots of demographics, conditions, labs, and medications derived from the **same** internal patient object—so a human reviewer or a bounded model sees **what rows** supported or failed to support a decision. This layer ranks and cites; it does not replace the core matcher contract unless an adjudication mode is enabled.

At no point does the main matcher re-parse the original JSON bundle; it reads only the **normalized patient** and **profile** view.

---

## 5. How this ties to “validation” (vs Chia on the trial side)

Chia validates **trial text extraction** on a dedicated eval command. **FHIR / Synthea does not have an analogous built-in “gold BRAT layer” inside this repo.** Instead, patient-side validation shows up in a few **separate** ideas:

| Mechanism | What it checks |
|-----------|----------------|
| **Deterministic matcher vs seeded expectations** | The eval seed pairs carry **pre-seeded mechanical labels** for structured fields (e.g. age/sex/lab-style cells). After scoring, **layer-1 style reporting** compares those seed cells to what the matcher produced for the same patient-backed fields—agreement and coverage statistics, not a second parse of FHIR. |
| **Synthetic cohort as “world truth”** | Synthea is treated as the **generator** of the chart. Structured criteria whose ground truth can be read mechanically from the bundle + as-of (within the model’s limits) are the strongest patient-side checks. Anything the bundle never recorded stays **no data** or indeterminate honestly. |
| **Human labels on patient–evidence packets** | For retrieval and bounded adjudication, the project maintains **JSON calibration rows** where humans set expected verdicts and cite which **source row ids** matter. That validates end-to-end behavior **given** the normalized patient rows, not the raw FHIR syntax. |
| **Unit and freshness policy** | The tri-state threshold design is itself a **contract test**: the system refuses to pretend a missing lab is a fail, and refuses silent unit coercion outside the whitelist. |

So: **FHIR → normalized patient → profile primitives → matcher + optional retrieval/adjudication.** “Validation” is **downstream agreement and human labeling**, not an automatic diff against the original FHIR JSON on every run.

---

## 6. Mental model in one table

| Stage | Artifact | Role |
|-------|-----------|------|
| Disk | FHIR bundle JSON | Source of truth for what was “in the chart” in the demo world. |
| Ingestion | Internal **patient** | Lossy, opinionated slice of FHIR focused on eligibility-style facts. |
| Per score run | **Profile** (patient + as-of) | Matcher-facing query surface with explicit unknown/stale/unit states. |
| Scoring | Verdicts + evidence | Answers trial criteria using profile primitives; may attach retrieved rows for audit. |
| Eval | Seed labels + layer reports + optional human evidence labels | Measures whether that pipeline behaves as intended on fixed pairs—not whether the FHIR file round-trips. |

If you later add a second FHIR source, the **contract** to preserve is this internal **patient** shape and **profile** semantics; the bundle parser can change underneath as long as those contracts stay stable for the matcher and evals.
