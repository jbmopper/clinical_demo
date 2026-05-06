# Trial extraction pipeline

End-to-end view of how **ClinicalTrials.gov** data becomes **curated trial JSON**, how **eligibility prose** is **extracted** into structured criteria, how **caches** behave, and known **failure** modes.

---

## 1. ClinicalTrials.gov ingestion (curation script)

- Queries the public **v2 API** with slice parameters (condition, sponsor class, recruitment status, phase filters per project rules).
- Writes **one JSON file per NCT** under the curated trials directory (gitignored bulk data) plus a **manifest** listing slices and file paths.
- Cardiometabolic-heavy mix with a small **NSCLC** slice for stretch testing.

Downstream loaders parse the raw `protocolSection` into the internal **`Trial`** domain object (title, conditions list, structured age/sex, **eligibility text** blob used by the extractor).

---

## 2. Eligibility text as extractor input

The extractor consumes the **free-text eligibility section** (and similar narrative fields on the `Trial` object), not the whole XML protocol. If that string is empty, the extractor returns **zero criteria** without calling the model.

---

## 3. “Chia-style” extraction (meaning in this pipeline)

The LLM is prompted to return **matcher-shaped criteria** plus optional **entity mention** lists using a vocabulary **aligned with** Chia entity types for audit — see `docs/extractor-chia-validation.md` for how that differs from full Chia graphs.

**Separate Chia eval:** Running extraction against the **Chia corpus files** uses the same schema but a **different cache directory** from CT trials.

---

## 4. Extractor revisions and versioning

- **Prompt version** string is embedded in every extraction run metadata and Langfuse spans.
- Any prompt or schema change that could shift outputs should bump **prompt** and/or **matcher** version constants so evals can attribute regressions.

---

## 5. Cache behavior (CT trial extractions)

- Cached extractions are stored as JSON envelopes keyed by **NCT id** (path rule mirrors “cache discipline” elsewhere).
- Cached content is the **raw LLM criteria list**; **deterministic enrichment** (injecting age/sex rows from structured CT fields when missing) happens **at scoring time** so refreshing structured CT metadata does not invalidate the whole cache file.

**Force re-extract:** CLI flags allow bypassing cache for a run.

---

## 6. Known failure modes

| Failure | Behavior |
|---------|----------|
| **Model refusal / missing parsed payload** | Hard errors surfaced to caller; no partial criteria. |
| **Max output length hit mid-JSON** | Treated as graceful degradation: **empty criteria** with explanatory metadata; span flagged warning; rollup becomes vacuous pass unless other paths catch it. |
| **Extractor invariant violation** | Single criterion soft-fails to indeterminate with explicit reason so the rest of the trial still scores. |
| **Compound bullets** | May become `free_text` when the prompt’s atomicity rules say splitting would lie about conjunction semantics — matcher defers. |
| **Terminology** | Separate from extraction: mapping happens in matcher lookup, not in the extractor. |

Related: `docs/extractor-chia-validation.md`, `docs/terminology-mapping-architecture.md`, `docs/system-architecture-walkthrough.md`.
