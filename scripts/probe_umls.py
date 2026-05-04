"""One-off probe of the UMLS `/search/current` endpoint.

Use this to sanity-check live UMLS availability without running the
full eval, and to sanity-check a surface's exact-match hit list
before wiring a curated alias for it.

    uv run python scripts/probe_umls.py --term "hemoglobin"
    uv run python scripts/probe_umls.py --term "hypertension" --sabs SNOMEDCT_US
    uv run python scripts/probe_umls.py --term "platelet count" --sabs LNC

Requires `UMLS_API_KEY` in `.env` or the environment; the UMLS
search API is auth-gated, unlike RxNav.
"""

from __future__ import annotations

import argparse
import sys

from clinical_demo.terminology import (
    LOINC_SOURCE,
    SNOMEDCT_SOURCE,
    UMLSSearchClient,
    UMLSSearchError,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--term", required=True, help="Surface form to search for.")
    parser.add_argument(
        "--sabs",
        action="append",
        default=None,
        help=(
            "UMLS source vocabulary abbreviation(s). Pass multiple "
            "times: --sabs SNOMEDCT_US --sabs LNC. Defaults to "
            f"{SNOMEDCT_SOURCE}."
        ),
    )
    parser.add_argument(
        "--search-type",
        default="exact",
        choices=(
            "exact",
            "words",
            "leftTruncation",
            "rightTruncation",
            "approximate",
            "normalizedString",
            "normalizedWords",
        ),
    )
    parser.add_argument("--page-size", type=int, default=25)
    args = parser.parse_args()

    sabs = tuple(args.sabs) if args.sabs else (SNOMEDCT_SOURCE,)

    try:
        client = UMLSSearchClient()
        result = client.search(
            args.term,
            sabs=sabs,
            search_type=args.search_type,
            page_size=args.page_size,
        )
    except UMLSSearchError as exc:
        print(f"UMLS error: {exc}", file=sys.stderr)
        return 1

    print(f"Term:        {result.query}")
    print(f"Sabs:        {','.join(result.sabs)}")
    print(f"SearchType:  {result.search_type}")
    print(f"ReturnIdTy:  {result.return_id_type}")
    print(f"Hits:        {len(result.hits)}")
    for system, codes in sorted(result.codes_by_system.items()):
        label = {
            "http://snomed.info/sct": f"SNOMED ({SNOMEDCT_SOURCE})",
            "http://loinc.org": f"LOINC ({LOINC_SOURCE})",
            "http://www.nlm.nih.gov/research/umls/rxnorm": "RxNorm",
        }.get(system, system)
        print(f"  {label}: {len(codes)} codes")
    for hit in result.hits[: min(10, len(result.hits))]:
        print(f"  [{hit.root_source}] {hit.ui}  {hit.name}")
    if len(result.hits) > 10:
        print(f"  ... {len(result.hits) - 10} more")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
