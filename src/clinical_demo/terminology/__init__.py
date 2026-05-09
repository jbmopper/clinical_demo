"""NLM terminology API clients for the D-69 binding-strategy comparison.

This package exists to back arms B (`one_pass`) and C (`two_pass`) of
the surface-form → ConceptSet binding pipeline; arm A (the
hand-curated baseline at `clinical_demo.matcher.concept_lookup` and
`clinical_demo.profile.concept_sets`) does not depend on anything
here. See PLAN.md §12 D-69 for the full comparison.

v0 surface (this PR): a `VSACClient` that resolves a single
value-set OID against the VSAC FHIR `$expand` endpoint and returns
a `ConceptSet` shaped exactly like the hand-curated constants — so
the matcher's existing dispatch keeps working when the value-set
membership comes from VSAC instead of `concept_sets.py`. RxNorm and
UMLS clients land alongside this when the extractor prompt grows
the OID/RxCUI emission for arms B and C.
"""

from __future__ import annotations

from clinical_demo.terminology.bindings import (
    CONDITION_BINDINGS,
    ECQM_DIABETES_OID,
    ECQM_HBA1C_LAB_OID,
    ECQM_HYPERTENSION_OID,
    LAB_BINDINGS,
    LOINC_SYSTEM,
    MEDICATION_BINDINGS,
    SNOMED_SYSTEM,
    Binding,
    RxNormBinding,
    VSACBinding,
    lookup_condition_binding,
    lookup_lab_binding,
    lookup_medication_binding,
)
from clinical_demo.terminology.cache import (
    StoredRxNormConcepts,
    StoredSurfaceResolution,
    StoredVSACExpansion,
    SurfaceResolution,
    SurfaceResolutionCandidate,
    SurfaceResolutionKind,
    SurfaceResolutionStatus,
    TerminologyCache,
    cache_path_for_rxnorm,
    cache_path_for_surface_resolution,
    cache_path_for_vsac,
    rxnorm_envelope_fingerprint,
    surface_resolution_envelope_fingerprint,
    vsac_envelope_fingerprint,
)
from clinical_demo.terminology.resolver import (
    RESOLVER_EXECUTION_POLICIES,
    TerminologyResolver,
    get_resolver,
    get_reviewed_mapping_registry,
)
from clinical_demo.terminology.reviewed_registry import (
    REVIEWED_REGISTRY_VERSION,
    DuplicateReviewedMappingError,
    ExpansionPolicy,
    ReviewedMappingCandidate,
    ReviewedMappingEntry,
    ReviewedMappingFile,
    ReviewedMappingKind,
    ReviewedMappingRegistry,
    ReviewedMappingStatus,
    load_reviewed_mapping_registry,
    normalize_surface,
)
from clinical_demo.terminology.rxnorm_client import (
    RxNormClient,
    RxNormConcepts,
    RxNormError,
)
from clinical_demo.terminology.umls_search_client import (
    LOINC_SOURCE,
    SNOMEDCT_SOURCE,
    UMLSSearchClient,
    UMLSSearchError,
    UMLSSearchHit,
    UMLSSearchResult,
)
from clinical_demo.terminology.vsac_client import (
    VSACClient,
    VSACError,
    VSACExpansion,
)

__all__ = [
    "CONDITION_BINDINGS",
    "ECQM_DIABETES_OID",
    "ECQM_HBA1C_LAB_OID",
    "ECQM_HYPERTENSION_OID",
    "LAB_BINDINGS",
    "LOINC_SOURCE",
    "LOINC_SYSTEM",
    "MEDICATION_BINDINGS",
    "RESOLVER_EXECUTION_POLICIES",
    "REVIEWED_REGISTRY_VERSION",
    "SNOMEDCT_SOURCE",
    "SNOMED_SYSTEM",
    "Binding",
    "DuplicateReviewedMappingError",
    "ExpansionPolicy",
    "ReviewedMappingCandidate",
    "ReviewedMappingEntry",
    "ReviewedMappingFile",
    "ReviewedMappingKind",
    "ReviewedMappingRegistry",
    "ReviewedMappingStatus",
    "RxNormBinding",
    "RxNormClient",
    "RxNormConcepts",
    "RxNormError",
    "StoredRxNormConcepts",
    "StoredSurfaceResolution",
    "StoredVSACExpansion",
    "SurfaceResolution",
    "SurfaceResolutionCandidate",
    "SurfaceResolutionKind",
    "SurfaceResolutionStatus",
    "TerminologyCache",
    "TerminologyResolver",
    "UMLSSearchClient",
    "UMLSSearchError",
    "UMLSSearchHit",
    "UMLSSearchResult",
    "VSACBinding",
    "VSACClient",
    "VSACError",
    "VSACExpansion",
    "cache_path_for_rxnorm",
    "cache_path_for_surface_resolution",
    "cache_path_for_vsac",
    "get_resolver",
    "get_reviewed_mapping_registry",
    "load_reviewed_mapping_registry",
    "lookup_condition_binding",
    "lookup_lab_binding",
    "lookup_medication_binding",
    "normalize_surface",
    "rxnorm_envelope_fingerprint",
    "surface_resolution_envelope_fingerprint",
    "vsac_envelope_fingerprint",
]
