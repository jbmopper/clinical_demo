# MIMIC note privacy policy

This policy defines how future MIMIC-IV and MIMIC-IV-Note data may be used in this repo. It is a product and engineering control for credentialed clinical data. It supports compliance discipline, but it is not a claim of HIPAA certification.

The core invariant is:

> Privacy wrapping must happen after deterministic retrieval/matching and before outbound model, trace, or export emission.

That gives the intended boundary:

```text
raw credentialed data -> local deterministic retrieval/matching -> privacy wrapper -> LLM/tracing/export
```

---

## 1. Scope

This policy applies to any data derived from MIMIC-IV, MIMIC-IV-Note, or other credentialed patient-note corpora, including:

- note bodies and snippets;
- row-level structured source records;
- source table identifiers and note identifiers;
- dates, times, and intervals as stored in the source;
- patient, admission, stay, encounter, document, or resource identifiers;
- local eval runs, calibration packets, screenshots, traces, and exported artifacts.

It does not apply to public trial text from ClinicalTrials.gov, Chia fixture text already licensed for this repo, or hand-authored synthetic fixtures that are not copied from credentialed data.

---

## 2. Allowed Surfaces

| Surface | MIMIC note policy |
|---------|-------------------|
| Local deterministic retrieval and matching | Allowed on a credentialed machine. Raw data may be used locally when required for correctness. |
| Local reviewer UI | Allowed for credentialed reviewers only. Must stay local or inside an approved private environment. |
| Non-HIPAA LLM prompts | Raw MIMIC note text is forbidden. Use the privacy wrapper or summary-only derived features. |
| HIPAA-eligible or approved sensitive LLM paths | Allowed only when explicitly configured and still traced/exported through policy controls. |
| Traces, logs, OTel, Langfuse-like sinks | Raw note text, source identifiers, exact patient identifiers, and exact source dates are forbidden. |
| Git, public PRs, public issues, docs, talks | Row-level MIMIC content is forbidden. Use aggregate, sanitized, or synthetic outputs only. |
| CI | Must not require MIMIC credentials or raw MIMIC files. |

---

## 3. Data Classification

Treat these as private by default:

- clinical note text and snippets, even if short;
- note identifiers, admission/stay/encounter identifiers, and original source row ids;
- exact dates, exact times, and raw shifted timelines;
- reviewer rationales that quote source rows;
- prompt payloads, model refusals, or error text that may echo prompt content;
- eval sqlite rows containing `ScorePairResult` JSON or retrieved source contexts.

Treat these as publishable only after explicit review:

- aggregate counts and rates;
- histograms that cannot recover row-level facts;
- model/config metadata with no patient identifiers;
- sanitized public summaries with `artifact_safety` metadata;
- synthetic examples manually rewritten so they are not source paraphrases.

---

## 4. Runtime Boundary

Raw credentialed data may feed local deterministic logic:

- source-row projection;
- lexical/code retrieval;
- composite subcheck retrieval;
- deterministic matcher predicates;
- local reviewer workflows.

Before anything leaves that local deterministic layer, the system must apply the privacy boundary:

- `llm_prompt` for non-HIPAA or default external model calls;
- `trace` for observability payloads;
- `metadata` for identifiers and run labels;
- `public_export` for files intended for git, PRs, docs, demos, or public reports.

The privacy layer must preserve citeability and matcher semantics:

- keep local row ids such as `patient:000` only when they are run-local citation ids, not source ids;
- keep criterion index, subcheck id, composite operator, citation id, code, numeric value, and unit when needed;
- do not anonymize before deterministic retrieval or matching;
- do not drop `COMPOSITE SUBCHECK CONTEXT` from adjudicator prompts.

---

## 5. Dates and Timing

Dates are policy-dependent:

- Local deterministic matching may use raw local dates when needed for age, temporal windows, or ordering.
- Outbound prompts and traces should use relative timing when possible, such as age, days since event, or months before `as_of`.
- Public artifacts should avoid exact patient dates entirely unless the date is synthetic and clearly marked.
- Trial dates and trial eligibility text are public unless combined with patient evidence in a way that reveals patient timing.

---

## 6. Public Artifacts

Public artifacts must be default-deny. A file derived from patient evidence may be committed only when it is one of:

- `summary-only`: aggregate counts, rates, run/config metadata, no row-level evidence;
- `sanitized`: row-level content removed or transformed under an explicit export contract;
- `synthetic`: generated or hand-authored examples not copied from credentialed source text.

Every public eval artifact must include explicit safety metadata, for example:

```json
{
  "artifact_safety": {
    "public_export": "sanitized",
    "contains_real_patient_data": false,
    "summary_only": true
  }
}
```

Forbidden in public artifacts:

- note rows or note snippets;
- source note identifiers;
- raw MIMIC source identifiers;
- exact patient identifiers;
- exact patient dates;
- reviewer rationale quoting source text;
- model inputs, outputs, refusals, or errors that include prompt payloads.

The `public-artifact-privacy-gate` should be treated as a minimum automated backstop, not a substitute for review.

---

## 7. Local Storage

Credentialed data must live outside the repo, for example under a configured local data root. The repo may store code that reads from that root, but not the data itself.

Local-only outputs include:

- raw normalized MIMIC rows;
- note snippet candidate packets;
- calibration labels with row citations against private rows;
- sqlite eval databases;
- screenshots of reviewer UI containing row text;
- debugging traces with prompt payloads.

These outputs should be ignored by git and never attached to public PRs.

---

## 8. Review Gates

Before merging MIMIC-related work, reviewers should check:

- CI does not require MIMIC credentials.
- Raw data enters only local deterministic code paths.
- Non-HIPAA LLM calls use `llm_prompt` privacy wrapping.
- Observability uses `trace` and `metadata` privacy wrapping.
- Public exports use `public_export` and pass the artifact privacy gate.
- Composite context, subcheck ids, row ids, citation validation, codes, units, and numeric values still survive where they are semantically required.
- No generated calibration artifact contains note text, source identifiers, or row-level patient evidence unless it is explicitly local-only and untracked.

Related: `docs/mimic-iv-calibration-and-governance.md`, `docs/free-text-note-evidence-design.md`, `docs/data-provenance-and-artifact-policy.md`.
