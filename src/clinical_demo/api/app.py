"""FastAPI app: thin HTTP surface over `score_pair` / `score_pair_graph`.

The reviewer UI (Phase 2.8) and any external integration call
this. The library does the work; the API maps requests to one of
the existing scorers and serializes the existing
`ScorePairResult` envelope back. No new business logic should
land in this module — if a route grows logic, push it into the
library first and keep the route a 5-line adapter.
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from ..evals.layer_three import (
    LayerThreeCalibrationRow,
    LayerThreeHumanLabel,
    build_calibration_rows,
    build_source_context,
    load_human_labels_if_exists,
    merge_human_labels,
    save_human_labels,
    select_stratified_judge_targets,
)
from ..evals.patient_evidence import (
    PatientEvidenceCalibrationRow,
    PatientEvidenceHumanLabel,
    PatientEvidenceSourceRow,
    load_patient_evidence_labels_if_exists,
    load_patient_evidence_rows,
    merge_patient_evidence_labels,
    patient_evidence_source_rows,
    save_patient_evidence_labels,
)
from ..evals.store import list_runs, load_run, open_store
from ..matcher import (
    DEFAULT_LLM_USE_LEVEL,
    DEFAULT_MATCHER_ASSUMPTION_MODE,
    LLMUseLevel,
    MatcherAssumptionMode,
)
from ..research import (
    CriterionResearchBlurb,
    CriterionResearchRequest,
    ResearchFetchError,
    fetch_criterion_research,
)
from ..scoring import cache_path_for, load_cached_extraction, score_pair
from ..scoring.score_pair import ScorePairResult
from .loaders import (
    EXTRACTIONS_DIR,
    CuratedDataMissing,
    list_patients,
    list_trials,
    load_patient,
    load_trial,
)

log = logging.getLogger(__name__)

DEFAULT_EVAL_DB = Path("eval/runs.sqlite")
DEFAULT_LAYER3_LABELS = Path("eval/calibration/layer3_human_labels.json")
DEFAULT_PATIENT_EVIDENCE_CANDIDATES = Path("eval/calibration/patient_evidence_candidates.json")
DEFAULT_PATIENT_EVIDENCE_LABELS = Path("eval/calibration/patient_evidence_labels.json")
PATIENT_EVIDENCE_SOURCE_LIMIT = 500


# --------------------- request / response schemas


class ScoreRequest(BaseModel):
    """Score one (patient, trial) pair.

    `as_of` defaults to today server-side. `orchestrator` chooses
    between the imperative `score_pair` and the LangGraph
    `score_pair_graph`; `critic_enabled` is only meaningful with
    `graph`. `use_cached_extraction` short-circuits the LLM
    extraction call when a cache hit exists — useful for the demo
    so repeat scoring is fast and free."""

    patient_id: str = Field(..., description="Curated cohort patient id.")
    nct_id: str = Field(..., description="Curated trial NCT id.")
    as_of: date | None = Field(
        default=None,
        description="Eligibility evaluation date. Defaults to today.",
    )
    orchestrator: Literal["imperative", "graph"] = "imperative"
    critic_enabled: bool = False
    use_cached_extraction: bool = True
    matcher_assumption_mode: MatcherAssumptionMode = DEFAULT_MATCHER_ASSUMPTION_MODE
    llm_use_level: LLMUseLevel = DEFAULT_LLM_USE_LEVEL


class TrialRow(BaseModel):
    nct_id: str
    title: str


class PatientRow(BaseModel):
    patient_id: str
    score: int | None = None
    slice: str | None = None


class EvalRunRow(BaseModel):
    run_id: str
    started_at: str
    finished_at: str
    notes: str
    n_cases: int
    n_errors: int


class LayerThreeCalibrationResponse(BaseModel):
    run_id: str
    label_path: str
    rows: list[LayerThreeCalibrationRow]


class LayerThreeCalibrationSaveRequest(BaseModel):
    labels: list[LayerThreeHumanLabel]
    label_path: str | None = None


class LayerThreeCalibrationSaveResponse(BaseModel):
    label_path: str
    saved: int


class PatientEvidenceCalibrationResponse(BaseModel):
    candidate_path: str
    label_path: str
    rows: list[PatientEvidenceCalibrationRow]


class PatientEvidenceCalibrationSaveRequest(BaseModel):
    labels: list[PatientEvidenceHumanLabel]
    label_path: str | None = None


class PatientEvidenceCalibrationSaveResponse(BaseModel):
    label_path: str
    saved: int


# --------------------- app


def create_app() -> FastAPI:
    """Factory so tests can spin up isolated app instances.

    Tests use `TestClient(create_app())` rather than importing a
    module-level singleton so a misconfigured global doesn't
    bleed across test files."""
    app = FastAPI(
        title="clinical-demo API",
        version="0.1.0",
        description=(
            "Eligibility scoring for the Clinical Trial Eligibility "
            "Co-Pilot demo. Wraps `score_pair`."
        ),
    )

    # Permissive CORS for the v0 demo. The reviewer UI is served
    # from the same origin in prod, but local dev hits the API
    # from a Vite/SvelteKit dev server on a different port. Lock
    # this down before any non-demo deployment.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/patients", response_model=list[PatientRow], tags=["catalog"])
    def patients() -> list[dict]:
        try:
            return list_patients()
        except CuratedDataMissing as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc

    @app.get("/trials", response_model=list[TrialRow], tags=["catalog"])
    def trials() -> list[dict]:
        try:
            return list_trials()
        except CuratedDataMissing as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc

    @app.get("/eval/runs", response_model=list[EvalRunRow], tags=["eval"])
    def eval_runs() -> list[dict]:
        if not DEFAULT_EVAL_DB.exists():
            return []
        with open_store(DEFAULT_EVAL_DB) as conn:
            return list_runs(conn)

    @app.get(
        "/layer3/calibration",
        response_model=LayerThreeCalibrationResponse,
        tags=["eval"],
    )
    def layer3_calibration(
        run_id: str,
        limit: int = 50,
        label_path: str | None = None,
    ) -> LayerThreeCalibrationResponse:
        if limit < 1:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="limit must be positive",
            )
        if not DEFAULT_EVAL_DB.exists():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"eval store not found at {DEFAULT_EVAL_DB}",
            )
        labels_path = Path(label_path) if label_path else DEFAULT_LAYER3_LABELS
        with open_store(DEFAULT_EVAL_DB) as conn:
            try:
                run = load_run(conn, run_id)
            except KeyError as exc:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        existing = load_human_labels_if_exists(labels_path)
        targets = select_stratified_judge_targets(run, limit=limit)
        source_contexts = {}
        for target in targets:
            if target.pair_id in source_contexts:
                continue
            try:
                patient = load_patient(target.patient_id)
                trial = load_trial(target.nct_id)
            except CuratedDataMissing as exc:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=str(exc),
                ) from exc
            except FileNotFoundError as exc:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
            source_contexts[target.pair_id] = build_source_context(patient, trial)
        return LayerThreeCalibrationResponse(
            run_id=run_id,
            label_path=str(labels_path),
            rows=build_calibration_rows(
                targets,
                existing_labels=existing,
                source_contexts=source_contexts,
            ),
        )

    @app.post(
        "/layer3/calibration",
        response_model=LayerThreeCalibrationSaveResponse,
        tags=["eval"],
    )
    def save_layer3_calibration(
        req: LayerThreeCalibrationSaveRequest,
    ) -> LayerThreeCalibrationSaveResponse:
        labels_path = Path(req.label_path) if req.label_path else DEFAULT_LAYER3_LABELS
        existing = load_human_labels_if_exists(labels_path)
        merged = merge_human_labels(existing, req.labels)
        save_human_labels(labels_path, merged)
        return LayerThreeCalibrationSaveResponse(
            label_path=str(labels_path),
            saved=len(merged),
        )

    @app.get(
        "/patient-evidence/calibration",
        response_model=PatientEvidenceCalibrationResponse,
        tags=["eval"],
    )
    def patient_evidence_calibration(
        candidate_path: str | None = None,
        label_path: str | None = None,
        refresh_source_rows: bool = False,
    ) -> PatientEvidenceCalibrationResponse:
        candidates_path = (
            Path(candidate_path) if candidate_path else DEFAULT_PATIENT_EVIDENCE_CANDIDATES
        )
        labels_path = Path(label_path) if label_path else DEFAULT_PATIENT_EVIDENCE_LABELS
        if not candidates_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"patient evidence candidate packet not found at {candidates_path}",
            )

        rows = load_patient_evidence_rows(candidates_path)
        labels = {
            (label.pair_id, label.criterion_index): label
            for label in load_patient_evidence_labels_if_exists(labels_path)
        }
        source_row_cache: dict[tuple[str, str], list[PatientEvidenceSourceRow]] = {}
        rows_with_labels = [
            row.model_copy(
                update={
                    "existing_label": labels.get(
                        (row.pair_id, row.criterion_index),
                    ),
                    "source_rows": (
                        _patient_evidence_source_rows(row, source_row_cache)
                        if refresh_source_rows
                        else row.source_rows
                    ),
                }
            )
            for row in rows
        ]
        return PatientEvidenceCalibrationResponse(
            candidate_path=str(candidates_path),
            label_path=str(labels_path),
            rows=rows_with_labels,
        )

    @app.post(
        "/patient-evidence/calibration",
        response_model=PatientEvidenceCalibrationSaveResponse,
        tags=["eval"],
    )
    def save_patient_evidence_calibration(
        req: PatientEvidenceCalibrationSaveRequest,
    ) -> PatientEvidenceCalibrationSaveResponse:
        labels_path = Path(req.label_path) if req.label_path else DEFAULT_PATIENT_EVIDENCE_LABELS
        existing = load_patient_evidence_labels_if_exists(labels_path)
        merged = merge_patient_evidence_labels(existing, req.labels)
        save_patient_evidence_labels(labels_path, merged)
        return PatientEvidenceCalibrationSaveResponse(
            label_path=str(labels_path),
            saved=len(merged),
        )

    @app.post(
        "/research/criterion",
        response_model=CriterionResearchBlurb,
        tags=["research"],
    )
    def criterion_research(req: CriterionResearchRequest) -> CriterionResearchBlurb:
        try:
            return fetch_criterion_research(req)
        except ResearchFetchError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=str(exc),
            ) from exc

    @app.post("/score", response_model=ScorePairResult, tags=["scoring"])
    def score(req: ScoreRequest) -> ScorePairResult:
        try:
            patient = load_patient(req.patient_id)
        except CuratedDataMissing as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
            ) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

        try:
            trial = load_trial(req.nct_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

        extraction = None
        if req.use_cached_extraction:
            cache_file = cache_path_for(req.nct_id, EXTRACTIONS_DIR)
            if cache_file.exists():
                extraction = load_cached_extraction(cache_file)

        as_of = req.as_of or date.today()
        try:
            if req.orchestrator == "imperative":
                return score_pair(
                    patient,
                    trial,
                    as_of,
                    extraction=extraction,
                    matcher_assumption_mode=req.matcher_assumption_mode,
                    llm_use_level=req.llm_use_level,
                )
            from ..graph import score_pair_graph

            return score_pair_graph(
                patient,
                trial,
                as_of,
                extraction=extraction,
                critic_enabled=req.critic_enabled,
                matcher_assumption_mode=req.matcher_assumption_mode,
                llm_use_level=req.llm_use_level,
            )
        except Exception as exc:
            log.exception("scoring failed for %s x %s", req.patient_id, req.nct_id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"scoring failed: {type(exc).__name__}: {exc}",
            ) from exc

    return app


def _patient_evidence_source_rows(
    row: PatientEvidenceCalibrationRow,
    cache: dict[tuple[str, str], list[PatientEvidenceSourceRow]],
) -> list[PatientEvidenceSourceRow]:
    """Return full parsed source rows for patient-evidence review when available."""

    key = (row.patient_id, row.nct_id)
    if key in cache:
        return cache[key]
    try:
        context = build_source_context(
            load_patient(row.patient_id),
            load_trial(row.nct_id),
            max_conditions=PATIENT_EVIDENCE_SOURCE_LIMIT,
            max_observations=PATIENT_EVIDENCE_SOURCE_LIMIT,
            max_medications=PATIENT_EVIDENCE_SOURCE_LIMIT,
        )
    except (CuratedDataMissing, FileNotFoundError) as exc:
        log.warning(
            "falling back to persisted patient-evidence source rows for %s/%s: %s",
            row.patient_id,
            row.nct_id,
            exc,
        )
        cache[key] = row.source_rows
        return row.source_rows
    source_rows = patient_evidence_source_rows(context)
    cache[key] = source_rows
    return source_rows


__all__ = [
    "CriterionResearchBlurb",
    "CriterionResearchRequest",
    "EvalRunRow",
    "LayerThreeCalibrationResponse",
    "LayerThreeCalibrationSaveRequest",
    "LayerThreeCalibrationSaveResponse",
    "ScoreRequest",
    "create_app",
]
