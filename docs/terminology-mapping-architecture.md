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

Related: `docs/concept-mapping-failure-taxonomy.md`, `docs/evaluation-layers-and-gates.md`.
