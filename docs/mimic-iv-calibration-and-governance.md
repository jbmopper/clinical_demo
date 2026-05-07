# MIMIC-IV calibration and governance

**Repository reality check:** There is **no MIMIC-IV adapter or loader** under `src/clinical_demo` today. Patient records consumed by scoring and eval are **Synthea FHIR bundles** (plus JSON manifests). This document captures **intended governance** from the project plan and how it should interact with this codebase **when** credentialed access exists — without implying MIMIC is already wired.

---

## 1. Purpose of a future MIMIC track

- Improve **realism** of evidence rows (messy units, sparse coding, note phrasing) for **local** calibration and retrieval/adjudication tests.
- Stress **note snippet** handling and **prompt-injection** defenses using credentialed text — not to ship MIMIC rows into the public demo.

---

## 2. Private-use boundaries

- **PhysioNet credentialing** is required for MIMIC-IV / MIMIC-IV-Note; access is individual, not “public internet.”
- **No raw MIMIC rows** in git: patient identifiers, dates as stored, and note bodies stay on local disk or credentialed storage only.
- **No reproduction** of MIMIC content in issues, PRs, docs with verbatim patient text, or public baseline JSON — summaries must be **aggregate** or **synthetic**.

---

## 3. Local data-root rules (planned)

- Configure a **`MIMIC_DATA_ROOT`** (or equivalent) **outside** the repo; add to `.gitignore` if any export scripts write there.
- Optional BigQuery configuration for hosted MIMIC — still treated as **secret + local**; query results must not be committed.

---

## 4. Adapter shape (intended)

Map `hosp` / `icu` (and later note tables) into the **same citeable row model** structured retrieval already uses — stable ids, codes, dates relative to protocol policies, and redacted display strings suitable for adjudicator prompts **inside** the credentialed environment.

**Downstream code** (retrieval ranker, adjudicator, eval calibration) should not branch on “Synthea vs MIMIC” once rows normalize.

---

## 5. Derived artifacts policy

| Allowed locally (credentialed machine) | Forbidden in public repo / reports |
|----------------------------------------|-------------------------------------|
| Aggregated metrics (counts, histograms of unit types) | Row-level exports, note excerpts, timing that could re-identify |
| Synthetic fixtures **inspired** by patterns (manual rewrite) | Copy-paste snippets of MIMIC notes |
| Private eval runs sqlite blobs | Same sqlite committed to git |

---

## 6. Relationship to this repo’s eval gates

Until an adapter lands, **terminology regression gates**, **patient-evidence JSON labels**, and **Chia layer-2** remain the authoritative automated signals. MIMIC is explicitly **non-blocking** for those tracks in the current plan.

When implemented, add a **separate** local-only makefile / script target so CI never accidentally depends on PhysioNet credentials.

Related: `docs/mimic-note-privacy-policy.md`, `docs/data-provenance-and-artifact-policy.md`, `docs/free-text-note-evidence-design.md`.
