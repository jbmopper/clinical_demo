from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from clinical_demo.evals.diagnostics import EvalDiagnostics

MODULE_PATH = Path(__file__).parents[2] / "scripts" / "check_compiler_diagnostics.py"
SPEC = importlib.util.spec_from_file_location("check_compiler_diagnostics", MODULE_PATH)
assert SPEC is not None
check_compiler_diagnostics = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = check_compiler_diagnostics
SPEC.loader.exec_module(check_compiler_diagnostics)


def _diagnostics(
    *,
    present: int = 1,
    missing: int = 0,
    gaps: int = 0,
    gap_kinds: dict[str, int] | None = None,
    blocking_cases: int = 0,
    blocking_findings: int = 0,
) -> EvalDiagnostics:
    return EvalDiagnostics(
        run_id="compiler-gate-test",
        n_cases=present + missing,
        n_errors=0,
        scored_cases=present + missing,
        total_criteria=1,
        total_scoring_latency_ms=1.0,
        avg_scoring_latency_ms=1.0,
        unmapped_count=0,
        unmapped_rate=0.0,
        indeterminate_count=0,
        indeterminate_rate=0.0,
        compiler_compilation_present_cases=present,
        compiler_compilation_missing_cases=missing,
        compiler_unresolved_gaps_total=gaps,
        compiler_unresolved_gaps_by_kind=gap_kinds or {},
        compiler_closed_world_blocking_cases=blocking_cases,
        compiler_closed_world_blocking_findings_total=blocking_findings,
    )


def _write(tmp_path: Path, diagnostics: EvalDiagnostics) -> Path:
    path = tmp_path / "diagnostics.json"
    path.write_text(diagnostics.model_dump_json())
    return path


def test_passing_thresholds_return_zero_and_report_ok(tmp_path: Path, capsys) -> None:
    path = _write(tmp_path, _diagnostics())

    rc = check_compiler_diagnostics.main(
        [
            "--diagnostics",
            str(path),
            "--require-compilation",
            "--max-unresolved-gaps",
            "0",
            "--max-closed-world-blocking-cases",
            "0",
            "--max-closed-world-blocking-findings",
            "0",
        ]
    )

    assert rc == 0
    out = capsys.readouterr().out
    assert "compiler diagnostics gate: OK" in out
    assert "OK require-compilation" in out


def test_require_compilation_fails_for_legacy_missing_compiler_cases(
    tmp_path: Path, capsys
) -> None:
    path = _write(tmp_path, _diagnostics(present=0, missing=2))

    rc = check_compiler_diagnostics.main(["--diagnostics", str(path), "--require-compilation"])

    assert rc == 1
    out = capsys.readouterr().out
    assert "compiler diagnostics gate: FAILED" in out
    assert "FAIL require-compilation: present=0 missing=2" in out


def test_unresolved_gap_threshold_fails_with_useful_output(tmp_path: Path, capsys) -> None:
    path = _write(
        tmp_path,
        _diagnostics(gaps=3, gap_kinds={"missing_unit": 1, "unmapped_concept": 2}),
    )

    rc = check_compiler_diagnostics.main(["--diagnostics", str(path), "--max-unresolved-gaps", "2"])

    assert rc == 1
    out = capsys.readouterr().out
    assert "FAIL unresolved-gaps: actual=3 max=2" in out
    assert "gap kinds: missing_unit=1, unmapped_concept=2" in out


def test_closed_world_blocking_thresholds_fail_with_useful_output(tmp_path: Path, capsys) -> None:
    path = _write(tmp_path, _diagnostics(blocking_cases=2, blocking_findings=5))

    rc = check_compiler_diagnostics.main(
        [
            "--diagnostics",
            str(path),
            "--max-closed-world-blocking-cases",
            "1",
            "--max-closed-world-blocking-findings",
            "4",
        ]
    )

    assert rc == 1
    out = capsys.readouterr().out
    assert "FAIL closed-world-blocking-cases: actual=2 max=1" in out
    assert "FAIL closed-world-blocking-findings: actual=5 max=4" in out


def test_gap_kind_threshold_can_fail_independently(tmp_path: Path, capsys) -> None:
    path = _write(tmp_path, _diagnostics(gaps=2, gap_kinds={"unmapped_concept": 2}))

    rc = check_compiler_diagnostics.main(
        ["--diagnostics", str(path), "--max-gap-kind", "unmapped_concept=1"]
    )

    assert rc == 1
    out = capsys.readouterr().out
    assert "FAIL gap-kind:unmapped_concept: actual=2 max=1" in out
