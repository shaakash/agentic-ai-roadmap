"""Shared agent state passed between graph nodes. Mirrors docs/05-agent-design.md."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from ..guardrails.entitlements import Claims
from ..semantic.metrics import MetricRow
from ..semantic.spec import QuerySpec


class Intent(str, Enum):
    DEFINITION = "definition"
    METRIC = "metric"
    BENCHMARK = "benchmark"
    CLARIFY = "clarify"  # router/planner needs one clarification


@dataclass
class NumberClaim:
    """A number asserted in the narrative, linked to its source row for grounding."""
    label: str
    value: float
    source_row_index: int | None = None


@dataclass
class AgentState:
    question: str
    claims: Claims
    intent: Intent | None = None
    clarifying_question: str | None = None
    spec: QuerySpec | None = None
    rows: list[MetricRow] = field(default_factory=list)
    definitions: list = field(default_factory=list)   # RetrievedDef
    draft: str | None = None
    numbers: list[NumberClaim] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)
    grounded: bool = False
    trace_id: str | None = None
