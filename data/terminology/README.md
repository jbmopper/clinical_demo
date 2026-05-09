# Reviewed Terminology Registry

`reviewed_mappings.json` is committed project data, not a resolver cache.

Use this registry for terminology decisions that a reviewer has explicitly
accepted, rejected, or classified as requiring non-atomic compiler handling.
Cache rows under `data/cache/terminology/` record observed resolver results and
can be deleted or regenerated; rows here should move through normal code review.

Each mapping is keyed by `(kind, normalized_surface)` and loaded by
`clinical_demo.terminology.reviewed_registry`. Duplicate keys are rejected at
load time so runtime resolver integration has a single deterministic answer.

Expansion policies:

- `exact_code`: the entry names one exact code or exact concept.
- `descendants`: the entry intentionally includes descendants under a reviewed
  hierarchy concept.
- `value_set_oid`: the entry delegates expansion to a reviewed value-set OID.
- `reviewed_code_list`: the entry points at a project-owned reviewed code list.
- `patient_vocabulary_closure`: the entry is closed over codes observed in the
  current patient vocabulary.

Statuses:

- `mapped`: the surface is mapped to a project ConceptSet.
- `ambiguous`: candidates exist, but the review could not choose one safely.
- `true_miss`: the surface was reviewed and should not map to terminology.
- `composite_unhandled`: the surface must be decomposed by compiler logic before
  terminology lookup.
- `extractor_bug`: the surface exists because extraction emitted the wrong span
  or type.
- `out_of_scope`: the surface is outside the matcher/compiler scope.
