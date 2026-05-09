# Matcher assumption modes and patient-evidence levels

This document explains how **evidence assumptions** (open vs closed world) interact with **deterministic matching**, and how **retrieval-only** vs **bounded adjudication** change what conclusions are allowed after the deterministic pass. It reflects current matcher and scoring behavior.

---

## 1. Matcher assumption modes (condition, medication, temporal window, trial exposure)

These modes apply when a criterion’s **trial-side concept has already resolved** to a matcher vocabulary (`ConceptSet`) and the code looks for matching rows on the patient profile.

| Mode | Intended use | When the chart has **no** matching active condition / medication / in-window event |
|------|----------------|-------------------------------------------------------------------------------------|
| **Open world** (default) | Clinical chart review: the FHIR slice you have is not assumed complete. | Verdict stays **indeterminate** with reason **no data** — “silent chart” is **not** treated as proof the patient lacks the condition or drug. |
| **Closed world (eval)** | Synthetic eval slices where the cohort record is treated as the full world for testing. | Raw predicate before polarity flip is **fail**, with a flag on the verdict that the conclusion **depended on the closed-world assumption** (so audits can separate honest “no row” from “negative under completeness assumption”). |
| **Closed world (demo)** | Same semantics as eval variant; separate literal so callers can tag demo runs distinctly if needed. | Same as eval closed world for the whitelisted kinds. |

**Kinds affected by open vs closed:** condition present/absent, medication present/absent, temporal-window lookbacks that reuse condition resolution for the event text, and the narrow free-text trial-exposure predicate for investigational-agent / clinical-trial participation criteria.

**Kinds *not* flipped by closed world:**

- **Unmapped concept:** If trial text never mapped to a `ConceptSet`, the verdict is **indeterminate (unmapped_concept)** in **every** mode. Closed world must not hide terminology failure behind a synthetic “absent.”
- **Labs (measurement thresholds):** Missing lab, stale lab, or unit mismatch stays **indeterminate** with the appropriate reason in **all** modes — a missing numeric measurement is never upgraded to a confident fail the way a missing condition row can be under closed world.
- **Age and sex:** Deterministic comparisons; absence semantics above do not apply the same way.
- **Most free-text criteria:** Deterministic path defers to human review unless the criterion is narrow enough for the correlatable free-text promotion path. Assumption mode only changes promoted trial-exposure absence and mapped list-like medication exposure absence; it does not make arbitrary prose decisive.

**Polarity and negation:** Per-kind handlers return a **raw** pass/fail/indeterminate for the predicate; the matcher then applies trial **inclusion/exclusion** and linguistic **negation** in one consistent step so “exclusion + absent disease” does not get silently inverted.

---

## 2. Retrieval-only (`llm_use_level`)

**What runs:** After deterministic matching, for each criterion that is still **indeterminate**, the system builds a small ranked list of **patient source rows** (demographics, conditions, labs, medications — each with a stable string id). Matching lexical overlap and resolved codes contribute to the score; trial metadata rows exist for context but are not mixed into the patient ranking list.

**What is allowed to conclude:** **Nothing about pass/fail changes.** The deterministic verdict and reason stay as they were. The system only **appends** structured evidence rows (labels, values, dates, codes, retrieval score and reasons) so a human (or a later process) can see what rows were surfaced.

**Billing:** No LLM call for this attachment step.

---

## 3. Bounded adjudication (`llm_use_level`)

**What runs:** Same retrieval as above, but for each **still-indeterminate** criterion with at least one retrieved row, a **structured-output LLM** is invoked. Its prompt includes: assumption mode text, full criterion JSON, the deterministic verdict, a short trial context string, and the formatted retrieved rows only — **not** the full narrative chart.

**What the model returns:** A raw predicate verdict (`pass` / `fail` / `indeterminate`), a small closed reason enum, **mandatory patient row ids** for any decisive pass/fail, and a short rationale.

**Fail-closed citation rule:** If the model emits pass or fail but cites **no** valid patient row ids from the retrieved set, the implementation **downgrades** the outcome to **indeterminate (human review required)** with an explicit rationale that citations were missing — decisive answers must be anchored to provided rows.

**Assumption mode in the prompt:** Open world is reinforced (“absence of a row is not proof of absence”); closed world allows the model to treat the retrieved slice under the stated contract.

**Polarity:** The model outputs the **raw** predicate; the same code path as the deterministic matcher then applies inclusion/exclusion and negation.

**Telemetry:** Each adjudication call records model id, prompt/adjudicator version ids, tokens, estimated USD, latency, and criterion index for dashboards and eval cost columns.

---

## 4. How this differs from the LangGraph “critic” loop

The **critic** is an **optional LangGraph-only** pass that reviews the whole rollup for process issues (polarity smells, extraction disagreements, etc.) and may trigger targeted re-runs. It is controlled by a **separate boolean** on the graph entry point, **not** by the `llm_use_level` switch used for patient-evidence retrieval.

The type system includes a **`critic`** value alongside other LLM-use levels for forward-looking telemetry enums; the **imperative** scoring path’s post-matching attachment logic keys only off **none**, **retrieval_only**, and **bounded_adjudication**. Treat **critic** as a graph concern, not a patient-evidence mode.

---

## 5. Practical reading order for reviewers

1. Pick **assumption mode** first — it answers “may I treat missing structured rows as negative?”
2. Pick **LLM use level** second — it answers “do I only see ranked rows, or may an LLM override indeterminates using those rows?”
3. Use **`evidence_under_assumption`** on verdicts to audit which rows only make sense if closed-world completeness holds.
4. Patient-evidence reports compare a label row only to runs with the same `matcher_assumption_mode`; mismatches are counted in the `Mode skipped` column instead of being treated as wrong verdicts.

Related: `docs/fhir-patient-processing.md` (where patient rows come from), `docs/patient-evidence-retrieval-architecture.md`, `docs/patient-evidence-labeling-guide.md`.
