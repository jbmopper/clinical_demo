"""UMLS Metathesaurus search REST client.

UMLS (https://www.nlm.nih.gov/research/umls/) sits one level above
VSAC: it indexes atoms (source-vocabulary rows) from ~200 coded
terminologies (SNOMED CT, LOINC, RxNorm, MeSH, ICD-10-CM, ...) under
CUIs and lets callers search by free text for concept or source-code
hits. The v0 VSAC client here only does `$expand` by OID, which is
useful when the trial-side registry already knows the OID to expand
but useless for an arbitrary extracted surface like "hemoglobin" or
"pregnant or breastfeeding" for which no curated OID exists.

This client is the open-resolver front door (D-73): given a surface
string and a coding system filter (`SNOMEDCT_US` for conditions,
`LNC` for labs), it returns the set of source codes whose atoms
match that surface. The resolver layer upstream decides whether the
hit cluster is high-confidence enough to emit a `resolved` decision
or should be recorded as `ambiguous` / `true_miss`.

Auth
----
Modern UMLS REST supports `?apiKey=<key>` query-parameter auth
without the older ticket-granting-ticket dance; the key is the same
UMLS UTS API key VSAC uses (`Settings.umls_api_key`). The older
`auth.lib.umls.edu` ticket flow still works but adds a round-trip
per request and buys nothing for our workload. v0 uses the query
parameter.

Rate / quota
------------
NLM's documented fair-use for UTS is ~20 req/s with no published
hard daily cap for authenticated users. Our workload is bounded by
the unique surface-form vocabulary across 49 eval cases (low
hundreds total), and every outcome -- resolved, ambiguous, true
miss -- is cached on disk by the surface cache upstream. A full
cold baseline is a one-time ~few-hundred-request warmup; repeat
runs are cache hits.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Literal

import httpx
from pydantic import BaseModel

from clinical_demo.profile import ConceptSet
from clinical_demo.settings import Settings, get_settings

DEFAULT_BASE_URL = "https://uts-ws.nlm.nih.gov/rest"

SNOMEDCT_SOURCE = "SNOMEDCT_US"
LOINC_SOURCE = "LNC"

# Canonical coding-system URI per UMLS `rootSource` value. Patient
# FHIR data (Synthea) codes Conditions in SNOMED CT and Observations
# in LOINC against these URIs; the matcher compares code lists
# against `PatientProfile.*.code`, so the URI the `ConceptSet` carries
# has to line up exactly with what the patient carries.
_SOURCE_SYSTEM_URI: dict[str, str] = {
    SNOMEDCT_SOURCE: "http://snomed.info/sct",
    LOINC_SOURCE: "http://loinc.org",
    "RXNORM": "http://www.nlm.nih.gov/research/umls/rxnorm",
}


UMLSSearchType = Literal[
    "exact",
    "words",
    "leftTruncation",
    "rightTruncation",
    "approximate",
    "normalizedString",
    "normalizedWords",
]


class UMLSSearchError(RuntimeError):
    """Any UMLS-side failure that prevented a usable search result.

    Caught by the resolver so a terminology outage or a malformed
    response degrades to `indeterminate(unmapped_concept)` rather
    than crashing a scoring run -- same soft-fail discipline as
    VSACError / RxNormError."""


class UMLSSearchHit(BaseModel):
    """One row from a UMLS search result.

    `ui` is the returned identifier (a source code when
    `returnIdType=code`, a CUI when `returnIdType=concept`). `name`
    is the atom / concept name UMLS matched against. `root_source`
    is the source-vocabulary abbreviation -- `SNOMEDCT_US` for
    SNOMED CT source concepts, `LNC` for LOINC, etc. v0 consumers
    only filter on `root_source`; `uri` is preserved for debugging
    and future provenance plumbing."""

    ui: str
    name: str
    root_source: str
    uri: str | None = None


class UMLSSearchResult(BaseModel):
    """Parsed envelope around one UMLS `/search/current` response.

    `codes_by_system` deduplicates the returned `ui` values under
    each source's canonical coding-system URI so the resolver can
    build a `ConceptSet` per system without re-walking the raw
    hits. `hits` is the full ordered list as UMLS returned it; the
    resolver uses it for candidate metadata when it decides to
    cache an `ambiguous` outcome.
    """

    query: str
    sabs: tuple[str, ...]
    search_type: UMLSSearchType
    return_id_type: str
    hits: list[UMLSSearchHit]
    codes_by_system: dict[str, frozenset[str]]

    def concept_set_for(self, system_uri: str, *, name: str | None = None) -> ConceptSet | None:
        """Assemble a `ConceptSet` for the given system URI, if any codes.

        Returns `None` when no hits landed in that system. The
        matcher's single-system-per-query contract (D-25) means this
        is the shape callers actually want: one call per system and
        a `ConceptSet` or a graceful miss.
        """
        codes = self.codes_by_system.get(system_uri)
        if not codes:
            return None
        return ConceptSet(
            name=name or self.query,
            system=system_uri,
            codes=codes,
        )


class UMLSSearchClient:
    """Thin sync wrapper over UMLS `/search/current`.

    Sync (not async) for the same reason VSACClient and RxNormClient
    are sync: v0 callers are CLI scripts, eval runners, and the
    resolver's hot path, and the surface area an async client would
    unlock is the same surface area `httpx.AsyncClient` would have
    given us. Tests inject `transport=` to return canned responses
    without hitting the network.
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout_seconds: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if api_key is None:
            settings: Settings = get_settings()
            secret = settings.umls_api_key
            if secret is None:
                raise UMLSSearchError(
                    "UMLS_API_KEY is not set; cannot call UMLS search. "
                    "Set it in .env or pass api_key= explicitly."
                )
            api_key = secret.get_secret_value()
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._transport = transport

    def search(
        self,
        term: str,
        *,
        sabs: Iterable[str],
        search_type: UMLSSearchType = "exact",
        return_id_type: str = "code",
        page_size: int = 50,
    ) -> UMLSSearchResult:
        """Run one UMLS search and return the parsed result.

        `sabs` is a non-empty iterable of UMLS source-vocabulary
        abbreviations (`"SNOMEDCT_US"`, `"LNC"`, `"RXNORM"`, ...);
        UMLS accepts a comma-separated list. `search_type=exact`
        matches the input against whole atom names (including
        synonyms). Use `"words"` for tokenized fallback searches
        when exact misses.

        `return_id_type="code"` returns one row per (source, code)
        pair whose atom name matched the query -- the shape the
        resolver wants for building a `ConceptSet`. `"concept"`
        returns one row per CUI instead; the resolver can follow
        up with a second call to expand each CUI into codes if
        needed.

        Raises `UMLSSearchError` for network, HTTP, or malformed-
        payload failures. Zero-hit responses do NOT raise -- they
        return an empty `UMLSSearchResult` so the resolver can
        distinguish "UMLS answered with no matches" (cache as a
        true miss) from "UMLS errored" (soft-fail, do not cache).
        """
        sabs_tuple = tuple(sabs)
        if not sabs_tuple:
            raise UMLSSearchError("UMLS search requires at least one source vocabulary in `sabs`.")

        params: dict[str, str] = {
            "string": term,
            "sabs": ",".join(sabs_tuple),
            "searchType": search_type,
            "returnIdType": return_id_type,
            "pageSize": str(page_size),
            "apiKey": self._api_key,
        }
        try:
            with httpx.Client(
                timeout=self._timeout,
                transport=self._transport,
            ) as client:
                response = client.get(f"{self._base_url}/search/current", params=params)
        except httpx.HTTPError as exc:
            raise UMLSSearchError(f"UMLS search request failed for {term!r}: {exc}") from exc

        if response.status_code != 200:
            raise UMLSSearchError(
                f"UMLS search returned {response.status_code} for {term!r}: {response.text[:200]}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise UMLSSearchError(f"UMLS search response for {term!r} was not JSON: {exc}") from exc

        return _parse_search_payload(
            payload,
            query=term,
            sabs=sabs_tuple,
            search_type=search_type,
            return_id_type=return_id_type,
        )


def _parse_search_payload(
    payload: dict[str, Any],
    *,
    query: str,
    sabs: tuple[str, ...],
    search_type: UMLSSearchType,
    return_id_type: str,
) -> UMLSSearchResult:
    """Parse a UMLS `/search/current` JSON body.

    UMLS encodes "no results" as a single sentinel row
    `{ui: "NONE", name: "NO RESULTS"}` rather than an empty list; we
    detect that and emit an empty result so the resolver can cache
    a clean `true_miss`.

    Raises `UMLSSearchError` when the envelope shape itself is
    wrong (missing `result` / `results`), because that signals an
    API contract change rather than an empty result.
    """
    result_obj = payload.get("result")
    if not isinstance(result_obj, dict):
        raise UMLSSearchError(
            f"UMLS search payload for {query!r} has no `result` object; "
            f"top-level keys: {sorted(payload.keys())}"
        )
    raw_results = result_obj.get("results")
    if not isinstance(raw_results, list):
        raise UMLSSearchError(
            f"UMLS search payload for {query!r} has no `results` list; "
            f"`result` keys: {sorted(result_obj.keys())}"
        )

    hits: list[UMLSSearchHit] = []
    codes_by_system: dict[str, set[str]] = {}
    for entry in raw_results:
        if not isinstance(entry, dict):
            continue
        ui = entry.get("ui")
        name = entry.get("name")
        root_source = entry.get("rootSource")
        if not isinstance(ui, str) or not isinstance(name, str):
            continue
        if ui == "NONE":
            # UMLS's "no results" sentinel. Skip so callers see an
            # empty `hits` list instead of a bogus code.
            continue
        if not isinstance(root_source, str):
            root_source = ""
        uri = entry.get("uri") if isinstance(entry.get("uri"), str) else None
        hits.append(UMLSSearchHit(ui=ui, name=name, root_source=root_source, uri=uri))
        if return_id_type == "code" and root_source:
            system_uri = _SOURCE_SYSTEM_URI.get(root_source)
            if system_uri is not None:
                codes_by_system.setdefault(system_uri, set()).add(ui)

    return UMLSSearchResult(
        query=query,
        sabs=sabs,
        search_type=search_type,
        return_id_type=return_id_type,
        hits=hits,
        codes_by_system={system: frozenset(codes) for system, codes in codes_by_system.items()},
    )


__all__ = [
    "DEFAULT_BASE_URL",
    "LOINC_SOURCE",
    "SNOMEDCT_SOURCE",
    "UMLSSearchClient",
    "UMLSSearchError",
    "UMLSSearchHit",
    "UMLSSearchResult",
    "UMLSSearchType",
]
