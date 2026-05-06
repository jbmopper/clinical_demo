# Known limitations and scope boundaries

What the demo **does not** claim, and where **Synthea + curated trials** stop being faithful proxies for real screening programs.

---

## 1. Disease and cohort focus

- **Cardiometabolic-heavy** eval slices (T2DM, HTN, lipids, CKD) are the statistical core.
- **Oncology / NSCLC** trials exist as a **stretch** slice — patient synthetic data and note absence mean biomarker/staging criteria are **not** validated end-to-end; default patient-evidence calibration scope **excludes** oncology rows unless widened deliberately.

---

## 2. Chart completeness assumptions

- **Open world (default)** explicitly models incomplete charts: missing rows are **not** automatic negatives for conditions/meds/temporal events.
- **Synthea** omits many real-world artifacts (imaging narratives, rich clinician free-text, social determinants beyond coarse condition coding) — criteria depending on those fields will skew **indeterminate** even though v0 `DocumentReference` note rows are now retrievable.

---

## 3. Extractor and matcher ceilings

- **Free-text criteria** defer to human review in deterministic mode; LLM matcher exists on **graph path only** for those kinds.
- **Extractor mention F1 vs Chia** measures only a **subset** of Chia (entity mentions), not relations or OR-groups.
- **Composite OR/AND criteria** now have a native extractor/fixer parent/subcheck contract, calibration-time scaffolding, and a standalone truth-table helper, but the main scorer does not yet consume composite groups.
- **Temporal windows** in the future direction are limited; future-window criteria return unsupported mood/path.
- **Hypothetical mood** criteria (planned procedures) return indeterminate — no planned-event patient model.

---

## 4. Terminology and units

- Unmapped trial phrases stay **indeterminate** even under closed-world — terminology failures must not masquerade as clinical negatives.
- Lab unit conversion is **whitelist-only**; anything outside returns **unit mismatch** rather than guessing.

---

## 5. LLM constraints

- **No multi-model router in production path** — cost-quality sweeps are future work; current defaults pin a single model snapshot for extractor/adjudicator unless settings overridden.
- **Critic loop** improves process traceability but is opt-in and graph-local; it is not a clinical safety validator by itself.
- **Bounded adjudicator** sees only retrieved rows — cannot infer from hidden chart sections.

---

## 6. Claims **not** supported yet

- “**TrialGPT leaderboard numbers**” — only a local export scaffold exists.
- “**MIMIC-calibrated** production matcher” — governance documented, adapter not shipped.
- “**Full note-aware eligibility**” — note ingestion/retrieval v0 exists, but there is no validated note-ranking policy, no MIMIC-calibrated note behavior, and deterministic free-text criteria still require review/adjudication.
- “**Live ClinicalTrials.gov search agent**” — trials are **pre-curated** files.

---

## 7. Regulatory / deployment framing

This repository is a **portfolio / research demo**: no autonomous enrollment, no validated medical device claims, no multi-tenant PHI storage story in code.

Related: `docs/data-provenance-and-artifact-policy.md`, `docs/mimic-iv-calibration-and-governance.md`, `docs/free-text-note-evidence-design.md`.
