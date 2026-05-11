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

**Current interpretation rule:** Treat small human-label pilots as directional, not scorecard-final. A 22-label local pilot showed `retrieval_only` had no labeled verdict movement while bounded adjudication reduced abstention but produced at least one wrong decisive verdict. Follow-up work added correlatable free-text promotion and assumption-aware patient-evidence reporting; a fresh closed-world local pilot run moved the matching-mode subset to `80.0%` accuracy and `40.0%` abstention. The next gate is more human labels, not broader LLM adjudication: push the local packet toward at least `40/60` usable labels, then compare open-world and closed-world subsets separately.

---

## 6. Terminology regression gate

**Question:** Did any surface we previously resolved backslide into top unmapped counts?

**Inputs:** Fresh eval diagnostics JSON + resolved-surface watchlist JSON.

**Exit code:** Non-zero if regressions found — suitable for CI.

---

## 7. Compiler parity and closed-world gates

**Question:** Does compiled-predicate execution match, improve, or regress
against the legacy matcher-input path?

**Inputs:** A `CriterionCompilationResult`, patient profile, trial, and matcher
assumption mode. The parity harness runs both deterministic execution sources:
legacy `matcher_inputs` and opt-in `compiled_predicates`.

**Gate shape:** Initially report-only. Classify each criterion as same,
compiled improved, compiled regressed, or changed. The next hard gate should
block closed-world eval runs when a structured criterion has neither an
executable compiled predicate nor an allowed review/unsupported class.
The concrete APIs are `compare_compilation_parity(...)`, `ParityReport`, and
`ClosedWorldValidationResult`.

**Current artifacts:** `ScorePairResult` carries `compiler_validation` and
`compiler_gap_queue`; eval diagnostics aggregate compiler coverage, unresolved
gaps by kind/stage/domain, and closed-world blockers. Medication-class surfaces
with reviewed entries compile through member RxNorm resolution before becoming
executable predicates, so missing class members remain visible as compiler
gaps instead of silently narrowing the class. Use
`uv run python scripts/eval.py compiler-review --run-id <run> --output <path>`
to export private reviewer rows for unresolved compiler gaps.

**CI gate:** Once a baseline is expected to be compiler-complete, use
`uv run python scripts/check_compiler_diagnostics.py --diagnostics <diagnostics.json> --require-compilation --max-closed-world-blocking-cases 0`.
During rollout, set nonzero thresholds from the current baseline and tighten
them as reviewer fixes land.

**Why separate from terminology gates:** Terminology regressions answer "did a
surface stop mapping?" Compiler parity answers "did the new predicate source
change patient-level verdict behavior?" Both are needed before
`matcher_execution_source="compiled_predicates"` can become default.

---

## 8. Bounded adjudication smoke vs full

- **Smoke:** Tiny limit on pairs or criteria with stub clients in tests — no network.
- **Full:** Whole seed with live OpenAI — costful; typically manual or budgeted job. Reporting should always record **model + versions + assumption mode + llm_use_level**.

---

## 9. Red-team set (planned / partial)

Adversarial cases (negation, temporal traps, prompt injection strings) belong in a **tracked fixture suite** once authored — many items still live in planning docs rather than a single consolidated JSON gate. When added, they should run under **`pytest`** or a dedicated eval recipe so they cannot rot.

---

## 10. Benchmark scorecards

- **Local TrialGPT/TREC scaffold:** export JSON + optional ranking metrics once relevance labels exist.
- **Baselines directory:** stores diagnostics summaries and small JSON manifests; large per-case report dumps are gitignored by pattern.

---

## 11. Recommended CI ordering (cost-aware)

1. Unit + lint + typecheck
2. Terminology regression script on pinned diagnostic + watchlist
3. Compiler parity report on cached deterministic fixtures
4. Optional: layer-1 render on cached sqlite from a committed baseline run
5. LLM-heavy jobs **nightly** or manual — not on every push

Related: `docs/patient-evidence-eval-runbook.md`, `docs/patient-evidence-labeling-guide.md`, `docs/trec-trialgpt-benchmark-plan.md`, `docs/terminology-mapping-architecture.md`.
