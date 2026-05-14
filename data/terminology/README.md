# Reviewed Terminology Registry

`reviewed_mappings.json`, `reviewed_medication_classes.json`,
`reviewed_expansions.json`, and `reviewed_reference_limits.json` are committed
project data, not resolver caches.

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

Condition/event rows now carry the same reviewed contract. Atomic surfaces such
as HoFH, congenital heart disease, myocardial infarction, stroke, transient
ischemic attack, deep venous thrombosis, pulmonary embolism, and interstitial
lung disease resolve from committed rows so PH-ILD and cardiovascular event-list
phrases can decompose into executable predicates without warmed cache state.
Composite or out-of-scope surfaces such as uncontrolled severe arrhythmia,
left-sided heart disease, active malignancy, liver dysfunction, sleep-apnea
severity phrases, illicit drug abuse, and heavy alcohol use are explicitly
classified so they become typed compiler gaps instead of opaque unmapped
concepts. The current top-gap tranche also records type 2 DM as a reviewed T2DM
abbreviation and classifies cpcPH, kidney transplant history, EGFR/ROS1
biomarkers, measurable-lesion criteria, CNS/spinal metastasis phrases, prior
anti-tumor/TKI exposure, recent major surgery, and oncology toxicity phrases so
the compiler can report why they are not executable condition mappings.
The final opaque-gap pass adds reviewed diabetes/HF/pregnancy surface variants
and classifies the singleton long tail: active hepatitis/HIV/TB infection,
breastfeeding, anticoagulation therapy, LDL-apheresis, hospitalization,
allergy/hypersensitivity, thyroid-control
phrases, NSCLC/staging/metastasis, xeno-crossmatch, and genomic/procedure/event
phrases now have committed non-opaque outcomes.

Procedure rows are first-class reviewed decisions rather than condition aliases.
Surfaces such as `history of full pneumonectomy` and `full pneumonectomy` map
to reviewed SNOMED procedure code lists and compile to `procedure_history`
predicates over parsed patient `Procedure` resources. This keeps
surgical-history evidence out of diagnosis/Condition matching while still
allowing closed-world execution when the patient file contains completed
procedure rows. Dialysis surfaces (`dialysis`, `renal dialysis`, and
`hemodialysis`) are also reviewed procedure rows; the compiler uses them to
decompose CKD/ESRD-on-dialysis condition phrases into condition plus completed
procedure subchecks instead of broadening the condition mapping.

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
surfaces such as `Sotatercept`, `abaloparatide`, `Symlin`, `teriparatide`,
`semaglutide`, `dapagliflozin`, `amylin`/pramlintide, and
`calcitonin`/salmon-calcitonin. Current-vocabulary class passes add reviewed
anchors for `anastrozole`, `carbamazepine`, and anticoagulant representatives
`warfarin`, `enoxaparin`, and `heparin`, letting aromatase-inhibitor,
anticonvulsant-therapy, and anticoagulation criteria compile without live
RxNorm lookups.
Medication-class entries are loaded by
`clinical_demo.terminology.medication_classes`. They key one or more reviewed
class surfaces such as `statins`, `lipid-lowering treatment`,
`bisphosphonate treatment`, `GLP-1 agonists`, `SGLT inhibitor`, `diabetes
medications other than insulin`, `anticoagulation therapy`, or `RASB` to member
medication surfaces such as `atorvastatin`, `simvastatin`, `semaglutide`,
`dapagliflozin`, `warfarin`, `enoxaparin`, and `heparin`. The compiler still
resolves every member through reviewed/cache-only RxNorm lookup before creating
an executable class predicate; missing members remain compiler gaps rather than
partial matches.

Reviewed expansion entries are loaded by
`clinical_demo.terminology.reviewed_expansions`. They turn reviewed broad
parents such as endocrine system disease, psychiatric disorder, and
cardiovascular disease into executable SNOMED code closures without reading the
warmed terminology cache. These closures are deliberately narrower than full
SNOMED transitive hierarchy dumps: each included code has committed reviewer
provenance, and a missing closure still produces a typed expansion gap rather
than silently executing the parent alone.

Reviewed reference-limit entries are loaded by
`clinical_demo.units.reference_limits`. They let the compiler translate
project-reviewed ULN/LLN multiplier criteria such as AST/ALT `<=3 x ULN` and
bilirubin `<=1.5 x ULN` into conventional-unit thresholds when patient
observations do not carry local reference ranges. Sex-specific entries, such as
reviewed male/female hemoglobin ULNs, compile to patient-sex-aware measurement
thresholds when both limits are available. These rows are demo reference-limit
decisions, not a substitute for institution/lab-provided reference intervals;
missing reference limits still produce typed compiler gaps instead of
executable predicates.

The ordinary unit registry in `clinical_demo.units.registry` remains
LOINC-scoped. For example, C-peptide accepts `nmol/L` trial thresholds and
converts them into the `ng/mL` convention used by the committed Synthea
observations; this is not a global `nmol/L` conversion for unrelated analytes.

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

Compiler-review artifacts treat reviewed `extractor_bug` and `out_of_scope`
rows as `review_gap` work rather than compiler implementation work. Reviewed
`composite_unhandled` rows intentionally stay in the implementation lane
because they need decomposition, route/provenance support, or new patient-data
capability before execution is safe.
