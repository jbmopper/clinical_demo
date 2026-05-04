"""Per-call LLM cost telemetry for scoring runs.

Captured per LLM invocation so cost-quality routing experiments
(PLAN 3.2 / 3.3) can attribute spend per criterion / per stage rather
than only at the run level. The extractor's per-pair token counts and
USD cost still ride on `ExtractorRunMeta` for backward compatibility;
this module covers the *additional* LLM calls that fire when scoring
escalates beyond deterministic-only — currently the bounded
patient-evidence adjudicator, with the LLM matcher and critic stages
reserved for follow-on commits so the routing dashboard can pivot on
stage without re-shaping the schema later.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

LLMCallStage = Literal[
    "extractor",
    "llm_match",
    "patient_evidence_adjudicator",
    "critic",
]
"""Closed enum of LLM-call stages a scoring run can fire.

`criterion_index` is non-null for every stage *except* `extractor`
(which is one call per pair, not per criterion). Persisted as a string
literal so the SQLite blob remains forward-compatible across version
bumps."""


class LLMCallCost(BaseModel):
    """Token / latency / USD record for one LLM invocation.

    Designed to be cheap to construct from any node that already has
    the relevant info on hand (Langfuse spans, OpenAI usage objects,
    `_estimate_cost_usd` results). All numeric fields are nullable
    because partial telemetry (e.g. usage missing on a refusal) is
    still useful.
    """

    stage: LLMCallStage
    criterion_index: int | None = None
    model: str
    prompt_version: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_input_tokens: int | None = None
    cost_usd: float | None = None
    latency_ms: float | None = None


__all__ = ["LLMCallCost", "LLMCallStage"]
