"""Matcher operating modes shared by API, eval, and reviewer UI."""

from __future__ import annotations

from typing import Literal

MatcherAssumptionMode = Literal["open_world", "closed_world_eval", "closed_world_demo"]
"""Evidence assumption used when interpreting missing patient rows.

`open_world` is the default clinical-review contract: absence of a row
means insufficient evidence, not absence of the condition. Closed-world
modes are explicit opt-ins for synthetic eval slices or hand-picked demo
cases where the source-data limitation is visible to the reviewer.
"""

LLMUseLevel = Literal["none", "retrieval_only", "bounded_adjudication", "critic"]
"""How far the matcher may go beyond deterministic structured matching."""

DEFAULT_MATCHER_ASSUMPTION_MODE: MatcherAssumptionMode = "open_world"
DEFAULT_LLM_USE_LEVEL: LLMUseLevel = "none"

__all__ = [
    "DEFAULT_LLM_USE_LEVEL",
    "DEFAULT_MATCHER_ASSUMPTION_MODE",
    "LLMUseLevel",
    "MatcherAssumptionMode",
]
