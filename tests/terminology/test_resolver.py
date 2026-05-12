"""Tests for the surface-form -> ConceptSet resolver.

The resolver is the cache-first orchestrator that the matcher hits
under `Settings.binding_strategy == "two_pass"`. These tests cover
its three modes -- cache-hit, cache-miss-with-fetcher, soft-fail --
across both VSAC and RxNorm bindings.

All tests run offline:
- VSAC traffic is faked via `httpx.MockTransport` (same pattern as
  `test_vsac_client.py`).
- RxNorm traffic is faked the same way.
- The cache is rooted at `tmp_path` so each test starts empty
  unless it explicitly writes a fixture in.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from clinical_demo.profile import ConceptSet
from clinical_demo.profile.concept_sets import FRACTURE, METFORMIN
from clinical_demo.terminology import (
    ECQM_DIABETES_OID,
    REVIEWED_REGISTRY_VERSION,
    ReviewedMappingEntry,
    ReviewedMappingRegistry,
    ReviewedMappingStatus,
    RxNormBinding,
    RxNormClient,
    RxNormConcepts,
    SurfaceResolution,
    TerminologyCache,
    TerminologyResolver,
    VSACBinding,
    VSACClient,
    VSACExpansion,
    cache_path_for_rxnorm,
    cache_path_for_surface_resolution,
    cache_path_for_vsac,
    load_reviewed_mapping_registry,
)
from clinical_demo.terminology.rxnorm_client import RXNORM_SYSTEM_URI
from clinical_demo.terminology.umls_search_client import (
    LOINC_SOURCE,
    SNOMEDCT_SOURCE,
    UMLSSearchClient,
)

VSAC_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "vsac" / "diabetes_expansion.json"
RXNORM_FIXTURE = (
    Path(__file__).resolve().parents[1] / "fixtures" / "rxnorm" / "metformin_drugs.json"
)
REPO_ROOT = Path(__file__).resolve().parents[2]
SNOMED = "http://snomed.info/sct"


# ---------- pre-warm helpers ----------


def _prewarm_vsac(
    cache: TerminologyCache,
    *,
    oid: str = ECQM_DIABETES_OID,
    codes: frozenset[str] | None = None,
    system_filter: str | None = None,
) -> VSACExpansion:
    """Write a `StoredVSACExpansion` to disk so the resolver hits
    the cache without needing a client. Returns the expansion the
    cache will return so tests can assert on it."""
    expansion = VSACExpansion(
        oid=oid,
        version="20210220",
        concept_set=ConceptSet(
            name="Diabetes",
            system=SNOMED,
            codes=codes if codes is not None else frozenset({"44054006", "73211009"}),
        ),
    )
    cache.put_vsac_expansion(expansion, system_filter=system_filter)
    return expansion


def _prewarm_rxnorm(
    cache: TerminologyCache,
    *,
    name: str = "metformin",
    codes: frozenset[str] | None = None,
    tty_filter: frozenset[str] | None = None,
) -> RxNormConcepts:
    concepts = RxNormConcepts(
        query=name,
        concept_set=ConceptSet(
            name=name,
            system=RXNORM_SYSTEM_URI,
            codes=codes if codes is not None else frozenset({"6809"}),
        ),
        term_types=frozenset({"IN"}),
    )
    cache.put_rxnorm_concepts(concepts, tty_filter=tty_filter)
    return concepts


def _reviewed_registry(
    entries: list[ReviewedMappingEntry] | None = None,
) -> ReviewedMappingRegistry:
    return ReviewedMappingRegistry(entries or [])


def _reviewed_mapping(
    surface: str,
    *,
    status: ReviewedMappingStatus = "mapped",
    concept_set: str | None = "FRACTURE",
) -> ReviewedMappingEntry:
    return ReviewedMappingEntry.model_validate(
        {
            "kind": "condition",
            "surface": surface,
            "status": status,
            "concept_set": concept_set,
            "reason": "unit-test reviewed decision",
            "source": "unit test",
            "provenance": "unit test",
            "reviewer": "unit-test",
            "reviewed_at": "2026-05-08",
            "resolver_version": REVIEWED_REGISTRY_VERSION,
            "expansion_policy": "reviewed_code_list",
        }
    )


def _reviewed_lab_mapping(surface: str, concept_set: str) -> ReviewedMappingEntry:
    return ReviewedMappingEntry.model_validate(
        {
            "kind": "lab",
            "surface": surface,
            "status": "mapped",
            "concept_set": concept_set,
            "reason": "unit-test reviewed lab decision",
            "source": "unit test",
            "provenance": "unit test",
            "reviewer": "unit-test",
            "reviewed_at": "2026-05-11",
            "resolver_version": REVIEWED_REGISTRY_VERSION,
            "expansion_policy": "exact_code",
        }
    )


def _reviewed_inline_condition_mapping(surface: str) -> ReviewedMappingEntry:
    return ReviewedMappingEntry.model_validate(
        {
            "kind": "condition",
            "surface": surface,
            "status": "mapped",
            "concept_set": "reviewed:condition:asthma-inline",
            "candidates": [
                {
                    "name": "Asthma",
                    "system": SNOMED,
                    "codes": ["195967001"],
                    "source": "unit test inline reviewed code set",
                    "score": 1.0,
                    "reason": "Inline reviewed code set should not require a Python ConceptSet.",
                }
            ],
            "reason": "unit-test reviewed inline condition decision",
            "source": "unit test",
            "provenance": "unit test",
            "reviewer": "unit-test",
            "reviewed_at": "2026-05-12",
            "resolver_version": REVIEWED_REGISTRY_VERSION,
            "expansion_policy": "exact_code",
        }
    )


def _vsac_client_with_body(body: bytes) -> tuple[VSACClient, list[httpx.Request]]:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, content=body, headers={"content-type": "application/fhir+json"})

    return VSACClient(api_key="dummy-key", transport=httpx.MockTransport(handler)), captured


def _vsac_client_failing(*, status: int = 500) -> VSACClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status, content=b"upstream error", headers={"content-type": "text/plain"}
        )

    return VSACClient(api_key="dummy-key", transport=httpx.MockTransport(handler))


def _rxnorm_client_with_body(body: bytes) -> tuple[RxNormClient, list[httpx.Request]]:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, content=body, headers={"content-type": "application/json"})

    return RxNormClient(transport=httpx.MockTransport(handler)), captured


# ---------- VSAC: cache hit ----------


def test_resolve_vsac_returns_cached_concept_set_without_client(tmp_path: Path) -> None:
    """Cache hit short-circuits before the client is touched. Pass
    `vsac_client=None` so any attempt to fetch would AttributeError;
    the test passing proves the cache really did short-circuit."""
    cache = TerminologyCache(tmp_path)
    expansion = _prewarm_vsac(cache)
    resolver = TerminologyResolver(cache, vsac_client=None)

    out = resolver.resolve(VSACBinding(oid=ECQM_DIABETES_OID))

    assert out is not None
    assert out == expansion.concept_set
    assert "44054006" in out.codes


# ---------- VSAC: cache miss + fetch ----------


def test_resolve_vsac_fetches_on_cache_miss_and_caches_result(tmp_path: Path) -> None:
    """First call: cache empty -> client fetches -> cache populated.
    Second call: cache hit -> client untouched. Counting captured
    requests pins the no-double-fetch property."""
    cache = TerminologyCache(tmp_path)
    body = VSAC_FIXTURE.read_bytes()
    client, captured = _vsac_client_with_body(body)
    resolver = TerminologyResolver(cache, vsac_client=client)

    first = resolver.resolve(VSACBinding(oid=ECQM_DIABETES_OID))
    second = resolver.resolve(VSACBinding(oid=ECQM_DIABETES_OID))

    assert first is not None
    assert second is not None
    assert first == second
    # Cache miss -> one HTTP call. Second call serves from disk.
    assert len(captured) == 1
    # And the row landed on disk for future processes.
    expected = cache_path_for_vsac(ECQM_DIABETES_OID, tmp_path)
    assert expected.exists()


def test_cached_only_policy_does_not_fetch_vsac_on_cache_miss(tmp_path: Path) -> None:
    cache = TerminologyCache(tmp_path)
    body = VSAC_FIXTURE.read_bytes()
    client, captured = _vsac_client_with_body(body)
    resolver = TerminologyResolver(
        cache,
        vsac_client=client,
        execution_policy="cached_only",
    )

    out = resolver.resolve(VSACBinding(oid=ECQM_DIABETES_OID))

    assert out is None
    assert captured == []
    assert not cache_path_for_vsac(ECQM_DIABETES_OID, tmp_path).exists()


def test_resolve_vsac_cache_miss_with_no_client_soft_fails(tmp_path: Path) -> None:
    """No credentials, no pre-warmed cache -> resolver returns
    None and the matcher falls back to the alias table. The whole
    point of the soft-fail discipline."""
    cache = TerminologyCache(tmp_path)
    resolver = TerminologyResolver(cache, vsac_client=None)

    out = resolver.resolve(VSACBinding(oid=ECQM_DIABETES_OID))
    assert out is None


def test_resolve_vsac_fetch_error_soft_fails(tmp_path: Path) -> None:
    """Upstream 500 -> client raises VSACError -> resolver catches
    and returns None. Matcher degrades to alias / unmapped without
    the run crashing."""
    cache = TerminologyCache(tmp_path)
    resolver = TerminologyResolver(cache, vsac_client=_vsac_client_failing(status=500))

    out = resolver.resolve(VSACBinding(oid=ECQM_DIABETES_OID))
    assert out is None
    # Cache must NOT contain a poisoned entry.
    assert not cache_path_for_vsac(ECQM_DIABETES_OID, tmp_path).exists()


def test_resolve_vsac_network_error_soft_fails(tmp_path: Path) -> None:
    """`httpx.HTTPError` (DNS, connection refused, etc.) is caught
    the same as `VSACError`. The transport raises
    `httpx.ConnectError`, the client wraps it in `VSACError` per
    its own contract; the resolver swallows either."""

    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("simulated DNS failure")

    cache = TerminologyCache(tmp_path)
    client = VSACClient(api_key="dummy-key", transport=httpx.MockTransport(boom))
    resolver = TerminologyResolver(cache, vsac_client=client)

    out = resolver.resolve(VSACBinding(oid=ECQM_DIABETES_OID))
    assert out is None


def test_resolve_vsac_passes_system_filter_to_cache_and_client(tmp_path: Path) -> None:
    """A binding with `system_filter` must produce a different
    cache key than the same OID without one. Pre-warm both keys
    with disjoint code sets and assert the resolver picks the
    right one."""
    cache = TerminologyCache(tmp_path)
    _prewarm_vsac(cache, codes=frozenset({"44054006"}))  # no filter
    _prewarm_vsac(cache, codes=frozenset({"73211009"}), system_filter=SNOMED)

    resolver = TerminologyResolver(cache, vsac_client=None)
    no_filter = resolver.resolve(VSACBinding(oid=ECQM_DIABETES_OID))
    with_filter = resolver.resolve(VSACBinding(oid=ECQM_DIABETES_OID, system_filter=SNOMED))

    assert no_filter is not None and with_filter is not None
    assert no_filter.codes == frozenset({"44054006"})
    assert with_filter.codes == frozenset({"73211009"})


# ---------- RxNorm: parallel coverage ----------


def test_resolve_rxnorm_returns_cached_without_client(tmp_path: Path) -> None:
    cache = TerminologyCache(tmp_path)
    concepts = _prewarm_rxnorm(cache)
    resolver = TerminologyResolver(cache, rxnorm_client=None)

    out = resolver.resolve(RxNormBinding(name="metformin"))
    assert out == concepts.concept_set


def test_resolve_rxnorm_fetches_on_miss_and_caches(tmp_path: Path) -> None:
    cache = TerminologyCache(tmp_path)
    body = RXNORM_FIXTURE.read_bytes()
    client, captured = _rxnorm_client_with_body(body)
    resolver = TerminologyResolver(cache, rxnorm_client=client)

    first = resolver.resolve(RxNormBinding(name="metformin"))
    second = resolver.resolve(RxNormBinding(name="metformin"))

    assert first is not None
    assert first == second
    assert len(captured) == 1
    assert cache_path_for_rxnorm("metformin", tmp_path).exists()


def test_resolve_rxnorm_cache_miss_with_no_client_soft_fails(tmp_path: Path) -> None:
    cache = TerminologyCache(tmp_path)
    resolver = TerminologyResolver(cache, rxnorm_client=None)

    out = resolver.resolve(RxNormBinding(name="metformin"))
    assert out is None


def test_resolve_rxnorm_network_error_soft_fails(tmp_path: Path) -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("simulated network failure")

    cache = TerminologyCache(tmp_path)
    client = RxNormClient(transport=httpx.MockTransport(boom))
    resolver = TerminologyResolver(cache, rxnorm_client=client)

    out = resolver.resolve(RxNormBinding(name="metformin"))
    assert out is None


def test_resolve_rxnorm_tty_filter_keys_cache_independently(tmp_path: Path) -> None:
    """Same name with vs. without `tty_filter` is two different
    cache rows, mirroring the VSAC system_filter behaviour."""
    cache = TerminologyCache(tmp_path)
    _prewarm_rxnorm(cache, codes=frozenset({"6809"}))  # no filter
    _prewarm_rxnorm(cache, codes=frozenset({"99999"}), tty_filter=frozenset({"IN"}))

    resolver = TerminologyResolver(cache, rxnorm_client=None)
    no_filter = resolver.resolve(RxNormBinding(name="metformin"))
    with_filter = resolver.resolve(RxNormBinding(name="metformin", tty_filter=("IN",)))

    assert no_filter is not None and with_filter is not None
    assert no_filter.codes == frozenset({"6809"})
    assert with_filter.codes == frozenset({"99999"})


# ---------- surface-form wrappers ----------


def test_resolve_condition_uses_registry_then_cache(tmp_path: Path) -> None:
    """End-to-end: the registry's T2DM binding -> the resolver's
    cache hit -> a ConceptSet shaped exactly like the alias path
    would have produced. This is the wire-up slice 4 exists for.

    Pre-warm under `system_filter=SNOMED` because the T2DM bindings
    pin that filter (live VSAC expansion now spans SNOMED + ICD-10-CM
    and `VSACClient` rejects multi-system without a filter). Cache
    keys include the filter, so a None-filter pre-warm would miss."""
    cache = TerminologyCache(tmp_path)
    expansion = _prewarm_vsac(cache, system_filter=SNOMED)
    resolver = TerminologyResolver(cache, vsac_client=None)

    for surface in ("type 2 diabetes", "T2DM", "  Type II Diabetes  "):
        out = resolver.resolve_condition(surface)
        assert out is not None, f"surface {surface!r} should resolve"
        assert out == expansion.concept_set


def test_resolve_condition_unregistered_surface_returns_none(tmp_path: Path) -> None:
    """Unknown surface -> `None` from the registry -> resolver
    returns `None` so the caller falls back to the alias table.
    Distinct from 'unmapped concept' (which is the matcher's
    final verdict if both bridges miss)."""
    cache = TerminologyCache(tmp_path)
    resolver = TerminologyResolver(cache, vsac_client=None)
    assert resolver.resolve_condition("acute pancreatitis") is None


def test_resolve_condition_open_alias_maps_and_caches_qualified_hypertension(
    tmp_path: Path,
) -> None:
    cache = TerminologyCache(tmp_path)
    resolver = TerminologyResolver(cache, vsac_client=None)

    out = resolver.resolve_condition("uncontrolled hypertension")

    assert out is not None
    assert out.name == "Essential hypertension"
    assert "38341003" in out.codes
    cached = cache.get_surface_resolution("condition", "Uncontrolled Hypertension")
    assert cached is not None
    assert cached.status == "mapped"
    assert cached.concept_set == out


def test_resolve_condition_open_alias_maps_t1d_and_hypertension_qualifiers(
    tmp_path: Path,
) -> None:
    cache = TerminologyCache(tmp_path)
    resolver = TerminologyResolver(cache, vsac_client=None)

    t1d = resolver.resolve_condition("T1D diagnosis")
    mild_hypertension = resolver.resolve_condition("mild to moderate hypertension")

    assert t1d is not None
    assert t1d.codes == frozenset({"46635009"})
    assert mild_hypertension is not None
    assert "38341003" in mild_hypertension.codes


def test_resolve_condition_open_alias_overrides_stale_true_miss_cache(
    tmp_path: Path,
) -> None:
    cache = TerminologyCache(tmp_path)
    cache.put_surface_resolution(
        SurfaceResolution(
            kind="condition",
            surface="type 1 diabetes",
            normalized_surface="type 1 diabetes",
            status="true_miss",
            concept_set=None,
            candidates=[],
            reason="stale pre-alias miss",
            resolver_version="open-surface-v0.2",
        )
    )
    resolver = TerminologyResolver(cache, vsac_client=None)

    out = resolver.resolve_condition("type 1 diabetes")

    assert out is not None
    assert out.codes == frozenset({"46635009"})
    cached = cache.get_surface_resolution("condition", "type 1 diabetes")
    assert cached is not None
    assert cached.status == "mapped"


def test_resolve_lab_soft_fails_when_cache_empty_and_no_client(
    tmp_path: Path,
) -> None:
    """`hba1c` is now in LAB_BINDINGS (HbA1c VSAC value set), but
    the cache is empty and no vsac_client is configured -> soft-fail
    to None. Same shape as the medication soft-fail test;
    documents that a fresh checkout without pre-warmed cache rows
    reproduces alias-only baseline behaviour."""
    cache = TerminologyCache(tmp_path)
    resolver = TerminologyResolver(cache, vsac_client=None)
    assert resolver.resolve_lab("hba1c") is None


def test_resolve_lab_open_alias_maps_high_frequency_synthea_observations(
    tmp_path: Path,
) -> None:
    cache = TerminologyCache(tmp_path)
    resolver = TerminologyResolver(cache, vsac_client=None)

    bmi = resolver.resolve_lab("body mass index")
    hemoglobin = resolver.resolve_lab("hemoglobin")
    platelet_count = resolver.resolve_lab("platelet count")
    c_peptide = resolver.resolve_lab("C-peptide concentrations")

    assert bmi is not None
    assert hemoglobin is not None
    assert platelet_count is not None
    assert c_peptide is not None
    assert bmi.codes == frozenset({"39156-5"})
    assert hemoglobin.codes == frozenset({"718-7"})
    assert platelet_count.codes == frozenset({"777-3"})
    assert c_peptide.codes == frozenset({"1986-9"})
    assert cache_path_for_surface_resolution("lab", "hemoglobin", tmp_path).exists()


def test_resolve_lab_open_alias_overrides_stale_true_miss_cache(tmp_path: Path) -> None:
    cache = TerminologyCache(tmp_path)
    cache.put_surface_resolution(
        SurfaceResolution(
            kind="lab",
            surface="C-peptide concentrations",
            normalized_surface="c-peptide concentrations",
            status="true_miss",
            concept_set=None,
            candidates=[],
            reason="stale pre-alias miss",
            resolver_version="open-surface-v0.2",
        )
    )
    resolver = TerminologyResolver(cache, vsac_client=None)

    out = resolver.resolve_lab("C-peptide concentrations")

    assert out is not None
    assert out.codes == frozenset({"1986-9"})
    cached = cache.get_surface_resolution("lab", "C-peptide concentrations")
    assert cached is not None
    assert cached.status == "mapped"


def test_resolve_lab_open_alias_returns_cached_without_reconsulting_tables(
    tmp_path: Path,
) -> None:
    cache = TerminologyCache(tmp_path)
    resolver = TerminologyResolver(cache, vsac_client=None)
    first = resolver.resolve_lab("body mass index")
    assert first is not None

    second = resolver.resolve_lab("  Body Mass Index  ")
    assert second == first


def test_resolve_lab_ambiguous_surface_is_cached_as_nonresolved(tmp_path: Path) -> None:
    cache = TerminologyCache(tmp_path)
    resolver = TerminologyResolver(cache, vsac_client=None)

    out = resolver.resolve_lab("blood pressure")

    assert out is None
    cached = cache.get_surface_resolution("lab", "blood pressure")
    assert cached is not None
    assert cached.status == "ambiguous"
    assert cached.concept_set is None
    assert {c.name for c in cached.candidates} == {
        "Systolic blood pressure",
        "Diastolic blood pressure",
    }


def test_resolve_medication_reviewed_mapping_wins_without_cache_or_client(
    tmp_path: Path,
) -> None:
    cache = TerminologyCache(tmp_path)
    resolver = TerminologyResolver(cache, rxnorm_client=None)

    out = resolver.resolve_medication("metformin")

    assert out == METFORMIN
    cached = cache.get_surface_resolution("medication", "metformin")
    assert cached is not None
    assert cached.status == "mapped"
    assert cached.concept_set == METFORMIN


def test_resolve_medication_unknown_surface_soft_fails_without_client(
    tmp_path: Path,
) -> None:
    cache = TerminologyCache(tmp_path)
    resolver = TerminologyResolver(cache, rxnorm_client=None)

    assert resolver.resolve_medication("unknown-drug") is None


def test_resolve_medication_open_rxnorm_searches_any_surface_and_caches(
    tmp_path: Path,
) -> None:
    cache = TerminologyCache(tmp_path)
    body = RXNORM_FIXTURE.read_bytes()
    client, captured = _rxnorm_client_with_body(body)
    resolver = TerminologyResolver(cache, rxnorm_client=client)

    first = resolver.resolve_medication("Glucophage")
    second = resolver.resolve_medication("glucophage")

    assert first is not None
    assert first == second
    assert len(captured) == 1
    assert cache_path_for_rxnorm("Glucophage", tmp_path).exists()
    cached = cache.get_surface_resolution("medication", "glucophage")
    assert cached is not None
    assert cached.status == "mapped"


def test_resolve_medication_open_rxnorm_caches_true_miss(tmp_path: Path) -> None:
    cache = TerminologyCache(tmp_path)
    body = json.dumps({"drugGroup": {"name": "not-a-med", "conceptGroup": []}}).encode()
    client, captured = _rxnorm_client_with_body(body)
    resolver = TerminologyResolver(cache, rxnorm_client=client)

    first = resolver.resolve_medication("not-a-med")
    second = resolver.resolve_medication("NOT-A-MED")

    assert first is None
    assert second is None
    assert len(captured) == 1
    cached = cache.get_surface_resolution("medication", "not-a-med")
    assert cached is not None
    assert cached.status == "true_miss"


# ---------- UMLS open search (conditions + labs) ----------


def _umls_client_with_body(body: bytes) -> tuple[UMLSSearchClient, list[httpx.Request]]:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, content=body, headers={"content-type": "application/json"})

    return (
        UMLSSearchClient(api_key="dummy-key", transport=httpx.MockTransport(handler)),
        captured,
    )


def _snomed_body(codes: list[tuple[str, str]]) -> bytes:
    return json.dumps(
        {
            "result": {
                "results": [
                    {"ui": ui, "name": name, "rootSource": SNOMEDCT_SOURCE} for ui, name in codes
                ]
            }
        }
    ).encode()


def _loinc_body(codes: list[tuple[str, str]]) -> bytes:
    return json.dumps(
        {
            "result": {
                "results": [
                    {"ui": ui, "name": name, "rootSource": LOINC_SOURCE} for ui, name in codes
                ]
            }
        }
    ).encode()


def _umls_empty_body() -> bytes:
    return json.dumps({"result": {"results": [{"ui": "NONE", "name": "NO RESULTS"}]}}).encode()


def test_resolve_open_condition_uses_umls_search_and_caches_mapped(tmp_path: Path) -> None:
    """Surface not in the alias table + UMLS exact-match returns hits
    -> mapped ConceptSet cached under the open-surface fingerprint.
    This is the whole point of D-73: the system must actually look
    things up, not declare them unmapped because they're not in a
    hand-coded dict."""
    cache = TerminologyCache(tmp_path)
    body = _snomed_body(
        [
            ("195967001", "Asthma"),
            ("304527002", "Acute asthma"),
        ]
    )
    umls_client, captured = _umls_client_with_body(body)
    resolver = TerminologyResolver(cache, umls_client=umls_client)

    result = resolver.resolve_condition("asthma")

    assert result is not None
    assert result.system == "http://snomed.info/sct"
    assert result.codes == frozenset({"195967001", "304527002"})
    assert len(captured) == 1
    cached = cache.get_surface_resolution("condition", "asthma")
    assert cached is not None
    assert cached.status == "mapped"
    assert cached.resolver_version.startswith("open-surface-v")
    # Candidate metadata carries UMLS atom names for auditability.
    assert {c.name for c in cached.candidates} >= {"Asthma"}


def test_resolve_open_condition_caches_true_miss_on_zero_hits(tmp_path: Path) -> None:
    cache = TerminologyCache(tmp_path)
    umls_client, captured = _umls_client_with_body(_umls_empty_body())
    resolver = TerminologyResolver(cache, umls_client=umls_client)

    first = resolver.resolve_condition("notarealconditionphrase")
    second = resolver.resolve_condition("notarealconditionphrase")

    assert first is None
    assert second is None
    assert len(captured) == 1  # second call served by cache
    cached = cache.get_surface_resolution("condition", "notarealconditionphrase")
    assert cached is not None
    assert cached.status == "true_miss"


def test_cached_only_policy_does_not_call_umls_open_search(tmp_path: Path) -> None:
    cache = TerminologyCache(tmp_path)
    umls_client, captured = _umls_client_with_body(_snomed_body([("195967001", "Asthma")]))
    resolver = TerminologyResolver(
        cache,
        umls_client=umls_client,
        execution_policy="cached_only",
        reviewed_registry=_reviewed_registry(),
    )

    out = resolver.resolve_condition("asthma")

    assert out is None
    assert captured == []
    assert cache.get_surface_resolution("condition", "asthma") is None


def test_cached_only_policy_still_returns_warmed_surface_cache(tmp_path: Path) -> None:
    cache = TerminologyCache(tmp_path)
    asthma = ConceptSet(
        name="Asthma",
        system="http://snomed.info/sct",
        codes=frozenset({"195967001"}),
    )
    cache.put_surface_resolution(
        SurfaceResolution(
            kind="condition",
            surface="asthma",
            normalized_surface="asthma",
            status="mapped",
            concept_set=asthma,
            candidates=[],
            reason="prewarmed test row",
            resolver_version="open-surface-v0.2",
        )
    )
    umls_client, captured = _umls_client_with_body(_snomed_body([("304527002", "Acute asthma")]))
    resolver = TerminologyResolver(
        cache,
        umls_client=umls_client,
        execution_policy="cached_only",
        reviewed_registry=_reviewed_registry(),
    )

    out = resolver.resolve_condition("asthma")

    assert out == asthma
    assert captured == []


def test_resolve_open_condition_without_umls_client_soft_fails(tmp_path: Path) -> None:
    """No UMLS_API_KEY -> no umls_client -> resolver returns None and
    does NOT write a cache row. Later, once an API key is set, the
    next call can still resolve; a premature miss cache would
    freeze alias-only behaviour forever."""
    cache = TerminologyCache(tmp_path)
    resolver = TerminologyResolver(cache, umls_client=None)

    assert resolver.resolve_condition("asthma") is None
    assert cache.get_surface_resolution("condition", "asthma") is None


def test_resolve_open_condition_skips_umls_for_composite_surfaces(tmp_path: Path) -> None:
    """Composite phrases like 'pregnant or breastfeeding' must NOT
    hit UMLS with an exact-match (guaranteed zero hits, wasted API
    traffic, and the resulting `true_miss` would also mislead
    downstream triage). Cache `composite_unhandled` without a
    network call."""
    cache = TerminologyCache(tmp_path)
    umls_client, captured = _umls_client_with_body(_umls_empty_body())
    resolver = TerminologyResolver(cache, umls_client=umls_client)

    out = resolver.resolve_condition("pregnant or breastfeeding")
    assert out is None
    assert len(captured) == 0
    cached = cache.get_surface_resolution("condition", "pregnant or breastfeeding")
    assert cached is not None
    assert cached.status == "composite_unhandled"


def test_reviewed_registry_fracture_mapping_overwrites_stale_true_miss(
    tmp_path: Path,
) -> None:
    """Reviewed registry decisions must win before cached non-mapped rows.

    This pins the `Bone fractures` regression: UMLS exact search had
    cached a `true_miss`, but the committed reviewed mapping should now
    replace that stale miss without paying another UMLS call.
    """
    cache = TerminologyCache(tmp_path)
    cache.put_surface_resolution(
        SurfaceResolution(
            kind="condition",
            surface="Bone fractures",
            normalized_surface="bone fractures",
            status="true_miss",
            concept_set=None,
            candidates=[],
            reason="old exact-search miss",
            resolver_version="open-surface-v0.2",
        )
    )
    umls_client, captured = _umls_client_with_body(_umls_empty_body())
    resolver = TerminologyResolver(
        cache,
        umls_client=umls_client,
        reviewed_registry=_reviewed_registry([_reviewed_mapping("Bone fractures")]),
    )

    out = resolver.resolve_condition("Bone fractures")

    assert out == FRACTURE
    assert len(captured) == 0
    cached = cache.get_surface_resolution("condition", "Bone fractures")
    assert cached is not None
    assert cached.status == "mapped"
    assert cached.concept_set == FRACTURE
    assert cached.candidates[0].source == "reviewed_registry"


def test_reviewed_registry_lab_mapping_uses_shared_concept_registry(tmp_path: Path) -> None:
    cache = TerminologyCache(tmp_path)
    resolver = TerminologyResolver(
        cache,
        reviewed_registry=_reviewed_registry(
            [_reviewed_lab_mapping("fasting serum LDL-C", "LDL_CHOLESTEROL")]
        ),
    )

    out = resolver.resolve_lab("fasting serum LDL-C")

    assert out is not None
    assert out.codes == frozenset({"18262-6"})
    cached = cache.get_surface_resolution("lab", "fasting serum LDL-C")
    assert cached is not None
    assert cached.status == "mapped"
    assert cached.candidates[0].source == "reviewed_registry"


def test_reviewed_registry_inline_code_set_maps_without_python_concept_set(
    tmp_path: Path,
) -> None:
    cache = TerminologyCache(tmp_path)
    resolver = TerminologyResolver(
        cache,
        reviewed_registry=_reviewed_registry([_reviewed_inline_condition_mapping("asthma")]),
    )

    out = resolver.resolve_condition("asthma")

    assert out is not None
    assert out.name == "asthma"
    assert out.system == SNOMED
    assert out.codes == frozenset({"195967001"})
    cached = cache.get_surface_resolution("condition", "asthma")
    assert cached is not None
    assert cached.status == "mapped"
    assert cached.concept_set == out
    assert cached.candidates[0].source == "reviewed_registry"


def test_committed_long_tail_reviewed_condition_rows_resolve_and_cache(
    tmp_path: Path,
) -> None:
    cache = TerminologyCache(tmp_path)
    resolver = TerminologyResolver(
        cache,
        reviewed_registry=load_reviewed_mapping_registry(
            REPO_ROOT / "data" / "terminology" / "reviewed_mappings.json"
        ),
    )

    hofh = resolver.resolve_condition("HoFH")
    congenital = resolver.resolve_condition("history of congenital heart disease")
    arrhythmia = resolver.resolve_condition("uncontrolled severe arrhythmia")
    ild = resolver.resolve_condition("interstitial lung disease")

    assert hofh is not None
    assert hofh.system == SNOMED
    assert hofh.codes == frozenset({"238078005"})
    assert congenital is not None
    assert congenital.system == SNOMED
    assert congenital.codes == frozenset({"13213009"})
    assert ild is not None
    assert ild.system == SNOMED
    assert ild.codes == frozenset({"233703007"})
    assert arrhythmia is None
    cached = cache.get_surface_resolution("condition", "uncontrolled severe arrhythmia")
    assert cached is not None
    assert cached.status == "composite_unhandled"
    assert cached.candidates[0].codes == frozenset({"698247007"})


def test_disabled_policy_bypasses_reviewed_registry(tmp_path: Path) -> None:
    cache = TerminologyCache(tmp_path)
    resolver = TerminologyResolver(
        cache,
        execution_policy="disabled",
        reviewed_registry=_reviewed_registry([_reviewed_mapping("Bone fractures")]),
    )

    assert resolver.resolve_condition("Bone fractures") is None
    assert cache.get_surface_resolution("condition", "Bone fractures") is None


def test_resolve_open_condition_soft_fails_on_umls_transport_error(tmp_path: Path) -> None:
    """UMLS 500 / network error -> resolver returns None and MUST
    NOT cache anything; a transient outage must not freeze into a
    cached true miss."""

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, content=b"server error")

    cache = TerminologyCache(tmp_path)
    umls_client = UMLSSearchClient(api_key="k", transport=httpx.MockTransport(handler))
    resolver = TerminologyResolver(cache, umls_client=umls_client)

    assert resolver.resolve_condition("asthma") is None
    assert cache.get_surface_resolution("condition", "asthma") is None


def test_resolve_open_lab_uses_umls_loinc_search_when_alias_misses(tmp_path: Path) -> None:
    """A lab surface not in `_OPEN_LAB_ALIASES` / `_OPEN_AMBIGUOUS_LABS`
    goes to UMLS with `sabs=LNC`. Example: LDL cholesterol."""
    cache = TerminologyCache(tmp_path)
    body = _loinc_body(
        [
            ("18262-6", "Cholesterol in LDL [Mass/volume] in Serum or Plasma by Direct assay"),
            ("13457-7", "Cholesterol in LDL [Mass/volume] in Serum or Plasma by calculation"),
        ]
    )
    umls_client, captured = _umls_client_with_body(body)
    resolver = TerminologyResolver(cache, umls_client=umls_client)

    result = resolver.resolve_lab("ldl cholesterol")

    assert result is not None
    assert result.system == "http://loinc.org"
    assert result.codes == frozenset({"18262-6", "13457-7"})
    # sabs=LNC was sent. searchType=words for labs (vs. exact for
    # conditions) because LOINC stores common names on Parts, not
    # on numeric test codes -- see the `_resolve_open_lab` comment.
    assert captured[0].url.params["sabs"] == LOINC_SOURCE
    assert captured[0].url.params["searchType"] == "words"


def test_resolve_open_lab_filters_out_loinc_component_parts(tmp_path: Path) -> None:
    """UMLS `words` search over LNC returns both numeric LOINC test
    codes (`777-3`, `718-7`, ...) and LOINC Parts (`LP*`, `LA*`,
    `MTHU*`). Parts are component atoms, not observations a patient
    can carry. Drop them so a mapped ConceptSet is actually
    matchable against `PatientProfile.observations`."""
    cache = TerminologyCache(tmp_path)
    body = _loinc_body(
        [
            ("MTHU004672", "Hemoglobin"),  # Part, must be filtered
            ("LP32067-8", "Hemoglobin"),  # Part, must be filtered
            ("718-7", "Hemoglobin [Mass/volume] in Blood"),  # numeric test code, kept
        ]
    )
    umls_client, _ = _umls_client_with_body(body)
    resolver = TerminologyResolver(cache, umls_client=umls_client)

    # Pick a surface NOT in `_OPEN_LAB_ALIASES` to force the UMLS
    # path. "hgb" isn't currently aliased.
    result = resolver.resolve_lab("hgb")
    assert result is not None
    assert result.codes == frozenset({"718-7"})


def test_resolve_open_lab_caches_true_miss_when_only_loinc_parts_returned(
    tmp_path: Path,
) -> None:
    cache = TerminologyCache(tmp_path)
    body = _loinc_body([("LP32067-8", "Hemoglobin"), ("MTHU004672", "Hemoglobin")])
    umls_client, _ = _umls_client_with_body(body)
    resolver = TerminologyResolver(cache, umls_client=umls_client)

    out = resolver.resolve_lab("hgb")
    assert out is None
    cached = cache.get_surface_resolution("lab", "hgb")
    assert cached is not None
    assert cached.status == "true_miss"


def test_resolve_open_lab_ambiguous_alias_still_wins_over_umls(tmp_path: Path) -> None:
    """`blood pressure` is known-ambiguous (systolic vs diastolic).
    The ambiguous-alias table must run BEFORE UMLS search so a
    generic LOINC hit cluster does not silently paper over the
    ambiguity. This pins the precedence against future refactors."""
    cache = TerminologyCache(tmp_path)
    umls_client, captured = _umls_client_with_body(_loinc_body([("8480-6", "Systolic BP")]))
    resolver = TerminologyResolver(cache, umls_client=umls_client)

    out = resolver.resolve_lab("blood pressure")
    assert out is None  # still surfaced as ambiguous, not resolved
    assert len(captured) == 0  # and UMLS was never consulted
    cached = cache.get_surface_resolution("lab", "blood pressure")
    assert cached is not None
    assert cached.status == "ambiguous"


def test_resolve_open_condition_skips_umls_on_repeat_resolved_hit(tmp_path: Path) -> None:
    """After the first mapped cache write, repeat calls must not
    re-query UMLS. This is the cost-control property: eval re-runs
    converge on cache-only traffic."""
    cache = TerminologyCache(tmp_path)
    umls_client, captured = _umls_client_with_body(_snomed_body([("195967001", "Asthma")]))
    resolver = TerminologyResolver(cache, umls_client=umls_client)

    first = resolver.resolve_condition("asthma")
    second = resolver.resolve_condition("Asthma  ")
    third = resolver.resolve_condition("ASTHMA")

    assert first == second == third
    assert first is not None
    assert len(captured) == 1


# ---------- defensive ----------


def test_resolve_unknown_binding_type_soft_fails(tmp_path: Path) -> None:
    """A binding type not in the dispatch table doesn't crash the
    resolver. Constructed via a Pydantic model that satisfies the
    structural shape but isn't either concrete branch."""

    class FakeBinding:
        """Future binding type the dispatch hasn't learned yet."""

    cache = TerminologyCache(tmp_path)
    resolver = TerminologyResolver(cache)
    # Bypass type-checker to simulate a future bindings.py addition
    # that landed without resolver.py learning about it.
    out = resolver.resolve(FakeBinding())  # type: ignore[arg-type]
    assert out is None
