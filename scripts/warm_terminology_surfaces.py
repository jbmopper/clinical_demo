"""Classify and warm terminology cache rows from eval diagnostics.

Example:
    uv run python scripts/warm_terminology_surfaces.py \
        --diagnostics eval/baselines/2026-05-04/patient_evidence_none_diagnostics.json
"""

from __future__ import annotations

import argparse

from clinical_demo.evals.diagnostics import load_diagnostics
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
    args = parser.parse_args()

    diagnostics = load_diagnostics(args.diagnostics)
    items = build_surface_work_queue(diagnostics, limit=args.limit)
    if args.write:
        write_surface_work_queue(args.write, items)
    if args.format == "json":
        print(surface_work_queue_to_json(items))
    else:
        print(render_surface_work_queue(items), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
