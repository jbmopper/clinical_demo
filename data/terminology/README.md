# Reviewed Terminology Registry

`reviewed_mappings.json`, `reviewed_medication_classes.json`, and
`reviewed_expansions.json` are committed project data, not resolver caches.

Use this registry for terminology decisions that a reviewer has explicitly
accepted, rejected, or classified as requiring non-atomic compiler handling.
Cache rows under `data/cache/terminology/` record observed resolver results and
can be deleted or regenerated; rows here should move through normal code review.
Compiler code may also read these rows directly when the right outcome is a
typed unresolved fragment rather than a terminology lookup. For example,
reviewed lab rows for standalone PVR, ECOG, life expectancy, corrected calcium,
vitamin D3, generic blood pressure, beta-hydroxybutyrate, QTc/CK/proteinuria,
Karnofsky, creatinine clearance, and plasma-glucose timing/provenance let
measurement compilation emit `unsupported_predicate`, `ambiguous_mapping`, or
extractor-bug diagnostics instead of an opaque `unmapped_concept`. Reviewed
mapped lab rows such as AST, ANC, serum creatinine, fasting blood glucose/FPG,
LDL-C, triglycerides, total bilirubin, and mean sitting office systolic BP
resolve through the shared profile `ConceptSet` registry rather than through ad
hoc compiler aliases.

Each mapping is keyed by `(kind, normalized_surface)` and loaded by
`clinical_demo.terminology.reviewed_registry`. Duplicate keys are rejected at
load time so runtime resolver integration has a single deterministic answer.
Mapped entries may point at a shared Python `ConceptSet` id, or they may carry
an inline reviewed code set in `candidates[]` when the surface is too specific
to deserve a new source constant. Inline reviewed rows are still committed
review decisions, not cache rows; they are the mechanism used to make the
2026-05-12 fresh-cache compiler run independent of warmed UMLS/RxNorm surface
cache files. The cache-independent tranche also records an intentional safety
correction: `PH` maps to pulmonary hypertension in the trial context, overriding
an unsafe warmed-cache pH-finding hit.

Medication entries now also cover the first committed patient-vocabulary
RxNorm anchors (`metformin`, `insulin`, statins, alendronic acid, and RAAS
representatives) plus cache-independent reviewed RxNorm code sets for trial-only
surfaces such as `Sotatercept`, `abaloparatide`, `Symlin`, and `teriparatide`.
Medication-class entries are loaded by
`clinical_demo.terminology.medication_classes`. They key one or more reviewed
class surfaces such as `statins`, `lipid-lowering treatment`,
`bisphosphonate treatment`, or `RASB` to member medication surfaces such as
`atorvastatin` and `simvastatin`. The compiler still resolves every member
through reviewed/cache-only RxNorm lookup before creating an executable class
predicate; missing members remain compiler gaps rather than partial matches.

Reviewed expansion entries are loaded by
`clinical_demo.terminology.reviewed_expansions`. They turn reviewed broad
parents such as endocrine system disease, psychiatric disorder, and
cardiovascular disease into executable SNOMED code closures without reading the
warmed terminology cache. These closures are deliberately narrower than full
SNOMED transitive hierarchy dumps: each included code has committed reviewer
provenance, and a missing closure still produces a typed expansion gap rather
than silently executing the parent alone.

Expansion policies:

- `exact_code`: the entry names one exact code or exact concept.
- `descendants`: the entry intentionally includes descendants under a reviewed
  hierarchy concept. For deterministic runs this requires a matching row in
  `reviewed_expansions.json`; otherwise the compiler emits an expansion gap.
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
