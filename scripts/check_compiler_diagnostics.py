"""Fail when compiler-readiness diagnostics regress beyond CI thresholds.

Example:
    uv run python scripts/check_compiler_diagnostics.py \
        --diagnostics eval/baselines/2026-05-05/open_resolver_closed_world_eval_diagnostics.json \
        --require-compilation \
        --max-unresolved-gaps 0 \
        --max-closed-world-blocking-cases 0 \
        --max-closed-world-blocking-findings 0
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass

from clinical_demo.evals.diagnostics import EvalDiagnostics, load_diagnostics


@dataclass(frozen=True)
class Finding:
    label: str
    ok: bool
    detail: str


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diagnostics", required=True, help="EvalDiagnostics JSON path.")
    parser.add_argument(
        "--require-compilation",
        action="store_true",
        help="Fail if no cases include compiler output or any scored case is missing it.",
    )
    parser.add_argument(
        "--max-unresolved-gaps",
        type=int,
        default=None,
        help="Fail when compiler_unresolved_gaps_total exceeds this value.",
    )
    parser.add_argument(
        "--max-closed-world-blocking-cases",
        type=int,
        default=None,
        help="Fail when compiler_closed_world_blocking_cases exceeds this value.",
    )
    parser.add_argument(
        "--max-closed-world-blocking-findings",
        type=int,
        default=None,
        help="Fail when compiler_closed_world_blocking_findings_total exceeds this value.",
    )
    parser.add_argument(
        "--max-gap-kind",
        action="append",
        default=[],
        metavar="KIND=N",
        help="Optional per-gap-kind maximum; may be repeated.",
    )
    args = parser.parse_args(argv)

    diagnostics = load_diagnostics(args.diagnostics)
    try:
        gap_kind_limits = _parse_gap_kind_limits(args.max_gap_kind)
    except argparse.ArgumentTypeError as exc:
        parser.error(str(exc))
    findings = evaluate_diagnostics(
        diagnostics,
        require_compilation=args.require_compilation,
        max_unresolved_gaps=args.max_unresolved_gaps,
        max_closed_world_blocking_cases=args.max_closed_world_blocking_cases,
        max_closed_world_blocking_findings=args.max_closed_world_blocking_findings,
        max_gap_kinds=gap_kind_limits,
    )
    print(render_report(diagnostics, findings), end="")
    return 0 if all(finding.ok for finding in findings) else 1


def evaluate_diagnostics(
    diagnostics: EvalDiagnostics,
    *,
    require_compilation: bool = False,
    max_unresolved_gaps: int | None = None,
    max_closed_world_blocking_cases: int | None = None,
    max_closed_world_blocking_findings: int | None = None,
    max_gap_kinds: dict[str, int] | None = None,
) -> list[Finding]:
    findings: list[Finding] = []
    if require_compilation:
        present = diagnostics.compiler_compilation_present_cases
        missing = diagnostics.compiler_compilation_missing_cases
        ok = present > 0 and missing == 0
        findings.append(
            Finding(
                label="require-compilation",
                ok=ok,
                detail=f"present={present} missing={missing}; expected present>0 and missing=0",
            )
        )
    _append_max_finding(
        findings,
        label="unresolved-gaps",
        actual=diagnostics.compiler_unresolved_gaps_total,
        maximum=max_unresolved_gaps,
    )
    _append_max_finding(
        findings,
        label="closed-world-blocking-cases",
        actual=diagnostics.compiler_closed_world_blocking_cases,
        maximum=max_closed_world_blocking_cases,
    )
    _append_max_finding(
        findings,
        label="closed-world-blocking-findings",
        actual=diagnostics.compiler_closed_world_blocking_findings_total,
        maximum=max_closed_world_blocking_findings,
    )
    for kind, maximum in sorted((max_gap_kinds or {}).items()):
        actual = diagnostics.compiler_unresolved_gaps_by_kind.get(kind, 0)
        _append_max_finding(
            findings,
            label=f"gap-kind:{kind}",
            actual=actual,
            maximum=maximum,
        )
    return findings


def render_report(diagnostics: EvalDiagnostics, findings: Sequence[Finding]) -> str:
    ok = all(finding.ok for finding in findings)
    lines = [
        f"compiler diagnostics gate: {'OK' if ok else 'FAILED'}",
        f"run: {diagnostics.run_id}",
        (
            "summary: "
            f"compilation present={diagnostics.compiler_compilation_present_cases} "
            f"missing={diagnostics.compiler_compilation_missing_cases}; "
            f"unresolved_gaps={diagnostics.compiler_unresolved_gaps_total}; "
            "closed_world "
            f"blocking_cases={diagnostics.compiler_closed_world_blocking_cases} "
            f"blocking_findings={diagnostics.compiler_closed_world_blocking_findings_total}"
        ),
    ]
    if diagnostics.compiler_unresolved_gaps_by_kind:
        gap_counts = ", ".join(
            f"{kind}={count}"
            for kind, count in sorted(diagnostics.compiler_unresolved_gaps_by_kind.items())
        )
        lines.append(f"gap kinds: {gap_counts}")
    if findings:
        lines.append("checks:")
        lines.extend(
            f"  {'OK' if finding.ok else 'FAIL'} {finding.label}: {finding.detail}"
            for finding in findings
        )
    else:
        lines.append("checks: none configured")
    lines.append("")
    return "\n".join(lines)


def _append_max_finding(
    findings: list[Finding],
    *,
    label: str,
    actual: int,
    maximum: int | None,
) -> None:
    if maximum is None:
        return
    findings.append(
        Finding(
            label=label,
            ok=actual <= maximum,
            detail=f"actual={actual} max={maximum}",
        )
    )


def _parse_gap_kind_limits(raw_limits: Sequence[str]) -> dict[str, int]:
    limits: dict[str, int] = {}
    for raw_limit in raw_limits:
        kind, separator, raw_count = raw_limit.partition("=")
        if not kind or separator != "=" or not raw_count:
            raise argparse.ArgumentTypeError("--max-gap-kind must use KIND=N")
        try:
            count = int(raw_count)
        except ValueError as exc:
            raise argparse.ArgumentTypeError("--max-gap-kind count must be an integer") from exc
        limits[kind] = count
    return limits


if __name__ == "__main__":
    raise SystemExit(main())
