"""Fail when resolved terminology surfaces regress to unmapped.

Example:
    uv run python scripts/check_terminology_regressions.py \
        --diagnostics eval/baselines/2026-05-05/open_resolver_none_diagnostics.json \
        --resolved-work-queue eval/baselines/2026-05-05/resolved_surface_watchlist.json
"""

from __future__ import annotations

import argparse

from clinical_demo.evals.diagnostics import load_diagnostics
from clinical_demo.terminology.work_queue import (
    find_resolved_surface_regressions,
    load_surface_work_queue,
    render_surface_regressions,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diagnostics", required=True, help="EvalDiagnostics JSON path.")
    parser.add_argument(
        "--resolved-work-queue",
        required=True,
        help="SurfaceWorkItem JSON list; only status=resolved rows are watched.",
    )
    parser.add_argument(
        "--min-count",
        type=int,
        default=1,
        help="Only fail for watched surfaces with at least this unmapped count.",
    )
    args = parser.parse_args()

    diagnostics = load_diagnostics(args.diagnostics)
    watchlist = load_surface_work_queue(args.resolved_work_queue)
    regressions = find_resolved_surface_regressions(
        diagnostics,
        watchlist,
        min_count=args.min_count,
    )
    print(render_surface_regressions(regressions), end="")
    return 1 if regressions else 0


if __name__ == "__main__":
    raise SystemExit(main())
