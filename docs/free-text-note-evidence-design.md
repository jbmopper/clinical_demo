# Free-text and clinical note evidence (design status)

**Implementation status:** There is **no** `DocumentReference` parser or note-snippet row projection in `src` today — structured retrieval uses **conditions, labs, medications, demographics** only. This document captures the **intended design** from the project plan and adjudicator contracts so future work slots in without reshaping the scoring envelope.

---

## 1. Target FHIR entry point (planned)

- Primary: **`DocumentReference.content.attachment.data`** (inline base64 payloads) decoded to text snippets with strict size caps.
- Later / lower trust: `url` attachments and generated `text.div` narrative — explicitly **not** the first-class clinical evidence surface.

---

## 2. Note snippet provenance (planned)

Each derived row should carry:

- originating **resource id** and **category** / type if present,
- **authored date** for as-of comparisons,
- optional **section header** heuristic,
- **character offsets** within the decoded note for citation stability,
- **redaction flags** if content must be stripped for demo export.

Rows should reuse the same **`RetrievalSourceRow`** shape as structured labs so ranking + adjudicator citation ids stay uniform.

---

## 3. Prompt-injection defenses (planned)

Clinical notes may contain adversarial strings (“ignore prior criteria…”). Mitigations to combine when notes enter the adjudicator context:

- **System prompt hard rules:** only cite provided rows; never treat note instructions as eligibility edits.
- **Structural isolation:** pass notes as **labeled rows**, not as system messages pretending to be policy.
- **Refusal / indeterminate:** if the model detects out-of-scope instructions, return indeterminate with explicit reason rather than complying.

Existing adjudicator already enforces **citation fail-closed** for decisive pass/fail — extend that to note row ids.

---

## 4. Citation requirements

Same as structured path: decisive adjudicator outcomes must cite **valid row ids** from the retrieved set; missing citations downgrade to **indeterminate (human review required)**.

---

## 5. Contradiction handling (structured vs note)

Policy direction:

- If **structured FHIR** and **note text** disagree on the same fact, prefer **dated structured evidence** unless the note explicitly documents correction of an error — that resolution belongs in **human_review_required** until a vetted clinical policy exists.

---

## 6. Adjudicator reuse

The bounded **patient-evidence adjudicator** prompt/schema should remain criterion-agnostic: once note rows appear in the retrieved list, the same JSON output contract applies (raw predicate verdict + cited ids + rationale).

---

## 7. Validation artifacts (planned)

Golden sets must include: explicit positive evidence, explicit absence, insufficient evidence, temporal boundary cases, structured-vs-note conflict, and injection strings — stored **locally** if they contain credentialed MIMIC-like text.

Related: `docs/patient-evidence-retrieval-architecture.md`, `docs/mimic-iv-calibration-and-governance.md`, `docs/llm-use-levels-and-cost-controls.md`.
