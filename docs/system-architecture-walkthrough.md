# System architecture walkthrough

End-to-end flow from **curated trial JSON + Synthea patient bundles** to **per-criterion verdicts**, **case rollup**, and **reviewer-facing artifacts**. Two orchestrations exist: a **single-threaded scorer** and a **LangGraph** pipeline that can parallelize matching and optionally run a **critic loop**. Both aim to return the same result envelope when the graph critic is off.

---

## 1. External inputs and where they land

| Input | Storage / access | Internal representation |
|--------|------------------|-------------------------|
| Trial protocol slice | Per-NCT JSON under curated data (see curation scripts) | `Trial`: title, structured age/sex, condition tags, **eligibility prose** |
| Patient chart | One FHIR R4 bundle JSON per patient (Synthea sample layout) | `Patient`: demographics, conditions, numeric observations, medication orders, optional death date |
| Screening date | Caller-provided `as_of` | Anchors age, active problems, lab freshness |
| Optional cached extraction | JSON envelope keyed by trial id | Skips the extractor LLM when supplied |

---

## 2. Imperative pipeline (default API / CLI path)

Stages run **in order** inside one call:

1. **Guardrail:** If the patient has a documented death on or before `as_of`, scoring **stops** with an error — no verdicts that pretend “current” eligibility still applies.

2. **Trial text extraction:** Unless a cached extraction is passed in, an LLM call turns eligibility prose into **structured criteria** (typed rows + audit mentions + model notes). Empty eligibility short-circuits without a model call.

3. **Enrichment:** Deterministic pass adds **age** and **sex** criterion rows from structured CT fields when the model omitted them, so the matcher always sees the same gates the trial record implies.

4. **Patient profile:** Wrap the patient in an **as-of profile** — the only surface matchers use for “does this person have code X / lab Y / threshold Z.”

5. **Per-criterion deterministic match:** For each extracted row, dispatch on **kind** (age, sex, condition present/absent, medication present/absent, measurement, temporal window, free text). Consult terminology lookups for coded concepts; compare against the profile. Respect **matcher assumption mode** (open vs closed world) where it applies. Apply **polarity and negation** once to produce final pass / fail / indeterminate.

6. **Retrieval layer (optional):** Controlled by **LLM use level** (separate from the graph critic):
   - **None:** skip.
   - **Retrieval only:** for each criterion still indeterminate after step 5, rank **structured patient source rows**, attach them as evidence, **do not** change the verdict.
   - **Bounded adjudication:** same ranking, then a **small structured LLM** may re-decide only from those rows, with citation fail-closed rules; polarity still applied in code after the model.

7. **Rollup:** Combine per-criterion outcomes into one case-level eligibility label using conservative rules (any fail → case fail; indeterminate classes block a blanket pass; a special state exists when only free-text remains indeterminate alongside passes).

8. **Envelope:** Return patient id, trial id, as-of, assumption mode, LLM use level, enriched criteria, extraction metadata (model, prompt version, tokens, cost), verdict list, summary counts, optional per-call cost records for adjudication.

---

## 3. LangGraph pipeline (optional orchestrator)

Same inputs and same final envelope shape when the critic is disabled.

**Graph shape (high level):**

- **Start → extract** — same extraction + enrichment + profile build as the imperative path’s front half, packaged as a node so cached extractions still short-circuit the LLM.

- **Fan-out → parallel match branches** — one dynamic branch per criterion:
  - **Deterministic match** for structured kinds.
  - **LLM match** only for **free-text** criteria (structured-output verdict aligned with deterministic matcher semantics).

- **Join → rollup** — waits for all branches, sorts verdicts by criterion index, builds the same summary as imperative mode.

- **Critic (opt-in)** — LLM reads rollup-level findings; does **not** directly set enrollment. It emits closed-enum process issues; a **revise** node may re-run extraction or matching for specific indices, then re-enter rollup until budget or convergence.

- **Finalize → end** — pass-through node reserved for **human checkpoint** interrupts (compile-time option): graph can pause before final commit so a UI or operator can inspect or override state, then resume.

Stub **clients** (OpenAI-shaped) can be injected at graph build time for tests; production builds default clients from settings.

---

## 4. Cross-cutting services

| Concern | Role |
|---------|------|
| **Terminology cache** | Pins resolver results (VSAC / RxNorm / open resolver) so replays stay deterministic and offline runs avoid hammering NLM. |
| **Observability** | Parent span per (patient, trial); nested **generation** spans for extractor, free-text matcher, adjudicator, critic as applicable — metadata carries ids, modes, and counts for dashboards. |
| **Eval store** | SQLite records full score envelopes per seed pair for layer-1 / layer-3 / patient-evidence reports. |
| **HTTP API** | Thin validation + loader + scorer call; returns the same JSON shape as the CLI. |
| **Reviewer UI** | External dev app posting to the API; renders verdicts, evidence, toggles for orchestrator and modes. |

---

## 5. How the two orchestrations relate

- **Parity goal:** With graph **critic off** and equivalent flags, results should match the imperative scorer — the graph exists to add **parallelism**, **free-text LLM matching**, and **critic/revise**, not to fork the domain model.

- **When to use which:** Imperative path is simpler for libraries and tests; graph path when you need Send-based parallelism, the LLM matcher for free-text, critic iterations, or LangGraph checkpoints.

---

## 6. Related deep dives

- Trial ingestion + extractor cache: `docs/trial-extraction-pipeline.md`
- Patient FHIR → profile: `docs/fhir-patient-processing.md`
- Assumption modes + retrieval vs adjudication: `docs/matcher-assumption-modes.md`
- Retrieval scoring: `docs/patient-evidence-retrieval-architecture.md`
- Terminology: `docs/terminology-mapping-architecture.md`
- Eval layers: `docs/evaluation-layers-and-gates.md`
- Scope limits: `docs/known-limitations-and-scope.md`
