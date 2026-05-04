"""Surface form -> ConceptSet resolver via the bindings registry + cache.

Stitches three pieces together for D-69 slice 4:

1. The trial-side bindings registry (`terminology.bindings`) maps a
   surface form to a `VSACBinding` or `RxNormBinding`.
2. The on-disk `TerminologyCache` (`terminology.cache`) services
   subsequent calls without paying NLM round-trip cost.
3. The live `VSACClient` / `RxNormClient` (`terminology.vsac_client` /
   `.rxnorm_client`) fetch on cache miss when credentials are set.

The resolver is what `matcher.concept_lookup.lookup_*` calls when
`Settings.binding_strategy == "two_pass"`. Its return contract is
intentionally identical to the alias table's: `ConceptSet` on
success, `None` on any kind of miss or soft-fail. The matcher's
existing `unmapped_concept` branch consumes `None` unchanged, so a
terminology outage degrades to the same `indeterminate` verdict the
alias path produces today (D-65 / D-66 soft-fail discipline applied
at the binding layer).

Soft-fail rules
---------------

- Surface form not in the bindings registry -> `None` (caller falls
  back to the alias table).
- Binding present, cache hit -> `ConceptSet`.
- Binding present, cache miss, credentials available, fetch
  succeeds -> `ConceptSet` (and the cache now has the row for next
  time).
- Binding present, cache miss, no credentials / no client -> `None`
  + warning log. Lets a fresh checkout without `UMLS_API_KEY` opt
  into `two_pass` and still produce useful output for any binding
  whose cache is pre-warmed (e.g. shipped with the repo for tests).
- Binding present, fetch raises (network, auth, rate limit,
  schema drift) -> caught, warning logged, `None` returned. The
  matcher's downstream verdict is the same shape as an alias miss;
  the warning is the only externally visible signal that a degrade
  happened.

Lifetime
--------
A `TerminologyResolver` is cheap to construct (no I/O); the
`get_resolver()` accessor keeps a process-wide singleton so the
matcher's hot path doesn't re-instantiate clients per criterion.
Tests build their own resolvers against a temp cache and inject
clients (or `None`) directly.
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache

import httpx

from clinical_demo.profile import ConceptSet
from clinical_demo.profile.concept_sets import (
    BMI,
    DIASTOLIC_BP,
    HEMOGLOBIN,
    HYPERTENSION,
    PLATELET_COUNT,
    SYSTOLIC_BP,
)
from clinical_demo.settings import Settings, get_settings
from clinical_demo.terminology.bindings import (
    Binding,
    RxNormBinding,
    VSACBinding,
    lookup_condition_binding,
    lookup_lab_binding,
    lookup_medication_binding,
)
from clinical_demo.terminology.cache import (
    SurfaceResolution,
    SurfaceResolutionCandidate,
    SurfaceResolutionKind,
    SurfaceResolutionStatus,
    TerminologyCache,
)
from clinical_demo.terminology.rxnorm_client import RxNormClient, RxNormError
from clinical_demo.terminology.umls_search_client import (
    LOINC_SOURCE,
    SNOMEDCT_SOURCE,
    UMLSSearchClient,
    UMLSSearchError,
    UMLSSearchResult,
)
from clinical_demo.terminology.vsac_client import VSACClient, VSACError

log = logging.getLogger(__name__)

OPEN_SURFACE_RESOLVER_VERSION = "open-surface-v0.2"
"""Bumped from v0.1 when `_resolve_open_condition` / `_resolve_open_lab`
started calling UMLS search on alias misses. Cached v0.1 entries are
ignored (treated as missing) via the version guard in
`_cached_surface_resolution`, so pre-existing `true_miss` rows from
the alias-only era get re-resolved against UMLS on the next hit."""

SNOMED_SYSTEM_URI = "http://snomed.info/sct"
LOINC_SYSTEM_URI = "http://loinc.org"

# LOINC numeric test code: e.g. "718-7", "32623-1". LOINC also
# publishes "Parts" (component atoms with `LP*` / `LA*` / `MTHU*`
# prefixes) that index concepts like "Hemoglobin" but are NOT the
# codes patient observations carry. Synthea's lab Observations are
# coded against numeric LOINC test codes only, so Parts would
# produce resolved-but-unmatchable ConceptSets. Filter them out.
_LOINC_NUMERIC_CODE = re.compile(r"^\d+-\d+$")

# Composite delimiters. A surface that contains any of these cannot
# be resolved atomically against UMLS -- sending "pregnant or
# breastfeeding" to `searchType=exact` is wasted API traffic and
# caching the resulting zero-hit as `true_miss` would also mislead
# downstream triage. Cache these as `composite_unhandled` instead
# so the work_queue sees a useful classification immediately.
_COMPOSITE_TOKENS: tuple[str, ...] = (" and ", " or ", ",", ";", "/")


def _normalize_surface(surface: str) -> str:
    return " ".join(surface.lower().strip(".,;:()[]{}\"'").split())


def _looks_composite(surface: str) -> bool:
    padded = f" {surface.lower()} "
    return any(token in padded for token in _COMPOSITE_TOKENS)


_OPEN_CONDITION_ALIASES: dict[str, tuple[ConceptSet, str]] = {
    "uncontrolled hypertension": (
        HYPERTENSION,
        "Qualifier-bearing hypertension surface collapsed to the hypertension concept.",
    ),
    "poorly controlled hypertension": (
        HYPERTENSION,
        "Qualifier-bearing hypertension surface collapsed to the hypertension concept.",
    ),
}

_OPEN_LAB_ALIASES: dict[str, tuple[ConceptSet, str]] = {
    "bmi": (BMI, "High-confidence LOINC mapping for body mass index."),
    "body mass index": (BMI, "High-confidence LOINC mapping for body mass index."),
    "body mass index bmi": (BMI, "High-confidence LOINC mapping for body mass index."),
    "hemoglobin": (HEMOGLOBIN, "High-confidence LOINC mapping for hemoglobin mass in blood."),
    "hemoglobin level": (HEMOGLOBIN, "High-confidence LOINC mapping for hemoglobin mass in blood."),
    "hemoglobin concentration": (
        HEMOGLOBIN,
        "High-confidence LOINC mapping for hemoglobin mass in blood.",
    ),
    "platelet count": (
        PLATELET_COUNT,
        "High-confidence LOINC mapping for platelet count in blood.",
    ),
    "platelets": (
        PLATELET_COUNT,
        "High-confidence LOINC mapping for platelet count in blood.",
    ),
}

_OPEN_AMBIGUOUS_LABS: dict[str, tuple[list[ConceptSet], str]] = {
    "blood pressure": (
        [SYSTOLIC_BP, DIASTOLIC_BP],
        "Blood pressure needs systolic or diastolic specificity before it can map to one LOINC.",
    ),
    "bp": (
        [SYSTOLIC_BP, DIASTOLIC_BP],
        "Blood pressure needs systolic or diastolic specificity before it can map to one LOINC.",
    ),
}


def _candidate(
    concept_set: ConceptSet,
    *,
    source: str,
    reason: str,
    score: float | None = None,
) -> SurfaceResolutionCandidate:
    return SurfaceResolutionCandidate(
        name=concept_set.name,
        system=concept_set.system,
        codes=concept_set.codes,
        source=source,
        score=score,
        reason=reason,
    )


def _is_rxnorm_true_miss(exc: RxNormError) -> bool:
    return "no drug matched this surface form" in str(exc)


def _umls_candidates(
    result: UMLSSearchResult,
    system_uri: str,
    reason: str,
    *,
    limit: int = 8,
    code_filter: re.Pattern[str] | None = None,
) -> list[SurfaceResolutionCandidate]:
    """Pack up to `limit` UMLS hits from `system_uri` as resolver
    candidates.

    The resolver still returns a unioned `ConceptSet` -- these are
    the audit rows so reviewers can see which UMLS atoms contributed
    without re-running the search. One `SurfaceResolutionCandidate`
    per (source code) entry, deduped by `ui`. `code_filter` drops
    hits whose `ui` does not match the given regex (used for LOINC
    Parts filtering).
    """
    seen: set[str] = set()
    out: list[SurfaceResolutionCandidate] = []
    for hit in result.hits:
        if hit.ui in seen:
            continue
        if hit.root_source not in ("SNOMEDCT_US", "LNC", "RXNORM"):
            continue
        if code_filter is not None and not code_filter.match(hit.ui):
            continue
        seen.add(hit.ui)
        out.append(
            SurfaceResolutionCandidate(
                name=hit.name,
                system=system_uri,
                codes=frozenset({hit.ui}),
                source="umls_search",
                score=None,
                reason=reason,
            )
        )
        if len(out) >= limit:
            break
    return out


class TerminologyResolver:
    """Cache-first surface-form -> ConceptSet resolver.

    Constructed with a `TerminologyCache` and (optionally) live
    clients. When a client is `None`, cache-miss for that source
    short-circuits to `None` instead of raising -- the matcher
    fall-through to the alias table is the intended behavior."""

    def __init__(
        self,
        cache: TerminologyCache,
        *,
        vsac_client: VSACClient | None = None,
        rxnorm_client: RxNormClient | None = None,
        umls_client: UMLSSearchClient | None = None,
    ) -> None:
        self._cache = cache
        self._vsac = vsac_client
        self._rxnorm = rxnorm_client
        self._umls = umls_client

    # ----- per-binding-type primitives -----

    def resolve(self, binding: Binding) -> ConceptSet | None:
        """Dispatch on binding type. Soft-fails to `None` per the
        module docstring."""
        if isinstance(binding, VSACBinding):
            return self._resolve_vsac(binding)
        if isinstance(binding, RxNormBinding):
            return self._resolve_rxnorm(binding)
        # Defensive: a future binding type added without a resolver
        # branch would fall through here. Soft-fail rather than
        # crash the matcher.
        log.warning("TerminologyResolver: unknown binding type %r", type(binding).__name__)
        return None

    def _resolve_vsac(self, binding: VSACBinding) -> ConceptSet | None:
        """Cache-first VSAC expansion. Cache miss + no client ->
        `None`. Fetch error -> `None` + warning."""
        cached = self._cache.get_vsac_expansion(binding.oid, system_filter=binding.system_filter)
        if cached is not None:
            return cached.concept_set

        if self._vsac is None:
            log.warning(
                "TerminologyResolver: VSAC cache miss for OID %s and no client "
                "configured (UMLS_API_KEY unset?); falling through.",
                binding.oid,
            )
            return None

        try:
            expansion = self._cache.vsac_expansion_or_fetch(
                binding.oid,
                system_filter=binding.system_filter,
                fetch=lambda: self._vsac.expand(  # type: ignore[union-attr]
                    binding.oid, system_filter=binding.system_filter
                ),
            )
        except (VSACError, httpx.HTTPError) as exc:
            log.warning(
                "TerminologyResolver: VSAC fetch for OID %s failed (%s); falling through.",
                binding.oid,
                exc,
            )
            return None
        return expansion.concept_set

    def _resolve_rxnorm(self, binding: RxNormBinding) -> ConceptSet | None:
        """Cache-first RxNorm name lookup. Same soft-fail discipline
        as `_resolve_vsac`. The binding stores `tty_filter` as a
        sorted tuple for hashability; the client + cache layer want
        a `frozenset[str] | None`, so we convert here."""
        tty: frozenset[str] | None = (
            frozenset(binding.tty_filter) if binding.tty_filter is not None else None
        )

        cached = self._cache.get_rxnorm_concepts(binding.name, tty_filter=tty)
        if cached is not None:
            return cached.concept_set

        if self._rxnorm is None:
            log.warning(
                "TerminologyResolver: RxNorm cache miss for name %r and no client "
                "configured; falling through.",
                binding.name,
            )
            return None

        try:
            concepts = self._cache.rxnorm_concepts_or_fetch(
                binding.name,
                tty_filter=tty,
                fetch=lambda: self._rxnorm.find_drug_concepts(  # type: ignore[union-attr]
                    binding.name, tty_filter=tty
                ),
            )
        except (RxNormError, httpx.HTTPError) as exc:
            log.warning(
                "TerminologyResolver: RxNorm fetch for %r failed (%s); falling through.",
                binding.name,
                exc,
            )
            return None
        return concepts.concept_set

    # ----- surface-form convenience wrappers -----
    #
    # Mirror the three `lookup_*` entry points in
    # `matcher.concept_lookup` so the matcher-side switch is a
    # one-line delegation.

    def resolve_condition(self, surface: str) -> ConceptSet | None:
        cache_hit, cached = self._cached_surface_resolution("condition", surface)
        if cache_hit:
            return cached

        binding = lookup_condition_binding(surface)
        if binding is not None:
            concept_set = self.resolve(binding)
            if concept_set is not None:
                self._cache_resolved_surface(
                    "condition",
                    surface,
                    concept_set,
                    source="bindings_registry",
                    reason="Resolved through the curated terminology bindings registry.",
                )
                return concept_set

        return self._resolve_open_condition(surface)

    def resolve_lab(self, surface: str) -> ConceptSet | None:
        cache_hit, cached = self._cached_surface_resolution("lab", surface)
        if cache_hit:
            return cached

        binding = lookup_lab_binding(surface)
        if binding is not None:
            concept_set = self.resolve(binding)
            if concept_set is not None:
                self._cache_resolved_surface(
                    "lab",
                    surface,
                    concept_set,
                    source="bindings_registry",
                    reason="Resolved through the curated terminology bindings registry.",
                )
                return concept_set

        return self._resolve_open_lab(surface)

    def resolve_medication(self, surface: str) -> ConceptSet | None:
        cache_hit, cached = self._cached_surface_resolution("medication", surface)
        if cache_hit:
            return cached

        binding = lookup_medication_binding(surface)
        if binding is not None:
            concept_set = self.resolve(binding)
            if concept_set is not None:
                self._cache_resolved_surface(
                    "medication",
                    surface,
                    concept_set,
                    source="bindings_registry",
                    reason="Resolved through the curated terminology bindings registry.",
                )
                return concept_set

        return self._resolve_open_medication(surface)

    # ----- open surface-form resolver -----

    def _cached_surface_resolution(
        self,
        kind: SurfaceResolutionKind,
        surface: str,
    ) -> tuple[bool, ConceptSet | None]:
        """Return cached open-surface result when current and resolved.

        Non-resolved current entries are also useful: returning None
        here skips repeated network calls for known ambiguous or
        composite inputs, while still letting the matcher emit its
        existing honest `unmapped_concept` verdict downstream.
        """
        try:
            cached = self._cache.get_surface_resolution(kind, surface)
        except Exception as exc:  # pragma: no cover - defensive cache corruption path.
            log.warning(
                "TerminologyResolver: surface cache read for %s %r failed (%s); falling through.",
                kind,
                surface,
                exc,
            )
            return False, None
        if cached is None:
            return False, None
        if cached.resolver_version != OPEN_SURFACE_RESOLVER_VERSION:
            return False, None
        if cached.status == "resolved":
            return True, cached.concept_set
        return True, None

    def _cache_resolved_surface(
        self,
        kind: SurfaceResolutionKind,
        surface: str,
        concept_set: ConceptSet,
        *,
        source: str,
        reason: str,
        candidates: list[SurfaceResolutionCandidate] | None = None,
    ) -> ConceptSet:
        if candidates is None:
            candidates = [_candidate(concept_set, source=source, reason=reason, score=1.0)]
        resolution = SurfaceResolution(
            kind=kind,
            surface=surface,
            normalized_surface=_normalize_surface(surface),
            status="resolved",
            concept_set=concept_set,
            candidates=candidates,
            reason=reason,
            resolver_version=OPEN_SURFACE_RESOLVER_VERSION,
        )
        try:
            self._cache.put_surface_resolution(resolution)
        except OSError as exc:
            log.warning(
                "TerminologyResolver: surface cache write for %s %r failed (%s).",
                kind,
                surface,
                exc,
            )
        return concept_set

    def _cache_nonresolved_surface(
        self,
        kind: SurfaceResolutionKind,
        surface: str,
        *,
        status: SurfaceResolutionStatus,
        reason: str,
        candidates: list[SurfaceResolutionCandidate] | None = None,
    ) -> None:
        resolution = SurfaceResolution(
            kind=kind,
            surface=surface,
            normalized_surface=_normalize_surface(surface),
            status=status,
            concept_set=None,
            candidates=candidates or [],
            reason=reason,
            resolver_version=OPEN_SURFACE_RESOLVER_VERSION,
        )
        try:
            self._cache.put_surface_resolution(resolution)
        except OSError as exc:
            log.warning(
                "TerminologyResolver: surface cache write for %s %r failed (%s).",
                kind,
                surface,
                exc,
            )

    def _resolve_open_condition(self, surface: str) -> ConceptSet | None:
        normalized = _normalize_surface(surface)
        local = _OPEN_CONDITION_ALIASES.get(normalized)
        if local is not None:
            concept_set, reason = local
            return self._cache_resolved_surface(
                "condition",
                surface,
                concept_set,
                source="local_open_alias",
                reason=reason,
            )

        return self._resolve_via_umls(
            surface,
            kind="condition",
            sabs=(SNOMEDCT_SOURCE,),
            system_uri=SNOMED_SYSTEM_URI,
            search_type="exact",
        )

    def _resolve_open_lab(self, surface: str) -> ConceptSet | None:
        normalized = _normalize_surface(surface)
        local = _OPEN_LAB_ALIASES.get(normalized)
        if local is not None:
            concept_set, reason = local
            return self._cache_resolved_surface(
                "lab",
                surface,
                concept_set,
                source="local_open_alias",
                reason=reason,
            )

        ambiguous = _OPEN_AMBIGUOUS_LABS.get(normalized)
        if ambiguous is not None:
            concept_sets, reason = ambiguous
            self._cache_nonresolved_surface(
                "lab",
                surface,
                status="ambiguous",
                reason=reason,
                candidates=[
                    _candidate(cs, source="local_open_alias", reason=reason, score=0.5)
                    for cs in concept_sets
                ],
            )
            return None

        return self._resolve_via_umls(
            surface,
            kind="lab",
            sabs=(LOINC_SOURCE,),
            system_uri=LOINC_SYSTEM_URI,
            # LOINC stores the common name (e.g. "Hemoglobin") on
            # component Parts (`LP*`/`MTHU*`), not on the numeric
            # test codes (`718-7`) that patient observations carry.
            # `exact` over LNC therefore returns Parts only --
            # resolved-but-unmatchable. `words` returns numeric test
            # codes mixed with Parts, and the downstream Parts
            # filter keeps only the codes the matcher can actually
            # compare against the patient.
            search_type="words",
            loinc_numeric_only=True,
        )

    def _resolve_via_umls(
        self,
        surface: str,
        *,
        kind: SurfaceResolutionKind,
        sabs: tuple[str, ...],
        system_uri: str,
        search_type: str = "exact",
        loinc_numeric_only: bool = False,
    ) -> ConceptSet | None:
        """Open-search a surface against UMLS and cache the outcome.

        Policy (conservative on purpose -- see D-73):

        1. If the surface contains conjunction / list punctuation,
           skip the API call and cache `composite_unhandled`. Sending
           composites to `searchType=exact` wastes API traffic and a
           zero-hit response would get cached as `true_miss`, which
           misleads downstream triage.
        2. If no UMLS client is configured (no `UMLS_API_KEY` on the
           host), fall through to `None` silently. The matcher's
           existing `unmapped_concept` branch absorbs this the same
           way it absorbs an alias miss today.
        3. Otherwise call UMLS with `searchType=exact` against the
           requested source vocabulary. Hits -> `resolved` with the
           unioned code set cached. Zero hits -> `true_miss` cached
           so repeat runs skip the network.
        4. On transport or parse error, soft-fail to `None` and do
           NOT cache: a transient failure must not freeze into a
           cached true miss.
        """
        if _looks_composite(surface):
            self._cache_nonresolved_surface(
                kind,
                surface,
                status="composite_unhandled",
                reason=(
                    "Surface contains conjunction/list punctuation; open UMLS "
                    "search is skipped because exact-match on a composite is "
                    "never a clean concept. Needs split or human review."
                ),
            )
            return None

        if self._umls is None:
            log.info(
                "TerminologyResolver: UMLS open search skipped for %s %r (no "
                "client configured; UMLS_API_KEY unset?).",
                kind,
                surface,
            )
            return None

        normalized = _normalize_surface(surface)
        try:
            # `search_type` is validated by `UMLSSearchClient.search`
            # against the `UMLSSearchType` literal.
            result = self._umls.search(
                normalized,
                sabs=sabs,
                search_type=search_type,  # type: ignore[arg-type]
            )
        except UMLSSearchError as exc:
            log.warning(
                "TerminologyResolver: UMLS search for %s %r failed (%s); "
                "soft-failing without cache write.",
                kind,
                surface,
                exc,
            )
            return None

        concept_set = result.concept_set_for(system_uri, name=surface)
        if concept_set is not None and loinc_numeric_only:
            # Keep only numeric LOINC test codes; drop Parts (LP/LA/
            # MTHU and any other non-numeric identifiers). See
            # `_LOINC_NUMERIC_CODE` docstring for why.
            numeric_codes = frozenset(
                code for code in concept_set.codes if _LOINC_NUMERIC_CODE.match(code)
            )
            if numeric_codes:
                concept_set = ConceptSet(
                    name=concept_set.name,
                    system=concept_set.system,
                    codes=numeric_codes,
                )
            else:
                concept_set = None

        if concept_set is None:
            self._cache_nonresolved_surface(
                kind,
                surface,
                status="true_miss",
                reason=(
                    f"UMLS `searchType={search_type}` against {','.join(sabs)} "
                    "returned no usable source codes for this surface"
                    + (
                        " (after filtering out LOINC component parts)."
                        if loinc_numeric_only
                        else "."
                    )
                ),
            )
            return None

        reason = (
            f"Resolved by UMLS `searchType={search_type}` against "
            f"{','.join(sabs)} ({len(concept_set.codes)} codes)."
        )
        return self._cache_resolved_surface(
            kind,
            surface,
            concept_set,
            source=f"umls_{search_type}_search",
            reason=reason,
            candidates=_umls_candidates(
                result,
                system_uri,
                reason,
                code_filter=_LOINC_NUMERIC_CODE if loinc_numeric_only else None,
            ),
        )

    def _resolve_open_medication(self, surface: str) -> ConceptSet | None:
        cached = self._cache.get_rxnorm_concepts(surface)
        if cached is not None:
            return self._cache_resolved_surface(
                "medication",
                surface,
                cached.concept_set,
                source="rxnorm_cache",
                reason="Resolved from a cached RxNorm raw-surface lookup.",
            )

        if self._rxnorm is None:
            return None

        try:
            concepts = self._cache.rxnorm_concepts_or_fetch(
                surface,
                fetch=lambda: self._rxnorm.find_drug_concepts(surface),  # type: ignore[union-attr]
            )
        except (RxNormError, httpx.HTTPError) as exc:
            if isinstance(exc, RxNormError) and _is_rxnorm_true_miss(exc):
                self._cache_nonresolved_surface(
                    "medication",
                    surface,
                    status="true_miss",
                    reason=str(exc),
                )
            log.warning(
                "TerminologyResolver: RxNorm open fetch for %r failed (%s); falling through.",
                surface,
                exc,
            )
            return None

        return self._cache_resolved_surface(
            "medication",
            surface,
            concepts.concept_set,
            source="rxnorm_open_search",
            reason="Resolved by querying RxNorm with the raw extracted medication surface.",
        )


# ---------- process-wide singleton accessor ----------


def _build_default_resolver(settings: Settings) -> TerminologyResolver:
    """Construct the singleton resolver from settings.

    `VSACClient` and `UMLSSearchClient` both require `UMLS_API_KEY`;
    if it's unset, both clients are `None` and the resolver
    soft-fails on VSAC cache misses and on open condition/lab
    surface resolution (intentional -- a fresh checkout without a
    UMLS account can still opt into `two_pass` and benefit from any
    pre-warmed cache rows). `RxNormClient` is unconditional -- the
    RxNav surface is public, no API key required."""
    cache = TerminologyCache(settings.terminology_cache_dir)

    vsac_client: VSACClient | None
    umls_client: UMLSSearchClient | None
    if settings.umls_api_key is not None:
        api_key = settings.umls_api_key.get_secret_value()
        try:
            vsac_client = VSACClient(api_key=api_key)
        except VSACError as exc:
            log.warning(
                "TerminologyResolver: VSACClient construction failed (%s); "
                "VSAC cache misses will soft-fail.",
                exc,
            )
            vsac_client = None
        try:
            umls_client = UMLSSearchClient(api_key=api_key)
        except UMLSSearchError as exc:
            log.warning(
                "TerminologyResolver: UMLSSearchClient construction failed (%s); "
                "open condition/lab search will soft-fail.",
                exc,
            )
            umls_client = None
    else:
        vsac_client = None
        umls_client = None

    rxnorm_client = RxNormClient()

    return TerminologyResolver(
        cache,
        vsac_client=vsac_client,
        rxnorm_client=rxnorm_client,
        umls_client=umls_client,
    )


@lru_cache(maxsize=1)
def get_resolver() -> TerminologyResolver:
    """Process-wide singleton. Cleared by tests via
    `get_resolver.cache_clear()` after monkey-patching settings."""
    return _build_default_resolver(get_settings())


__all__ = [
    "TerminologyResolver",
    "get_resolver",
]
