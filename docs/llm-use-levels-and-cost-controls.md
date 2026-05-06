# LLM use levels and cost controls

This document describes **which stages may call an LLM**, what **`none` / `retrieval_only` / `bounded_adjudication`** change in the imperative scoring path, how **cost telemetry** is recorded, and what is **explicitly not** routed yet. Grounded in settings defaults and the scoring graph wiring.

---

## 1. LLM use level enum (imperative scoring)

| Level | Deterministic extract + match | After deterministic pass |
|--------|--------------------------------|---------------------------|
| **none** | Unchanged (extractor still runs unless a cached extraction is supplied). | No retrieval attachment pass; no adjudicator. |
| **retrieval_only** | Same. | For each **indeterminate** criterion: rank patient rows, **attach** them as evidence on the verdict; **do not** change pass/fail/indeterminate. **No LLM** in this branch. |
| **bounded_adjudication** | Same. | Same retrieval, then for those indeterminates **with** rows: call the **patient-evidence adjudicator** structured LLM; may replace the verdict subject to citation fail-closed rules. |

**Note on `critic` in the type union:** The shared literal type includes **`critic`** for forward-compatible telemetry tagging, but the **imperative** post-matcher hook only branches on the three behaviors above. The **LangGraph critic loop** is a **separate opt-in flag** (`critic_enabled`) on the graph entry point; it does not reuse `llm_use_level` to turn itself on.

---

## 2. Other LLM stages (outside `llm_use_level`)

These can still run depending on entry point and options:

- **Criterion extractor:** One structured call per trial eligibility text when no cache is passed (model and max output tokens from settings).
- **LLM matcher node (graph):** Only for `free_text` criteria when using the LangGraph orchestrator — not part of `llm_use_level`.
- **Critic node (graph):** Optional; reviews process quality after rollup; does not directly set eligibility without going through matcher actions.
- **Layer-3 judge (eval tooling):** Offline grading of matcher verdicts; not part of live `/score` unless explicitly invoked by scripts.

---

## 3. What bounded adjudication is *not* allowed to do

- It does **not** receive the full FHIR bundle or narrative chart — only the **retrieved row bundle** plus structured criterion JSON, deterministic verdict, trial context string, and assumption mode.
- It does **not** invent unit conversions beyond plain comparability in the prompt rules; ambiguous units should fall back to indeterminate.
- It cannot emit decisive pass/fail **without** citing at least one retrieved patient row id — the implementation downgrades to indeterminate with a fixed rationale if citations are missing or invalid.

---

## 4. Telemetry captured today

**Per pair (extractor):** Model id, temperature, max tokens, prompt version, input/output/cached token counts, estimated USD, latency — attached to observability spans and duplicated into the score result’s extraction metadata where applicable.

**Per adjudication call:** Stage tag **`patient_evidence_adjudicator`**, criterion index, model id, adjudicator + prompt version strings, tokens, USD estimate, latency — appended to an ordered **LLM call cost** list on the score result. Summaries aggregate adjudicator subtotals for CLI and eval reports.

**LangGraph / Langfuse:** Generation-style spans nest under the parent scoring span with tags for patient id, trial id, verdict counts, orchestrator mode, assumption mode, and LLM use level — useful for filtering dashboards without rejoining SQLite.

---

## 5. Settings knobs that act as cost levers

- **Extractor** max output tokens (large protocols need headroom; truncation returns empty criteria with warning metadata).
- **LLM matcher** max output tokens (free-text criteria only on graph path).
- **Adjudicator** reuses the **extractor model** and temperature from settings and currently shares the **LLM matcher max output token** ceiling for its structured parse call — split knobs may land later if adjudicator responses need a different cap.
- **Critic / judge** token caps exist as separate settings entries for when those nodes run.

---

## 6. How future routing or model sweeps should be evaluated

1. **Freeze inputs:** same curated eval seed, same cached extractions when comparing matcher-only behavior.
2. **Tag runs:** persist `matcher_version`, extractor prompt version, adjudicator version, assumption mode, and `llm_use_level` on each run row.
3. **Split metrics:** deterministic-only (`none`), reviewer assist (`retrieval_only`), and automated override (`bounded_adjudication`) should be reported **separately** — combining them hides regressions in citation quality or assumption semantics.
4. **Cost:** sum `LLMCallCost` entries by **stage**; adjudicator is already split from extractor in the envelope.
5. **Safety:** track refusal and missing-parsed rates per stage; any routing policy that increases adjudicator calls should move **abstention rate** and **citation agreement** (against human labels) in lockstep, not just headline accuracy.

Related: `docs/matcher-assumption-modes.md`, `docs/evaluation-layers-and-gates.md`, `docs/patient-evidence-labeling-guide.md`.
