# Concept mapping failure taxonomy

Categories used when trial-side strings **do not** resolve cleanly to a matcher `ConceptSet`, or when tooling classifies why a surface dominates **unmapped_concept** counts. This aligns with **work queue statuses**, matcher **reason enums**, and operational language in eval diagnostics.

---

## 1. Work queue statuses (terminology triage)

| Status | Meaning |
|--------|---------|
| **resolved** | Resolver produced a `ConceptSet`; matcher can bind codes for future runs with cache support. |
| **ambiguous** | Resolver surfaced multiple plausible bindings; human must choose before treating as resolved. |
| **true_miss** | Reasonable string for real-world trials, but **no acceptable** vocabulary binding exists yet in our stack (genuine gap to extend dictionaries or APIs). |
| **composite_unhandled** | Surface bundles multiple concepts (`and` / `or` / lists) or temporal-window **event** text needs extraction work before mapping is meaningful. |
| **extractor_bug** | The extractor placed text in a typed slot that **cannot** be mapped as a single concept (manual override — e.g. performance scores, life expectancy phrases). |
| **out_of_scope** | Criterion kind or concept class is outside the patient data model or matcher v0 (manual override or no resolver channel). |
| **unresolved** | No hit, no heuristic bucket, no manual row yet — still needs triage. |

---

## 2. Matcher verdict reasons (patient-facing, not exclusive to mapping)

These overlap the taxonomy but are **runtime** outcomes on a single criterion:

| Reason | Typical mapping story |
|--------|-------------------------|
| **unmapped_concept** | Lookup returned `None` — string never bound to a `ConceptSet` (could be any of: true miss, composite, extractor bug, out-of-scope; work queue tells which). |
| **no_data** | Concept bound, but patient profile lacks the needed row (or open-world forbids inferring absence). |
| **unit_mismatch** | Lab mapped, but units cannot be normalized safely. |
| **ambiguous_criterion** | Trial wording too underspecified for a numeric or coded check. |
| **human_review_required** | Free-text bucket or adjudicator deferral. |
| **extractor_invariant_violation** | Schema-valid JSON but impossible combination (e.g. kind says measurement but payload empty) — soft-fail per criterion. |

---

## 3. How to pick a category (operator playbook)

1. **Run diagnostics** → find `(kind, surface)` keys with counts.
2. **Try resolver + cache** via work-queue builder.
3. If composite heuristics fire → **composite_unhandled** until split or event extraction exists.
4. If API returns junk for Synthea reality → **manual override** to **extractor_bug** or **out_of_scope** rather than a poisonous `resolved`.
5. If API returns nothing and surface is clean atomic clinical term → **true_miss** or **unresolved** until vocabulary extended.
6. If multiple good codes → **ambiguous** with candidates saved.

---

## 4. “Free-text-required” (cross-cutting)

Not a separate enum value — manifests as **extractor** emitting **`free_text`** criteria or matcher returning **`human_review_required`**. Often overlaps **composite_unhandled** when the protocol bundles many clauses in one bullet.

Related: `docs/terminology-mapping-architecture.md`, `docs/trial-extraction-pipeline.md`.
