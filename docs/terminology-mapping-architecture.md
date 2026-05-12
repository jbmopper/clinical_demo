# Terminology mapping architecture

How trial-side **surface strings** (conditions, medications, labs) become **`ConceptSet`** objects the matcher can use, how **caches** keep runs deterministic, and how **work-queue classification** turns unmapped mass into actionable buckets.

---

## 1. ConceptSet (matcher-facing output)

A **ConceptSet** is a named bundle: **coding system URI** + a **frozenset of codes** (e.g. multiple equivalent LOINCs for one lab concept). The profile layer requires system + code together so SNOMED and ICD numeric collisions cannot match by accident.

Matchers call **lookup** helpers for:

- **Conditions** and temporal-window **event text** (routed through condition resolution).
- **Medications**.
- **Labs** for measurement thresholds.

Lookup returns **`None`** when no binding exists — the verdict becomes **indeterminate (unmapped_concept)** with missing-evidence text, regardless of open/closed world.

---

## 2. Resolver front door

A **terminology resolver** service sits between raw strings and `ConceptSet`s. Implementations may call:

- **VSAC** value-set expansion (cached per OID + filter fingerprint).
- **RxNorm** drug concept fetch (cached per query fingerprint).
- **UMLS / LOINC search** style clients for open resolution paths where curated maps do not exist.

The resolver is the **source of truth** for “is this string mappable today?” — the work queue reuses it when warming or classifying surfaces.

---

## 3. On-disk terminology cache

**Why:** Live NLM calls are slow, rate-limited, and **non-deterministic across days**. Caching pins “what the matcher saw” to disk so eval replays and CI-style **`--no-llm`** runs do not silently drift when a remote synonym changes.

**How:** Separate namespaces per upstream (VSAC envelope, RxNorm envelope, surface-resolution rows). Cache filenames embed **query identity** and a **schema fingerprint** of the stored envelope so incompatible old files are never read silently — they become orphaned files under the gitignored cache root.

**Surface resolution cache:** Stores resolution status, optional winning `ConceptSet`, candidate list, resolver version string, and human-readable **reason** text for non-resolutions.

---

## 4. Reviewed registry decisions

Before hitting live resolution, the resolver checks the committed reviewed
registry under `data/terminology/`. Those rows are project decisions, not
generated cache observations. They can map a surface to a reviewed `ConceptSet`,
record ambiguity with candidates, or classify a surface as `extractor_bug`,
`out_of_scope`, `true_miss`, or `composite_unhandled`.

Reviewed rows **win** over stale cache entries and over hypothetical API hits
that would produce a misleading `ConceptSet` for Synthea. Recent examples are
standalone PVR and ECOG measurement surfaces (`out_of_scope`), life expectancy
as a measurement (`extractor_bug`), generic blood pressure (`ambiguous` with
systolic/diastolic candidates), and reviewed lab/vital mappings such as AST,
ANC, serum creatinine, fasting glucose/FPG, LDL-C, triglycerides, bilirubin,
and mean sitting office systolic BP. Reviewed non-mapping rows also cover
provenance-sensitive surfaces such as fasting/random/OGTT plasma glucose, and
unsupported data-model surfaces such as beta-hydroxybutyrate, QTc, creatine
kinase, proteinuria, Karnofsky, creatinine clearance, and derived imaging or
prognostic scores. The resolver writes compatible surface-resolution cache rows
for repeated eval runs, while the compiler can consume the same reviewed
decisions directly as typed gaps or mapped measurement predicates. The compiler
also owns decomposition before lookup when the surface is intentionally generic:
for example, explicit systolic/diastolic BP clauses, `SBP`/`DBP` pairs, and
generic `BP X/Y` threshold shorthand compile into separate systolic and
diastolic LOINC predicates instead of asking the reviewed registry to choose
one generic `blood pressure` mapping.

---

## 5. Work queue: from eval diagnostics to classified surfaces

Eval diagnostics produce **top unmapped surfaces** (criterion kind + surface string + count). The work queue:

1. Maps criterion kind → resolver channel (**condition / medication / lab**) or marks **out_of_scope** if the kind has no resolver (e.g. unsupported kind).
2. Applies a **reviewed registry decision** if present.
3. Otherwise calls resolver; on success records **mapped** with the `ConceptSet`.
4. If still unresolved, may reuse a **prior cached resolution** with the same open-resolver version.
5. Heuristics mark **composite_unhandled** when the surface looks like a conjunction/list (`and`, `or`, commas, slashes) or when the kind is **temporal_window** (event extraction is a prerequisite).
6. Otherwise leaves **unresolved** for human follow-up.

---

## 6. Regression gate

A watchlist JSON file can record surfaces previously classified **`resolved`**. A CI-style script intersects a new eval diagnostic’s top unmapped list with that watchlist — if any watched surface reappears at sufficient count, the check **fails**. That prevents silent terminology regressions from shipping between baselines.

---

## 7. Ambiguity and candidates

When the resolver returns **candidates** without a single committed `ConceptSet`, the cache can hold **ambiguous** (or similar) status with structured candidate metadata so humans can pick a binding without losing API context.

---

## 8. Criterion Compiler

The resolver alone is not enough. Trial text often needs to be compiled before
it is checkable: broad terminology classes need expansion, compound criteria
need boolean subchecks, measurements need canonical units or normal-range
semantics, and temporal phrases need event windows. The target flow is:

```text
extracted criterion
  -> criterion compiler / resolver
  -> validated atomic predicates plus explicit unresolved fragments
  -> deterministic matcher
```

Manual Python aliases are a compatibility fallback. New reviewed decisions
should be committed registry rows under `data/terminology/` with provenance,
reviewer metadata, expansion policy, and regression coverage. Runtime API
responses and warmed lookup outcomes remain generated cache rows under
`data/cache/terminology/`.

Resolver execution must also be explicit. Eval and API paths should run
`cached_only` by default so a deterministic score cannot silently depend on
today's network response. Probe and cache-warming scripts may opt into
`live_allowed`, and every persisted run/report should record the resolver
execution policy alongside the reviewed-registry and resolver versions.

The concrete implementation plan lives in `PLAN.md` under **Criterion Compiler /
Resolution Layer Plan Objects**. It defines the work objects `CC-00` through
`CC-12`, their dependencies, exit criteria, test targets, and which parts can
run in parallel. As of 2026-05-11, the compiler emits concrete supports, gaps,
expansion plans, unit-normalization plans, and `CheckablePredicate`s. Scoring
still defaults to legacy `matcher_inputs`, but
`matcher_execution_source="compiled_predicates"` can execute the compiler
predicate source through the same `MatchVerdict` envelope.

- Parallel foundations: compiler IR, reviewed registry, terminology candidate
  ranking, and unit knowledge base.
- Parallel specialist compilers after the IR exists: compound criteria,
  temporal events, measurements, and medications/classes.
- Serial integration: compiler pipeline, validation gates, reviewer workflow,
  and eval/baseline gates.

Foundation status:

- `CC-00` now has a versioned compiler IR and `ScorePairResult` carries the
  compilation result used by scoring.
- `CC-01` now has a committed reviewed registry under `data/terminology/`;
  `Bone fractures` maps through that registry before stale cache rows or live
  lookup, and reviewed lab non-mapping/ambiguity decisions are consumed by the
  measurement compiler.
- `CC-02` now has deterministic query variants, candidate ranking, confidence
  gates, and the resolver execution policy contract wired into settings and
  CLIs: eval/API default to `cached_only`, while the cache warmer explicitly
  opts into `live_allowed`.
- `CC-03` now has offline expansion policy objects for exact codes, reviewed
  code lists, patient-vocabulary closure, and explicit unsupported states for
  descendant/value-set expansion that still need graph/cache backing.
- `CC-04` now has a unit registry shared by the compiler-facing code and
  `PatientProfile` threshold checks. It accepts conservative spelling, casing,
  spacing, slash, and micro-symbol variants while dropping ambiguous normalized
  aliases so unknown units still fail closed.
- `CC-05` now has an opt-in compiled-predicate matcher, so eval can compare
  legacy matcher-input execution against compiled-predicate execution before
  the default path changes. Native composite groups now compile their subchecks
  into the parent and execute through the compiled-predicate matcher with the
  same any_of/all_of rollup semantics as the legacy matcher-input path.
- `CC-06` through `CC-09` have helper foundations for compound/time,
  measurement, and medication compilation. Temporal event lookup now tries
  conservative condition-event variants for diagnosis/history-shaped surfaces
  such as `recent T2D diagnosis`, while workflow anchors such as screening or
  baseline visits remain explicit unsupported predicates. Medication
  compilation now strips route-only words such as `oral` before ingredient
  resolution while preserving the route aspect in compiler provenance. It also reads
  `data/terminology/reviewed_medication_classes.json` for reviewed
  patient-vocabulary-closure class expansions such as statins, GLP-1 receptor
  agonists, and SGLT2 inhibitors; class predicates are emitted only when every
  member surface resolves through cached/reviewed RxNorm lookup.
- `CC-08` now checks reviewed lab decisions before local measurement alias
  lookup, so known out-of-scope, extractor-bug, and ambiguous measurement
  surfaces become explicit compiler gaps with provenance instead of opaque
  unmapped concepts. Reviewed mapped lab surfaces resolve through the shared
  profile `ConceptSet` registry and unit registry, while missing threshold
  values remain blocking `predicate_translation` gaps instead of executable
  predicates. It also decomposes explicit systolic/diastolic blood-pressure
  thresholds, SBP/DBP abbreviation pairs, and generic BP pair shorthand into
  typed systolic/diastolic measurement compounds, which removes the generic
  blood-pressure ambiguity bucket from the current compiler-review packet.
- `CC-10` now has `ClosedWorldValidationResult` reporting for closed-world
  readiness over compiled criteria, and `ScorePairResult` exposes it to API and
  eval consumers.
- `CC-11` now has deterministic `CompilerGapQueueItem` projection for reviewer
  workflow plus `CompilerGapReviewRow` and deduped `CompilerGapReviewGroup`
  artifacts from persisted eval runs.
- `CC-12` now has `ParityReport` and `compare_compilation_parity(...)` for
  legacy-vs-compiled execution comparison, and eval diagnostics aggregate
  compiler coverage, unresolved gaps, and closed-world blockers. The companion
  `scripts/check_compiler_diagnostics.py` gate can fail CI when those counts
  exceed baseline thresholds.

Active integration status:

- The next integration slice is reviewer promotion flows and baseline threshold
  selection behind the parity gate, using a fresh eval to expose the remaining
  predicate gaps.

Related: `docs/concept-mapping-failure-taxonomy.md`, `docs/evaluation-layers-and-gates.md`.
