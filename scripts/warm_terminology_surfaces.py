"""Classify and warm terminology cache rows from eval diagnostics.

Example:
    uv run python scripts/warm_terminology_surfaces.py \
        --diagnostics eval/baselines/2026-05-04/patient_evidence_none_diagnostics.json
"""

from __future__ import annotations

import argparse
import os

from clinical_demo.evals.diagnostics import load_diagnostics
from clinical_demo.settings import ResolverExecutionPolicy
from clinical_demo.terminology.work_queue import (
    build_surface_work_queue,
    render_surface_work_queue,
    surface_work_queue_to_json,
    write_surface_work_queue,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diagnostics", required=True, help="EvalDiagnostics JSON path.")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--write", help="Optional JSON output path.")
    parser.add_argument(
        "--resolver-execution-policy",
        choices=("live_allowed", "cached_only", "disabled"),
        default="live_allowed",
        help="Warmers default to live_allowed; use cached_only to inspect existing reviewed/cache state.",
    )
    args = parser.parse_args()
    _apply_resolver_execution_policy(args.resolver_execution_policy)

    diagnostics = load_diagnostics(args.diagnostics)
    items = build_surface_work_queue(diagnostics, limit=args.limit)
    if args.write:
        write_surface_work_queue(args.write, items)
    if args.format == "json":
        print(surface_work_queue_to_json(items))
    else:
        print(render_surface_work_queue(items), end="")
    return 0


def _apply_resolver_execution_policy(policy: ResolverExecutionPolicy) -> None:
    os.environ["RESOLVER_EXECUTION_POLICY"] = policy
    from clinical_demo.settings import get_settings
    from clinical_demo.terminology.resolver import get_resolver, get_reviewed_mapping_registry

    get_settings.cache_clear()
    get_resolver.cache_clear()
    get_reviewed_mapping_registry.cache_clear()


if __name__ == "__main__":
    raise SystemExit(main())
