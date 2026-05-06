# Clinical Trial Eligibility Co-Pilot — Project Plan

> **Purpose.** Build a portfolio-grade demo for a 20-minute presentation in the
> final round of a Generative AI Forward Deployed Engineer interview at KPMG's
> AI & Data Labs practice.
>
> **Companion docs.** See `description.md` for the user/workflow narrative and
> high-level architecture; this file is the working build plan, scope contract,
> and decision log. When the two disagree, this file wins.

---

## 0. Current state (updated before every commit)

> Single source of truth for "where are we." If you're a future
> session resuming from a summary, **trust this section over the
> summary** — it's git-tracked and last-touched right before the
> head commit. Detailed task history lives in §6; per-decision
> rationale lives in §12.

- **Active phase:** Phase 2 — Workflow + eval.
- **Current correction:** matcher v0.2 (PLAN 2.19) makes
  `matcher_assumption_mode` change behavior, not just metadata, and
  fixes the silent-flip bug in v0.1. Before: `_match_condition` /
  `_match_medication` / `_match_temporal_window` returned raw `fail`
  on mapped-but-absent concepts regardless of mode. For
  `condition_present` inclusion criteria that came out as the
  expected hard `fail`; for `condition_absent` inclusion criteria
  the polarity helper silently flipped that to `pass` — so the
  matcher was claiming the patient *did not have* the condition any
  time we couldn't find a row, which is the literal definition of
  conflating absence-of-evidence with evidence-of-absence. Now:
  `open_world` returns `indeterminate(no_data)` on mapped-but-
  absent for those three kinds (an honest "the record is silent");
  `closed_world_eval` and `closed_world_demo` opt back into
  absence-as-negative for the same kinds and stamp
  `evidence_under_assumption=True` on the verdict so audits can
  pivot on which decisions depend on the closed-world contract.
  Labs (`measurement_threshold`) deliberately stay
  `indeterminate(no_data)` in every mode — a missing lab is not the
  same as a normal lab, and the user prefers N/A visibility. The
  unmapped-concept guardrail is preserved: terminology gaps remain
  `indeterminate(unmapped_concept)` in every mode, so closed-world
  cannot mask mapping failures (D-73). The case-level rollup
  gains a fourth state `pass_pending_review` for "no fails, every
  remaining indeterminate is `human_review_required`" — i.e.
  structured criteria all decided positively and only free-text is
  left for a human eye. `MatchVerdict` now carries `assumption` and
  `evidence_under_assumption` for the trail.

  Twin baselines (`eval/baselines/2026-05-04-2.19/`):
  `7ad02d2ce814` (open_world) and `505d88763f00`
  (closed_world_eval), same seed, same binding strategy, no LLM. The
  closed-world numbers exactly match the previous v0.1 baseline
  (`pass`=110 / `fail`=32 / `indeterminate`=919 / `ok`=142),
  confirming v0.2 closed-world is a faithful re-implementation of
  the prior implicit behavior; open-world is the new honest default
  (`pass`=77 / `fail`=21 / `indeterminate`=963 / `ok`=98 / `no_data`
  62 vs 18). The 44-criterion swing between modes is exactly the
  mapped-but-absent verdicts, which is the toggle's whole point.
  `pass_pending_review` does not fire on the current eval seed yet
  because every case carries at least one non-free-text
  indeterminate (composites or missing labs); it becomes a real
  state once Phase 3 LLM disambiguation eats into the
  unmapped-concept floor.

  Previous correction (still relevant): open terminology resolution
  is genuinely open for conditions and labs via `UMLSSearchClient`
  (SNOMED `searchType=exact`, LOINC `searchType=words` + numeric
  Parts filter); composites short-circuit to
  `composite_unhandled`; hand-curated `extractor_bug` /
  `out_of_scope` classifications win over resolver hits in the work
  queue. UMLS fair-use is ~20 req/s with no published daily cap;
  one-time cold warmup of ~149 unique surfaces, then served from
  the on-disk surface cache. New snapshot on 2026-05-05:
  `eval/baselines/2026-05-05/open_resolver_none_diagnostics.json`
  (`17fc2bc0a9cd`) moves deterministic no-LLM `unmapped_concept` to
  445/1061 (41.9%), down 106 criteria / 9.2 pp from the 2026-05-04
  no-LLM baseline; the paired
  `open_resolver_surface_work_queue.json` captures the remaining
  top surfaces as composites, out-of-scope data-model gaps,
  ambiguity, extractor bug, or true misses. `scripts/check_terminology_regressions.py`
  now fails if a surface preserved in a legacy `status=resolved` watchlist
  reappears in a run's `top_unmapped_surfaces`; the first watchlist
  lives at `eval/baselines/2026-05-05/resolved_surface_watchlist.json`.
- **Last completed:** PLAN task 2.21 first slice —
  **deterministic criterion fixing layer.** Added
  `clinical_demo.extractor.fix.fix_extracted_criteria` between extraction
  enrichment and matching in both imperative `score_pair` and LangGraph
  `extract_node`. The first fixer pass normalizes known condition and
  measurement surfaces, infers systolic/diastolic blood pressure when source
  text says which one, converts zero-window diagnosis-shaped temporal rows
  such as "T1D diagnosis" into condition criteria, and routes unsafe composites
  to cited `free_text` review rows instead of letting them fall through as
  generic atomic terminology misses. The original `source_text` is preserved
  and fixer provenance is appended to extraction metadata / free-text notes.
  Verification: `uv run pytest` 677/677, targeted criterion-fixer /
  scoring / graph / terminology tests 110/110, targeted ruff clean, targeted
  format check clean, targeted mypy clean.
  Previous: PLAN task 2.20 first slice —
  **mapping expansion + `mapped` terminology language.** Renamed work-queue,
  regression-gate, and diagnostic report language from `resolved` to `mapped`
  while keeping legacy `status=resolved` watchlists and old surface-cache
  fingerprints readable. Added high-confidence mappings for type 1 diabetes
  / T1D diagnosis, C-peptide concentrations, and qualified hypertension
  surfaces such as "mild to moderate hypertension." Curated local mappings now
  override stale `true_miss` cache rows so adding a mapping case actually
  repairs old misses. `scripts/check_terminology_regressions.py` now accepts
  `--mapped-work-queue` and keeps `--resolved-work-queue` as a deprecated
  alias. Verification: `uv run pytest` 671/671, targeted terminology /
  diagnostics tests 86/86, targeted ruff clean, targeted format check clean,
  targeted mypy clean, both mapped and legacy regression-gate CLI invocations
  clean, and `git diff --check` clean.
  Previous: Coming-week calibration/reporting slice 1 —
  **patient-evidence report + local TrialGPT/TREC scaffold.** After merging
  PR #2/#3/#4 into `main`, added a patient-evidence eval report that compares
  one or more persisted runs against
  `eval/calibration/patient_evidence_labels.json`, including verdict accuracy
  against `expected_matcher_verdict`, abstention rate, citation agreement,
  case-level rollup movement, and adjudicator cost/call/token totals. Added
  `scripts/eval.py patient-evidence` with `--strict-labels` and
  `--min-usable-labels` gates; current labels are still 0/60 usable, so the
  40-label gate fails as intended. Added a local TrialGPT/TREC-style benchmark
  scaffold (`clinical_demo.evals.trial_benchmark`) plus
  `scripts/export_trial_benchmark.py`; the first export writes 27 patient
  summary queries, 49 candidate trial rows, and 60 criterion cases to
  `eval/benchmarks/local_trialgpt_trec_seed.json`. Verification: focused
  patient-evidence / benchmark tests 12/12, targeted ruff clean,
  `uv run mypy src scripts tests/evals/test_patient_evidence.py
  tests/evals/test_trial_benchmark.py` clean, JSON validation for the benchmark
  artifact clean, `uv run pytest` 666/666, full ruff/format checks clean,
  terminology regression gate clean, and `git diff --check` clean. Follow-up
  planning now explicitly tracks MIMIC-IV access/use and official
  TREC/TrialGPT benchmark ingestion instead of treating the local benchmark
  scaffold as the end state.
  Previous: PLAN task 2.18 regression gate + 2026-05-05
  **open-resolver baseline snapshot.** Created
  `eval/baselines/2026-05-05/` with open-world deterministic
  (`17fc2bc0a9cd`), closed-world deterministic (`5a0e5717803c`), and
  retrieval-only (`d659d6ff19bb`) diagnostics, plus
  `open_resolver_surface_work_queue.json`, `resolved_surface_watchlist.json`,
  and `SUMMARY.md`. Bounded adjudication was intentionally not rerun under the
  current low weekly LLM budget. Added `scripts/check_terminology_regressions.py` plus
  `find_resolved_surface_regressions` / renderer helpers in
  `clinical_demo.terminology.work_queue`. Each baseline scored 47/49 cases,
  with the same 2 deceased-patient refusals as prior baselines. Verification:
  `uv run pytest tests/terminology/test_work_queue.py tests/terminology/test_cache.py
  tests/terminology/test_resolver.py` 78/78, targeted ruff clean, all baseline
  JSON artifacts validate with `uv run python -m json.tool`, and
  `uv run python scripts/check_terminology_regressions.py --diagnostics
  eval/baselines/2026-05-05/open_resolver_none_diagnostics.json
  --resolved-work-queue eval/baselines/2026-05-05/resolved_surface_watchlist.json`
  reports no mapped terminology regressions. PR #2 and PR #3 were merged into
  `main` on 2026-05-05, followed by PR #4 documenting this coming-week plan.

### Coming week plan (2026-05-05 to 2026-05-12)

- **Target effort:** 20-30 hours.
- **Primary outcome:** calibrated patient-trial evidence matching with credible
  cost/quality reporting: trials + patients go in, relevant patient evidence is
  retrieved, bounded adjudication is measured against human labels, and the
  results can support the presentation's cost/quality story.
- **Operating rule for LLM/API spend:** use deterministic checks, retrieval,
  citations, and regression gates first; then use LLM calls where they add
  actual product behavior: criterion repair/normalization, bounded
  patient-evidence adjudication, note/free-text evidence, ambiguity review, and
  critic/revision. LLMs may propose or adjudicate against cited evidence; they
  must not become gold labels or silently paper over unmapped concepts.
- **Task sequence:**
  1. ~~Merge PR #2, then PR #3, preserving the baseline/gate stack.~~ Done;
     PR #4 also merged the documentation update.
  2. Fill `eval/calibration/patient_evidence_labels.json`: target 60/60 rows;
     minimum useful gate is 40/60. Each filled row needs `label`,
     `expected_matcher_verdict`, cited source row IDs when evidence exists,
     reviewer, and rationale.
  3. ~~Add calibrated patient-evidence reporting across `none`,
     `retrieval_only`, and `bounded_adjudication`: verdict agreement against
     expected matcher verdicts, citation agreement, abstention rate, cost,
     calls/tokens, and case-level rollup movement.~~ Done for report plumbing;
     meaningful metrics still wait on filled labels.
  4. ~~Add a TrialGPT/TREC-style local benchmark scaffold that mirrors
     retrieval -> criterion matching -> ranking. This week is a local exporter
     from the existing curated seed, not full official dataset ingestion. Use
     NLM TrialGPT and NIST/TREC Clinical Trials as framing references:
     <https://www.ncbi.nlm.nih.gov/research/trialgpt/about/> and
     <https://trec.nist.gov/data/trials.html>.~~ Done as a local schema,
     exporter, and initial seed artifact.
  5. Continue mapping expansion and rename status language from `resolved` to
     `mapped` where the system means "this surface has a usable concept/code
     mapping." Keep compatibility for existing `resolved_*` artifacts until a
     small migration lands, but new docs/reports should say `mapped`.
  6. Add the criterion fixing layer: normalize criterion surfaces/units/polarity,
     route unsafe non-atomic phrases into `human_review_required`, and add an
     explicit composite representation before splitting OR/AND bundles into
     ordinary matcher rows. Key invariant: an OR bundle such as ADA
     hyperglycemia criteria must not become several top-level inclusion rows,
     because the current scorer treats the criteria list as an AND contract.
  7. Bring free-text/note patient-evidence LLM v0 forward. Done for note
     ingestion/retrieval v0 (`DocumentReference.content.attachment.data` ->
     citeable note rows), but docs and plan language need cleanup and the next
     behavior slice is composite-aware evidence review/adjudication over
     retrieved structured/note rows.
  7a. Add reviewer-facing composite line items before deeper matcher changes:
     detect/represent `any_of` / `all_of` subchecks with stable ids, retrieve
     evidence per subcheck, and show the subcheck evidence in the calibration
     UI. Do not let line items alter eligibility rollup until matcher semantics
     explicitly understand composite groups.
  7b. Tighten the calibration UI around matcher assumption mode. `open_world`
     remains the clinical default; `closed_world_eval` is a synthetic-eval
     override for selected closed data types only. Rows whose matcher result is
     clearly open-world `no_data`, free-text review, labs, or unmapped concepts
     should either disable closed-world choices or display an inline warning
     before the reviewer can persist that assumption.
  8. Start the MIMIC-IV data track while access is pending: document the local
     data-root contract, `.gitignore`/artifact rules, table-to-evidence mapping,
     and minimum cohort plan. After credentialed access lands, use MIMIC-IV
     as private calibration/enhancement input for patient data files: improve
     schema coverage, note/evidence retrieval, and realism checks without
     reproducing MIMIC records in system outputs. Do not commit raw MIMIC data,
     derived row-level excerpts, or any credentialed artifact to the repo.
  9. Promote the TrialGPT/TREC work from local scaffold to external benchmark
     plan: obtain the official TREC Clinical Trials topics/corpus/qrels and
     TrialGPT code/data references, add an adapter into the local benchmark
     schema, and report retrieval/ranking metrics separately from the local
     patient-evidence calibration metrics.
- **Assumptions:** oncology remains out of the core scope this week; broad
  multi-model sweeps wait until patient-evidence labels have enough signal;
  LLM-generated labels must not be treated as gold.

- **Previous completed context:** PLAN task 2.19 — **closed-world matcher
  semantics + open-world honesty fix.** Bumped `MATCHER_VERSION` to
  `matcher-v0.2`. `match_criterion` /  `match_extracted` now take
  `matcher_assumption_mode` as a kwarg, threaded down through
  `_dispatch` to per-kind handlers. Per-kind handler signature
  changed to a 5-tuple
  `(verdict, reason, rationale, evidence, evidence_under_assumption)`
  via `_HandlerResult`. `_match_condition`, `_match_medication`,
  `_match_temporal_window` got an explicit closed-world branch that
  returns `fail` with `evidence_under_assumption=True` for
  mapped-but-absent inputs under `closed_world_eval` /
  `closed_world_demo`; the open-world branch returns
  `indeterminate(no_data)`. `_match_measurement` and the demographics
  / age / sex paths return `evidence_under_assumption=False` — labs
  stay `no_data` in every mode. `unmapped_concept` is unchanged in
  every mode (D-73 guardrail). `MatchVerdict` gained `assumption:
  MatcherAssumptionMode | None` and `evidence_under_assumption:
  bool`. `score_pair` and `score_pair_graph` thread the mode into
  `match_extracted`; the graph carries the mode on `ScoringState`
  so `deterministic_match_node`, `revise_node`, and
  `llm_match_node` can pick it up without closure tricks.
  `EligibilityRollup` gained `pass_pending_review` and `_rollup`
  reason-aware: `fail > non-HRR indeterminate > HRR-only-indeterminate
  (pass_pending_review) > pass`. Tests updated:
  `tests/matcher/test_matcher.py` now has explicit open vs
  closed-world tests for `condition_present`, `condition_absent`,
  `temporal_window`, and the unmapped-concept guardrail; the
  pre-fix "absent silently flips to pass" test was rewritten to
  pin both modes' new behaviors.
  `tests/scoring/test_score_pair.py` got
  `pass_pending_review` integration + helper coverage and updated
  `_build` callsites for the new required kwargs.
  `tests/adjudication/test_patient_evidence.py` similarly. Twin
  no-LLM baselines saved at `eval/baselines/2026-05-04-2.19/`
  (`open_world_diagnostics.json`, `closed_world_eval_diagnostics.json`,
  `SUMMARY.md`). Verification: `uv run pytest` 656/656,
  `uv run ruff check .` clean.
  Previous: PLAN task 2.17 final slice + 2.18 first slice —
  **open UMLS/LOINC search wired into the resolver front door.** Added
  `clinical_demo.terminology.umls_search_client.UMLSSearchClient` with
  `httpx.MockTransport`-driven offline tests (13 new tests in
  `tests/terminology/test_umls_search_client.py`). Extended
  `TerminologyResolver._resolve_open_condition` /
  `_resolve_open_lab` to call UMLS on alias miss, cache `resolved`
  with candidate provenance when hits land, and cache `true_miss` on
  clean zero-hit responses; transport / parse errors soft-fail without
  a poisoned cache row. Bumped `OPEN_SURFACE_RESOLVER_VERSION` to
  `open-surface-v0.2` so cached alias-only `true_miss` rows get
  re-resolved against UMLS on next hit. Added
  `scripts/probe_umls.py` mirroring `probe_rxnorm.py` for operational
  sanity-checking. Fixed work-queue precedence so
  `_manual_nonresolved` classifications win over resolver-cached
  matches for surfaces that UMLS can look up but the matcher cannot
  usefully score against (life expectancy, ECOG). Snapshot at
  `eval/baselines/2026-05-04-umls/`. Verification: `uv run pytest`
  652/652, `uv run ruff check .` clean, deterministic smoke eval
  `43c765d1dbcc` with deltas above.
  Previous: PLAN task 2.18 first slice — **top-unmapped work queue
  and cache warmer.** Added `clinical_demo.terminology.work_queue` with
  `SurfaceWorkItem`, `build_surface_work_queue`, JSON/text renderers, and
  cache writes for nonresolved classifications. Added
  `scripts/warm_terminology_surfaces.py`, e.g.
  `uv run python scripts/warm_terminology_surfaces.py --diagnostics
  eval/baselines/2026-05-04/patient_evidence_none_diagnostics.json --limit 20`.
  Focused tests cover resolved alias warming, ambiguous BP cache reuse,
  composite pregnancy/breastfeeding classification, temporal-window review
  classification, known data-model gaps (PVR, pneumonectomy, ECOG), life
  expectancy extractor-kind misclassification, and text rendering.
  Verification: `uv run pytest tests/terminology/test_work_queue.py
  tests/terminology/test_cache.py tests/terminology/test_resolver.py` 66/66
  and targeted ruff clean.
  Previous: PLAN task 2.17 first slice — **open terminology resolver
  front door with cached surface decisions.** `TerminologyCache` now has
  schema-fingerprinted `surface.<kind>.<query>.<fp>.json` envelopes that store
  `resolved`, `ambiguous`, `true_miss`, or `composite_unhandled` decisions plus
  candidate/provenance metadata. `TerminologyResolver.resolve_*` checks this
  surface cache before the old registry, writes resolved registry results into
  the same front-door cache, then falls through to open lab/condition aliases or
  raw RxNorm medication lookup. Added curated LOINC ConceptSets for BMI
  (`39156-5`), hemoglobin (`718-7`), and platelet count (`777-3`), alias-mode
  fallbacks for the same high-frequency surfaces, and unit normalization for
  BMI spellings, eGFR `m^2`, hemoglobin `g/L` <-> `g/dL`, and platelet
  count-per-microliter thresholds. Verification: `uv run pytest` 622/622,
  `uv run ruff check .` clean, deterministic smoke eval `8f9900f3fefb`.
  Previous: PLAN task 2.11 — **deceased-patient structured-safety
  guard wired through loader, scoring, and API.** `Patient.deceased_date:
  date | None` is parsed from FHIR `Patient.deceasedDateTime` (with a
  defensive fallback for `deceasedBoolean=true` that pins the date to
  `birth_date` and logs a warning). Both `score_pair` and `score_pair_graph`
  raise the new `clinical_demo.scoring.PatientDeceasedError` (typed attrs:
  `patient_id`, `deceased_date`, `as_of`; message cites
  `Patient.deceasedDateTime`) when `deceased_date <= as_of`, including the
  equality boundary; later-than-`as_of` deaths still score so retrospective
  replays continue to work. FastAPI `/score` maps the refusal to
  `422 {error: "patient_deceased", patient_id, deceased_date, as_of,
  source_field, message}` instead of a 500. New deceased-path tests in the
  synthea / scoring / graph / api suites; `uv run pytest` 608/608,
  `uv run ruff check .` clean, `uv run mypy src` clean.
  Previous: D-72 follow-up — **adjudicator cost telemetry persisted
  on `ScorePairResult` and `eval/runs.sqlite`.** New
  `clinical_demo.cost_telemetry.LLMCallCost` carries per-call `stage`,
  `criterion_index`, model + prompt version, token counts, USD, and latency.
  `adjudicate_patient_evidence` now returns `(MatchVerdict, LLMCallCost | None)`;
  `_apply_retrieval_only` collects them into a list that rides on
  `ScorePairResult.llm_calls`. `ScoringSummary` gains `adjudicator_calls`,
  `adjudicator_input_tokens`, `adjudicator_output_tokens`, and
  `adjudicator_cost_usd` aggregates so the SQLite store can persist them as
  flat columns for fast pivots. `eval/runs.sqlite` schema bumped v2 -> v3 with
  an additive migration adding the four `adjudicator_*` columns; `save_run`
  populates them from the rolled-up summary. `scripts/eval.py` summary printer
  now prints "adjudicator calls: N  cost (sum over M cases): $X". Web typings
  (`web/src/lib/api.ts`) gained `LLMCallCost` and the new summary fields so
  the reviewer dashboard can surface adjudicator spend without re-walking
  evidence. Tests: new adjudicator no-op-returns-no-cost pin, updated
  `test_bounded_adjudication_can_replace_indeterminate_with_cited_verdict` to
  assert `llm_calls` / summary aggregates, and a new v2 -> v3 migration test.
  Verification: `uv run pytest` 599/599, `uv run ruff check .` clean,
  `uv run mypy src` clean. This unblocks the Phase 3.2 cost-quality sweep
  precondition called out in D-72; the remaining blocker is filling the
  60-row `eval/calibration/patient_evidence_labels.json` gold set.
  Previous: PLAN tasks 2.15/2.16 empirical rerun —
  **Bounded adjudication plus deterministic unit reconciliation evaluated.**
  Added `clinical_demo.adjudication.patient_evidence`, a citation-required
  structured-output LLM adjudicator that sees exactly one criterion, its
  deterministic verdict, retrieved patient source rows, trial context, and the
  matcher assumption mode. `llm_use_level="bounded_adjudication"` now runs this
  pass after retrieval for indeterminate verdicts; decisive LLM answers are
  fail-closed back to `indeterminate/human_review_required` if they do not cite
  valid retrieved row IDs. Also added a small deterministic conventional-unit
  layer: eGFR/BP/HbA1c missing-unit inference, eGFR unit aliases, and LDL-C
  `mmol/L` <-> `mg/dL` conversion against Synthea observations. Refreshed all
  30 curated trial extraction caches under extractor-v0.5 on 2026-05-04
  (641 criteria, $0.0870 extractor cost, 35.2 min wall). Three cached 49-pair
  eval runs are snapshotted under `eval/baselines/2026-05-04/`: deterministic
  `none` run `8e718e87c3fa` (18 fail / 31 indeterminate cases),
  `retrieval_only` run `dd8a939ea584` (same verdicts, 627 unresolved
  criterion verdicts now carrying retrieved source-row evidence), and
  `bounded_adjudication` run `4458ecd2199a` (27 fail / 22 indeterminate cases).
  Bounded adjudication changed 624 criterion-level verdict/reason pairs:
  39 indeterminate -> pass, 15 indeterminate -> fail, and 570 still
  indeterminate but mostly clarified to `no_data`. Top-level movement was
  9 cases from indeterminate -> fail, 0 cases -> pass. The 60-row
  patient-evidence label file still has 0 filled labels, so this is an
  empirical mode comparison, not calibrated quality yet. Verification:
  `uv run pytest` passes 597 tests, `uv run ruff check .` passes, and
  `npm run build` passes.
  Previous: PLAN tasks 2.13/2.14 product move —
  **Retrieval-only scoring mode wired through the product surface.**
  `ScorePairResult` now records `matcher_assumption_mode` and
  `llm_use_level`; `score_pair`, `score_pair_graph`, `scripts/score_pair.py`,
  `scripts/eval.py run`, and FastAPI `/score` accept the same controls.
  `llm_use_level="retrieval_only"` leaves deterministic verdicts unchanged
  but appends ranked `retrieved_patient_row` evidence to indeterminate
  verdicts using stable patient source-row IDs, lexical overlap, and
  ConceptSet/code anchors. The Svelte score view exposes LLM-use and
  assumption-mode controls and renders retrieved rows inline with their row
  IDs and retrieval reasons. Targeted Python tests and the Svelte production
  build pass; a no-LLM eval smoke was blocked by stale/missing extractor-v0.5
  cache files, not by retrieval plumbing.
  Previous: PLAN task 2.6 follow-up —
  **Patient-side FHIR evidence calibration packet scaffold (PLAN 2.12)**.
  Added `clinical_demo.evals.patient_evidence` with reviewer-facing schemas,
  deterministic evidence-focused target selection, source-row IDs for
  citations, JSON load/save helpers, and bucket summaries. Added
  `scripts/build_patient_evidence_calibration.py`, which reads a persisted
  eval run plus the calibrated Layer-3 judge report, selects 60 patient-side
  evidence candidates, attaches patient/trial source context, and writes both
  `eval/calibration/patient_evidence_candidates.json` and the blank label
  template `eval/calibration/patient_evidence_labels.json`. Current packet
  includes all 20 judge-incorrect rows plus stratified condition present/absent,
  medication present/absent, measurement/unit, free-text patient-evidence, and
  unmapped-concept examples. Human review of those 60 labels is still owed
  before 2.12 is complete as a gold set.
  Previous: PLAN task 2.6 follow-up —
  **Calibrated full Layer-3 judge run**. Reran
  `scripts/eval.py judge` on two-pass run `394703892184` with the 25-row
  human label file and wrote
  `eval/baselines/2026-04-30/layer3_judge_calibrated.json`. Results:
  1,086 judged verdicts, 1,066 `correct`, 20 `incorrect`, all
  high-confidence, total judge cost `$0.1738`. Calibration against the human
  labels was 25/25 agreement (`agreement_rate=1.0`, `cohen_kappa=1.0`).
  The incorrect rows are concentrated in unsupported evidence / wrong-verdict
  cases, especially BP threshold polarity, CKD stage specificity, HbA1c range
  interpretation, and duration/specificity constraints for diabetes. This
  confirms the same architecture lesson as the manual pass: the matcher is
  mostly honest, but patient-side evidence adjudication now needs its own
  gold/calibration set before building a new LLM adjudicator.
  Previous: PLAN task 2.6 follow-up —
  **Layer-3 human calibration pass + source-context reviewer update**. The
  initial manual pass saved 25 labels to
  `eval/calibration/layer3_human_labels.json`; all 25 are `correct`. This is
  a calibration win for the judge/matcher rubric, but also a product-quality
  warning: many "correct" rows are correct because the deterministic matcher
  is honest and fail-closed (`indeterminate` with a defensible reason), not
  because the pipeline is clinically strong enough to resolve the case. To
  make future review judge source evidence rather than only the matcher's
  rationale, the calibration UI now shows patient-record and trial-record
  source context alongside each row.
  Previous: **Layer-3 calibration GUI**. Added a local browser workflow for
  creating the human label file that calibrates the LLM judge: backend helpers
  select a deterministic reason/verdict-stratified sample from a persisted
  `RunResult`, convert `JudgeTarget`s into UI rows, and load/merge/save
  `LayerThreeHumanLabel` JSON. FastAPI exposes `GET /eval/runs`,
  `GET /layer3/calibration?run_id=...&limit=...`, and
  `POST /layer3/calibration`, writing by default to
  `eval/calibration/layer3_human_labels.json`. The Svelte reviewer app has a
  `Score` / `Layer-3 calibration` mode switch, a calibration panel with run
  selection, progress counts, readable criterion/verdict/evidence JSON,
  `correct` / `incorrect` / `unjudgeable` radio labels, optional reviewer
  rationale, and a save action.
  Previous: PLAN task 2.6 v0 — **Layer-3 LLM-as-judge scaffolding and
  smoke**. Added `clinical_demo.evals.layer_three` with a pinned judge
  version (`llm-judge-v0.1`) and rubric prompt (`llm-judge-rubric-v0.2`), a
  structured judge schema (`correct` / `incorrect` / `unjudgeable`),
  verdict-target selection over persisted `RunResult`s, optional human
  calibration labels, agreement-rate + Cohen's kappa calculation, and a text
  renderer. Added `scripts/eval.py judge`; 5-verdict smoke on
  `98568ccd090d` saved `layer3_judge_smoke.json` and fixed the justified
  `indeterminate` rubric issue.
  Previous: PLAN task 2.5 prompt follow-up — **extractor-v0.5 Chia
  Observation / Scope tightening**. The first tightening attempt
  (`extractor-v0.4`) regressed the retained sample; `extractor-v0.5`
  recovered aggregate metrics (micro F1 37.7%, lenient micro F1 58.6%)
  and cut `Observation` false positives, but did not solve `Observation`
  exact TP or `Scope` recall.
  Previous: PLAN task 2.5 diagnostic follow-up — **Chia overlap /
  containment layer-2 view**. Added secondary same-type partial-match
  diagnostics to `clinical_demo.evals.layer_two` while preserving exact
  `(type, surface)` precision / recall / F1 as the primary score.
  Replayed the frozen v0.3 retained sample from cache; exact micro F1
  stayed 37.5%, and the boundary-aware view added 159 partial matches,
  raising lenient micro F1 to 57.4% and lenient macro F1 to 54.3%.
  Previous: PLAN task 2.5 prompt pass — **extractor-v0.3 Chia mention
  discipline**. Bumped `PROMPT_VERSION` to `extractor-v0.3`, added Hard
  Rule 14 plus Chia-style mention boundary guidance, and added a fourth
  few-shot focused on `Scope`, full `Temporal` windows, comparator-rich
  `Value`, `Qualifier`, `Observation`, `Negation`, `Multiplier`,
  `Reference_point`, and `Procedure` labels. Reran the frozen 50-document
  retained sample; micro F1 34.4% -> 37.5%, macro F1 33.0% -> 35.4%,
  cost $0.0710.
  Previous: PLAN task 2.5 retained-sample follow-up — **Chia layer-2
  error profile**. Extended `scripts/eval.py chia` with deterministic
  retained-sample controls and froze the 50-document baseline: 923 gold
  mentions, 573 predicted, 257 true positives; micro F1 34.4%; macro
  F1 33.0%; extraction cost $0.0588.
  Previous: PLAN task 2.5 v0 — **Chia entity-mention F1 eval**. Added
  `clinical_demo.evals.layer_two`, `report_layer_two`, and
  `scripts/eval.py chia`; 5-document smoke cost $0.0078 and produced
  25.7% micro F1 / 24.9% macro F1. Snapshot:
  `eval/baselines/2026-04-30/layer2_chia_entity_f1_smoke.json`.
  Previous: D-69 slice 5 — **two-pass terminology eval rerun and
  diagnostic report**. Cached imperative eval with
  `binding_strategy="two_pass"` ran 49 pairs with 0 errors; run id
  `98568ccd090d`. Snapshot under `eval/baselines/2026-04-30/`.
  Headline vs. D-68: `unmapped_concept` rate 81.9% -> 60.8%;
  layer-1 coverage 55.3% -> 98.7%; agreement 81.0% -> 88.3%.
  Added `eval report --diagnostics`, `--binding-strategy` for eval
  runs, and a structured D-68 diagnostics baseline.
  Previous: D-69 slice 4 hotfix — **T2DM binding
  needed an explicit SNOMED filter, and the test suite needed
  to be hermetic from `.env`**. A live smoke under
  `BINDING_STRATEGY=two_pass` surfaced two latent issues. (1)
  The slice-4 T2DM bindings shipped without a `system_filter`,
  carried over from when the recorded fixture happened to be
  SNOMED-only. The *live* eCQM Diabetes expansion now spans
  SNOMED + ICD-10-CM, and `VSACClient` rejects multi-system
  expansions without a filter (the matcher's ConceptSet is
  single-system per query). The resolver was correctly
  soft-failing and falling through to the alias table on every
  T2DM lookup, defeating the entire wire-up. Added
  `system_filter=SNOMED_SYSTEM` to all five T2DM surface forms
  so live `two_pass` lookups now resolve to the 493-code SNOMED
  Diabetes value set (vs. the alias table's 6-code curated
  entry; meaningful recall delta worth measuring at slice-5).
  (2) The legacy alias-table tests (`test_lookup_*_known_aliases`
  and `test_lookup_medication_v0_returns_none_for_everything`)
  silently inherited `binding_strategy` from the developer's
  `.env`, so flipping the env var to `two_pass` started routing
  those tests through the resolver -- producing different
  ConceptSets (or non-None RxNorm hits) that broke object-
  identity assertions. Added a tests-root `conftest.py` with a
  session-wide autouse fixture that overrides
  `Settings.model_config["env_file"]` to `None` for every test,
  making the suite hermetic from `.env`. The fixture manages the
  override directly (not via `monkeypatch`) so it doesn't shift
  the fixture setup order in nested files (the langfuse shim's
  `_reset_caches` autouse depends on monkeypatch having unwound
  before its teardown reads `lru_cache.cache_clear` off a
  swapped attribute -- requesting `monkeypatch` in the conftest
  fixture would invert that order). Existing per-test
  `two_pass_settings` opt-in still works because it monkeypatches
  `get_settings` directly inside the matcher module. Also
  updated `test_resolve_condition_uses_registry_then_cache` to
  pre-warm the cache under `system_filter=SNOMED` because cache
  keys include the filter (no-filter pre-warm misses after the
  T2DM patch). One test docstring updated for the now-pinned
  T2DM filter. Pytest stays at 547/547. Live smoke now resolves
  T2DM (493 SNOMED codes), hypertension (14), HbA1c (5),
  metformin (137); rosuvastatin correctly soft-fails (not in
  registry, not in alias table). Cache populated under
  `data/cache/terminology/` after the smoke; second-run latency
  drops dramatically as expected.
  Previous: D-69 slice 4 follow-on -- **VSAC bindings
  registry population (conditions + labs)**. Two canonical eCQM
  value-set OIDs added to the registry beyond the T2DM seed,
  each validated against live VSAC `$expand` and shipped with
  a recorded fixture so resolver tests stay
  offline-deterministic. (1) **Essential Hypertension** -- OID
  `2.16.840.1.113883.3.464.1003.104.12.1011` (CMS165's
  Controlling High Blood Pressure value set; 14 SNOMED codes
  including `59621000` Essential hypertension); bound from
  surface forms `hypertension`, `essential hypertension`, `high
  blood pressure`, `htn` with `system_filter=
  "http://snomed.info/sct"` because the value set is
  multi-system and the matcher's PatientProfile is
  single-system per query. (2) **HbA1c Laboratory Test** --
  OID `2.16.840.1.113883.3.464.1003.198.12.1013` (CMS122's
  Diabetes HbA1c Poor Control value set; 5 LOINC codes:
  4548-4 standard HbA1c %, 4549-2, 17855-8, 17856-6, 96595-4);
  bound from `hba1c`, `hemoglobin a1c`, `haemoglobin a1c`,
  `a1c`, `glycated hemoglobin`, `glycosylated hemoglobin`
  with `system_filter="http://loinc.org"`. New module-level
  constants `ECQM_HYPERTENSION_OID`, `ECQM_HBA1C_LAB_OID`,
  `SNOMED_SYSTEM`, `LOINC_SYSTEM` so probe scripts and
  regression tests can reference them by name instead of
  retyping dotted strings. Fixtures added at
  `tests/fixtures/vsac/hypertension_expansion.json` and
  `tests/fixtures/vsac/hba1c_lab_expansion.json` -- recorded
  via inline httpx round-trip (probe_vsac.py's `--record` is
  hardwired to the diabetes fixture path; an extension to
  multi-fixture support is a future ergonomics improvement).
  Hyperlipidemia and CKD intentionally NOT included: research
  surfaced canonical OIDs only under non-CMS authorities (HL7
  Patient Care WG for hyperlipidemia; CKD Stage 5 only is too
  narrow to bind to "ckd"); rather than guess we leave them on
  the named follow-on list with the slice-5 eval rerun
  empirically deciding the priority. Test changes: replaced
  the single `test_ecqm_diabetes_oid_is_the_canonical_cms_value_set`
  with a parametrize over all three OID constants; added
  positive parametrized tests pinning each populated condition
  / lab surface form to its OID + system_filter; new
  `test_vsac_fixture_matches_pinned_oid` parametrize verifies
  each recorded fixture's `id` field equals the constant we
  pin (catches accidental fixture/OID mismatch); replaced the
  empty-lab-registry pin with positive lookups; updated the
  resolver-side soft-fail test docstring to reflect lab
  registry now hits and falls through on cache+client miss.
  Default `binding_strategy` stays `alias`; this expansion is
  inert in production until an operator opts into `two_pass`.
  Slice-5 eval rerun is the first chance to measure how much
  these eight new bindings (4 hypertension surfaces + 6 HbA1c
  surfaces; -2 for the 4-surface dedup on the OID) close the
  alias-only `unmapped_concept` baseline.
  Previous: D-69 slice 4 follow-on -- **medication bindings
  registry population**. Six cardiometabolic ingredient
  bindings added to `MEDICATION_BINDINGS`: metformin, insulin,
  atorvastatin, simvastatin, semaglutide (GLP-1
  representative), dapagliflozin (SGLT2 representative). Each
  was validated against live RxNav `/drugs.json` via
  `scripts/probe_rxnorm.py` and confirmed to return non-empty
  SCD/SBD code lists -- the exact TTYs Synthea uses for
  `MedicationRequest.medicationCodeableConcept.coding` (sample
  cohort sweep showed atorvastatin RxCUI 259255 and simvastatin
  312961 both as SCD codes, matching what `/drugs.json` returns
  by default). `tty_filter=None` on every entry intentionally:
  unioning SCD + SBD gives the broadest hit rate without
  cross-system noise; future Synthea data drift toward IN/PIN
  would mean *adding* TTYs, not dropping current ones.
  Class-level coverage ("any GLP-1 agonist", "any SGLT2
  inhibitor") is intentionally NOT modeled here -- RxNav
  `/drugs.json?name=...` is an ingredient/brand lookup, not a
  class lookup; representing a class would mean either querying
  RxClass (separate API surface) or unioning multiple ingredient
  bindings. Deferred until trial eligibility text actually
  demands it; the slice-5 eval rerun will surface the gap as a
  named follow-up rather than us papering over it with
  hardcoded class lists. Two test changes: replaced the
  `test_lab_and_medication_bindings_empty_in_v0` pin with a
  per-entry parametrize that asserts each medication binding is
  an `RxNormBinding` with no `tty_filter`, and a positive
  lookup-via-helper test that exercises the same normalization
  path the matcher uses; updated the resolver-side soft-fail
  test docstring to match the new "registry hits but cache empty
  + no client = None" reality. Bindings docstring + tests pin
  the validation discipline so future expansions can't slip
  past review.
  Previous: PLAN task 2.10 / **D-69 slice 4** —
  matcher-side terminology binding wire-up. Three new pieces and
  one switched dispatch:
    - `Settings.binding_strategy` literal grew from `Literal["alias"]`
      to `Literal["alias", "two_pass"]`. `alias` stays the default
      so a fresh checkout reproduces the D-68 baseline byte-for-byte;
      `two_pass` opts the matcher into the new path. `one_pass`
      (LLM emits the binding inline) remains intentionally unwired
      and rejected at config-validation time so eval runs can't
      silently look terminology-backed when they aren't.
    - New `clinical_demo.terminology.bindings` module: a small
      surface-form -> (`VSACBinding(oid, system_filter)` |
      `RxNormBinding(name, tty_filter)`) registry. v0 seeds *one*
      binding (T2DM -> eCQM Diabetes OID
      `2.16.840.1.113883.3.464.1003.103.12.1001`) so the wire-up
      is end-to-end exercisable against the recorded VSAC fixture
      we already ship. Lab and medication registries are
      intentionally empty in v0; population is a separate commit
      so each addition can be validated against its source
      authority (VSAC search UI / RxNav probe scripts) without
      the slice-4 plumbing diff being noisy.
    - New `clinical_demo.terminology.resolver` module:
      `TerminologyResolver` orchestrates registry -> cache ->
      live VSAC / RxNorm -> soft-fail. Cache hit short-circuits
      before any client is touched; cache miss with no
      credentials returns `None` (a fresh checkout without
      `UMLS_API_KEY` can opt into `two_pass` and still benefit
      from any pre-warmed cache rows); fetch error is caught
      and logged, returns `None`. Process-wide singleton via
      `get_resolver()` so the matcher's hot path does not
      re-instantiate clients per criterion.
    - `matcher.concept_lookup.lookup_*` now dispatches on
      `binding_strategy`. Under `two_pass`: try the resolver
      first; on `None` fall back to the alias table; if both
      miss, return `None` (the matcher's existing
      `unmapped_concept` branch). Under `alias` (default): the
      resolver factory is never called, so a fresh checkout
      pays zero terminology overhead. Both modes preserve the
      surface-form normalization parity that lets a string hit
      both bridges identically.
  Soft-fail discipline mirrors D-65/D-66: any terminology-side
  failure (no key, network error, schema drift, upstream HTTP
  500) degrades to the alias fallback, never crashes the run.
  33 new tests: `tests/terminology/test_bindings.py` (11 — seed
  binding integrity, normalization parity vs. `concept_lookup`,
  empty-registry pinning, type discipline);
  `tests/terminology/test_resolver.py` (14 — cache-hit /
  cache-miss-with-fetch / cache-miss-no-client soft-fail / fetch
  error / network error / system_filter + tty_filter cache-key
  discrimination across both VSAC and RxNorm, plus surface-form
  wrapper coverage and an unknown-binding-type defensive
  branch); `tests/matcher/test_concept_lookup.py` (+7 — alias
  mode trip-wires the resolver factory to prove it isn't
  consulted; `two_pass` mode honors a resolver hit, falls back
  to alias on resolver miss, and returns `None` only when both
  bridges miss). Slice 5's eval rerun will be the first chance
  to measure how much the seed binding (alone) closes the
  baseline's `unmapped_concept` rate; expanding bindings beyond
  T2DM is the natural next commit and will widen that delta
  monotonically without needing further plumbing changes.
  Previous: CT.gov structured age/sex enrichment — the
  second of the two §0 cleanups, landed serially after the
  Rule-13 prompt patch so each commit's eval delta is
  independently attributable in slice 5. New module
  `clinical_demo.extractor.enrich` adds a deterministic
  post-processor `enrich_with_structured_fields(extracted, trial)`:
  if the extractor didn't emit a `kind="age"` row but
  `trial.minimum_age` / `trial.maximum_age` parses, inject one
  with the parsed bounds and a sentinel `source_text`
  (`"[ct.gov structured field: ...]"`) so reviewers can tell
  injected criteria from LLM-extracted ones at a glance; same
  for `kind="sex"` against constraining `trial.sex` values
  (MALE / FEMALE only — `ALL` is vacuous). Wired into the
  imperative `score_pair` path and the `extract_node` graph
  path, both of which now match against the enriched view.
  Critically the enrichment runs *at use time*, not at
  cache-write time — `scripts/extract_criteria.py` keeps
  caching the LLM's raw output, so a CT.gov metadata refresh
  doesn't invalidate the D-66 extractor cache and a second
  `PROMPT_VERSION` bump in two commits is avoided. Chose
  post-processing over a prompt-side hint deliberately: CT.gov
  structured fields are canonical (the trial designer asserts
  "minimum age = 18"), and routing canonical structured data
  through an LLM for re-interpretation is silly and lossy.
  Also: no-override discipline — if the extractor *did* emit
  age or sex (the eligibility text may have nuanced the bound
  with exception clauses), enrichment leaves it alone.
  Estimated layer-1 coverage delta: 55% → ~95% on the D-68
  baseline; the matcher's existing `_match_age` / `_match_sex`
  branches consume the synthetic rows unchanged. 36 new tests
  (24 in `tests/extractor/test_enrich.py` covering the parser,
  the inject/no-inject branches, and identity-as-no-op
  optimization; 2 in `tests/scoring/test_score_pair.py` pinning
  the end-to-end wiring).
  Previous: extractor compound-criterion routing patch (one of
  the two §0 follow-up cleanups, sequenced before D-69 slice 4
  so its eval delta is independently attributable). Adds
  Hard Rule 13 to the extractor system prompt — "Single-concept
  typed slots: condition_text / medication_text / measurement_text
  / event_text must each contain exactly ONE clinical concept;
  compound clauses joined by 'or' / 'and' / commas route to
  `free_text` instead." Cross-references it from Rule 2
  (Atomicity). Adds a third few-shot example built from real
  D-68 baseline misroutes ("severe liver dysfunction (Child-Pugh
  C grade) or significant jaundice or hepatic encephalopathy"
  and a four-class lipid-lowering medication compound), each
  routed to `free_text` with a Rule-13-citing note. `PROMPT_VERSION`
  bumped `extractor-v0.1` → `extractor-v0.2`, which auto-orphans
  all 30 cached extractions in `data/curated/extractions/` per
  the D-66 cache key — slice 5's eval rerun re-extracts from
  scratch under the new discipline (intentional; the whole point
  of versioning the cache key on prompt version). Estimated
  impact: ~50–100 verdicts move from silent
  `unmapped_concept` to `human_review_required` where the LLM
  matcher node can actually engage. 2 new prompt tests pin the
  Rule-13 must-have phrase, the version floor at v0.2, and the
  presence of the compound-clause few-shot example.
  Previous: PLAN task 2.10 / **D-69** slice 3 — RxNorm REST
  client + cache integration. New
  `clinical_demo.terminology.rxnorm_client` module: thin sync
  wrapper over RxNav `/drugs.json?name=...` returning a
  matcher-shaped `RxNormConcepts` envelope (query + ConceptSet of
  RxCUIs + the set of RxNorm term types that contributed). Unions
  codes across every populated `conceptGroup` by default (Synthea
  patient bundles can be coded at any TTY level — IN, SCD, SBD —
  so a narrower default would silently drop valid evidence); a
  `tty_filter=frozenset({...})` arg restricts to a chosen set for
  slice-4 ablations. Auth model is the key difference from VSAC:
  RxNav is **public, no API key** (gated only on a ~20 rps rate
  limit), so a fresh checkout can probe RxNorm without an NLM
  account. Same fail-loud discipline as VSAC: empty / malformed
  responses raise `RxNormError` rather than returning an empty
  ConceptSet (which would tell the matcher "no codes count" —
  the wrong default). `TerminologyCache` extended with parallel
  `get/put/_or_fetch_rxnorm_concepts` methods, an
  `rxnorm_envelope_fingerprint` independent from the VSAC one
  (so an RxNorm envelope rev does not invalidate VSAC entries
  and vice versa), filename pattern
  `rxnorm.<query_tag>.<filter_tag>.<schema_fp>.json` with the
  query hashed (case-insensitive, whitespace-stripped) so
  filename-unsafe surface forms like "Glucophage" or
  "metformin/glipizide" round-trip cleanly. Recorded fixture
  `tests/fixtures/rxnorm/metformin_drugs.json` plus live probe
  script `scripts/probe_rxnorm.py`. 27 new offline tests (12
  client + 15 cache); the cache tests also pin the
  vsac/rxnorm-coexist-in-one-root contract. Decision **D-69**
  updated; matcher wiring still lands in slice 4.
  Previous: D-69 slice 2 — on-disk terminology cache
  (`TerminologyCache`) with auto-invalidating envelope
  fingerprint, atomic writes, and `vsac_expansion_or_fetch`
  convenience. D-69 slice 1 — VSAC FHIR `$expand` client +
  `UMLS_API_KEY` plumbing. Before that: D-67 / D-68 (first
  baseline regression with indeterminacy diagnostic): layer-1
  agreement 81.0%, coverage 55.3%, 89% of all indeterminates are
  `unmapped_concept`. Snapshots in `eval/baselines/2026-04-21/`.
- **Next:** Add explicit composite/OR criterion representation before treating
  compound free-text criteria as independently matchable rows. First slice:
  reviewer-facing line items for `any_of` / `all_of` subchecks with per-subcheck
  retrieved evidence, plus UI guidance that closed-world labels are synthetic
  eval assumptions, not the default clinical stance. Do not let composite line
  items change eligibility rollup until matcher semantics own composite groups.
  Do **not** regenerate `eval/calibration/patient_evidence_candidates.json`
  until composite schema + per-subcheck retrieval are in place; otherwise the
  large artifact will bake in the temporary shallow splitter and create noisy
  review churn. Composite-aware retrieval may widen review/adjudication context,
  but `match_extracted` and the case rollup must stay unchanged until the
  extractor/fixer can emit parent/subcheck groups reliably.
- **Gates at HEAD:** `uv run pytest` 677/677; targeted criterion-fixer /
  scoring / graph / terminology tests 110/110; targeted ruff clean; targeted
  format check clean; targeted mypy clean; mapped + legacy terminology
  regression gate clean; `git diff --check` clean.
- **Branch:** `codex/criterion-fixing-layer` stacked on
  `codex/mapped-terminology-expansion`.

### Non-trivial open follow-ups

These are *not* blockers for the next task; they're tracked here
so they don't get lost between sessions.

- **Gemini EAP / Vertex ADC path.** The current calibration research helper
  uses the Gemini Developer API / AI Studio API-key endpoint first and OpenAI
  fallback second. Gemini API-key calls are currently blocked by depleted
  AI Studio prepay credits; Google Cloud's $300 credit applies to Vertex /
  Gemini EAP instead. If Google research assist matters later, add a separate
  Vertex provider that uses Application Default Credentials from
  `gcloud auth application-default login` or the EAP ADC setup script, plus
  `GOOGLE_CLOUD_PROJECT` / region settings. Do not treat an OAuth
  `client_secret_*.json` file as a drop-in replacement for `GOOGLE_API_KEY`.
- **Eval seed human-review pass** (Phase 1 task 1.6): ~856
  free-text criteria across 49 pairs are still
  `free_text_review_status="pending"`. End-to-end matcher evals
  cannot be claimed as ground truth until this pass is complete.
  See the open-question list in §13.
- **Critic iteration default re-validation** (Phase 2 task 2.7):
  default `max_critic_iterations=2` was picked on theory, not
  data. Re-validate against the real revision manifest after the
  first baseline regression run; if 95%+ of revisions land in
  iteration 1, drop to 1.
- **Mapping expansion + `mapped` terminology language.** Continue the practical
  mapping work surfaced by diagnostics. Anything the system can map should be
  mapped, cached, and kept out of future top-unmapped lists. The user-facing
  and report-facing success term should be `mapped`, not `resolved`; keep
  compatibility aliases only for old artifact filenames / cache rows until a
  migration removes them.
- **Criterion fixing layer.** Add a bounded repair layer between extraction and
  matching that can normalize surfaces, split safe composites, preserve
  original criterion text, attach candidate mapping provenance, and mark
  uncertain fixes for human review. This layer may use an LLM for
  interpretation, but deterministic validators and cached terminology results
  decide what is allowed into the matcher.
- **Patient deceased-date guard.** *Resolved by PLAN task 2.11.*
  `Patient.deceased_date` is parsed from `Patient.deceasedDateTime`
  (with a defensive fallback for `deceasedBoolean=true`); `score_pair`
  and `score_pair_graph` raise `PatientDeceasedError` for deceased
  patients on/before `as_of`; FastAPI `/score` maps the refusal to a
  structured 422.
- **Patient-side note evidence extraction.** The architecture has
  always said "light LLM for unstructured notes," but the current
  implementation deliberately excludes `DocumentReference` text from
  both the deterministic profile and the LLM matcher snapshot. Track
  this as its own slice: parse `DocumentReference.content.attachment`
  (`data` base64 and later `url`), ignore/generated-low-trust
  `resource.text.div`, retrieve the smallest criterion-relevant note
  snippets, require citations for any note-supported pass/fail, and
  preserve `indeterminate` when note evidence is absent or ambiguous.
  Validation needs its own golden note snippets: explicit evidence,
  explicit absence, insufficient evidence, temporal/as-of cases,
  note-vs-structured contradiction, and prompt injection in patient
  narrative text.
- **MIMIC-IV access, governance, and evidence adapter.** MIMIC-IV should be the
  realistic patient-evidence track, not a replacement for the current
  Synthea-based unit/calibration fixtures. While access is pending, define the
  local data-root contract and adapter interfaces. Once credentialed access is
  granted through PhysioNet, map MIMIC-IV `hosp`/`icu` tables into the same
  citeable patient-row interface used by Synthea and map MIMIC-IV-Note into the
  note-snippet interface for local calibration/enhancement of patient files.
  The product should not reproduce MIMIC records or expose row-level MIMIC
  excerpts; raw MIMIC data, row-level exports, and derived credentialed snippets
  stay outside git and outside public artifacts.
- **Official TREC/TrialGPT benchmark ingestion.** The local benchmark scaffold
  is useful but insufficient for "score our system against others." Add the
  official TREC Clinical Trials topics/corpus/qrels and TrialGPT code/data
  references as an external benchmark adapter, then report standard retrieval
  and ranking metrics separately from internal patient-evidence calibration.
- **Robust Synthea generation + realism gaps.** The current Nov 2021
  sample is useful for loader/matcher bring-up but too small and too
  clean to support strong demo/eval claims. Follow
  `docs/synthea-generation-research.md`: generate a reproducible broad
  adult population plus an enriched cardiometabolic keep-filtered
  batch, parameterize the cohort input path, persist generation
  manifests, rebuild positive/near-miss eval pairs, and add perturbed
  FHIR fixtures that mimic real export messiness (local codes, missing
  displays, unit drift, stale meds, duplicate conditions, partial
  history, and note-vs-structured contradictions).
- *(Promoted to PLAN task 2.10 / D-69.)* The hand-curated
  vocab-expansion play that D-68 surfaced as highest-impact has
  been re-scoped around NLM terminology APIs. The ranked top-N
  surface forms in
  `eval/baselines/2026-04-21/INDETERMINACY.md` are the input list
  for VSAC/RxNorm/UMLS binding work; the current slice starts with
  VSAC expansion support and keeps runtime matcher behavior on the
  existing aliases until the resolver is wired and measured.
- **Chia-style trial annotation as calibration scaffold (Phase 3 idea).**
  User raised this during the 2.19 review: rather than continuing
  to score the matcher indirectly through the eligibility rollup,
  produce Chia-shaped entity annotations on our 30-trial seed and
  measure extractor F1 against ground truth we control. This gives
  Layer-2 a corpus that overlaps our actual cardiometabolic /
  oncology slices (Chia itself doesn't), and unblocks a clean
  cost/quality story for the staged introduction of LLM
  disambiguation, free-text classifiers, and research helpers in
  Phase 3. Sequencing: do this *after* (a) the Phase-3 LLM phases
  start landing so we have something whose performance to score
  against the scaffold, or (b) we want a hard quality-floor before
  shipping. Until then, layer-2 stays Chia-corpus-only. Tracked
  here so it doesn't get lost; not a blocker for 2.19 or 3.x slice
  zero.
- **`closed_world_demo` UI/API banner.** PLAN 2.19 left this
  deferred. The matcher already accepts `closed_world_demo` and
  treats it identically to `closed_world_eval` in the deterministic
  layer; the missing piece is the visible "this score is computed
  under the closed-world assumption" affordance in the API
  response and the Svelte reviewer header. Pick this up when we
  start polishing for the demo.
### Maintenance contract for this section

When closing out a task:

1. Update **Last completed** with task id and the commit SHA(s).
2. Update **Next** with the next task id from §6.
3. Update **Gates at HEAD** with the actual numbers from a fresh
   `mypy` + `ruff check` + `ruff format --check` + `pytest -q`.
4. Add/remove **follow-ups** as they appear/resolve. Don't let
   this list grow past ~5 items; promote chronic ones into §13
   open questions or into a new task row.

---

## 1. North Star

A clinical research coordinator (CRC) loads a patient and a trial. The system
returns, for every eligibility criterion, one of `eligible | ineligible |
indeterminate`, with a citation to the source criterion text and a citation to
the supporting (or missing) patient evidence. The CRC accepts, overrides, or
flags. Aggregated verdict + a "missing data" worklist are produced.

Two entry directions, one engine:

- **Patient → Trials.** Given one patient, surface candidate trials.
- **Trial → Patients.** Given one trial, screen and rank a cohort.

The system never autonomously enrolls anyone.

---

## 2. What the JD is actually testing (and how this project answers it)

| JD signal | How this project demonstrates it |
|---|---|
| End-to-end shipping | Deployed demo on `juliusm.com`, not slides. |
| Context engineering | Trial protocols + multi-year FHIR records do not fit naively in context — explicit pre-extraction, retrieval, structured intermediate representations. |
| Evaluation discipline | Three-layer eval: deterministic (numeric criteria vs. Synthea ground truth), reference-based (extraction vs. Chia annotations), LLM-as-judge with calibration against hand-graded examples. Regression harness. Red-team set. |
| Model strategy fluency | Cost/quality sweep across 4–5 models. Documented routing policy with quantified savings vs. naive frontier-everywhere. |
| Auditable / observable | Langfuse traces from day one. Every verdict cites both criterion text and patient evidence. |
| Production discipline for enterprise | Deployment readiness doc framing PHI handling, prompt injection, model risk management (SR 11-7 / FDA GMLP / NIST AI RMF), rollout phases. |
| Coaching while building | Pod-composition section in deployment readiness doc — what 3 engineers + an account lead each own; what a junior dev's first ticket looks like. |
| Bias to action | Ship the ugly path end-to-end before polishing any one part. |

---

## 3. Domain scope

**Primary cluster: cardiometabolic.** Type 2 diabetes, hypertension,
hyperlipidemia, related CKD. Picked because Synthea models this domain richly
(longitudinal HbA1c, BP, lipids, eGFR, multiple meds, complications) *and*
trials in this space lean heavily on numeric criteria — which gives clean
deterministic ground truth for the eval.

**Stretch domain: lung cancer is deferred unless explicitly hand-crafted.**
Oncology is useful for demonstrating where confidence should drop, but it is
not part of the core demo unless we also add oncology-capable patient evidence
(pathology/staging/biomarker records or notes). The project should not ask the
cardiometabolic Synthea cohort to prove NSCLC matching. If time gets tight,
remove oncology from the eval seed and presentation entirely rather than
letting unmapped oncology concepts dominate the next engineering step.

**Explicitly out of scope:** all other Synthea modules. If asked "why not X?"
in the interview, the answer is "I prioritized depth in domains where I could
prove correctness over breadth I couldn't validate."

---

## 4. Data trinity

| Source | Role | Risks |
|---|---|---|
| **Synthea v4.0.0** (sample data, FHIR R4) | Synthetic patient records. Provides deterministic ground truth for numeric cardiometabolic criteria. | Structured FHIR rows are not a full chart. Absence of a row should be treated as insufficient evidence unless a closed-world eval mode is explicitly enabled. Oncology depth is shallow; do not use it for core validation without supplementation. |
| **MIMIC-IV / MIMIC-IV-Note** (credentialed PhysioNet access; Phase 3) | Private calibration/enhancement input for patient data files once access is approved. Use `hosp`/`icu` tables and MIMIC-IV-Note locally to improve evidence schema coverage, retrieval behavior, synthetic/fixture realism, and note adjudication tests. | The system must not reproduce MIMIC records or expose MIMIC-derived row-level excerpts. Credentialed data must stay outside git and public artifacts. Dates are deidentified and patient-relative; notes require strict citation, prompt-injection handling, and no raw excerpt leakage beyond the local credentialed environment. This validates realism, not public demo distribution. |
| **ClinicalTrials.gov v2 API** | Real trial protocols (eligibility text, conditions, phase, sponsor). | Eligibility criteria are free text — extraction is the hard part. |
| **Chia corpus** (Phase IV, 1,000 trials, hand-annotated) | Golden ground truth for the criterion-extraction step (entities + relationships per the Chia schema). | Doesn't overlap perfectly with our chosen domains; use the schema everywhere, use the labels where they fit. |
| **TREC Clinical Trials / TrialGPT** (Phase 3 external benchmark) | External patient-summary-to-trial retrieval/ranking benchmark and architecture comparison. The local scaffold already mirrors retrieval -> criterion matching -> ranking; official ingestion is needed for comparable scores. | TREC/TrialGPT benchmark results answer a different question from patient-evidence calibration: ranking against external relevance judgments, not whether a specific local FHIR row supports a criterion. Keep metrics/reporting separate. |

**Curated working set targets:**

- ~150 Synthea patients tilted to the cardiometabolic profile, with
  multi-condition overlap (a patient with T2DM + HTN + CKD3 is realistic and
  great for stress-testing).
- ~30 trials from CT.gov, focused on cardiometabolic disease for the core demo.
  Lung cancer trials are optional stretch examples only if paired with
  hand-crafted oncology evidence; otherwise exclude them from the correctness
  story.
- ~50–100 Chia-annotated trials retained as extraction golden set, filtered
  toward overlap with our domains.
- A small patient-side FHIR evidence gold/calibration set drawn from the eval
  seed: criterion text + retrieved patient source rows + human labels for
  whether the chart supports presence, explicit absence, a measurement
  comparison, or insufficient evidence. This is the patient-side analogue to
  Chia, scoped to matcher adjudication rather than full enrollment truth. It
  should contain rows the current project is actually trying to adjudicate, not
  out-of-scope terminology misses masquerading as evidence labels.

Generation parameters, Synthea-vs-real-EHR gaps, and the follow-up plan for a
more robust generated cohort are captured in
[`docs/synthea-generation-research.md`](./docs/synthea-generation-research.md).

---

## 5. Architecture (one paragraph)

A trial is parsed and its eligibility text is run through a **Criterion
Extractor** (cheap model, JSON-schema output following Chia entities). A
patient is parsed by a **Patient Profiler** (deterministic FHIR parsers; light
LLM only for unstructured notes). For each (patient, trial) pair, a **LangGraph
workflow** fans out per criterion: a deterministic matcher attempts the verdict
first (numeric thresholds, age, sex, active conditions); only on miss does it
escalate to an LLM matcher with the relevant patient slice as context.
Per-criterion verdicts are joined and passed to an **Aggregator + Critic** loop
(frontier model) that checks for contradictions, missed deterministic matches,
and hallucinated criteria, with a bounded number of revision iterations. The
final per-criterion + aggregate result is rendered in a **Svelte reviewer UI**
on `juliusm.com`, side-by-side with sources, with accept/override/flag
controls whose feedback is captured into the eval dataset. Every step is traced
in **Langfuse**.

Architecture diagram (Mermaid + ASCII) lives in `description.md`.

---

## 6. Build plan with hour estimates

Estimates assume focused work, alone, with normal blockers. Total budget is
~100–150 hours across three phases plus a polish/buffer phase. If I'm running
hot or slow, the *scope* gives, not the deadline — see §9.

### Phase 1 — Data + skeleton (target: end-to-end ugly path running)

| # | Task | Est. (hr) |
|---|---|---|
| 1.1 | Project scaffolding: Python 3.12, `uv`, repo layout, ruff/black, pre-commit, `.env.example`, README stub, dependency pinning. | 2 |
| 1.2 | Pull Synthea sample data; write loader that yields parsed Patient objects (demographics, conditions, observations, medications) from per-patient FHIR bundles. *Done.* | 4 |
| 1.3 | Curate the working patient cohort (~150) by querying the loader for cardiometabolic profiles; persist a manifest. *Done.* | 2 |
| 1.4 | Pull ~30 trials from CT.gov v2 API; persist raw JSON + a normalized trial record. *Done.* | 3 |
| 1.5 | Pull Chia corpus, parse the BRAT annotations, build a Pydantic representation of the Chia schema (entities + relations). *Done.* | 4 |
| 1.6 | Hand-pick ~30 trials and ~50 (patient, trial) pairs as the **eval seed set**. Hand-label expected per-criterion verdicts for the pairs (this is the most boring, most important task in the whole project — block out a real afternoon). *Skeleton + mechanical pass done; free-text human pass owed (~856 criteria across 49 pairs).* | 6 |
| 1.7 | Patient Profiler v0: deterministic FHIR → typed Python objects with `as_of_date` slicing. *Done — `PatientProfile` wrapper, 5-state threshold primitives (meets/does_not_meet/no_data/stale_data/unit_mismatch), curated SNOMED+LOINC ConceptSets, eval seed labelers refactored to use the profile.* | 4 |
| 1.8 | Criterion Extractor v0: single model, single prompt, JSON-schema output mirroring the Chia entity types. No retries, no router. *Done — OpenAI structured outputs (`gpt-4o-mini-2024-07-18` default), matcher-ready discriminated schema, 2 few-shot examples drawn from real eligibility text, prompt versioned at `extractor-v0.1`, smoke-script `extract_criteria.py`, 34 unit tests with stub client.* | 4 |
| 1.9 | Deterministic matcher v0: covers numeric criteria, age, sex, active condition presence/absence. Returns `pass | fail | indeterminate`. *Done — `MatchVerdict` with typed `Evidence` rows, 8-kind dispatcher (age, sex, condition_present/absent, medication_present/absent, measurement_threshold, temporal_window, free_text), polarity/negation XOR truth-table, surface-form → ConceptSet lookup table for cardiometabolic conditions and labs, 79 unit tests (per-kind pass/fail/indeterminate + integration), matcher pinned at `matcher-v0.1`.* | 4 |
| 1.10 | Glue script: `score_pair(patient, trial) -> List[CriterionVerdict]`, runs from the CLI. *Done — `clinical_demo.scoring.score_pair()` library entry returns a `ScorePairResult` (verdicts + extraction + summary + conservative `eligibility` rollup), `scripts/score_pair.py` CLI with `--no-llm` replay mode, `--force-extract`, `--json`, on-disk extraction cache shared with `extract_criteria.py`, 11 unit tests pinning the rollup truth table and the cache round-trip.* | 2 |
| 1.11 | Wire Langfuse from day one — every LLM call traced; project name `clinical-demo`. *Done — `clinical_demo.observability` shim wraps Langfuse v4 (`@observe`-style `traced(...)` context manager that no-ops when keys are absent and is defensive on every call), `extract_criteria` emits one `generation` per call (model + prompt_version + input/output + tokens + cost + latency, refusals tagged `WARNING`), `score_pair` opens a parent `span` per (patient, trial) pair tagged with `patient_id`/`nct_id`/`eligibility`/verdict counts so the extractor's generation nests under it; CLI scripts `flush()` at exit; 15 unit tests pin the no-op + recording-client contracts.* | 2 |
| **Phase 1 total** | | **~37 hr** |
| **Exit criterion** | One CLI command takes one patient + one trial and prints per-criterion verdicts with citations. Ugly is fine. | |

### Phase 2 — Workflow + eval

| # | Task | Est. (hr) |
|---|---|---|
| 2.1 | LangGraph migration: per-criterion fan-out, deterministic-first conditional routing, LLM matcher node, join. *Done — `clinical_demo.graph` package: `ScoringState` TypedDict with an `operator.add` reducer over `(criterion_index, MatchVerdict)` tuples; nodes for `extract`, deterministic match (thin wrapper over `match_criterion`), LLM match (new — strict structured-output OpenAI call gated on `kind == "free_text"`, with stub-friendly Protocol client), and `rollup` (sort indices, reuse imperative `_summarize`/`_rollup`); routing via `fan_out_criteria` returning `Send` objects (or rollup name when zero criteria); `score_pair_graph()` mirrors `score_pair()` with the same `ScorePairResult` envelope; opens a parent `score_pair_graph` span tagged `orchestrator=langgraph` so extractor + per-criterion `llm_match` generations nest under it. Side-by-side mirror script `scripts/score_pair_graph.py`. 35 new tests pin state, routing, both matcher nodes, end-to-end, and span structure (299 total passing). Decisions D-45..D-49.* | 5 |
| 2.2 | Aggregator + Critic loop: bounded revision iterations, termination conditions, human-checkpoint hook. *Done — `clinical_demo.graph` package gains `critic_node`, `revise_node`, `finalize_node` and a `route_after_critic` conditional edge wired as `rollup → critic → [revise → rollup` \| `finalize]`. The critic is a separate LLM call with its own pinned prompt (`LLM_CRITIC_VERSION = "llm-critic-v0.1"`) that emits closed-enum **process** findings (`polarity_smell`, `extraction_disagreement_with_text`, `low_confidence_indeterminate`) with `info` \| `warning` \| `blocker` severities; it never re-decides eligibility itself. Revise picks the highest-severity warning, dispatches to a closed-enum action (`rerun_match_with_focus`, `flip_polarity_and_rematch`, `rerun_extract_for_criterion`), and re-runs the existing matcher path so revisions stay auditable. Loop terminates on (a) no actionable findings, (b) `max_critic_iterations` budget (default 2), (c) no-progress detection comparing the current iteration's finding fingerprints to the previous; LangGraph's `recursion_limit` is a runtime config backstop. New `merge_indexed_verdicts` reducer gives `indexed_verdicts` replace-by-index semantics so revised verdicts supersede rather than coexist. Human checkpoint is opt-in (`human_checkpoint=True`): graph compiles with `InMemorySaver(serde=JsonPlusSerializer(pickle_fallback=True))` and `interrupt_before=[FINALIZE_NODE]`, requires a `thread_id`, and resumes via the same `score_pair_graph()` entry. Observability tags critic/revise/finalize spans with iteration + action + criterion-index + verdict-changed metadata, plus per-pair `critic_iterations` / `revisions_total` / `revisions_changed_verdict` on the parent. 32 new tests across `test_critic_node.py`, `test_revise_node.py`, `test_route_after_critic.py`, `test_critic_loop_e2e.py`, `test_human_checkpoint.py` cover defensive index filtering, refusal handling, fingerprint snapshots, action dispatch (free-text vs deterministic, polarity flip, no-op recording), termination conditions, e2e parity when the critic is disabled, and HITL pause/resume — plus expansions to `test_state.py` (new reducer + state keys) and `test_observability.py` (new spans). 340 total passing. Decisions D-50..D-58.* | 4 |
| 2.3 | Eval harness scaffolding: dataset format, runner, results store, basic CLI (`eval run`, `eval report`). *Done — new `clinical_demo.evals` package adds `EvalCase` / `CaseRecord` / `RunResult` pydantic envelopes, `load_dataset()` reusing the existing `eval_seed.json` shape, and a one-call `run_eval(scorer, cases)` that's deliberately orchestrator-agnostic (the scorer is a `Callable[[EvalCase], ScorePairResult]`, so `score_pair()`, `score_pair_graph()`, and any future variants are all "just a scorer"). SQLite store (`evals.store`) is two append-only tables — `runs` plus `cases` carrying flat per-case summary cols **and** the full `ScorePairResult` as a `result_json` blob (D-60); a normalized verdicts table is deferred until a layer query motivates it. Per-case scorer exceptions are caught and recorded on the row instead of failing the run (D-62). New `scripts/eval.py` exposes `run` (with `--orchestrator`, `--no-llm`, `--critic-enabled`, `--pair-id`, `--limit`, `--notes`) and `report` (id-or-list, `--format text\|json`); `eval/runs.sqlite` is gitignored. 20 new tests across `test_run.py` (dataset round-trip, filtering, runner success + failure isolation + callback ordering) and `test_store.py` (idempotent schema + `user_version`, save/load round-trip including `extraction_meta`, append-only enforcement, failed-case persistence, listing newest-first). 360 total passing. Decisions D-59..D-63.* | 4 |
| 2.4 | Layer 1 eval — deterministic: per-criterion accuracy on numeric/structured criteria. *Done — `evals/layer_one.py` aligns seed `CriterionVerdict`s against matcher `MatchVerdict`s per field (`min_age`, `max_age`, `sex`; `healthy_volunteers` documented uncoverable in v0), produces `LayerOneCell`s with `agree`/`disagree`/`missing` status, and rolls up per-field + overall agreement (excludes missing) and coverage (includes missing). `evals/report_layer_one.py` is a one-screen text renderer; `scripts/eval.py report --layer 1` dispatches to it (`--format json` also supported). 13 new tests. 373 total passing.* | 2 |
| 2.5 | Layer 2 eval — reference-based: criterion extraction F1 vs. Chia annotations. *v0 done — entity-mention F1 over normalized `(type, surface)` pairs, because the extractor emits flat `mentions` but not Chia relations/equivalence groups. Added `evals.layer_two`, `report_layer_two`, and `scripts/eval.py chia` with prompt/schema/model-aware extraction caching under `data/curated/chia_extractions/`. 5-document live smoke: 275 gold, 114 predicted, 50 TP; micro precision 43.9%, recall 18.2%, F1 25.7%; macro F1 24.9%; cost $0.0078; JSON snapshot in `eval/baselines/2026-04-30/layer2_chia_entity_f1_smoke.json`. Retained 50-document sample frozen with `--sample-size 50 --sample-seed 20260430`: baseline micro F1 34.4%, macro F1 33.0%, cost $0.0588. `extractor-v0.3` mention-discipline pass improved retained micro F1 to 37.5% (+3.2 pp) and macro F1 to 35.4% (+2.4 pp), mostly via `Value`, `Temporal`, `Procedure`, `Reference_point`, and `Measurement`, but over-predicted `Observation` and barely moved `Scope`. Added overlap/containment diagnostics: same v0.3 retained sample has 159 same-type partial matches, lenient micro F1 57.4%, lenient macro F1 54.3%. `extractor-v0.4` prompt tightening regressed and was not retained. `extractor-v0.5` recovered aggregate metrics: micro F1 37.7%, macro F1 35.3%, lenient micro F1 58.6%, lenient macro F1 55.3%; it cuts `Observation` false positives but still does not solve `Observation` exact TP or `Scope` recall. Error profile in `docs/chia-layer2-error-profile.md`; next layer-2 work should be narrow `Scope` / `Observation` analysis or else moving on to layer 3, not graph-schema expansion yet.* | 4 |
| 2.6 | Layer 3 eval — LLM-as-judge: rubric, prompt, calibration against ~30–50 hand-graded examples; report inter-rater agreement. *Done — `evals.layer_three` adds a pinned judge/rubric (`llm-judge-v0.1` / `llm-judge-rubric-v0.2`), structured judge labels (`correct` / `incorrect` / `unjudgeable`), persisted-run target selection, optional human labels, agreement-rate + Cohen's kappa, and `report_layer_three`. `scripts/eval.py judge` runs the judge over a stored eval run with `--limit`, `--only-free-text`, `--human-labels`, and `--output-json`. 5-verdict live smoke on run `98568ccd090d` cost $0.0008 and saved `eval/baselines/2026-04-30/layer3_judge_smoke.json`; the smoke caught and fixed an important rubric issue so justified `indeterminate` verdicts are graded `correct`, not `unjudgeable`. Calibration GUI follow-up done — FastAPI exposes `/eval/runs` plus `/layer3/calibration` GET/POST over deterministic stratified judge targets and JSON label persistence, and the Svelte reviewer has a `Layer-3 calibration` mode for reviewing criterion/verdict/evidence JSON, assigning human labels, adding rationale, and saving `eval/calibration/layer3_human_labels.json`. First human pass: 25 labels, all `correct`. Full calibrated judge run on `394703892184`: 1,086 judgments, 1,066 correct, 20 incorrect, cost `$0.1738`; calibration agreement 25/25, kappa 1.0. Interpretation: the judge/matcher rubric is calibrated for conservative verdicts, but the result highlights the deterministic matcher's patient-evidence coverage weakness. Use 2.12-2.16 to reduce correct-but-not-useful indeterminates and the 20 judged incorrect rows while keeping terminology gaps distinct from patient-evidence adjudication gaps.* | 6 |
| 2.7 | First baseline regression run; commit numbers to repo as `eval/baselines/`. *Done — fresh extraction over all 30 curated trials under the D-66 cache scheme (570 criteria, $0.067, ~18 min wall), then two eval runs against the 49-pair seed: imperative (`b55783ff962f`, ~14s scoring on cache-warm) and graph + critic (`ae7ac16936b8`, ~5 min). Both runs written to `eval/runs.sqlite`; layer-1 reports + pretty run summaries snapshotted under `eval/baselines/2026-04-21/` with a `SUMMARY.md` (provenance + per-field numbers + slice rollup) and an `INDETERMINACY.md` (per-criterion diagnostic answering "why so much indeterminacy"). Headline: layer-1 overall agreement 81.0%, coverage 55.3%, and identical between orchestrators (critic acts on rollup/rationale, not per-criterion structured-field dispatch). All 8 layer-1 disagreements are matcher-correct + seed-partial-label artifacts (mechanical labeler scored `min_age` independently of `max_age`). 0 `pass` eligibility verdicts across 49 pairs is real — synthea cohort × these specific trials don't align well, and the rollup is correctly conservative. Diagnostic finding: 92% of all 841 per-criterion verdicts are `indeterminate`, of which 89% are `unmapped_concept`; conditions dominate (73% of unmapped) over labs (17%) over medications (6%); top investment is concept-vocabulary expansion (D-67). Side fix landed in this task: store schema bumped v1→v2 with an additive `ALTER TABLE` migration to persist `expected_structured` and `free_text_review_status` per case, so layer-1+ analyses run from a self-contained persisted run instead of re-loading the seed file (was a silent layer-1-empty-report bug). 2 new store tests (v1→v2 migration, label round-trip), 1 existing test edited for the version bump. 393 total passing. Decisions D-67, D-68.* | 2 |
| 2.8 | Svelte reviewer UI v0: side-by-side trial criteria + patient evidence; per-criterion verdict pills; click-to-source. *Done — SvelteKit single-page app under `web/` (Svelte 5, TypeScript, static adapter). Hand-typed `lib/api.ts` over the four FastAPI routes (no codegen — surface is ~30 lines and `juliusm.com` will retype anyway). Single `+page.svelte` mounts patient + trial selectors from `/patients` and `/trials`, posts `/score` with toggles for orchestrator (`imperative` \| `graph`), critic loop, cached extraction, and `as_of`; renders the `ScorePairResult` as a header card (eligibility pill + verdict counts + extractor model / cost / token meta) and a list of `<CriterionRow>`s. Each row is a click-to-expand affordance: collapsed shows polarity + kind + source bullet + verdict pill; expanded shows the matcher's rationale, typed evidence rows (lab / condition / medication / demographics / trial_field / missing), and a `<details>` with the raw extracted criterion JSON for debugging. Layer-3 calibration mode now also shows patient-record and trial-record source context so reviewers can inspect whether mappings, absence claims, and unit assumptions are grounded in the actual source rows. `<VerdictPill>` is a closed-enum component over `pass` \| `fail` \| `indeterminate` with a per-verdict palette. Health badge in the header probes `/health` on mount; catalog and score errors are surfaced inline as banners (no toasts, no router). API base URL defaults to `http://127.0.0.1:8000` and is overridable via `VITE_API_BASE`. Per **D-64** this lives here as a *dev rig only* — the production reviewer surface ports into the `juliusm.com` repo, so this directory carries no JS test runner, no build pipeline beyond `vite dev`, and no deploy adapter. `web/.gitignore` covers `node_modules` / `.svelte-kit` / `build` so the repo root stays Python-only. Decision D-64. | 8 |
| 2.9 | Backend: minimal FastAPI endpoint that the Svelte UI calls; CORS; deploy plan for `juliusm.com`. *Done — `clinical_demo.api` package: `create_app()` factory exposing `GET /health`, `GET /patients`, `GET /trials`, `POST /score`. `/score` accepts `patient_id`, `nct_id`, optional `as_of` (defaults to today), `orchestrator` (`imperative` or `graph`), `critic_enabled`, `use_cached_extraction`, returns the existing `ScorePairResult` envelope verbatim. Loader helpers promoted out of `scripts/` into `api/loaders.py` (third caller threshold) with process-scope caches and a `CuratedDataMissing` exception for clean 503 mapping. Wide-open CORS for the v0 demo (lock down before public deploy). `scripts/serve.py` boots uvicorn. 12 new TestClient tests pin /health, listing endpoints, scoring round-trip, error mapping (404 unknown patient/trial, 503 missing curated data, 500 scorer raises, 422 missing field), and the orchestrator switch. Built ahead of 2.4-2.7 per user direction to bias toward end-to-end usability. 385 total passing.* | 3 |
| 2.10 | **Terminology API bridge (D-69).** Replace the hand-curated trial-term bridge with NLM-backed resolution in slices. First slice: `clinical_demo.terminology` with a VSAC FHIR `$expand` client, `Settings.umls_api_key`, a live probe script, and offline parser/error-path tests. Follow-on slices: add RxNorm medication normalization, UMLS source-vocabulary search, a small cache of reviewed trial-side bindings, matcher wiring through `concept_lookup.py`, and an eval rerun comparing against the D-68 `unmapped_concept` baseline. | 10 |
| 2.11 | **Patient structured-safety cleanup.** Carry `Patient.deceasedDateTime` through the Synthea loader/domain model and make scoring fail/skip explicitly when the patient is deceased before `as_of`. Keep it deterministic, cite the source field in evidence or API error detail, and test it before any public-demo run. *Done — `Patient.deceased_date: date \| None` round-trips through the Synthea loader (`deceasedDateTime` parsed; `deceasedBoolean=true` without a date falls back to `birth_date` with a warning). `score_pair` and `score_pair_graph` raise the new `clinical_demo.scoring.PatientDeceasedError` (cites `Patient.deceasedDateTime`) when `deceased_date <= as_of`, including the equality boundary; later-than-as_of deaths still score (retrospective replay still works). FastAPI `/score` maps the error to `422 {error: "patient_deceased", patient_id, deceased_date, as_of, source_field, message}` instead of a 500. New deceased-path tests in synthea / scoring / graph / api suites; `uv run pytest` 608/608, `uv run ruff check .` clean, `uv run mypy src` clean.* | 1 |
| 2.12 | **Core-scope and calibration reset.** Keep the patient-side analogue to Chia, but make it serve the product rather than block it. Filter or regenerate the 60-row packet so the gold set focuses on in-scope cardiometabolic rows the system can reasonably adjudicate from Synthea FHIR: condition presence, explicit absence where available, medication evidence, measurements/units, no-data, and insufficient-evidence cases. Exclude or separately mark out-of-scope terminology gaps such as NSCLC unless paired with hand-crafted oncology evidence. Persist reviewed labels with `patient_id`, `nct_id`, `criterion_index`, criterion source text, cited source-row IDs, human evidence label (`supports_present` / `supports_absent` / `supports_measurement_comparison` / `insufficient_evidence`), expected matcher verdict, and the matcher assumption mode used. *Done for first pass — candidate selection now defaults to `cardiometabolic_core`, filters out the NSCLC slice, ignores non-patient-evidence judge errors, records `eval_slice`, and regenerated the 60-row packet with 0 NSCLC rows. Labels are still intentionally blank; human review is next before treating it as gold.* | 2 |
| 2.13 | **Matcher assumption modes and LLM-use levels.** Make the workflow explicit about what kind of evidence contract it is operating under before adding more model behavior. Default `open_world`: absence of a patient row means `insufficient_evidence` / `indeterminate`, not fail. Optional `closed_world_eval`: for synthetic benchmark slices only, absence from the curated structured record may count as negative evidence. Optional `closed_world_demo`: allowed only for hand-picked demo cases with a visible banner explaining the assumption. Pair this with LLM-use levels that the API, UI, and eval harness can toggle: `none` (deterministic only), `retrieval_only` (retrieve/cite evidence, no adjudication), `bounded_adjudication` (criterion-level LLM over retrieved sources), and `critic` (frontier review of aggregate reasoning). *Mostly done for product plumbing — `MatcherAssumptionMode` and `LLMUseLevel` are typed contracts; patient-evidence candidate rows and human labels persist `matcher_assumption_mode`; scorer/API/eval/CLI/UI now accept the controls; `ScorePairResult` records both modes. 2026-05-04 eval snapshots compare `none`, `retrieval_only`, and `bounded_adjudication`. Remaining work is true closed-world behavior in matcher/eval execution plus cost/quality accounting for routing.* | 3 |
| 2.14 | **Structured patient-evidence retrieval path.** Add the source-grounded retrieval layer that embodies the core product loop without asking an LLM to decide yet: for each unresolved criterion, retrieve relevant structured FHIR rows using lexical matching, normalized surface forms, code/ConceptSet anchors where available, and simple section/kind filters. Return ranked source rows with stable IDs and retrieval reasons. Leave vector retrieval behind an interface so Phase 3 can add embeddings or note snippets without reshaping the graph. This powers `retrieval_only` mode and gives reviewers a useful "what did the system look at?" view even when adjudication is off. *Done for structured rows — `clinical_demo.retrieval.patient_evidence` ranks patient source rows using ConceptSet/code anchors, lexical overlap, and row-kind preferences; the calibration packet includes retrieved row ids/reasons; `llm_use_level=\"retrieval_only\"` now attaches `retrieved_patient_row` evidence to indeterminate verdicts in both imperative and graph scoring; FastAPI `/score`, eval, CLI, and the Score UI expose/render it. Numeric-only overlaps are ignored so terms like `type 1 diabetes` do not highlight unrelated lab rows just because a unit contains `1`. The 2026-05-04 retrieval-only eval attached evidence to 627 unresolved criterion verdicts and, by design, changed 0 verdicts. Remaining work is the vector/note retrieval interface for Phase 3.* | 4 |
| 2.15 | **Bounded LLM patient-evidence adjudicator.** Add the criterion-level adjudicator over retrieved evidence, not over the whole chart. Input is the extracted criterion, deterministic verdict/reason, retrieved patient rows, trial source text, and matcher assumption mode; output is strict `pass` / `fail` / `indeterminate` with cited source row IDs and a reason. Use terminology/code matches as precision anchors when available, but allow the adjudicator to classify supported, contradicted, or insufficiently supported evidence when concept mapping is incomplete. This is the architectural home for "does this patient appear to match enough to flag for CRC review?", not a post-hoc explanation layer. Evaluate against the reset 2.12 labels. *First pass implemented and rerun — `clinical_demo.adjudication.patient_evidence` defines the prompt, structured output, fail-closed citation validation, Langfuse generation span, and `PATIENT_EVIDENCE_ADJUDICATOR_VERSION`; `llm_use_level=\"bounded_adjudication\"` runs it after retrieval for indeterminate verdicts in imperative and graph scoring. The 2026-05-04 bounded run changed 39 criterion verdicts from indeterminate -> pass and 15 from indeterminate -> fail; top-level eligibility moved 9/49 cases from indeterminate -> fail and 0 -> pass. Remaining work is human calibration: `eval/calibration/patient_evidence_labels.json` still has 0/60 filled labels, so prompt tuning should wait for actual failures.* | 5 |
| 2.16 | **Unit reconciliation / conventional-unit pass.** Add a hybrid unit layer for high-impact measurements before the cost-routing sweep. Deterministic code owns a small whitelisted registry and numeric conversions (initially BP mmHg, eGFR `mL/min/1.73 m2` variants, LDL-C `mmol/L` <-> `mg/dL`, and percent-like HbA1c); an LLM/source pass may infer the intended measurement/unit from trial text when the extractor omits or phrases it oddly, but it may not perform arbitrary conversions. Rerun eval and report reductions in `unit_mismatch` / `ambiguous_criterion`. *First pass implemented and rerun — profile unit normalization now covers eGFR variants and LDL-C `mmol/L` <-> `mg/dL`; matcher infers missing conventional units for eGFR, HbA1c, and BP thresholds when a matching patient observation exists. The refreshed deterministic eval has only 2 criterion-level `unit_mismatch` reasons left, but the current baseline is not enough to quantify pre/post reduction cleanly because extractor-v0.5 cache refresh also changed the criterion set. Remaining work is deciding whether any additional high-impact unit families deserve whitelisting.* | 3 |
| 2.17 | **Open terminology resolver front door.** Replace the current registry-gated `two_pass` policy with an open resolver contract: input is `(kind, surface_text, optional criterion context)`, output is a cached `ConceptSet` resolution, cached ambiguity, cached true miss, or explicit composite/non-mappable classification. Resolution order: curated overrides first, resolved/negative cache second, terminology API search third. The existing bindings registry becomes curated overrides plus offline fixtures; it must not be the only path that can call NLM/RxNorm. High-confidence single hits may feed the deterministic matcher; ambiguous hits must return candidate metadata instead of pretending certainty; true misses remain `unmapped_concept`; composite phrases become `composite_unhandled` / `human_review_required` unless safely split into atomic concepts. Cache all outcomes, including misses and ambiguity, so repeated eval runs do not rediscover the same surfaces. Initial target surfaces come from the 2026-05-04 diagnostics: `hemoglobin`, `platelet count`, `bmi` / `body mass index`, generic `blood pressure`, pregnancy/breastfeeding, uncontrolled hypertension, common PAH/PH terms, and high-frequency medication/class surfaces. Exit criterion: the deterministic two-pass eval no longer has obviously mappable high-frequency concepts in `top_unmapped_surfaces`; remaining unmapped rows are true misses, composites, extractor errors, or out-of-scope concepts with explicit labels. *Done — `UMLSSearchClient` against `https://uts-ws.nlm.nih.gov/rest/search/current` is wired into `_resolve_open_condition` (SNOMED exact) and `_resolve_open_lab` (LOINC words + numeric-code filter) with `composite_unhandled` short-circuit before the API call and `true_miss` caching on clean zero-hit responses. RxNorm raw-surface search stays the med path. Smoke eval `43c765d1dbcc` moved `unmapped_concept` from 551/1077 (51.2%) to 445/1061 (41.9%), `indeterminate` from 92.5% to 86.6%, and added +52 pass / +9 fail / +61 `ok` verdicts. All 15 surfaces remaining in `top_unmapped_surfaces` are legitimately non-atomic (composites, out-of-scope for Synthea, extractor bugs, ambiguous). Snapshot lives at `eval/baselines/2026-05-04-umls/`.* | 8 |
| 2.18 | **Mappable-unmapped regression gate and cache warmer.** Turn `evals.diagnostics.top_unmapped_surfaces` into an engineering work queue. Add a report that classifies each top surface as `mapped` (formerly `resolved`), `ambiguous`, `true_miss`, `composite_unhandled`, `extractor_bug`, or `out_of_scope`, with resolver provenance and cache status. Add a cache-warming script that maps the top-N surfaces for a run/dataset and writes reusable cache rows before scoring. CI/local regression should fail or warn loudly when a high-frequency surface marked `mapped` falls back to `unmapped_concept`. Snapshot a new baseline comparing alias, registry-only two-pass, and open-resolver two-pass. *Done — work queue + cache warmer shipped first, then the 2026-05-05 baseline snapshot added open-world deterministic, closed-world deterministic, and retrieval-only diagnostics. `scripts/check_terminology_regressions.py` currently fails when any `status=resolved` watched surface reappears in `top_unmapped_surfaces`; follow-up 2.20 renames that status to `mapped` while preserving compatibility for the first watchlist at `eval/baselines/2026-05-05/resolved_surface_watchlist.json`. PR #2 snapshots the baseline and PR #3 adds the regression gate.* | 4 |
| 2.19 | **Closed-world matcher semantics.** After open mapping is working, make assumption modes change behavior instead of only being metadata/prompt context. `open_world` remains default: no patient row means insufficient evidence / indeterminate. `closed_world_eval` may treat absence from the curated synthetic structured record as negative evidence for specific closed, structured kinds only (condition_absent, medication_absent, selected demographics/labs), and must record the assumption in evidence. `closed_world_demo` is allowed only for hand-picked demo pairs with a visible UI/API banner. Do not use closed-world behavior to mask terminology failures; mapping has to run first. *Done — matcher v0.2 threads `matcher_assumption_mode` into `_match_condition` / `_match_medication` / `_match_temporal_window` (labs deliberately excluded; user wants N/A visibility). `open_world` returns `indeterminate(no_data)` for mapped-but-absent (also fixes a pre-existing silent-flip bug where `condition_absent` criteria silently flipped `fail` to `pass`); closed-world modes return `fail` with `evidence_under_assumption=True` stamped on the verdict. `unmapped_concept` is unchanged across modes (D-73 guardrail). `MatchVerdict` carries `assumption` + `evidence_under_assumption`. `EligibilityRollup` gains `pass_pending_review` for "no fails, every remaining indeterminate is `human_review_required`" — useful in any mode. UI/API banner for `closed_world_demo` deferred to follow-up (we are nowhere near demo polish yet). Twin baselines in `eval/baselines/2026-05-04-2.19/`: closed-world v0.2 reproduces v0.1 numbers exactly (`pass`=110 / `fail`=32 / `indeterminate`=919 / `ok`=142), confirming faithful re-implementation; honest open-world is `pass`=77 / `fail`=21 / `indeterminate`=963 / `ok`=98 / `no_data` 62 vs 18.* | 3 |
| 2.20 | **Mapping expansion + `mapped` terminology rename.** Continue adding high-impact mapping cases from diagnostics, including obvious condition/lab/medication surfaces that should not survive as `unmapped_concept`. Rename report/cache/work-queue success language from `resolved` to `mapped`, with backward-compatible reads for existing `status=resolved` artifacts and legacy filenames. The exit criterion is that newly mapped high-frequency surfaces stay out of `top_unmapped_surfaces`, the regression gate speaks in `mapped` terms, and old baselines still load. | 3 |
| 2.21 | **Criterion fixing layer.** Add a bounded layer after extraction and before deterministic matching that repairs criterion shape without hiding uncertainty: normalize surfaces and abbreviations, split safely splittable composites into atomic checks, repair obvious polarity/unit/context issues, attach mapping candidates/provenance, and mark unsafe fixes as `human_review_required`. LLM use is allowed here for interpretation, but deterministic validators and terminology cache results decide what is safe to feed into the matcher. | 5 |
| 2.22 | **Composite criterion representation.** Add an explicit representation for compound criteria with boolean semantics (`any_of`, `all_of`, later nested groups) before splitting OR/AND bundles into matcher-visible rows. The immediate target is reviewer-facing line items: an ADA hyperglycemia bullet should become subchecks such as HbA1c threshold, fasting glucose threshold, OGTT threshold, and random glucose + symptoms threshold, each with its own retrieved evidence and citation state, while the parent criterion remains one top-level eligibility row. Do not model OR bundles as independent inclusion criteria under the current AND rollup. Sequence: first add a real parent/subcheck schema and per-subcheck retrieval; second wire the UI/adjudicator context to that schema; third add matcher/adjudicator semantics for parent `any_of` / `all_of`; only then regenerate `eval/calibration/patient_evidence_candidates.json`. First slices landed: shared extractor-side composite group/subcheck construction; calibration rows expose stable composite group/subcheck ids with per-subcheck retrieved evidence; safe mapped lab thresholds can become typed subcheck criteria; scoring retrieval now unions parent and composite-subcheck evidence for retrieval-only / bounded adjudication without changing deterministic verdicts; a standalone matcher helper defines `any_of` / `all_of` truth tables but is intentionally not wired into `match_extracted` yet. Exit criterion: bounded adjudication can receive the parent criterion plus subcheck evidence without silently changing deterministic rollup, then matcher wiring can be added behind tests. Follow-up: extractor prompt/schema support, nested groups, Chia relation/equivalence alignment, and regression metrics for composite handling. | 5 |
| **Phase 2 total** | | **~89 hr** |
| **Exit criterion** | Full pipeline runs through LangGraph; baseline eval numbers committed; UI shows real results from real data. | |

### Phase 3 — Cost optimization, red-team, polish, writeup

| # | Task | Est. (hr) |
|---|---|---|
| 3.1 | Model abstraction layer that lets the same node call any of 4–5 models with consistent JSON-schema enforcement. It must preserve the LLM-use levels from 2.13 (`none`, `retrieval_only`, `bounded_adjudication`, `critic`) and make every LLM stage explicit: extraction, criterion fixing, mapping ambiguity review, bounded patient-evidence adjudication, note/free-text evidence adjudication, and critic/revision. Cost/quality experiments should measure routing choices, not hidden behavior changes. | 3 |
| 3.2 | Cost/quality sweep: same 50–100 in-scope cardiometabolic pairs, every model at every LLM-enabled node, log cost + composite quality score. Include deterministic-only and retrieval-only baselines so the dashboard can show how much value each additional LLM level adds. Preconditions: complete the open terminology resolver baseline (2.17/2.18) so cost/quality is not dominated by avoidable `unmapped_concept`, then fill the 60-row patient-evidence labels. The immediate blocker is the calibrated label set: target 60/60, minimum useful gate 40/60, with no LLM-generated labels treated as gold. Adjudicator token/cost telemetry now persists on `ScorePairResult.llm_calls` and the v3 `eval/runs.sqlite` schema (`adjudicator_cost_usd` / `adjudicator_input_tokens` / `adjudicator_output_tokens` / `adjudicator_calls`), so routing economics are already auditable from local eval artifacts. | 4 |
| 3.3 | Define and implement the routing policy after 2.12-2.16 establish the patient-side labels, matcher assumption modes, retrieval/adjudication path, unit layer, and LLM cost accounting; re-run eval; produce the "money slide" dashboard (cost vs. quality, before/after policy). Start with efficient measured reruns over `none`, `retrieval_only`, and one bounded-adjudication model before broad model sweeps; the policy should say when the system has enough support to flag a possible match and when it must abstain. | 4 |
| 3.3a | **TrialGPT/TREC-style benchmark scaffold.** Add a local benchmark schema/exporter that frames our seed around TrialGPT's retrieval -> criterion matching -> ranking shape and the TREC Clinical Trials patient-summary-to-suitable-trials task. This is a lightweight local scaffold for comparable reporting, not full official TREC ingestion. *First slice done — `clinical_demo.evals.trial_benchmark` defines patient-summary queries, trial-ranking candidates, criterion matching cases, prediction/metric schemas, and unknown-safe MRR / recall@10 helpers. `scripts/export_trial_benchmark.py` exports the 49-pair seed into `eval/benchmarks/local_trialgpt_trec_seed.json` (27 patient queries, 49 candidate trials, 60 criterion cases).* | 2 |
| 3.3b | **Official TREC/TrialGPT benchmark ingestion.** Download/register the official TREC Clinical Trials topics, trial corpus, and relevance judgments; pull the TrialGPT code/data references; write an adapter from external patient-summary/trial records into `clinical_demo.evals.trial_benchmark`; and report standard retrieval/ranking metrics such as recall@k, precision@k, nDCG@k, and MRR. Keep this as an external benchmark scoreboard, separate from the internal FHIR-row citation calibration. | 4 |
| 3.4 | Red-team set: prompt injection in patient narrative fields, adversarial negation, unit confusion, temporal traps, OOD criteria. ~15–20 cases. | 4 |
| 3.5 | Run red-team set; document failures; implement at least the cheap mitigations (input sanitization, structured-output enforcement, suspicious-pattern detection). | 4 |
| 3.6 | **Patient note/free-text evidence slice.** Parse FHIR `DocumentReference` attachments (`content.attachment.data` first; `url` later), build a patient-note evidence index with provenance (resource id, date, section/header, excerpt/offset), retrieve only criterion-relevant snippets for free-text criteria, and add a patient-side LLM evidence step that can return `pass | fail | indeterminate` only with citations. Generated `resource.text.div` is display/fallback only, not high-trust clinical evidence. This should start now as a bounded v0, not wait for perfect realism: Synthea free text is acceptable for plumbing tests only, hand-crafted note fixtures should cover clinical behavior, and MIMIC-IV-Note later calibrates realism. Validation set must cover explicit evidence, explicit absence, insufficient evidence, temporal/as-of boundaries, structured-vs-note contradiction, and prompt injection in note text. | 6 |
| 3.6a | **MIMIC-IV evidence adapter and data governance.** While access is pending, define `MIMIC_DATA_ROOT`/BigQuery config, ignored local artifact paths, and table-to-evidence mappings. After access is approved, use MIMIC-IV `hosp`/`icu` rows and MIMIC-IV-Note locally to calibrate and enhance patient data files, evidence schemas, retrieval behavior, and note adjudication tests. The system should consume these lessons/interfaces, not reproduce MIMIC records. No raw MIMIC data, derived row-level exports, or note excerpts are committed or included in public reports. | 5 |
| 3.7 | Reviewer UI v1: accept/override/flag with feedback persistence; basic auth gate (single-user is fine); polish. | 4 |
| 3.8 | Deploy to `juliusm.com`; smoke test; capture a screen-recording fallback in case live demo dies. | 3 |
| 3.9 | **Deployment readiness doc** — see §7. Includes a real revision pass. | 11 |
| 3.10 | 20-minute presentation deck — see §8. | 4 |
| 3.11 | Project README and repo polish (architecture diagram, eval results table, "how to reproduce", honest limitations section). | 3 |
| 3.12 | **Performance pass (far-future / after correctness).** Profile end-to-end latency before optimizing. Candidate work: precompute/cache patient profiles and note indexes, parallelize per-criterion deterministic matches, batch or cache terminology resolution, avoid duplicate extraction/cache reads, stream API progress for long graph runs, tune LLM matcher/critic concurrency with rate-limit guards, and add latency/cost budgets to eval reports so speedups are measured rather than guessed. | 4 |
| **Phase 3 total** | | **~65 hr** |
| **Exit criterion** | Deployed demo, dashboard, writeup, deck. The whole story can be told in 20 minutes. | |

### Phase 4 — Buffer / dogfood

| # | Task | Est. (hr) |
|---|---|---|
| 4.1 | Run the demo cold five times; fix what breaks. | 3 |
| 4.2 | Stretch oncology: add 1–2 hand-crafted lung cancer patient profiles + 1 oncology trial; show generalization slide. | 6 |
| 4.3 | Anything that overflowed earlier phases. | flex |
| **Phase 4 total** | | **~10–15 hr** |

**Grand total target: ~149 hours**, with hard scope cuts available (§9).

---

## 7. Deployment readiness doc — outline

A 6–10 page Markdown doc in the repo, written for a KPMG partner who is
technically literate but not an AI engineer. This is the differentiator. Sections:

1. **Problem & persona.** Who the CRC is, what their day looks like, what
   "good" means in business terms (eligible-patients-not-missed, time per
   screening, enrollment-deadline misses avoided).
2. **System overview.** One paragraph + the architecture diagram. No more.
3. **What it does and does not do.** Especially the "does not."
4. **Eval methodology + current numbers.** Including known weaknesses and the
   threshold below which I would not deploy.
5. **Cost analysis + routing policy.** Actual dollars per (patient, trial) at
   target quality. Naive baseline vs. routed.
6. **Risk register.** Hallucination, PHI exposure, prompt injection, model
   drift, demographic bias, regulatory (FDA SaMD-adjacent under 21 CFR 820.30),
   over-reliance / automation bias on the CRC's part.
7. **Model risk management framing.** Reference SR 11-7 (since financial
   services parallels carry weight at KPMG), FDA's Good Machine Learning
   Practice principles, NIST AI RMF. One paragraph each — *this is where the
   BA brain shines*.
8. **Rollout plan.** Pilot → expansion → scale. Concrete gates.
9. **Pod composition.** What 3 engineers + an account lead each own; first
   ticket for a junior; "coaching while building" example.
10. **Open questions for the client.** Real ones. This signals seniority.

---

## 8. 20-minute presentation arc

Brutal time budget. Practice with a stopwatch. Suggested split:

| Minutes | Beat | Slide(s) |
|---|---|---|
| 0:00–2:00 | Problem framing + who the user is. Why trial enrollment matters. | 1–2 |
| 2:00–6:00 | Live demo of the full workflow on one patient + trial. | UI, no slides |
| 6:00–8:00 | Architecture: one diagram, why LangGraph, why this split. | 1 |
| 8:00–14:00 | **The spike: eval methodology + cost-quality dashboard.** Show the routing policy and the savings. This is the money portion. | 3–4 |
| 14:00–17:00 | Deployment readiness highlights: risk register, MRM framing, rollout. | 1–2 |
| 17:00–20:00 | Honest limitations + open questions + what I'd build next with the pod. | 1 |

Q&A is separate. Stop at 20:00 even if mid-sentence — that *is* the demo of
production discipline.

---

## 9. Scope cuts (in priority order if time runs out)

Cut from the bottom up:

1. Drop the oncology stretch domain entirely — present only cardiometabolic.
   This is now the default unless hand-crafted oncology patient evidence is
   added; do not let NSCLC terminology gaps drive the core roadmap.
2. Drop reviewer UI accept/override; show read-only verdicts.
3. Drop one of the 4–5 models from the cost sweep (keep at least 3 spanning a real price range).
4. Drop the FastAPI deployment to `juliusm.com`; demo locally with a screen recording as backup.
5. ~~Drop the Critic loop; show a single-pass aggregator.~~
   *(N/A as of Phase 2.2 — the critic loop is built and gated by
   `critic_enabled=False`. If we need to "cut" it for the demo,
   we just don't pass the flag; no work to remove.)*
6. Drop the LangGraph migration; keep an async Python orchestrator. (Acknowledge this in the deck — explain *why* you didn't migrate, which is itself a senior-engineer answer.)

**Do not cut**, ever:

- The eval harness with at least one full layer working.
- The deployment readiness doc.
- The cost sweep across at least 3 models.
- A working live demo of a single (patient, trial) pair.
- Langfuse traces.

---

## 10. Stack

| Concern | Choice | Why |
|---|---|---|
| Language (backend) | Python 3.12 | LLM ecosystem is Python-native. |
| Package mgmt | `uv` | Fast, modern, lockfile. |
| LLM orchestration | LangGraph | Conditional routing, fan-out/join, critique loop, human checkpoint — real uses, not resume-padding. Acknowledge trade-offs in the deck. |
| Observability | Langfuse | Already familiar; matches "auditable" requirement. |
| Validation | Pydantic v2 | Structured outputs, schema enforcement. |
| FHIR parsing | `fhir.resources` (Pydantic-based) | Avoid hand-rolling. |
| HTTP / API | FastAPI | Minimal surface; pairs with Pydantic. |
| Frontend | Svelte (existing `juliusm.com` Astro setup) | Reuse personal-site infra; integration is itself a portfolio signal. Fall back to Streamlit if Svelte becomes a slog. |
| Eval | Custom harness, deliberately. Reference Inspect / OpenAI Evals / Promptfoo in the writeup but build something *we* control. | Eval design is the spike; using a black-box tool would undercut the demo. |
| Models | A spanning set across price tiers (e.g., a frontier, a mid-tier, a cheap) from at least two providers. Final choice locked in Phase 3 based on what's current. | Avoid single-provider lock-in narrative. |

---

## 11. Success criteria

How I'll know the project succeeded *before* the interview happens:

- A naive observer can use the deployed UI to evaluate a (patient, trial) pair
  in under 60 seconds and understand what the verdict means.
- The eval harness produces a single command that prints a results table
  comparable across runs, committed to the repo.
- The cost-quality dashboard shows a routing policy that beats
  "frontier-everywhere" on cost by ≥3× at ≥95% of the quality.
- The deployment readiness doc would survive being forwarded to a KPMG
  partner without requiring me in the room.
- The 20-minute deck has been delivered out loud, twice, to a friendly human,
  and finished within time.

---

## 12. Decision log

Captured so any choice can be defended in the interview without mid-flight
rationalization. Each entry: *what was decided, what was rejected, why.*

### D-1. Domain: cardiometabolic primary, lung cancer stretch
**Rejected:** credit memos (banking is "meh", domain authenticity risk),
KYC (even more synthetic-document-heavy and low downstream complexity), FDA
drug labels (too summarization-shaped, weak workflow), prior auth (highest
real-world value but most domain-folklore-dependent).
**Why:** clinical trial eligibility has the cleanest data trinity (Synthea +
CT.gov + Chia) and the workflow has real branching, real decisions, and a
real human-in-the-loop. Cardiometabolic specifically because Synthea is
strongest there *and* the criteria are most numeric — which gives clean
deterministic ground truth for the eval. Lung cancer added as a generalization
probe, not as a domain claim.

### D-2. Project shape: workflow assistant, not chatbot, not pure eval harness
**Rejected:** chatbot integrations (KPMG explicitly past this), pure
eval/cost-optimization framework as a product (lacks tangible application),
audit workpaper assistant (data authenticity risk; KPMG-on-the-nose to the
point of looking hand-tailored).
**Why:** the JD's repeated emphasis on shipped systems with real workflows
and human checkpoints. A workflow assistant lets us demonstrate *and* talk
about eval/cost discipline as the technical spike, without making it
abstract.

### D-3. LangGraph as the orchestration layer
**Rejected:** plain async Python orchestration.
**Why:** the workflow genuinely needs conditional routing (deterministic →
LLM escalation), fan-out/join (per-criterion parallelism), a bounded
critique loop, and a human checkpoint. These are LangGraph's actual value
prop, not a contrived use. Will explicitly acknowledge in the deck that for
strictly linear pipelines a function-of-functions is fine — *that* is the
senior-engineer signal, not blind framework enthusiasm.

### D-4. Synthetic data, no real PHI, but write the policy as if real
**Rejected:** trying to use real de-identified data (MIMIC requires
credentialing, slow, and unnecessary for a demo).
**Why:** Synthea is realistic enough to demo and removes any conceivable
data-handling risk. The PHI/security writeup is *more* valuable than real
data because it forces the same engineering discipline.

### D-5. Frontend on `juliusm.com` (Svelte/Astro), with Streamlit fallback
**Rejected:** Streamlit-only, Next.js/React rebuild.
**Why:** integrating into an existing portfolio site is itself a signal of
full-stack chops and is a venue the interviewer can revisit. Streamlit is
the documented escape hatch if Svelte becomes a time sink — that is an
engineering-judgment call to be made at the Phase 2 UI checkpoint, not now.

### D-6. Build the eval harness ourselves, do not adopt Inspect/OpenAI
Evals/Promptfoo wholesale
**Rejected:** off-the-shelf eval frameworks.
**Why:** eval design is *the* technical spike of this project. Using a
black-box framework would undercut the demonstration. Will reference the
ecosystem in the writeup to show awareness; will adopt patterns (golden
sets, regression suites, judge calibration) without ceding architectural
control.

### D-7. Cost optimization is a first-class deliverable, not a footnote
**Rejected:** treating cost as something to mention briefly.
**Why:** named explicitly by Julius as a strength and as something that
flows naturally from being able to eval. Most AI engineers stop at "does it
work." The routing-policy slide is the centerpiece of the technical
portion of the presentation.

### D-8. Hand-labeling the eval seed set is the most important boring task
**Rejected:** synthesizing labels with an LLM, or skipping ground truth and
relying on LLM-as-judge alone.
**Why:** without honest hand-labels, every downstream eval number is
self-referential and a senior interviewer will see through it immediately.
The afternoon spent labeling 50 pairs is what makes everything else credible.

### D-10. Synthea sample data: per-patient bundles, not bulk ndjson
**Rejected:** bulk-FHIR ndjson (one file per resource type).
**Why:** the upstream `synthea-sample-data` artifact ships per-patient
`Bundle` JSON files (latest dated Nov 2021 — Synthea the generator has
v4.0.0 from Mar 2026 but the sample-data artifact lags). Per-patient
bundles map 1:1 to our `Patient` domain object and the streaming benefit
of ndjson is irrelevant at the 555-patient scale. The PLAN.md task
description is updated accordingly.

### D-11. Encounters/Procedures/Allergies/Immunizations excluded from v0
**Rejected:** parsing every FHIR resource type Synthea emits.
**Why:** none of the cardiometabolic eligibility criteria we expect to
encounter in Phase 1 require these. Add when an actual criterion needs
them rather than building speculatively. Each new resource type costs
a parser, tests, and a domain-model decision.

### D-12. `is_clinical` flag on Condition is necessary-but-not-sufficient
**Rejected:** stronger upstream filtering at load time.
**Why:** Synthea categorizes most social findings (e.g.,
"Full-time employment", "Stress") as `encounter-diagnosis`, not
`social-history`. Filtering them out reliably needs either a curated
clinical-codes allowlist, a SNOMED-hierarchy walk, or matcher-side
reasoning. That decision belongs to task 1.3 (cohort curation) and the
matcher (task 1.9). The loader does the cheap-and-correct half and
hands off the hard half to a layer that can make a domain-informed call.

### D-13. Trial curation: sliced search over CT.gov, no hand-cherry-picking
**Rejected:** hand-curating each of the 30 trials, or one big query with
thousands of results then sampling.
**Why:** the curation script (`scripts/curate_trials.py`) splits the
target ~30 trials into seven labeled slices (T2DM industry/academic,
hypertension industry/academic, hyperlipidemia, CKD, NSCLC), each issuing
its own filtered CT.gov query and taking the first N hits with
eligibility text ≥200 chars. This trades a bit of curation noise for
reproducibility and an honest cross-section of what real CT.gov queries
return. The resulting noise (e.g., "ocular hypertension" matching the
hypertension query, a portal-hypertension chemo trial in the academic
hypertension slice) is *kept on purpose* — handling off-target trials
gracefully is part of what the extractor and matcher must demonstrate.
If demo polish demands it, we can hand-substitute a few trials in
Phase 3 and document that move.

### D-14. Trial domain model: keep CT.gov's structured fields verbatim
**Rejected:** parsing `minimum_age` / `maximum_age` strings into ints,
collapsing `phase` to a single value, looking up sponsor-class codes
into long names.
**Why:** CT.gov uses out-of-band conventions ("18 Years", "N/A",
"PHASE2" with optional second value, sponsor-class enums whose meaning
shifts) that we don't want to silently lose or normalize away. The
domain model holds them as the source provides them; downstream
consumers (matcher, UI) parse on demand with the right amount of
domain context. This is the same "convert once at the boundary, only
the fields you'll use" rule that the patient model follows.

### D-15. Cohort curation by weighted score, not random sample
**Rejected:** random sample of cardiometabolic patients; hand-curation
of all 150.
**Why:** the eligible Synthea pool is 267 patients with at least one
cardiometabolic SNOMED Condition active in 2025. A random 150 would be
dominated by prediabetes-only patients (Synthea's most common
cardiometabolic finding), giving boring "indeterminate" verdicts on
T2DM trials. Instead, score = `2 * core_count + prediabetes_count`
where the core set is T2DM, essential HTN, hypertensive disorder,
hyperlipidemia, and pure hypercholesterolemia. The 2x weight pulls
multi-condition patients to the top while still admitting
prediabetes-only patients as long-tail near-miss cases. CKD is
*excluded* from the cohort filter because Synthea emits ~12 CKD
patients across all 555 bundles — too sparse to slice meaningfully.
The curation date (`as_of`) is hard-coded in the script (2025-01-01)
and persisted in the manifest so the cohort is reproducible without
depending on the system clock. Final cohort: 150 patients, 74% with
≥2 cardiometabolic conditions, 100% SBP / 93% LDL / 50% HbA1c / 50%
eGFR availability.

### D-16. BP-panel components fixed in loader as part of cohort work
**Rejected:** deferring the loader bug to task 1.7 (Patient Profiler).
**Why:** while profiling Synthea for cohort curation we discovered the
loader was silently dropping every blood pressure measurement: Synthea
encodes BP as a panel under LOINC 85354-9 with no top-level value, and
the loader only handled top-level `valueQuantity`. Without the fix, 0
of 555 patients had a systolic BP and the cohort manifest would have
shown that fake limitation as a real one. Fix is a small generalization
(one `_parse_observation` returns a list; expands `component[]` when
the wrapper has no value) and adds two tests. Loader docstring updated
accordingly. The bug was real, hidden, and exactly the kind of thing
the cohort sanity-check exists to surface.

### D-17. Chia loader keeps the entity/relation type vocabulary open
**Rejected:** typing entity / relation labels as a closed enum drawn
from the published BRAT `annotation.conf`.
**Why:** scanning the actual corpus before designing the model
revealed that reality differs from the documentation in two
directions. The schema config lists 24 entity types, but the corpus
uses 31 — including process-of-annotation markers (`Parsing_Error`,
`Grammar_Error`, `Context_Error`), judgement annotations
(`Subjective_judgement`, `Undefined_semantics`, `Not_a_criteria`),
and one apparent typo (`c-Requires_causality`). Relations are even
worse: 5 documented, 14 in use (`Has_value`, `Has_temporal`,
`Has_qualifier`, `Subsumes`, `Has_index`, etc.). A closed enum would
force one of two bad choices: drop ~3% of annotations, or churn the
enum every time a new corpus is added. Instead we keep types as
plain strings, expose two `frozenset` constants
(`DOCUMENTED_ENTITY_TYPES`, `DOCUMENTED_RELATION_TYPES`) so consumers
can validate explicitly when they want to, and let downstream code
(extractor / matcher) decide what to use, ignore, or normalize. The
truth is that this corpus is messier than its spec — the model
should reflect that.

### D-18. Discontinuous spans and n-ary equivalence groups are first-class
**Rejected:** flattening discontinuous-span entities to their
bounding range, and splaying n-ary `OR` groups into pairwise binary
relations.
**Why:** 1,822 of the 48,870 entities (~3.7%) have discontinuous
spans — usually clinically meaningful pulls like
"major impairment of [renal] function" + "[hepatic]" from a single
phrase. Collapsing them to a bounding range loses the distinction
between "renal function" and "hepatic function" (the conjoined
words live in different parts of the surface). N-ary OR groups in
the corpus go up to 25 members; the cardinality matters semantically
(a 25-way OR is a clinically broad permission, not an arbitrary
nesting of binary ORs). So `ChiaEntity.spans` is a list, and
`ChiaEquivalenceGroup.member_ids` is a list — both faithful to the
BRAT structure. Cost: callers that just want a single (start, end)
get a `.start` / `.end` convenience pair on the entity.

### D-19. Eval seed splits "mechanical" from "human-review" verdicts
**Rejected:** producing a single flat list of (patient, criterion,
verdict) triples without distinguishing how each label was derived.
**Why:** the structured fields a trial gives us (minimum_age,
maximum_age, sex, healthy_volunteers) are deterministic to verdict
against the typed patient model — those labels are defensibly
correct on day one. Free-text criteria (clinical-judgement
language, prior-therapy exclusions, hard thresholds in narrative
text) need a human reviewer; pretending we labeled them honestly
would seed-train the matcher to match my mistakes. The schema
encodes the split as a `method` field on every `CriterionVerdict`
(`"mechanical"` vs `"human_review"`), plus a per-pair
`free_text_criteria_count` and `free_text_review_status`. Eval
consumers wanting strict ground truth filter to `human_review`;
consumers measuring structured-field handling include both. The
deployment writeup will state the split explicitly:
"49 pairs, 82 mechanical structured-field verdicts (66 pass / 16
fail / 0 indeterminate), 856 free-text criteria pending CRC review
before the matcher can be evaluated end-to-end."

### D-20. Slice-aware patient ranking for pair selection
**Rejected:** uniformly sampling (patient, trial) pairs at random.
**Why:** uniform sampling produces mostly low-information pairs —
e.g., a patient with no diabetes paired with a T2DM trial yields
"`fail` because no Type 2 diabetes" for nearly every criterion,
which doesn't exercise the matcher's harder paths. Instead we rank
the cohort per slice by `(slice-topical, has-required-lab,
cohort-score, age)` so each slice gets pairs likely to *test*
something: a T2DM trial paired with a high-score diabetic patient
who has HbA1c on file actually exercises threshold matching, lab
freshness, and condition-evidence reasoning. The NSCLC slice is an
intentional exception — the cardiometabolic cohort has no NSCLC
patients, so all pairs there test the matcher's "fail gracefully on
out-of-domain trials" path.

### D-22. Patient Profiler is a wrapper, not a materialized snapshot
**Rejected:** materializing each query result into a frozen
`PatientProfileSnapshot` Pydantic model.
**Why:** the underlying `Patient` is already immutable Pydantic and
the lookups are cheap (one filter scan, occasionally a max). A
materialized snapshot would add a copy step at construction, raise
the question of "which view is canonical when the patient updates",
and serialize the answers we don't need. The wrapper is a thin
view: `PatientProfile(patient, as_of)` with the as-of date baked in,
so all queries share consistent semantics without re-passing the
date everywhere. The matcher, the seed labeler, and any future
component that needs as-of semantics use the same surface.

### D-23. Threshold checks are a 5-state tri-state, not a boolean
**Rejected:** `meets_threshold(...) -> bool` (or `bool | None`).
**Why:** the matcher's verdict is itself tri-state
(pass / fail / indeterminate), and the cause of indeterminacy
matters for downstream eval and human review. The profile returns
`ThresholdResult.{MEETS, DOES_NOT_MEET, NO_DATA, STALE_DATA,
UNIT_MISMATCH}`. The matcher maps the last three to `indeterminate`
*with a reason*, so a reviewer can tell "we don't have this lab"
from "we have an old one" from "we can't compare units" — three
very different actions: order the lab, refresh the data, or
normalize the protocol.

### D-24. Unit handling fails closed when units aren't in the alias table
**Rejected:** silently coercing all unit strings to a single
canonical numeric value via a generic UCUM library.
**Why:** for the few labs we care about at v0 (HbA1c, LDL, eGFR,
BP), the patient-side units are well-known and a tiny per-LOINC
alias table covers them. UCUM-style auto-conversion adds a real
risk of nonsense conversions ("HbA1c 53 mmol/mol" → "53 %"
silently if the conversion isn't actually implemented for that
quantity), and the failure mode is *correctness*, not
*availability*. The profile returns `UNIT_MISMATCH` instead, the
matcher emits `indeterminate (unit_mismatch)`, and a human (or a
later version with an explicit conversion table) can resolve.

2026-05-01 update: keep the rejection of generic, silent UCUM
auto-conversion, but promote a narrow explicit reconciliation
layer into Phase 2 task 2.14. The new shape is hybrid: an
LLM/source pass may identify that trial text intends a conventional
unit for a known measurement, while deterministic whitelisted code
performs any numeric conversion. First targets are the recurring
calibration failures: BP thresholds with implicit mmHg, eGFR unit
variants, LDL-C `mmol/L` against patient `mg/dL`, and percent-like
HbA1c.

### D-25. ConceptSet carries the coding system URI
**Rejected:** ConceptSet as just a `frozenset[str]` of code values.
**Why:** clinical codes are unique only within their coding system.
A SNOMED 73211000 is "Neoplasm of bone of upper limb"; an ICD-10
73211000 doesn't exist; an HCC 73211000 means something else again.
A bare set of code strings invites silent cross-system matches.
ConceptSet pairs `codes` with `system` and the profile primitives
filter by *both* when given a ConceptSet (raw-string callers opt
out of the system check, useful for ad-hoc tests). This costs one
field on the model and saves one entire class of silent-correctness
bugs.

### D-21. Cap each patient at N appearances across the seed manifest
**Rejected:** letting the slice-rank winner dominate every slice
(7 slices × top-1 ranked patient = the same person in 7 of 49 pairs).
**Why:** the highest-scoring cohort patient happens to satisfy every
slice's "topical" filter (they have all four cardiometabolic
conditions and all four labs). Without a cap, the seed set's
49 pairs would be drawn from ~7 distinct patients — useless for
exercising the matcher's behavior across diverse profiles.
`MAX_PAIRS_PER_PATIENT=2` produces 27 distinct patients × 30
distinct trials, giving the matcher real coverage on both axes.

### D-26. Extractor schema is matcher-shaped, not Chia-shaped
**Rejected:** mirror Chia's full annotation graph (entities + binary
relations + n-ary equivalence groups + scopes) into the extractor
output.
**Why:** Chia is a research-grade representation aimed at *humans*
reading annotation files. The matcher just needs "what kind of
criterion is this and which slots does it bind?" — not the full
relational graph. Forcing the LLM to produce the Chia graph would
(a) explode the prompt and output token cost for a benefit only the
eval consumes, and (b) push hard reasoning (resolving relations into
matcher-actionable claims) onto the model rather than into
deterministic post-processing. So the schema is a discriminated
`kind`+payload (age / sex / condition_present / condition_absent /
medication_present / medication_absent / measurement_threshold /
temporal_window / free_text). The Chia entity vocabulary is preserved
as a flat `mentions` list per criterion, audit-only — never read by
the matcher. This keeps the extractor cheap and the matcher's
dispatch table boringly explicit.

### D-27. `free_text` as a first-class extractor output
**Rejected:** silently dropping criteria the LLM can't structure.
**Why:** "I don't know how to structure this" is itself a
load-bearing signal — both for the eval (what fraction of real
eligibility text resists structured extraction?) and for the
operator UI (these are the rows a human reviewer must adjudicate).
Carrying a `free_text` row through the same envelope means the
matcher emits a `human_review_pending` verdict for it instead of the
trial appearing more checkable than it is. This pairs cleanly with
the eval seed set's existing mechanical / human-review-pending
split (D-19) and the same accounting flows end-to-end.

### D-28. OpenAI Structured Outputs over JSON Mode
**Rejected:** prompt-instructed JSON output with client-side schema
validation and retry-on-malformed.
**Why:** strict structured outputs (`response_format=PydanticModel`,
`strict: true`) give server-side schema enforcement, including
required-field, enum, and union discipline. The matcher then sees
either a well-formed payload or a typed `refusal`, never malformed
JSON. The cost: schema authors lose a few JSON-Schema features
(`additionalProperties`, defaults, optional-without-explicit-null,
open dicts) — all features that would have made the matcher's life
*harder* anyway by widening the input contract. Net win.

### D-29. Single model snapshot pinned in v0; router/sweep is Phase 3
**Rejected:** building the model abstraction layer alongside the
extractor.
**Why:** the project plan explicitly partitions "make it work" (Phase
1) from "make it cheap and routed" (Phase 3). Starting v0 with the
abstraction layer means we can't measure baseline quality of the
single-model path against the routed path — the eval would have
nothing to compare against. So v0 is `gpt-4o-mini-2024-07-18` only,
no fallbacks, no retries, structured outputs strict mode. The price
table for cost estimation is hard-coded with two models (mini + 4o)
because two is enough to write the bookkeeping correctly without
overcommitting to a Phase-3 design.

### D-30. Prompt versioning via constant, persisted with every run
**Rejected:** treating the prompt as part of the code revision and
relying on git-blame for attribution.
**Why:** the prompt and the schema are the load-bearing artifacts
for extraction quality, but they evolve faster than the code around
them. A `PROMPT_VERSION = "extractor-v0.1"` constant gets persisted
inside every `ExtractorRunMeta`, so when an eval shows a regression
or improvement the analyst can attribute it to a specific prompt
revision in seconds — no git archaeology required. Bumping the
version is a deliberate act when the prompt's behaviour is meant to
change, not a side-effect of a typo fix.

### D-31. Settings via `pydantic-settings` + `SecretStr`
**Rejected:** ad-hoc `os.getenv` calls at the call-sites.
**Why:** centralising in `clinical_demo.settings` gives a typed,
documented config surface; `SecretStr` prevents accidental key
leakage into logs/exception messages; `lru_cache` on the accessor
makes the env-parse cost a one-time event; tests can construct an
explicit `Settings` instance to exercise edge cases without touching
the process env.

### D-32. Two parallel verdict types: `CriterionVerdict` (eval seed) and `MatchVerdict` (matcher)
**Rejected:** widening the existing `evals.seed.CriterionVerdict` to
also carry matcher output.
**Why:** they answer different questions over different inputs.
`CriterionVerdict` wraps a `StructuredCriterion` (CT.gov-derived)
with a hand-applied label and a `method ∈ {mechanical, human_review}`
field — its job is *ground truth*. `MatchVerdict` wraps an
`ExtractedCriterion` (LLM-derived) with a typed `Evidence` list and
`matcher_version` — its job is *system output*. Both share the
`Verdict = Literal["pass", "fail", "indeterminate"]` enum so the
eval harness can compare them; everything else diverges. Conflating
them would force one schema to carry foreign fields it has no use
for and would couple the two release cadences (every matcher rev
would touch the eval-seed migration). Cost of keeping them separate:
one alignment function in the eval harness later. Cost of merging
them: a model with two purposes serving neither well.

### D-33. Closed `VerdictReason` enum, not free-text rationale only
**Rejected:** a single `rationale: str` field carrying everything.
**Why:** free-text rationales are great for the reviewer UI tooltip,
but they're a nightmare for regression analysis. With a closed
`VerdictReason` enum (`ok`, `no_data`, `stale_data`, `unit_mismatch`,
`unmapped_concept`, `unsupported_kind`, `unsupported_mood`,
`human_review_required`, `ambiguous_criterion`) an analyst can pivot
"matcher's `unmapped_concept` rate jumped 30% between revisions" in
SQL, no NLP. The free-text `rationale` stays for human consumption.
Adding a new reason is a deliberate act — exactly the property we
want when trying to keep matcher behaviour auditable.

### D-34. Surface-form → ConceptSet lookup is hand-curated and small
**Rejected:** UMLS/RxNorm normalisation, embedding-based concept
resolution, or LLM mapping.
**Why:** the matcher's value comes from *predictability*. A reviewer
should be able to read `concept_lookup.py` in 30 seconds and see
exactly which surface forms the matcher recognises. Any unmapped
surface form lands as `indeterminate (unmapped_concept)`, which is
the *honest* signal — it tells the eval harness exactly where the
matcher's vocabulary needs to grow. Phase 2+ will extend this; v0
intentionally trades recall for traceability. The medication table
is empty in v0 because we haven't done the RxNorm work and would
rather under-promise than fuzzy-match `"metformin"` against an
arbitrary RxNorm code.

### D-35. Polarity / negation as XOR flip applied after dispatch
**Rejected:** baking polarity into each per-kind handler.
**Why:** the polarity and negation rules are uniform across all
criterion kinds, so the per-kind handlers compute the *raw* answer
to the criterion's predicate ("does the patient have T2DM?") and
the dispatcher applies a single XOR flip. Eight cases collapse to
one truth table that gets unit-tested exhaustively. `indeterminate`
verdicts are invariant under both flips — no amount of polarity can
turn "we don't know" into a decision.

### D-36. Typed `Evidence` discriminated union, with `MissingEvidence`
**Rejected:** an opaque `dict[str, Any]` evidence blob, or
omitting evidence entirely on `fail` verdicts.
**Why:** every verdict — including `fail` and `indeterminate` — must
cite the records the matcher actually consulted. A `MissingEvidence`
row that says "no HbA1c lab on or before 2025-01-01" makes a
`no_data` indeterminate verdict legible in a way that an empty
evidence list never could. Typed `Evidence` (`LabEvidence`,
`ConditionEvidence`, `MedicationEvidence`, `DemographicsEvidence`,
`TrialFieldEvidence`, `MissingEvidence`) lets the reviewer UI render
each row appropriately and lets the eval harness count by evidence
kind without parsing strings.

### D-37. Hypothetical mood and `within_future` short-circuit to indeterminate
**Rejected:** treating planned events as if they had occurred, or
inferring them from "intent to" language.
**Why:** v0 has no patient-side data on planned events (Synthea
doesn't generate planned-event records, and we have no source that
does). Quietly returning `fail` on "planned bariatric surgery"
would be wrong; quietly returning `pass` would be worse. The
`unsupported_mood` indeterminate is the matcher saying "the data
exists somewhere — just not on this profile" and the eval harness
will show whether this affects enough criteria to be worth a Phase 2
fix.

### D-38. Conservative top-level rollup: any-fail → fail, else any-indeterminate → indeterminate
**Rejected:** majority-vote, weighted scoring, "soft" rollups that
ignore unmapped concepts.
**Why:** at v0 the rollup is the single signal a non-clinician
consumer of the system reads first. Clinical screening reality is
also conservative: one missed exclusion is disqualifying. The rule
("any `fail` wins; else any `indeterminate` wins; else `pass`") is
trivially auditable, matches what the reviewer would do manually,
and is exactly the surface a Phase-2 critic loop will refine —
e.g. "override an `unmapped_concept` indeterminate when a textual
match is present" or "weight inclusion failures against exclusion
failures." Empty verdict lists collapse to `pass` (vacuously true);
callers must check `summary.total_criteria == 0` themselves before
trusting that as positive evidence — documented and tested.

### D-39. ScorePairResult is a single envelope, not a tuple
**Rejected:** returning `(verdicts, summary, eligibility, meta)`
tuples or expecting callers to bundle their own.
**Why:** every consumer wants the verdicts plus the run metadata —
the CLI needs cost to print, the eval harness needs prompt+matcher
versions to attribute regressions, the reviewer UI needs the
patient/trial/as_of triple to render headers. Bundling them in one
Pydantic model means each consumer picks what it needs without an
ad-hoc tuple-unpacking contract that would have to change every
time the envelope grew a new field. Persisting `ScorePairResult`
to disk for evals is a free side-benefit.

### D-40. On-disk extractor cache + `--no-llm` replay mode
**Rejected:** re-extracting on every CLI invocation, or building
an LRU memory cache that doesn't survive process restarts.
**Why:** the extractor is the only LLM-cost surface in the pipeline
and the demo loop is iterative — the developer/operator wants to
re-render verdicts after touching the matcher, the lookup tables,
or the rollup rules without paying tokens each time. The cache
file is a `StoredExtraction` JSON keyed by NCT id, written by
`extract_criteria.py` and read by `score_pair.py`. `--no-llm`
makes the contract explicit: refuse to make a network call; fail
loudly on cache miss. This also makes CI-grade end-to-end tests
possible without an API key.

### D-41. Observability shim that no-ops when unconfigured
**Rejected:** importing `langfuse.openai` as a drop-in replacement
for the OpenAI client (the SDK's own quickstart pattern), and
crashing if Langfuse keys aren't set.
**Why:** two reasons. (1) The OpenAI drop-in routes *every* call
through Langfuse's wrapper, including the ones in unit tests that
inject a stub client via the `_ClientLike` Protocol — a bad seam
to fight every time we want to add a parallel evaluator or a
non-OpenAI provider. Wrapping at *our* extractor boundary keeps
observability decoupled from the LLM SDK and matches the seam
where we already control prompt-version, cost, and refusal
handling. (2) A fresh checkout, CI run, or local dev session
without Langfuse credentials must work. The shim returns a
`_NoopSpan` sentinel whose `.update()` / `.end()` accept any
kwargs and discard them, so the call sites have one shape:
`with traced(...) as span:`. No `if span is None` everywhere.

### D-42. Defensive on every Langfuse call (observability never breaks the app)
**Rejected:** letting SDK exceptions escape to the application.
**Why:** an analytics provider going down (or a new SDK version
changing a method signature) cannot be allowed to break an
eligibility verdict path. Every call through the shim is
try/except'd, with failures logged at WARNING and execution
continuing with a no-op span. We tolerate a lost trace; we do not
tolerate a lost or wrong verdict because the tracer panicked.
Symmetric to: pre-commit gitleaks blocks credential leaks, the
`SecretStr` fields in Settings prevent log spillage, and the
shim's "fail open" stance prevents observability failures from
becoming application failures.

### D-43. One generation per LLM call, one parent span per scoring pair
**Rejected:** a single trace per CLI invocation, or a span per
matcher kind, or a flat list of generations with no parent.
**Why:** the unit of decision in this system is the (patient,
trial) pair, so that's the parent observation. The extractor's
`generation` (which is what carries cost / tokens / model in the
Langfuse UI) nests under that parent automatically because we use
`start_as_current_observation`. Pivoting on `eligibility`,
`patient_id`, `nct_id`, or verdict counts in the dashboard becomes
a one-row query rather than a join across spans. The matcher does
*not* emit per-criterion observations: it's deterministic, has no
cost, and emitting one span per criterion would balloon the
ingest volume without adding signal — the per-criterion verdicts
are already on the parent's `output`. If/when matcher v0.2 grows
expensive components (a vector lookup, an LLM-backed concept
mapper), they earn their own generation.

### D-44. Tag with metadata, not user/session
**Rejected:** mapping `patient_id` → Langfuse `user_id` and the
CLI invocation → `session_id`.
**Why:** Langfuse's user/session model is built around a human
end-user with a chat history; in our system the "user" is the
clinician operating the reviewer UI, not the patient being
screened, and the "session" semantics don't fit batch eligibility
runs at all. Putting patient/trial ids into `metadata` instead
preserves the full pivot capability without abusing the schema.
This leaves `user_id` and `session_id` available later for the
reviewer UI to populate correctly.

### D-45. State as `TypedDict` + `operator.add` reducer, not Pydantic
**Rejected:** `ScoringState` as a Pydantic `BaseModel` with custom
field validators.
**Why:** LangGraph reducers fire on every concurrent state update,
and Pydantic re-validates the model on each call. That's wrong on
two axes — it's slow on the hot path, and it's incorrect because
intermediate states *must* violate the "all criteria scored"
invariant by design (verdicts accumulate one branch at a time during
fan-in). `TypedDict + Annotated[list, operator.add]` is what every
LangGraph example uses for a reason. Domain models that *are*
Pydantic (Patient, Trial, MatchVerdict, ExtractionResult) sit
*inside* the dict — Pydantic's invariants apply to them
individually; the dict is just the carrier.

### D-46. Carry `(criterion_index, MatchVerdict)` in the reducer, not bare verdicts
**Rejected:** reducer slot of `list[MatchVerdict]`, sort verdicts
later by some derived key (criterion_id, source_text hash).
**Why:** `ExtractedCriterion` has no stable id field today, and
adding one would touch the extractor schema and every existing
matcher fixture. Parallel fan-in does not preserve arrival order,
so for deterministic verdict ordering (which we want for eval,
replay, human review) we need an explicit index. Carrying it as
the first element of a 2-tuple keeps the reducer cheap (concat) and
the ordering restoration trivial (sort on key 0). The rollup node
strips the indices when constructing the public `MatchVerdict`
list.

### D-47. Per-criterion routing inside `fan_out_criteria`, not a separate router node
**Rejected:** `extract → router_node → fan_out_to_matchers`.
**Why:** A bookkeeping node that does nothing visible adds depth to
the trace tree, an extra hop in the runtime, and zero correctness
value over inlining the routing decision in the conditional edge
function. The decision is per-criterion; making it inside the same
function that emits the `Send` objects keeps it co-located with the
fan-out (so future routing rules — say, the v0.2 deterministic →
LLM fallback — land in one place). The empty-criteria edge case is
handled by returning the rollup node name directly (a `str`
return), not an empty `Send` list, which would leave the graph
stuck after `extract`.

### D-48. LLM matcher is a separate prompt + node, not the extractor reused
**Rejected:** repurposing the extractor's prompt to also emit a
verdict on free-text criteria.
**Why:** The extractor's job is *structuring*; the matcher's job is
*deciding*. They have different system prompts, different output
schemas, and different cost / quality trade-offs (matchers run N
times per trial, extractors once). Conflating them would make the
prompt longer (worse cache hit rate), the schema looser (worse
validation), and the eval harder (you can't pivot extraction
quality independently from matching quality). Costs the same in
tokens to keep them separate and pays back in clarity.

The LLM matcher's patient snapshot is a *typed bundle* (age, sex,
active conditions, current medications) — never narrative text. Two
reasons: (a) it keeps the prompt-injection surface narrow before
Phase 3.4 builds the red-team set, and (b) for the kind of
free-text criteria v0 sees (mobility, allergies, informed consent,
geography), the typed snapshot is usually sufficient or
`indeterminate` is the honest answer.

### D-49. Side-by-side `score_pair()` and `score_pair_graph()` for one cycle
**Rejected:** rename + replace the imperative `score_pair()` with
the graph version in one commit.
**Why:** Side-by-side gives a cheap A/B regression test for free —
the eval harness in 2.3 can run both orchestrators on the same
inputs and surface any divergence, which is also the cleanest way
to validate the LLM matcher's behaviour against the deterministic
baseline. The cost is one extra script file (`score_pair_graph.py`)
and ~50 lines of mostly-shared CLI plumbing. Once eval confirms
parity (or surfaces the intended differences), the imperative path
will delegate to the graph and the duplicate disappears.

### D-50. Critic identifies process problems; the matcher decides eligibility
**Rejected:** an LLM critic that takes the verdicts and emits a
revised verdict directly ("the patient is actually a pass on
criterion 3").
**Why:** if the critic can change the answer in one shot, the
audit trail collapses into "the model changed its mind." Instead
the critic emits closed-enum **process findings** —
`polarity_smell`, `extraction_disagreement_with_text`,
`low_confidence_indeterminate` — each tied to one criterion index,
each with a one-sentence rationale and an `info|warning|blocker`
severity. The revise node then dispatches the finding to a
closed-enum **action** (re-run the LLM matcher with focus, flip
polarity and re-match, re-extract that one criterion) and the
*existing* matcher path produces the new verdict. So every
verdict in the trace was produced by a matcher; every revision
has a recorded reason, action, and `verdict_changed` flag. This
is the discipline the deployment-readiness writeup needs and the
shape an eval pivot ("critic interventions that actually changed
an answer") relies on.

### D-51. `merge_indexed_verdicts` replace-by-index reducer
**Rejected:** keeping `operator.add` on `indexed_verdicts` and
filtering duplicates at read time.
**Why:** `operator.add` was the right choice for the initial
parallel fan-out (D-46), but the critic loop *replaces* the
verdict at index N rather than appending another one. Filtering
at read time would mean every consumer of the rollup has to know
about revision history, and the LangGraph reducer contract
becomes a lie: state would no longer be the source of truth, the
read function would be. Custom reducer keeps the invariant —
exactly one verdict per criterion index in state — and pushes
revision history into the dedicated `critic_revisions` audit log
(append-only via `operator.add`), where it belongs.

### D-52. Layered termination: budget + no-progress + recursion backstop
**Rejected:** a single `max_critic_iterations` cap.
**Why:** any one of those signals is the wrong one to trust
alone. A pure budget keeps spending tokens on revisions that
aren't moving anything. Pure no-progress detection is fragile
when the LLM emits the same finding with different rationale
text. Pure `recursion_limit` only fires after the loop has
already gone wrong. So the loop terminates on the *earliest* of:
(a) the critic returns no actionable warnings; (b)
`max_critic_iterations` is hit (default 2 — one critique + one
revision + one re-critique that confirms convergence); (c)
fingerprint-based no-progress check (the set of
`(criterion_index, finding_kind)` pairs is unchanged from the
previous iteration). LangGraph's `recursion_limit` stays
configured as a runtime backstop in case any of those checks have
a bug. Two iterations is what the manifest will end up actually
spending in 95% of pairs; the budget is there for the long tail.

### D-53. Critic is a separate prompt and a separate node, not the matcher reused
**Rejected:** asking the same LLM matcher to also produce a
"would I revise this?" annotation as a side output.
**Why:** the critic's job (review verdicts, emit findings, never
decide eligibility) and the matcher's job (decide one verdict,
return a `MatchVerdict`) have different inputs (matcher: one
criterion + restricted snapshot; critic: all verdicts + the
trial's eligibility text), different outputs, different
prompts, and crucially different versioning concerns: the
matcher prompt is regression-tested against the eval seed, the
critic prompt is regression-tested against the *manifest of
critic-driven revisions*. Collapsing them into one prompt would
mean a prompt change for one job invalidates eval baselines for
the other. Cost is one extra LLM call per pair when the critic
is enabled, which is why it stays opt-in (`critic_enabled=False`
by default in v0).

### D-54. Revise re-uses the LLM matcher node, doesn't introduce a "re-matcher"
**Rejected:** a dedicated revision-time matcher with its own
prompt that takes "previous verdict + critic finding" as
context.
**Why:** another prompt to version, another set of eval baselines
to maintain, and a second code path through which a verdict can
be produced. The revise node instead constructs a
`{criterion, patient}` input identical to the matcher's normal
input and calls the existing `llm_match_node` (or the
deterministic matcher, for non-`free_text` criteria). The
"focus" from the critic finding is recorded in the revise span's
input and in the `CriticRevision.rationale`, but the matcher
prompt is unchanged. Same prompt version, same eval baselines.
For deterministic criteria the revise node is a no-op
(deterministic matchers are already stable); the no-op is still
recorded as a `CriticRevision` with `verdict_changed=False` so
the audit trail stays complete.

### D-55. Human checkpoint as an opt-in `interrupt_before` on `finalize`
**Rejected:** (a) a separate "human review" graph; (b) always
interrupting and requiring an explicit "approve" call.
**Why:** the v0 demo doesn't have a human reviewer in the loop,
so the default path must run end-to-end without one. But the
deployment-readiness writeup needs a real seam where a human can
review and override before the verdict is "final." LangGraph's
`interrupt_before` on a designated node is the clean way: the
`finalize` node is a deliberately-empty pass-through whose only
purpose is to be that seam. When `human_checkpoint=True` the
graph compiles with an `InMemorySaver` checkpointer and pauses
before `finalize`; the caller resumes via the same
`score_pair_graph(thread_id=...)` entry. When the flag is off,
`finalize` runs inline and emits its span like any other node.
One node, two modes, no graph fork.

### D-56. `pickle_fallback=True` on the InMemorySaver
**Rejected:** making `PatientProfile` Pydantic so it serialises
via msgpack like the other state.
**Why:** `PatientProfile` is a thin wrapper around the parsed
FHIR bundle and isn't meant to be a wire type — its purpose is
in-process access. Forcing it to be Pydantic would either bloat
the profile with thousands of fields or hide most of the bundle
behind opaque dicts. The HITL checkpointer is in-process by
construction (it's an `InMemorySaver`, not durable storage), so
`pickle_fallback=True` on the serializer is the right pragmatic
choice: the typed state still goes through msgpack via the
Pydantic types, the profile pickles. When/if Phase 4 adds a
durable checkpoint store, the profile will be re-hydrated from
the bundle on resume rather than serialised at all, and this
fallback can be removed.

### D-57. Critic span tagging surfaces revisions in the trace
**Rejected:** tagging only the parent `score_pair_graph` span
with critic stats.
**Why:** the parent-only view is enough for cohort-level metrics
("X% of pairs had critic revisions") but not enough to debug a
single pair: the trace would show that a verdict changed without
showing *why* the critic flagged it or *what* the revise node
did. So critic spans carry `critic_iteration` and the count of
findings; revise spans carry `criterion_index`, `action`,
`finding_kind`, `verdict_changed`. The parent still gets
`critic_iterations`, `revisions_total`, `revisions_changed_verdict`
for the cohort view. Cost is metadata only — no new generations,
no new spans beyond the ones already added for the loop — but
the debug experience is the difference between "verdict
changed mid-pair, who knows why" and "verdict flipped because
the critic flagged a polarity smell on criterion 3 and the
revise node ran `flip_polarity_and_rematch`."

### D-58. Critic audit data lives in the trace, not on `ScorePairResult`
**Rejected:** extending `ScoringSummary` (or `ScorePairResult`)
with `critic_revisions: list[CriticRevision]` and
`critic_iterations: int`.
**Why:** the imperative `score_pair()` and the graph
`score_pair_graph(critic_enabled=False)` have to keep returning
the same envelope so the eval harness in 2.3 can A/B them
without branching on which orchestrator produced the result
(D-49). Adding critic fields to the envelope either breaks that
parity or saddles the imperative path with optional fields it
will never populate. The audit data is fully captured in the
Langfuse trace (D-57), and the in-process caller can still read
it off the graph's `final_state` if it needs to. Phase 2.3 may
introduce a richer `ScoreRunResult` envelope once the eval
harness lands; deferred until there's a concrete consumer.

### D-59. Eval harness scorer is a `Callable`, not a registered orchestrator
**Picked:** `run_eval(scorer, cases)` where
`scorer: Callable[[EvalCase], ScorePairResult]`.
**Rejected:** an `Orchestrator` enum + dispatch table inside the
harness; or a base class the imperative and graph paths both
subclass.
**Why:** the harness's job is to score N cases and persist the
result. Knowing *how* the scorer works (which model, which
prompt, critic on/off, which extraction policy) is the caller's
responsibility, and a `Callable` is the smallest contract that
respects that. A registry would force every new orchestrator
variant to land code in `evals/` even when the variant is
genuinely orthogonal — a critic-enabled vs critic-disabled run
is not a new orchestrator, it's a different `partial`. The
script (`scripts/eval.py`) carries the bridging logic; the
library doesn't.

### D-60. Two-table schema with a `result_json` blob, not a normalized verdicts table
**Picked:** `runs` + `cases` tables; the full `ScorePairResult`
serializes into `cases.result_json`. Per-case summary columns
(eligibility, verdict counts, extraction cost, latency) are
flattened onto `cases` so an operator can `SELECT eligibility,
COUNT(*)` without `json_extract` gymnastics.
**Rejected:** a third `verdicts` table with one row per
criterion verdict from day one.
**Why:** v0 doesn't have a query that needs per-verdict joins —
layer-1 (deterministic vs Synthea) walks the structured-criterion
verdicts in a single dict comparison; layer-2 (Chia) is a
separate dataset entirely; layer-3 (LLM judge) is the same
shape. JSON blob storage costs ~one Pydantic round-trip on read
and gains zero meaningful lookup speed at the dataset sizes we
care about (49 pairs today, ~500 once we burn down the
human-review backlog). When a real query motivates a
`verdicts` table, the migration is `INSERT INTO verdicts
SELECT … FROM cases CROSS JOIN json_each(result_json, '$.verdicts')` —
fully recoverable from the blob.

### D-61. Runs are append-only; same `run_id` is a hard error
**Picked:** `save_run` raises `IntegrityError` on duplicate
`run_id`. Re-scoring a dataset gets a new id.
**Rejected:** "upsert" semantics that overwrite a previous run
in place.
**Why:** the eval store is the audit trail for "what did the
system look like on date X." Silently overwriting a run
destroys baselines and makes regressions invisible; explicit
re-runs with new ids preserve the lineage. Storage cost is
trivial.

### D-62. Per-case scorer failures recorded on the row, not allowed to abort the run
**Picked:** `run_eval` wraps each `scorer(case)` in a
`try/except`; on failure, persist `error TEXT` and NULL out the
per-case summary cols. `n_errors` is a top-level field on
`RunResult`.
**Rejected:** propagating the first exception and aborting; or
silently skipping the case with no record.
**Why:** in a 50-pair run, a single 429 or transient extraction
failure shouldn't lose 49 successes. Recording the error keeps
the failure visible for layer-1 to reason about, but doesn't
gate progress. v0 doesn't surface a failure-rate metric in the
reporter (the count is one digit at the bottom of the summary);
that earns its place once we have a real production baseline.

### D-63. No layer-specific eval logic in 2.3
**Picked:** `evals/run.py` and `evals/store.py` are pure
plumbing. They don't know what "deterministic accuracy" or
"LLM judge calibration" mean.
**Rejected:** baking layer-1 metrics (e.g. structured-verdict
agreement rate) into the runner or the reporter so 2.3 ships
with "real" numbers.
**Why:** layer-specific logic belongs in tasks 2.4-2.6, where
each layer can pick its own metric, output format, and
red-team set without retrofitting the harness. A reporter
abstraction was considered and cut: `eval report` is a one-screen
pretty-printer of `RunResult` summary counts, and that's all v0
needs. Layer reporters can read `runs.sqlite` directly when they
land — the schema is stable and queryable.

### D-64. Reviewer UI lives in `web/` as a dev rig; production reviewer ports into `juliusm.com`
**Picked:** scaffold the SvelteKit reviewer SPA inside this
repo under `web/`, but treat it as **scaffolding for the API**,
not as the production artifact. No JS test runner, no deploy
adapter beyond `adapter-static`, no CI integration on the JS
side; `web/.gitignore` keeps `node_modules` and the build
output local. Same Svelte version family the personal site
uses (Svelte 5 / SvelteKit 2) so when this is ported into
`juliusm.com` the components and types lift over with edits
to routing and styling, not rewrites.
**Rejected (a):** building the UI directly inside the
`juliusm.com` Astro repo. That couples a per-trial demo to
the personal site's deploy cycle and Astro's conventions
before the demo's API and verdict shape have stabilized; any
churn here would force a docs/site rebuild. Keep them
decoupled until the API and the model are settled.
**Rejected (b):** Streamlit fallback (the original D-5 escape
hatch). The criterion-row UI is the part of the demo most
worth showing — colored verdict pills, click-to-expand
evidence, side-by-side imperative vs. graph + critic toggles.
Streamlit's rendering primitives don't carry that as well,
and the Svelte path was already bounded enough to ship.
**Rejected (c):** a TypeScript codegen client (e.g.
`openapi-typescript`) over the FastAPI's OpenAPI schema. The
API surface is four endpoints and ~30 lines of types; a
hand-written `lib/api.ts` is faster to ship, easier to read
in review, and avoids a build-time dependency on the FastAPI
being importable. When the surface grows past ~10 routes,
revisit.
**Why:** the user explicitly framed this UI as "have one in
this repo for testing before we move it into the site." Two
implications fall out: (i) keep the surface tight enough that
the port is mechanical, and (ii) don't pay for production
concerns (CI matrix, e2e tests, deploy adapters) that the
production owner — `juliusm.com` — will own. The dev rig's
job is to exercise the FastAPI through a real UI so that any
contract drift between `ScorePairResult` and the renderer
shows up here, not in the personal site's deploy.

### D-65. Promote LLM token caps into Settings; convert extractor length-truncation from a 500 to a graceful empty extraction
**Picked:** three changes, taken together, in response to the
first end-to-end demo run hitting `LengthFinishReasonError`
on the largest curated trial (NCT05268237; 6.3k input tokens,
4096 output overflow):

1. Promote `extractor_max_output_tokens` (4096), the
   previously hard-coded `llm_match` cap (512), and the
   `critic` cap (1024) into `Settings`; bump the extractor
   to 16384 (the model's hard ceiling for `gpt-4o-mini`),
   the matcher to 1024, the critic to 2048. Cost is
   unaffected by raising caps because providers only bill
   for tokens *emitted*; the cap is a budget, not a quota.
2. Wire `nodes/llm_match.py` and `nodes/critic.py` to read
   from `Settings` instead of inline literals. Magic numbers
   in source were a config-drift bug waiting to happen
   (e.g. critic prompt asks for ~30 findings → 1024 tokens
   easily overflowed once revisions stacked).
3. In `extract_criteria`, catch `openai.LengthFinishReasonError`
   specifically (before the catch-all `except`) and return an
   `ExtractionResult` with `criteria=[]`, a
   `metadata.notes` flag describing the truncation, and full
   cost/token preservation on `ExtractorRunMeta` (we paid
   for those tokens; eval rollups must not undercount). The
   Langfuse span is tagged `WARNING`, not `ERROR`, so
   dashboards can split graceful degradation from genuine
   failures. Downstream rollup collapses an empty criteria
   list to a vacuous `pass` — acceptable v0 behavior.

**Rejected (a):** "just bump the extractor cap, leave matcher
and critic alone." Lazy: the same overflow mode exists for
both other call sites and would have surfaced the moment a
big trial actually triggered the critic loop on the demo. Fix
all three call sites once.

**Rejected (b):** raise `LengthFinishReasonError` as a typed
`ExtractorTruncatedError` and let the orchestrator decide. v0
has one orchestrator pair (imperative + graph) and the right
behavior in both is "log + skip + keep going." Adding a typed
exception would force every caller (CLI, eval harness, API,
both orchestrators) to handle it identically — that's the
extractor's job.

**Rejected (c):** retry with a doubled cap. `gpt-4o-mini`'s
hard ceiling is 16384; once that's the cap, retry has nothing
to give. The right Phase 3 follow-up is splitting extraction
across criterion sections (inclusion / exclusion) so each
sub-call has half the prompt and half the expected output.

**Why:** the failure was real, the user-visible message was
a stack trace, and the production-discipline lesson is that
LLM stacks have *known* failure modes (length truncation,
refusals, tool-call malformation, content filters) that
production code should degrade across, not bubble up to the
user. The fix here is the same shape as the existing
`ExtractorRefusalError` / `ExtractorMissingParsedError`
handling — explicit per-mode treatment, span-tagged so the
operator can tell which mode fired, regression-tested so the
contract is pinned. This is the FDE-relevant story: "robust
to provider failure modes" is exactly what a deployed system
needs and exactly what unit tests can pin without a live API.

### D-66. Per-criterion soft-fail on extractor invariant violations + auto-invalidating cache key
**Picked:** two changes, taken together, in response to the
second end-to-end demo run hitting `ValueError: ExtractedCriterion
claimed a kind requiring \`measurement\` but the \`measurement\`
payload is None.` on NCT05268237 — for *both* orchestrators, off
the same stale cache file written before D-65's prompt/cap fixes
landed.

1. **Matcher soft-fail.** `_required(...)` now raises a typed
   `_ExtractorInvariantViolation` (sentinel exception, scoped to
   the matcher module). `match_criterion` catches it and emits
   `MatchVerdict(verdict="indeterminate",
   reason="extractor_invariant_violation")` with a `MissingEvidence`
   row naming the offending payload slot. The reason joins the
   existing `VerdictReason` enum, so the UI's pill renderer and
   the eval rollup pick it up automatically. One bad criterion no
   longer kills a 30-criterion trial's score; the bad row stays
   visible in the verdict list with full audit trail so a reviewer
   sees exactly which criterion the extractor fumbled.

2. **Cache filename embeds (prompt_version, schema_fingerprint, model).**
   `cache_path_for(...)` now returns
   `<NCT>.<prompt_version>.<schema_fp>.<model>.json`. The schema
   fingerprint is an 8-char SHA-256 of canonical-JSON
   `ExtractedCriteria.model_json_schema()` — so any field
   add/rename/retype on the extractor schema *automatically*
   produces a new filename, making old envelopes invisible to the
   read path. Three independently revvable signals → three filename
   segments. Old envelopes become orphans in the same directory
   (gitignored, harmless).

**Rejected (a):** swallow the `ValueError` silently and skip the
criterion. Loses the audit trail. The whole point of the matcher
is to be *honest* about what it can't decide; "indeterminate +
explicit reason" is the existing language for that.

**Rejected (b):** raise a typed `ExtractorInvariantError` and
make the API surface a 422. Same problem as the D-65 rejected
typed-exception path: forces every caller to handle one exception
type per failure mode. The matcher's job is exactly to smooth
LLM-side noise into typed verdicts; turning a noise event into
an `indeterminate` *is* its job.

**Rejected (c):** manual prompt-version bump only, no schema
fingerprint. Cheaper to write but easy to forget. A new field on
`ExtractedCriterion` is a typed, IDE-supported change that should
"just work"; humans should not be on the hook to remember to bump
a string constant in a sibling module. Auto-invalidation is one
hash and zero ongoing cost; the failure mode of *not* doing it
is exactly what produced the NCT05268237 incident.

**Rejected (d):** wipe `data/curated/extractions/` on schema
change. Destructive, hides which keys were old, and slows
diff-style comparison across schema revisions. Renaming via key
preserves history at zero storage cost.

**Why:** these are the two complementary halves of the same
robustness story. (1) makes a single bad LLM output fail
*soft*, not catastrophic — same shape as D-65's length-truncation
fix but at the matcher layer instead of the extractor layer.
(2) makes sure we never *re-encounter* the same bad output by
reusing it from cache after the bug has been fixed upstream.
Together they close the loop: even if a future schema rev
exposes a new model misbehavior, the old cache won't perpetuate
it, and the matcher won't crash the whole trial on it. FDE
relevance: "auditable degradation paths" + "cache keys you can
trust" are both prerequisites for a system you'd let a clinician
look at unattended.

### D-67. Eval store v1→v2 schema migration: persist labels alongside results
**Picked:** add `expected_structured_json` and
`free_text_review_status` columns to the `cases` table, bump
`_SCHEMA_VERSION` from 1 to 2, and apply the additive
`ALTER TABLE` migration in `open_store` when an existing v1 DB
is encountered. Layer-1 reports now read labels from the row
itself instead of expecting them on the in-memory `EvalCase`,
which the SQLite round-trip had been silently dropping.

**Why this matters:** the bug surfaced as
`build_layer_one_report` returning `cells=[]` for a fresh
baseline run. The seed had labels; the runner pulled them; the
store didn't persist them; `load_run` reconstructed `EvalCase`
with default `expected_structured=[]`; layer-1 had nothing to
align against. Symptomatically a "no SVs in the seed?" red
herring; underneath it's a "the persisted run isn't actually
self-contained" problem.

**Rejected (a):** layer-1 re-reads the seed file. Tightly
couples the report layer to a file path that may have moved
since the run. Worse, runs against a since-updated seed would
silently use the new labels — which destroys the whole point
of a baseline (apples-to-apples comparison across runs even as
the labels evolve). Persisting the labels-at-run-time on the
row is the only honest design.

**Rejected (b):** version-bump-and-wipe (the path the
`store.py` header literally documented as the v0 plan: "delete
the DB or downgrade"). Acceptable for a one-dev project at the
moment of bumping but forces every future schema change to
nuke history. Doing the proper additive migration *now* —
before the store has accumulated any historical baselines —
sets the migration habit cheaply, and the migration step is
~10 lines of `ALTER TABLE`. Per `store.py`'s own header
comment, this is exactly the "and only then" moment.

**Why:** baselines exist precisely to be re-comparable across
time; a baseline file that doesn't carry its own labels can't
honor that promise once the seed evolves. The migration ladder
is also the thing that lets every future column add land
without an explicit "wipe your DB" step in the changelog.
FDE-relevant: a system that persists evaluation rows is doing
production data work, and production data systems get schema
migrations. The cost of doing this once now beats doing it
under pressure later.

### D-68. First baseline regression: snapshot two orchestrators + an indeterminacy diagnostic
**Picked:** for the v0 baseline at `eval/baselines/2026-04-21/`,
snapshot two complete eval runs (imperative and graph + critic)
plus their layer-1 JSON reports, and write *two* prose docs:
`SUMMARY.md` (provenance + numbers + slice rollup) and
`INDETERMINACY.md` (per-criterion `(verdict, reason, kind)`
breakdown plus the top-N unmapped surface forms by category).

**Why both prose docs:** the JSON reports are the regression
artifact, but they don't tell a reader *what to do next*.
SUMMARY.md anchors "here is what is true today, with caveats"
(e.g. the 81% layer-1 agreement is depressed by mechanical-
labeler partial labels, not by matcher quality; the 0-pass
rollup is real and is a cohort/trial alignment story).
INDETERMINACY.md answers the user's actual question — "what's
causing all the indeterminacy" — by walking 841 verdicts and
ranking three concrete next investments by impact-per-hour
(vocabulary expansion > extractor compound-criterion routing >
structured age-field wiring).

**Rejected:** snapshotting only one orchestrator. The
imperative ≡ graph+critic equivalence at layer 1 is a
non-trivial *finding* — proves the critic acts on rollup, not
per-criterion structured dispatch — and gets surfaced only by
having both side-by-side.

**Rejected:** running with `--no-llm=False` (i.e. live LLM
calls during the eval). Adds non-determinism to a baseline
whose whole purpose is reproducibility. The cache-warm path
under `--no-llm` is exactly what a regression run should look
like; the LLM is invoked once during the upstream extraction
pass and never again.

**Why this is the right baseline shape now:** Phase 2's eval
exit criterion is "baseline numbers committed." The numbers in
SUMMARY.md plus the diagnostic in INDETERMINACY.md *are* that
exit; future work can credibly say "moved coverage 55%→X%"
because we wrote down the 55% and what it means. FDE-relevant:
"how much of this system actually works, on what slices, and
where would a fix produce the most movement" is exactly what a
client conversation runs on.

### D-69. Move concept binding toward NLM terminology APIs
**Picked:** start replacing hand-curated surface-form aliases and
`ConceptSet` constants with NLM terminology APIs, but land it in
small, measurable slices. The first slice is a VSAC FHIR `$expand`
client, UMLS API-key plumbing, a live probe script, and offline
tests around a recorded diabetes expansion fixture.

The immediate goal is not to make LangGraph compare multiple
terminology systems. It is simpler: resolve trial-side clinical
terms into auditable SNOMED/LOINC/RxNorm code sets, then let the
existing matcher compare those codes against patient FHIR facts.

Current implementation:

- **VSAC FHIR API client** in `clinical_demo.terminology`. Given a
  value-set OID, it expands the value set into the same
  matcher-shaped `ConceptSet` envelope used by the hand-curated
  constants today. It records the VSAC-reported version so future
  eval runs can pin terminology provenance.
- **Settings plumbing** via `UMLS_API_KEY`. Fresh checkouts still
  run without an NLM account because the matcher remains on the
  alias path until the resolver is wired.
- **Live probe script** at `scripts/probe_vsac.py` for checking a
  real key and refreshing the recorded fixture.
- **Offline tests** around the VSAC parser and error paths.
- **Terminology cache** (slice 2) at
  `clinical_demo.terminology.cache`. File-backed
  `TerminologyCache` keyed by `(oid, system_filter,
  envelope_schema_fp)`; filename pattern
  `vsac.<oid>.<filter_tag>.<schema_fp>.json`. Mirrors the
  D-40/D-66 extractor-cache discipline: an 8-hex SHA over the
  on-disk envelope's JSON schema auto-orphans every prior entry
  on any envelope rev, writes are atomic via temp file +
  `os.replace`, and reads on a corrupt file fail loud (Pydantic
  `ValidationError`) rather than silently re-fetching. Public
  surface includes a `vsac_expansion_or_fetch(oid, fetch=...)`
  convenience that takes a no-arg fetcher closure so the cache
  stays decoupled from `VSACClient` (no fetch ↔ cache import
  cycle as the API surface grows). Settings field
  `terminology_cache_dir: Path = Path("data/cache/terminology")`
  defaults under the already-gitignored `data/cache/` root and
  is overridable via `TERMINOLOGY_CACHE_DIR`. 17 offline tests
  pin the round-trip, key discrimination, fingerprint behavior,
  atomicity, and settings wiring.
- **RxNorm REST client** (slice 3) in
  `clinical_demo.terminology.rxnorm_client`. Thin sync wrapper
  over RxNav `/drugs.json?name=...` returning a matcher-shaped
  `RxNormConcepts` envelope (query + ConceptSet of RxCUIs + the
  set of RxNorm term types that contributed). Default unions
  codes across every populated `conceptGroup` because Synthea
  patient bundles can be coded at any TTY level (IN, SCD, SBD);
  `tty_filter=frozenset({...})` restricts for slice-4 ablations.
  Auth model is the key difference from VSAC: RxNav is
  **public, no API key** (~20 rps per IP), so a fresh checkout
  can probe RxNorm without an NLM account. Same fail-loud
  discipline as VSAC: empty / malformed responses raise
  `RxNormError`. `TerminologyCache` extended with parallel
  `get/put/_or_fetch_rxnorm_concepts` methods plus an independent
  `rxnorm_envelope_fingerprint` (so an RxNorm envelope rev does
  not invalidate VSAC entries and vice versa); filename pattern
  `rxnorm.<query_tag>.<filter_tag>.<schema_fp>.json` with the
  query hashed (case-insensitive, whitespace-stripped) so
  filename-unsafe surface forms like "Glucophage" or
  "metformin/glipizide" round-trip cleanly. Recorded fixture +
  live probe script `scripts/probe_rxnorm.py`. 27 new offline
  tests; the cache tests pin the
  vsac/rxnorm-coexist-in-one-root contract.

Follow-on work:

1. Wire `lookup_condition`, `lookup_lab`, and `lookup_medication`
   through the resolved bindings while preserving the existing
   alias path as a fallback during migration. This is the slice
   that promotes the `binding_strategy` literal beyond `alias`.
   Trial-side bindings registry maps surface form → either a
   VSAC OID (for conditions / labs / sets that have a known
   value set) or an RxNorm name lookup (for medications).
2. Optional UMLS search client for source vocabularies not
   covered by a known VSAC value set. Defer until follow-on 1
   reveals a real surface form that needs it; the matcher
   shouldn't grow API surfaces speculatively.
3. Re-run the eval harness and compare against the D-68
   `unmapped_concept` baseline; report `unmapped_concept` rate,
   agreement/coverage deltas, binding precision on a hand-checked
   sample, latency, and failure modes.

**Rejected (a):** expand the alias dict by hand as the main plan.
It is useful as a fallback and smoke-test baseline, but it is not a
realistic vocabulary strategy once the project has access to UMLS,
VSAC, RxNorm, and source vocabularies.

**Rejected (b):** load the full UMLS distribution into the runtime
path or package it into Lambda. The app only needs a small set of
trial-side bindings at scoring time; API-backed resolution plus a
small cache is a better fit for the current scale.

**Rejected (c):** accept inactive strategy names in configuration.
`Settings.binding_strategy` currently accepts only `alias`; future
terminology-backed modes should be wired, tested, and recorded
before their config values are accepted.

**Rejected (d):** stand up Snowstorm or another self-hosted
terminology server for this slice. VSAC and NLM APIs are enough to
start replacing the hand-built bridge; self-hosting can wait until
we have evidence that API-backed resolution is the bottleneck.

**Why:** the D-68 baseline diagnostic identified `unmapped_concept`
as the single largest failure mode (89% of all indeterminates). The
right next move is to use the terminology systems designed for this
problem, but to keep the matcher auditable: trial text resolves to
versioned code sets, patient data stays coded FHIR facts, and the
verdict comes from code-set intersection plus the existing
date/value/unit logic.

### D-70. Treat Layer-3 calibration as a signal to add bounded LLM evidence passes
**Picked:** keep the deterministic matcher as the first pass, but
add Phase 2 matcher nodes that can look back at the source rows
when deterministic matching is honestly conservative. The first
node is a patient-evidence adjudicator for condition
presence/absence, social-history/substance-use absence criteria,
compound condition text, and recoverable extractor payload
failures. The second is a unit reconciliation layer where an LLM
may infer intended measurement/unit from criterion text, but
whitelisted deterministic code performs numeric conversions.

**Why:** the first human Layer-3 calibration pass labeled 25/25
sampled matcher verdicts as `correct`. That means the rubric and
review UI can recognize justified fail-closed behavior, but it
also shows that "correct" is too weak a success criterion for the
product. If a reviewer repeatedly agrees that
`indeterminate(unit_mismatch)` or `indeterminate(unmapped_concept)`
is honest, the next engineering task is not more annotation. It is
to build a source-grounded path that resolves the cases where a
clinical coordinator would reasonably expect the system to use the
patient chart and trial text.

**Placement:** these are Phase 2 correctness tasks (2.12-2.16),
after terminology expansion (2.10) and before Phase 3's model
cost-quality sweep (3.2) and routing dashboard (3.3). Task 2.12
resets the patient-side FHIR evidence labels around in-scope rows;
2.13 makes assumption modes and LLM-use levels explicit; 2.14 builds
retrieval-only evidence plumbing; 2.15 adds bounded adjudication; and
2.16 adds the unit path. Routing economics only become meaningful once
the graph has the right kinds of matcher nodes to route between and
labels that can tell whether those routes improved usefulness.

### D-71. Re-center matching on retrieved evidence, not concept mapping gates
**Picked:** the core product loop is now stated as: feed trials and
patients into the system, retrieve relevant patient evidence, and decide
whether there is enough support to flag a possible match for CRC review.
Terminology APIs and ConceptSets remain important, but as precision anchors
inside retrieval/adjudication, not as the only door into matching. If a
criterion says "NSCLC" and no reviewed ConceptSet exists, the system should
not simply stop at `unmapped_concept`; it should either retrieve candidate
patient evidence and adjudicate it, or clearly report that the required
evidence is missing/out of scope.

**Rejected:** treating the current 60-row patient-evidence packet as a
mandatory annotation gate when many rows are really scope or terminology
gaps. In particular, oncology/NSCLC rows should not define the next core
work unless oncology-capable patient evidence is deliberately added.

**Why:** the reviewer UI surfaced a bad failure mode in the plan itself:
`Extract criterion -> require deterministic ConceptSet mapping -> fail into
unmapped_concept -> build calibration around the failures`. That is auditable,
but it is not the coordinator workflow. The demo should show that the system
can take real trial criteria and patient records, retrieve/cite relevant
evidence, and classify the case as supported, contradicted, or insufficiently
supported. Closed-world assumptions are useful for synthetic evals, but they
must be explicit matcher modes (`open_world` default; `closed_world_eval` only
where the data contract justifies it), not hidden assumptions.

### D-72. Treat the 2026-05-04 mode rerun as movement, not calibration
**Picked:** keep the 2026-05-04 `none` / `retrieval_only` /
`bounded_adjudication` evals as baseline artifacts, but do not claim
bounded adjudication quality until the patient-evidence labels are filled.

**Why:** the rerun proves the new architecture is functioning: retrieval-only
adds cited source rows without changing deterministic verdicts, and bounded
adjudication can convert some unresolved criterion verdicts into decisive
pass/fail while leaving unsupported rows as `no_data`. The top-level effect is
still conservative: 9/49 cases moved indeterminate -> fail and 0 moved -> pass.
That may be clinically reasonable, but without the 60-row gold labels the
project cannot distinguish "good conservative rejection" from "missed
opportunity to identify a possible match." The same rerun originally also
exposed a second Phase 3 blocker — adjudicator cost telemetry was captured in
Langfuse spans but not persisted into `eval/runs.sqlite` — which has now been
cleared by the `LLMCallCost` plumbing on `ScorePairResult.llm_calls` plus the
v2 -> v3 SQLite migration adding `adjudicator_cost_usd` /
`adjudicator_input_tokens` / `adjudicator_output_tokens` /
`adjudicator_calls`. Routing economics are auditable from local eval
artifacts now; the remaining D-72 blocker is just the gold-label fill.

**Placement:** fill `eval/calibration/patient_evidence_labels.json` before
prompt tuning or routing claims, then run the Phase 3.2 cost-quality sweep
against the now-instrumented adjudicator path. Until then, `retrieval_only`
is the credible
cheap reviewer-evidence baseline and `bounded_adjudication` is a promising,
uncalibrated option.

### D-73. Make terminology resolution open, not registry-gated
**Picked:** the matcher must be able to take any extracted clinical surface and
attempt terminology resolution through a cache-backed resolver. The bindings
registry remains useful, but only as curated overrides, provenance fixtures,
and a way to pin known value sets. It is no longer allowed to be the front
door that decides whether the resolver may call terminology APIs at all.

**Why:** the current `two_pass` bridge works for registered surfaces, but the
2026-05-04 deterministic run still has 551/1077 `unmapped_concept` criteria.
Diagnostics show the registry resolved 24/24 observed registered surfaces, so
the infrastructure is not the main blocker. The blocker is policy: if a
surface such as `hemoglobin`, `platelet count`, `body mass index`, generic
`blood pressure`, `pregnant or breastfeeding`, or `uncontrolled hypertension`
is not in `terminology.bindings`, the matcher falls back to aliases and then
declares it unmapped without giving NLM/RxNorm a chance. That is backwards for
the product goal. The system should map everything that can be mapped, remember
the result, and make the residual failure explicit.

**New resolver contract:**

1. Input is `(kind, surface_text, optional criterion context)`, not "surface
   text that happens to exist in our registry."
2. Normalize/canonicalize the surface first, including abbreviation and
   punctuation cleanup.
3. Check curated overrides and reviewed negative overrides first.
4. Check mapped / ambiguous / miss cache second.
5. On miss, query the appropriate terminology service:
   - RxNorm for medications and medication ingredients/classes where supported,
   - LOINC-oriented search for measurements/labs,
   - SNOMED/UMLS/VSAC search for conditions and findings,
   - value-set expansion only when a curated value-set OID is known and
     appropriate.
6. Rank candidates with deterministic rules. High-confidence single hits may
   feed the matcher. Multiple plausible hits return `ambiguous_criterion` with
   candidates and provenance. No plausible hit caches a true miss.
7. Cache all outcomes, including true misses and ambiguity, so repeated evals
   do not pay API cost or silently change behavior.
8. Composite phrases are not "unmapped" by default. Safely splittable phrases
   should yield atomic concepts; unsafely broad or procedural phrases should be
   classified as `composite_unhandled` / `human_review_required` with the
   reason visible.

**Rejected:** continuing to expand `terminology.bindings` as the primary
coverage strategy. It is still valuable for stable high-trust concepts and
offline tests, but a registry-only front door guarantees that every unseen
surface starts life as `unmapped_concept`, which is exactly the failure mode
the project is supposed to eliminate.

**Guardrail:** closed-world assumptions and LLM adjudication must not paper
over terminology misses. The mapper/resolver gets first shot. Only after a surface is
mapped, ambiguous, true-miss, or explicitly composite should retrieval,
closed-world absence logic, or bounded adjudication decide what the patient
evidence supports.

**Implementation status (2026-05-04):** `UMLSSearchClient` (SNOMED exact
for conditions, LOINC `words` + numeric-test-code filter for labs) and
the existing `RxNormClient` satisfy step 5; composite short-circuit and
`true_miss` caching satisfy steps 6–8. Smoke eval `43c765d1dbcc` moved
`unmapped_concept` from 551 to 445 criteria (−9.2 pp) and added 61 new
`ok` verdicts, 52 new pass verdicts, and 9 new fail verdicts that the
old alias-only path was silent on. Rate footprint is ~149 one-time
warmup requests spread across RxNav (public) and UMLS (authenticated,
~20 req/s soft limit with no published daily cap); everything is
cached on disk by the surface cache upstream, so repeat runs are
cache-only. Snapshot: `eval/baselines/2026-05-04-umls/`.

### D-9. Defer KPMG-specific framing of the writeup until Phase 3
**Rejected:** writing the deployment readiness doc up front.
**Why:** the writeup should be *informed by what was actually built*, not
projected onto it. Premature writing leads to the system being shaped to
match the writeup rather than the other way around.

---

## 13. Open questions (to keep visible during build)

- **Eval seed-set human-review pass (Phase 1 task 1.6).** The
  mechanical labeler produced 82 structured-field verdicts across
  49 pairs, but the seed set has ~856 free-text criteria pending
  human review (in `data/curated/eval_seed.json`, every pair carries
  `free_text_review_status="pending"`). End-to-end matcher evals
  cannot be claimed as ground truth until this pass is complete.
  Plan: budget a real afternoon to walk through every pair, mark
  the obvious ones (clearly satisfied/violated by the patient
  record), flag the clinical-judgement ones as `indeterminate`
  with rationale. Flip `free_text_review_status` to `"complete"`
  pair by pair as you go. Owed labels are surfaced in the manifest
  summary so progress is visible.
- Will the Chia entity schema be sufficient as the criterion structured
  representation, or will it need extension for our domains? (Decided in
  Phase 1 task 1.5: the Chia vocabulary is **rich enough** for the
  extractor's structural targets — Condition, Drug, Measurement, Value,
  Temporal, Qualifier, Negation cover the criteria types in our chosen
  trial slices. We will *not* try to extend the schema; instead the
  matcher will normalize Chia surface text against the patient model
  separately. Open variant: whether to surface `Non-representable` /
  `Not_a_criteria` as a "skip" verdict in the matcher — defer to
  task 1.9.)
- How many critique-loop iterations are useful before diminishing
  returns? (Default of 2 picked in Phase 2 task 2.2 — one
  critique + one revision + one re-critique to confirm
  convergence — paired with no-progress fingerprint detection so
  the loop also terminates earlier when findings are stable.
  Re-validate against the real revision manifest in Phase 2 task
  2.7 after the first baseline regression run; if 95%+ of
  revisions land in iteration 1, drop the default to 1.)
- For the LLM-as-judge calibration, is there enough human-judge agreement on
  the borderline cases for the metric to mean anything? (Initial Phase 2.6
  pass: 25/25 human labels marked `correct`, so the rubric is usable for
  checking matcher honesty. Remaining question: whether judge scores should
  be weighted by usefulness / mapped-case movement once 2.12-2.16 add
  patient-side labels, explicit assumption modes, source-grounded matcher
  paths, and unit reconciliation.)
- Will the Svelte reviewer UI integration land cleanly into the Astro
  routing on `juliusm.com`, or should it be a sibling subdomain? (Decide at
  Phase 2 task 2.9.)
- Cost sweep: which exact models to include, given pricing and availability
  at the time of Phase 3? (Decide at the start of Phase 3 task 3.2.)
