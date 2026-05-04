"""Tests for the UMLS Metathesaurus search REST client.

Offline-only: network traffic is faked via `httpx.MockTransport`, so
CI / fresh checkouts pass without a UMLS API key. A live one-off
probe lives in `scripts/probe_umls.py` for the rare moments we want
to re-record a fixture against the real API.
"""

from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from clinical_demo.terminology.umls_search_client import (
    DEFAULT_BASE_URL,
    LOINC_SOURCE,
    SNOMEDCT_SOURCE,
    UMLSSearchClient,
    UMLSSearchError,
    UMLSSearchResult,
)


def _client_with_response(
    *,
    status: int,
    body: bytes,
    content_type: str = "application/json",
) -> tuple[UMLSSearchClient, list[httpx.Request]]:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(status, content=body, headers={"content-type": content_type})

    transport = httpx.MockTransport(handler)
    client = UMLSSearchClient(api_key="dummy-key", transport=transport)
    return client, captured


def _snomed_search_body(codes: list[tuple[str, str]]) -> bytes:
    """Shape one UMLS `/search/current` response with `returnIdType=code`."""
    return json.dumps(
        {
            "pageSize": len(codes),
            "pageNumber": 1,
            "result": {
                "classType": "searchResults",
                "results": [
                    {
                        "ui": ui,
                        "name": name,
                        "rootSource": SNOMEDCT_SOURCE,
                        "uri": f"https://uts-ws.nlm.nih.gov/rest/content/current/source/{SNOMEDCT_SOURCE}/code/{ui}",
                    }
                    for ui, name in codes
                ],
            },
        }
    ).encode()


def _loinc_search_body(codes: list[tuple[str, str]]) -> bytes:
    return json.dumps(
        {
            "pageSize": len(codes),
            "pageNumber": 1,
            "result": {
                "classType": "searchResults",
                "results": [
                    {
                        "ui": ui,
                        "name": name,
                        "rootSource": LOINC_SOURCE,
                    }
                    for ui, name in codes
                ],
            },
        }
    ).encode()


def _no_results_body() -> bytes:
    """UMLS's zero-hit sentinel row."""
    return json.dumps(
        {
            "pageSize": 25,
            "pageNumber": 1,
            "result": {
                "classType": "searchResults",
                "results": [{"ui": "NONE", "name": "NO RESULTS"}],
            },
        }
    ).encode()


# ---------- happy path ----------


def test_search_snomed_parses_hits_into_concept_set() -> None:
    body = _snomed_search_body(
        [
            ("59621000", "Essential hypertension"),
            ("38341003", "Hypertensive disorder, systemic arterial"),
        ]
    )
    client, _ = _client_with_response(status=200, body=body)

    result = client.search("hypertension", sabs=(SNOMEDCT_SOURCE,))

    assert isinstance(result, UMLSSearchResult)
    assert result.query == "hypertension"
    assert len(result.hits) == 2
    concept_set = result.concept_set_for("http://snomed.info/sct")
    assert concept_set is not None
    assert concept_set.system == "http://snomed.info/sct"
    assert concept_set.codes == frozenset({"59621000", "38341003"})


def test_search_loinc_builds_loinc_concept_set() -> None:
    body = _loinc_search_body([("718-7", "Hemoglobin [Mass/volume] in Blood")])
    client, _ = _client_with_response(status=200, body=body)

    result = client.search("hemoglobin", sabs=(LOINC_SOURCE,))

    concept_set = result.concept_set_for("http://loinc.org", name="hemoglobin")
    assert concept_set is not None
    assert concept_set.name == "hemoglobin"
    assert concept_set.codes == frozenset({"718-7"})


def test_search_sends_required_query_params_and_api_key() -> None:
    body = _snomed_search_body([("44054006", "Diabetes mellitus type 2")])
    client, captured = _client_with_response(status=200, body=body)

    client.search("type 2 diabetes", sabs=(SNOMEDCT_SOURCE,), search_type="exact")

    assert len(captured) == 1
    parsed = urlparse(str(captured[0].url))
    assert parsed.path.endswith("/search/current")
    params = parse_qs(parsed.query)
    assert params["string"] == ["type 2 diabetes"]
    assert params["sabs"] == [SNOMEDCT_SOURCE]
    assert params["searchType"] == ["exact"]
    assert params["returnIdType"] == ["code"]
    # The API key is passed as a query parameter, not a header, so
    # the endpoint can stay bearer-token-less in the httpx layer.
    assert params["apiKey"] == ["dummy-key"]


def test_search_honors_custom_base_url() -> None:
    body = _snomed_search_body([("44054006", "Diabetes mellitus type 2")])
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, content=body, headers={"content-type": "application/json"})

    client = UMLSSearchClient(
        api_key="k",
        base_url="https://example.test/api",
        transport=httpx.MockTransport(handler),
    )
    client.search("diabetes", sabs=(SNOMEDCT_SOURCE,))
    assert str(captured[0].url).startswith("https://example.test/api/search/current")


def test_default_base_url_points_to_uts_ws() -> None:
    """Pins the canonical NLM endpoint. A probe or client constructed
    without an override must hit uts-ws.nlm.nih.gov, which is the
    modern `apiKey=` flavored endpoint."""
    assert DEFAULT_BASE_URL == "https://uts-ws.nlm.nih.gov/rest"


# ---------- zero-hit semantics ----------


def test_search_returns_empty_result_on_no_results_sentinel() -> None:
    """The resolver relies on this: `NONE` is NOT an error. It's a
    cache-as-true-miss signal. The client must surface it as an
    empty `UMLSSearchResult` with no hits, not by raising."""
    client, _ = _client_with_response(status=200, body=_no_results_body())

    result = client.search("notarealclinicalterm", sabs=(SNOMEDCT_SOURCE,))

    assert result.hits == []
    assert result.codes_by_system == {}
    assert result.concept_set_for("http://snomed.info/sct") is None


def test_search_skips_rows_with_missing_fields() -> None:
    """Some UMLS result rows come back with missing / non-string
    fields (e.g. pagination sentinels); the parser skips them rather
    than crashing."""
    payload = {
        "result": {
            "results": [
                {"ui": "59621000", "name": "Essential hypertension", "rootSource": SNOMEDCT_SOURCE},
                {"ui": "missing-name"},  # dropped
                {"name": "missing-ui", "rootSource": SNOMEDCT_SOURCE},  # dropped
            ],
        }
    }
    client, _ = _client_with_response(status=200, body=json.dumps(payload).encode())

    result = client.search("hypertension", sabs=(SNOMEDCT_SOURCE,))
    assert result.codes_by_system["http://snomed.info/sct"] == frozenset({"59621000"})


# ---------- failure modes (caller must degrade, not crash) ----------


def test_search_raises_on_http_500() -> None:
    client, _ = _client_with_response(status=500, body=b"boom")
    with pytest.raises(UMLSSearchError, match="500"):
        client.search("diabetes", sabs=(SNOMEDCT_SOURCE,))


def test_search_raises_on_non_json_body() -> None:
    client, _ = _client_with_response(
        status=200, body=b"<html>oops</html>", content_type="text/html"
    )
    with pytest.raises(UMLSSearchError, match="not JSON"):
        client.search("diabetes", sabs=(SNOMEDCT_SOURCE,))


def test_search_raises_when_payload_has_no_result_object() -> None:
    client, _ = _client_with_response(status=200, body=json.dumps({"unrelated": 1}).encode())
    with pytest.raises(UMLSSearchError, match="no `result`"):
        client.search("diabetes", sabs=(SNOMEDCT_SOURCE,))


def test_search_raises_when_payload_has_no_results_list() -> None:
    payload = {"result": {"classType": "searchResults"}}
    client, _ = _client_with_response(status=200, body=json.dumps(payload).encode())
    with pytest.raises(UMLSSearchError, match="no `results`"):
        client.search("diabetes", sabs=(SNOMEDCT_SOURCE,))


def test_search_raises_on_network_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    client = UMLSSearchClient(api_key="k", transport=httpx.MockTransport(handler))
    with pytest.raises(UMLSSearchError, match="request failed"):
        client.search("diabetes", sabs=(SNOMEDCT_SOURCE,))


def test_search_raises_when_sabs_is_empty() -> None:
    """At least one source vocabulary must be specified; UMLS without
    `sabs` defaults to every source and is almost never what the
    resolver wants."""
    client = UMLSSearchClient(
        api_key="k", transport=httpx.MockTransport(lambda r: httpx.Response(200))
    )
    with pytest.raises(UMLSSearchError, match="at least one source"):
        client.search("hypertension", sabs=())
