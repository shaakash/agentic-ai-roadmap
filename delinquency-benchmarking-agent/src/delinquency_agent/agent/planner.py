"""Planner node: map a user question to a typed QuerySpec via LLM tool-calling.

The planner emits ONLY a QuerySpec — never SQL, never a number, never a
narrative. It is the only node that receives the metric catalog in its system
prompt, so it "knows" what metrics exist. Everything else in the agent is
catalog-agnostic at runtime.

Entity resolution rules (enforced by the prompt):
    "my" / "our" / "we"         → entity = "self"  (resolved to claims.entity_id)
    "industry" / "market"       → entity = "INDUSTRY"
    A specific member ID (M07)  → entity = "self" if it equals claims.entity_id,
                                    else clarify (callers cannot access peer rows).

On an unmappable question (missing time period, unknown metric, out-of-scope
entity), the planner returns PlanResult with clarifying_question set.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

from pydantic import BaseModel, Field

from ..config import get_llm
from ..guardrails.entitlements import Claims
from ..semantic.catalog import list_metrics
from ..semantic.spec import Comparison, EntityRef, QuerySpec


# ---------------------------------------------------------------------------
# Structured output schema
# ---------------------------------------------------------------------------

class PlannerOutput(BaseModel):
    """Schema the planner LLM must emit for metric/benchmark questions."""

    metric_id: str = Field(
        description="Exact metric_id from the catalog. Must be one of the listed IDs."
    )
    entity: str = Field(
        description=(
            "'self' when the question is about the caller's own entity, "
            "'INDUSTRY' for industry-wide figures."
        )
    )
    product: str = Field(
        default="credit_card",
        description="Product code. Currently only 'credit_card' is supported."
    )
    bucket: Optional[str] = Field(
        default=None,
        description=(
            "DPD bucket override if specified in the question "
            "(current, x_day, b30, b60, b90, b120, b150, b180_plus, newly_writeoff). "
            "Null to use the metric's default bucket."
        )
    )
    at_or_worse: bool = Field(
        default=True,
        description=(
            "True for 'bucket or worse' (e.g. '90+'), "
            "False for exactly that bucket."
        )
    )
    lag_months: Optional[int] = Field(
        default=None,
        description="Lag period in months for lagged metrics. Null to use catalog default."
    )
    months: list[str] = Field(
        description=(
            "List of YYYY-MM strings identifying the reporting months. "
            "'June 2023' → ['2023-06'], "
            "'Q2 2023' → ['2023-04','2023-05','2023-06'], "
            "'last 6 months' → 6 months ending at the panel end month, "
            "'full year 2023' → all 12 months of 2023 within the panel."
        )
    )
    comparison: list[str] = Field(
        default_factory=list,
        description=(
            "Comparison views to compute alongside the base metric. "
            "Values: market_share, ranking, index. "
            "Use 'market_share' for 'compare to industry', "
            "'ranking' for 'where do I rank', "
            "'index' for 'trend re-based to a month'."
        )
    )
    index_base_month: Optional[str] = Field(
        default=None,
        description=(
            "Required when comparison includes 'index'. "
            "YYYY-MM of the month to set as 100."
        )
    )
    clarify: bool = Field(
        default=False,
        description=(
            "Set to True if the question cannot be mapped to a valid QuerySpec "
            "(missing time period, ambiguous metric, out-of-scope entity)."
        )
    )
    clarifying_question: Optional[str] = Field(
        default=None,
        description="One targeted question to resolve the gap. Required when clarify=True."
    )


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def _build_system_prompt(claims: Claims, panel_months: list[str]) -> str:
    catalog_lines = "\n".join(
        f"  {m.metric_id:35s} → {m.label}  [formula={m.formula.value}]"
        for m in list_metrics()
    )

    panel_start = panel_months[0]  if panel_months else "2023-01"
    panel_end   = panel_months[-1] if panel_months else "2024-12"

    return f"""\
You are a query planner for a credit bureau delinquency benchmarking tool.
Your only job is to translate a user question into a structured QuerySpec.
You must NEVER produce SQL, numbers, or a narrative. Only fill in the schema.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AVAILABLE METRICS  (use the exact metric_id)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{catalog_lines}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CALLER CONTEXT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Caller entity_id : {claims.entity_id}
• Caller scope     : {claims.scope}
• "my" / "our" / "we" / "us"  → entity = "self"
• "industry" / "market"        → entity = "INDUSTRY"
• If the question names a specific member ID that equals {claims.entity_id} → "self"
• If the question names any other member ID → set clarify=True (no peer row access)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DATA PANEL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Available months : {panel_start} through {panel_end}
• Product          : credit_card  (only supported product)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DPD BUCKET CODES  (for the 'bucket' field)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
current, x_day, b30, b60, b90, b120, b150, b180_plus, newly_writeoff
Default for most metrics is b90 (90+ DPD). For roll-rate metrics the
from_bucket / to_bucket are fixed by the metric — do not set bucket.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
COMPARISON TYPES  (for the 'comparison' field)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
market_share  → my value as % of industry total
ranking       → my rank among all members
index         → my value re-based to 100 at a chosen base month

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MONTH RESOLUTION EXAMPLES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"June 2023"          → ["2023-06"]
"Q2 2023"            → ["2023-04","2023-05","2023-06"]
"last 6 months"      → last 6 months ending at {panel_end}
"full year 2023"     → ["2023-01",...,"2023-12"] (only those in the panel)
"last 12 months"     → 12 months ending at {panel_end}
"2023"               → all months of 2023 that fall within {panel_start}–{panel_end}

When in doubt about the time period, set clarify=True.\
"""


# ---------------------------------------------------------------------------
# Public result type and function
# ---------------------------------------------------------------------------

@dataclass
class PlanResult:
    spec: QuerySpec | None
    clarifying_question: str | None = None


def plan(
    question: str,
    claims: Claims,
    panel_months: list[str] | None = None,
) -> PlanResult:
    """Produce a QuerySpec for a metric/benchmark question.

    Args:
        question:     User's original question.
        claims:       Resolved caller permissions (entity_id, scope).
        panel_months: Sorted list of available YYYY-MM strings from the DB.
                      Defaults to a 24-month panel ending at 2024-12 if not provided.

    Returns:
        PlanResult with spec set (or None + clarifying_question on ambiguity).

    Raises:
        EnvironmentError: if OPENAI_API_KEY is not set.
    """
    months_list = panel_months or _default_panel_months()
    system_prompt = _build_system_prompt(claims, months_list)

    llm = get_llm()
    structured = llm.with_structured_output(PlannerOutput)

    output: PlannerOutput = structured.invoke([
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": question},
    ])

    if output.clarify:
        return PlanResult(
            spec=None,
            clarifying_question=output.clarifying_question or (
                "Could you clarify which metric, time period, or entity you are asking about?"
            ),
        )

    # Validate months are within panel
    valid_months = [m for m in output.months if m in months_list]
    if not valid_months:
        return PlanResult(
            spec=None,
            clarifying_question=(
                f"The requested time period falls outside the available data panel "
                f"({months_list[0]} – {months_list[-1]}). "
                "Which period would you like to query?"
            ),
        )

    # Map entity string → EntityRef (the semantic layer handles 'self' resolution)
    entity_ref = (
        EntityRef.INDUSTRY if output.entity.upper() in ("INDUSTRY", "MARKET")
        else EntityRef.SELF
    )

    # Map comparison strings → Comparison enum
    comparison = []
    for c in output.comparison:
        try:
            comparison.append(Comparison(c))
        except ValueError:
            pass  # planner produced an invalid comparison; skip it

    spec = QuerySpec(
        metric_id        = output.metric_id,
        entity           = entity_ref,
        product          = output.product,
        bucket           = output.bucket,
        at_or_worse      = output.at_or_worse,
        lag_months       = output.lag_months,
        months           = valid_months,
        comparison       = comparison,
        index_base_month = output.index_base_month,
    )

    return PlanResult(spec=spec)


def _default_panel_months() -> list[str]:
    """Fallback panel if the graph cannot query the DB at startup."""
    import datetime
    months = []
    start = datetime.date(2023, 1, 1)
    for i in range(24):
        m = (start.month + i - 1) % 12 + 1
        y = start.year + (start.month + i - 1) // 12
        months.append(f"{y:04d}-{m:02d}")
    return months
