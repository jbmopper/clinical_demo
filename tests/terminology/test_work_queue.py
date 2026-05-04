"""Tests for terminology surface work-queue/cache warmer."""

from __future__ import annotations

from pathlib import Path

from clinical_demo.evals.diagnostics import EvalDiagnostics, SurfaceCount
from clinical_demo.terminology import TerminologyCache, TerminologyResolver
from clinical_demo.terminology.work_queue import build_surface_work_queue, render_surface_work_queue


def _diagnostics(*surfaces: SurfaceCount) -> EvalDiagnostics:
    return EvalDiagnostics(
        run_id="run-1",
        n_cases=1,
        n_errors=0,
        scored_cases=1,
        total_criteria=sum(item.count for item in surfaces),
        total_scoring_latency_ms=1.0,
        avg_scoring_latency_ms=1.0,
        unmapped_count=sum(item.count for item in surfaces),
        unmapped_rate=1.0,
        indeterminate_count=sum(item.count for item in surfaces),
        indeterminate_rate=1.0,
        top_unmapped_surfaces=list(surfaces),
    )


def test_work_queue_resolves_open_alias_and_writes_cache(tmp_path: Path) -> None:
    cache = TerminologyCache(tmp_path)
    resolver = TerminologyResolver(cache, vsac_client=None, rxnorm_client=None)
    diagnostics = _diagnostics(
        SurfaceCount(kind="measurement_threshold", surface="hemoglobin", count=10)
    )

    items = build_surface_work_queue(diagnostics, cache=cache, resolver=resolver)

    assert items[0].status == "resolved"
    assert items[0].cache_status == "written"
    assert items[0].concept_set is not None
    assert items[0].concept_set.codes == frozenset({"718-7"})
    assert cache.get_surface_resolution("lab", "hemoglobin") is not None


def test_work_queue_reuses_ambiguous_cache_row(tmp_path: Path) -> None:
    cache = TerminologyCache(tmp_path)
    resolver = TerminologyResolver(cache, vsac_client=None, rxnorm_client=None)
    diagnostics = _diagnostics(
        SurfaceCount(kind="measurement_threshold", surface="blood pressure", count=5)
    )

    first = build_surface_work_queue(diagnostics, cache=cache, resolver=resolver)
    second = build_surface_work_queue(diagnostics, cache=cache, resolver=resolver)

    assert first[0].status == "ambiguous"
    assert first[0].cache_status == "written"
    assert second[0].status == "ambiguous"
    assert second[0].cache_status == "hit"
    assert {candidate.name for candidate in second[0].candidates} == {
        "Systolic blood pressure",
        "Diastolic blood pressure",
    }


def test_work_queue_classifies_unresolved_composite_and_writes_cache(tmp_path: Path) -> None:
    cache = TerminologyCache(tmp_path)
    resolver = TerminologyResolver(cache, vsac_client=None, rxnorm_client=None)
    diagnostics = _diagnostics(
        SurfaceCount(
            kind="condition_absent",
            surface="pregnant or breastfeeding females",
            count=7,
        )
    )

    items = build_surface_work_queue(diagnostics, cache=cache, resolver=resolver)

    assert items[0].status == "composite_unhandled"
    assert items[0].cache_status == "written"
    cached = cache.get_surface_resolution("condition", "pregnant or breastfeeding females")
    assert cached is not None
    assert cached.status == "composite_unhandled"


def test_work_queue_classifies_temporal_windows_as_review_work(tmp_path: Path) -> None:
    cache = TerminologyCache(tmp_path)
    resolver = TerminologyResolver(cache, vsac_client=None, rxnorm_client=None)
    diagnostics = _diagnostics(
        SurfaceCount(kind="temporal_window", surface="stable background therapy for PAH", count=7)
    )

    items = build_surface_work_queue(diagnostics, cache=cache, resolver=resolver)

    assert items[0].status == "composite_unhandled"
    assert "Temporal-window event" in items[0].reason


def test_work_queue_classifies_known_data_model_gaps(tmp_path: Path) -> None:
    cache = TerminologyCache(tmp_path)
    resolver = TerminologyResolver(cache, vsac_client=None, rxnorm_client=None)
    diagnostics = _diagnostics(
        SurfaceCount(
            kind="measurement_threshold", surface="pulmonary vascular resistance (PVR)", count=7
        ),
        SurfaceCount(kind="condition_absent", surface="history of full pneumonectomy", count=7),
        SurfaceCount(kind="measurement_threshold", surface="ecog performance status", count=4),
    )

    items = build_surface_work_queue(diagnostics, cache=cache, resolver=resolver)

    assert [item.status for item in items] == ["out_of_scope", "out_of_scope", "out_of_scope"]
    assert all(item.cache_status == "written" for item in items)


def test_work_queue_classifies_life_expectancy_as_extractor_bug(tmp_path: Path) -> None:
    cache = TerminologyCache(tmp_path)
    resolver = TerminologyResolver(cache, vsac_client=None, rxnorm_client=None)
    diagnostics = _diagnostics(
        SurfaceCount(kind="measurement_threshold", surface="life expectancy", count=4)
    )

    items = build_surface_work_queue(diagnostics, cache=cache, resolver=resolver)

    assert items[0].status == "extractor_bug"
    assert "not a structured measurement" in items[0].reason


def test_render_work_queue_keeps_high_frequency_surface_visible(tmp_path: Path) -> None:
    cache = TerminologyCache(tmp_path)
    resolver = TerminologyResolver(cache, vsac_client=None, rxnorm_client=None)
    diagnostics = _diagnostics(
        SurfaceCount(kind="measurement_threshold", surface="platelet count", count=9)
    )

    out = render_surface_work_queue(
        build_surface_work_queue(diagnostics, cache=cache, resolver=resolver)
    )

    assert "platelet count" in out
    assert "resolved" in out
