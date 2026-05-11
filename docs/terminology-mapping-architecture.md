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

## 4. Curated overrides and manual triage

Before hitting live resolution, the work-queue path checks a **small manual table** for known problematic surfaces (performance status, life expectancy, etc.). Manual rows **win** over a hypothetical API hit that would produce a misleading `ConceptSet` for Synthea — they are labeled **`extractor_bug`** or **`out_of_scope`** with explicit reasons and are written into the cache so repeated eval runs do not re-query.

---

## 5. Work queue: from eval diagnostics to classified surfaces

Eval diagnostics produce **top unmapped surfaces** (criterion kind + surface string + count). The work queue:

1. Maps criterion kind → resolver channel (**condition / medication / lab**) or marks **out_of_scope** if the kind has no resolver (e.g. unsupported kind).
2. Applies **manual override** if present.
3. Otherwise calls resolver; on success records **resolved** with the `ConceptSet`.
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
  lookup.
- `CC-02` now has deterministic query variants, candidate ranking, confidence
  gates, and the resolver execution policy contract wired into settings and
  CLIs: eval/API default to `cached_only`, while the cache warmer explicitly
  opts into `live_allowed`.
- `CC-03` now has offline expansion policy objects for exact codes, reviewed
  code lists, patient-vocabulary closure, and explicit unsupported states for
  descendant/value-set expansion that still need graph/cache backing.
- `CC-04` now has a unit registry shared by the compiler-facing code and
  `PatientProfile` threshold checks.
- `CC-05` now has an opt-in compiled-predicate matcher, so eval can compare
  legacy matcher-input execution against compiled-predicate execution before
  the default path changes.
- `CC-06` through `CC-09` have helper foundations for compound/time,
  measurement, and medication compilation.
- `CC-10` now has `ClosedWorldValidationResult` reporting for closed-world
  readiness over compiled criteria, and `ScorePairResult` exposes it to API and
  eval consumers.
- `CC-11` now has deterministic `CompilerGapQueueItem` projection for reviewer
  workflow plus `CompilerGapReviewRow` artifacts from persisted eval runs.
- `CC-12` now has `ParityReport` and `compare_compilation_parity(...)` for
  legacy-vs-compiled execution comparison, and eval diagnostics aggregate
  compiler coverage, unresolved gaps, and closed-world blockers.

Active integration status:

- The next integration slice is adding CI/baseline thresholds and reviewer
  promotion flows, then hardening predicate behavior behind the parity gate.

Related: `docs/concept-mapping-failure-taxonomy.md`, `docs/evaluation-layers-and-gates.md`.
