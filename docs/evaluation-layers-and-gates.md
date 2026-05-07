# Evaluation layers and gates

How automated **layers**, **CLI workflows**, and **regression scripts** fit together. Names follow the modules that implement them.

---

## 1. Deterministic unit tests (`pytest`)

- Broad coverage: matcher modes, FHIR loader edge cases, retrieval scoring, adjudicator fail-closed citations, API contracts, graph smoke paths.
- **Gate:** CI expectation is green tests + lint + typecheck per project conventions — first line of defense before any LLM spend.

---

## 2. Layer 1 — structured seed alignment

**Question:** For seed pairs with mechanical **min age / max age / sex** expectations, does the matcher’s structured pass/fail/indeterminate agree with the seed cell?

**Inputs:** A persisted eval run (`RunResult`) plus the seed JSON’s expected cells.

**Coverage limits:** Only fields listed in the layer-1 covered set; **healthy volunteers** and some other seed columns are skipped as uncoverable with the current extractor schema — counts appear in the report so the gap is visible.

**Gate:** Operational (report disagreements); not always a hard CI fail unless you wire one.

---

## 3. Layer 2 — Chia entity mention F1

**Question:** On Chia-held eligibility text, does extractor **mention** multiset overlap Chia **entity** multiset (vocabulary-filtered)?

**Command:** Dedicated eval subcommand with optional sampling, caching extractions under a separate directory from CT trials.

**Gate:** Baseline JSON snapshots checked in under `eval/baselines/` for trend viewing; optional hard threshold is a team policy choice.

---

## 4. Layer 3 — LLM judge vs matcher

**Question:** For stratified targets from a run, does a structured **judge** model label matcher verdicts `correct` / `incorrect` / `unjudgeable` with rationale?

**Artifacts:** Persisted judge reports consumed by calibration UIs and by patient-evidence target selection.

**Gate:** Human calibration on a small slice is expected before trusting judge numbers alone.

---

## 5. Patient-evidence calibration and report

**Question:** Against hand labels (`expected_matcher_verdict`, citations), how accurate are runs under `none` vs `retrieval_only` vs `bounded_adjudication`? What are abstention and citation agreement rates? How much adjudicator cost?

**Inputs:** `eval/runs.sqlite` (or equivalent) **plus** JSON label file.

**Gate flags:** Scripts can require **minimum usable label count** before exiting zero — intentionally fails when labels are still empty so nobody publishes bogus accuracy.

**Operator path:** Use `docs/patient-evidence-eval-runbook.md` for the current sequence: deterministic eval, private calibration packet, public summary export, privacy gate, then labeling/reporting.

---

## 6. Terminology regression gate

**Question:** Did any surface we previously resolved backslide into top unmapped counts?

**Inputs:** Fresh eval diagnostics JSON + resolved-surface watchlist JSON.

**Exit code:** Non-zero if regressions found — suitable for CI.

---

## 7. Bounded adjudication smoke vs full

- **Smoke:** Tiny limit on pairs or criteria with stub clients in tests — no network.
- **Full:** Whole seed with live OpenAI — costful; typically manual or budgeted job. Reporting should always record **model + versions + assumption mode + llm_use_level**.

---

## 8. Red-team set (planned / partial)

Adversarial cases (negation, temporal traps, prompt injection strings) belong in a **tracked fixture suite** once authored — many items still live in planning docs rather than a single consolidated JSON gate. When added, they should run under **`pytest`** or a dedicated eval recipe so they cannot rot.

---

## 9. Benchmark scorecards

- **Local TrialGPT/TREC scaffold:** export JSON + optional ranking metrics once relevance labels exist.
- **Baselines directory:** stores diagnostics summaries and small JSON manifests; large per-case report dumps are gitignored by pattern.

---

## 10. Recommended CI ordering (cost-aware)

1. Unit + lint + typecheck
2. Terminology regression script on pinned diagnostic + watchlist
3. Optional: layer-1 render on cached sqlite from a committed baseline run
4. LLM-heavy jobs **nightly** or manual — not on every push

Related: `docs/patient-evidence-eval-runbook.md`, `docs/patient-evidence-labeling-guide.md`, `docs/trec-trialgpt-benchmark-plan.md`, `docs/terminology-mapping-architecture.md`.
