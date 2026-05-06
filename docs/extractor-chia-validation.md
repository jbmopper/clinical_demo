# Trial text extraction: output shape and Chia-based validation

This note describes what the **criterion extractor** returns when given a trial’s eligibility prose (whether that prose comes from ClinicalTrials.gov curation or from a Chia corpus text file), and **how that output is compared to Chia** when you run the dedicated validation path. It avoids implementation identifiers; see the extractor and eval packages for code.

---

## 1. What the extractor returns (conceptual schema)

The model returns a single **envelope** with two conceptual parts: a **list of criteria** and **metadata**.

### 1.1 Top level

| Field | Role |
|--------|------|
| **Criteria** | Ordered list of atomic eligibility rules the model read out of the text. |
| **Metadata** | Optional self-reported notes from the model (ambiguity, skips, etc.). |

Alongside that (outside the model’s JSON), the system usually records **run metadata**: which model ran, prompt revision id, tokens, cost, latency. That supports regression tracking but is not part of the semantic extraction shape.

### 1.2 Each criterion row

Every row is one **checkable unit** the downstream matcher can try to resolve against a patient. Each row includes:

| Concept | Meaning |
|--------|--------|
| **Kind** | What family of rule this is: age, sex, condition present/absent, medication present/absent, numeric measurement threshold, time window, or a catch-all **free text** bucket when the model should not force a typed slot. |
| **Polarity** | Whether satisfying the rule **helps** enrollment (inclusion) or **hurts** it (exclusion), as read from the section of the protocol. |
| **Source text** | A verbatim excerpt of the trial eligibility wording this row is supposed to represent—used for citations and human review. |
| **Negated** | Whether the natural-language predicate is negated in scope (e.g. “no history of …”), independent of inclusion vs exclusion section. |
| **Mood** | Whether the criterion reads as current fact, hypothetical/planned, or historical—feeds temporal and interpretation behavior downstream. |
| **Typed payload** | Exactly **one** of several structured shapes is filled: age bounds, sex, condition phrase, medication phrase, measurement operator/threshold/unit, temporal window, or a free-text note. The kind tells which slot is active. |
| **Mentions** | A **flat list** of short spans: each has **surface text** and a **type label** drawn from a fixed vocabulary aligned with Chia-style **entity** categories (condition, drug, measurement, value, time, negation, mood, qualifier, etc.). |

### 1.3 How different parts are used later

- **Matcher and scoring** consume the **kind**, **polarity**, **negated**, **mood**, **typed payload**, and **source text**. They do **not** consume the mention list for matching logic.
- **Mentions** exist for **audit and evaluation**: they say “here are the phrases and labels the model thinks are salient inside this bullet,” in a vocabulary comparable to Chia’s entity types.

So the extractor is deliberately **“matcher-shaped”** for the core decision fields, with a **Chia-flavored annotation strip** (`mentions`) hung on each row for analysis—not a full Chia graph (no explicit OR-groups, binary relations, or equivalence sets in the model output).

---

## 2. What Chia provides on disk

For trials included in the Chia dataset, each inclusion or exclusion document is stored as:

- **Plain text** of that eligibility slice (the same string the extractor sees when you point the pipeline at Chia).
- A **standoff annotation file** with **typed entities** anchored to character spans in that text (conditions, drugs, values, temporal expressions, negation, etc.), plus richer structure the corpus also encodes (**relations**, **OR groups**, attributes).

The validation path described below uses **only the entity layer** as gold: type + textual span. It does **not** require the model to reproduce relations or groups.

---

## 3. How “validation against Chia” works (system behavior)

This is **not** something that runs every time you score a random curated trial against a patient. It is a **separate evaluation ritual** you run when you want to measure the extractor against Chia.

### 3.1 Inputs

1. **Chia side:** One inclusion or exclusion document (text + human entity annotations).
2. **Model side:** Run the **same** eligibility text through the criterion extractor (the prompt adds a short section header so the model knows inclusion vs exclusion). Optionally reuse a **cached** prior run so you do not pay for the API again.

### 3.2 What gets compared

The system builds two **bags of keys** (multisets: the same key can appear more than once if repeated):

- **Gold bag:** For every **human-annotated entity** in that Chia document whose type is in the extractor’s allowed mention-type vocabulary, add one key: *(entity type, normalized surface text)*. Entity types the extractor is not allowed to emit are **ignored** for scoring (they are tracked as “skipped gold” so you know the ceiling is capped by vocabulary overlap).

- **Predicted bag:** Walk **every** criterion row in the model output, and for **every** entry in that row’s **mentions** list, add the same kind of key: *(mention type, normalized surface text)*.

Normalization is lightweight (case, whitespace, a few punctuation tweaks)—no coding pipeline, no synonyms. This is intentionally a **string-level** fidelity check, not a clinical coding equivalence check.

### 3.3 What the scores mean

From those two bags the system computes overlap statistics you would expect from precision/recall/F1 on multiset overlap, plus optional **lenient** pairing when predicted text is almost the same span as gold (substring or token overlap), reported separately.

**Important limits:**

- **Only `mentions` participate** in the Chia comparison. If the model put everything into typed fields and left `mentions` empty, the predicted bag could be empty even when the structured criteria look good—so this metric is about **mention coverage**, not full end-to-end extraction quality.
- **Chia relations and OR-groups are not scored.** The model is not asked to output them in v0, so there is nothing comparable to align.
- **Structured criterion rows** (age, labs, etc.) are **not** directly compared to Chia’s graph; Chia is not a parallel list of “same atomic criteria.” The validation story is **entity-mention alignment**, not “identical criterion decomposition.”

### 3.4 What this validates in plain terms

You are answering: **On eligibility text where humans drew entity spans with Chia types, does our extractor’s optional mention tags cover the same phrases and labels, roughly, under a shared type vocabulary?**

You are **not** answering: “Does every ClinicalTrials.gov trial we curate automatically get a Chia grade?” **No**—unless that trial’s text is also part of a Chia file you explicitly run through this path.

---

## 4. End-to-end picture

| Stage | What happens |
|--------|----------------|
| **Normal product path** | Trial eligibility (e.g. from CT.gov JSON) → extractor envelope → matcher uses typed criteria + patient data; **mentions** are for humans and tooling, not matching. |
| **Chia validation path** | Chia slice text → same extractor → compare **flattened mentions** from all criteria to **Chia human entities** (type + text), vocabulary-filtered → report precision/recall/F1 and diagnostics. |

So: the extractor always speaks the **same JSON shape**. Chia is a **reference dataset** used in a **dedicated eval** to stress-test one slice of that shape (**mentions** vs **entities**). It is not wired into live enrollment logic as a gate.
