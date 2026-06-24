"""Synthesizer node: draft a grounded narrative from data rows + definitions.

Core constraint: the model may ONLY use numbers from the DATA TABLE passed in
the prompt. It must register every number it cites in the `number_claims`
field, linked to the row index. The grounding guard (grounding.py) verifies
this after the call.

Two synthesis modes:
    with rows    – metric/benchmark answer; rows are the primary source
    without rows – definition answer; definitions are the primary source

Temperature 0 throughout. The model's role is to narrate facts, not generate
them. It is the last LLM node before the grounding guard.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional

from pydantic import BaseModel, Field

from ..config import get_llm
from ..knowledge.retrieve import RetrievedDef
from ..semantic.metrics import MetricRow
from .state import NumberClaim


# ---------------------------------------------------------------------------
# Structured output schemas
# ---------------------------------------------------------------------------

class NumberClaimOutput(BaseModel):
    """A single number cited in the narrative, with provenance."""

    label:     str   = Field(description="Brief label, e.g. 'M07 90+ rate Jun-2023'")
    value:     float = Field(description="Raw numeric value as stored in the data row")
    row_index: int   = Field(description="0-based index of the source row in the data table", ge=0)


class SynthesisOutput(BaseModel):
    """Full structured response from the synthesizer LLM."""

    answer: str = Field(
        description=(
            "The narrative answer in 2–4 sentences. "
            "State percentages with two decimal places (e.g. '4.13%'). "
            "Every numeric claim must appear in number_claims."
        )
    )
    number_claims: list[NumberClaimOutput] = Field(
        default_factory=list,
        description=(
            "All numbers cited in the answer. "
            "Each must reference a row_index from the data table."
        )
    )
    citations: list[str] = Field(
        default_factory=list,
        description=(
            "Headings of definition sections cited (e.g. "
            "'Methodology 4.1 – Coincidence view (snapshot share)'). "
            "Only cite headings that were actually used in the answer."
        )
    )


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class ChartSpec:
    kind:   str                           # "line" | "bar"
    x:      list[str]  = field(default_factory=list)
    series: dict[str, list[float]] = field(default_factory=dict)
    title:  str = ""


@dataclass
class Synthesis:
    answer:       str
    numbers:      list[NumberClaim]
    citations:    list[str]
    chart:        ChartSpec | None = None


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def _format_rows_table(rows: list[MetricRow]) -> str:
    """Render rows as a numbered JSON-like table for the prompt."""
    if not rows:
        return "(no data rows)"

    lines = []
    for i, row in enumerate(rows):
        entry = {
            "row": i,
            "entity": row.entity_id,
            "month": row.reporting_month,
            "metric": row.metric_id,
            "value": row.value,
        }
        if row.industry_value is not None:
            entry["industry_value"] = row.industry_value
        if row.market_share is not None:
            entry["market_share"] = row.market_share
        if row.rank_best_first is not None:
            entry["rank_best_first"] = row.rank_best_first
            entry["total_members"]   = row.total_members
            entry["percentile"]      = row.percentile
        if row.index_value is not None:
            entry["index_value"] = row.index_value
        if row.suppressed:
            entry["SUPPRESSED"] = row.suppression_reason
        lines.append(json.dumps(entry))

    return "\n".join(lines)


def _format_definitions(defs: list[RetrievedDef]) -> str:
    if not defs:
        return "(no definition context provided)"
    parts = []
    for d in defs:
        parts.append(f"### {d.citation}\n{d.text}")
    return "\n\n".join(parts)


_SYSTEM_PROMPT_WITH_ROWS = """\
You are a credit risk analyst assistant at a consumer credit bureau.
You answer questions about delinquency benchmarking data.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STRICT RULES — violating any rule is an error
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Every number you state MUST come from the DATA TABLE below.
   Do NOT compute, round differently, or infer new values.
2. Register every number you cite in number_claims, with the exact row_index.
3. Present rate values as percentages with two decimal places:
   if value = 0.0413, write "4.13%"; if value = 42.7 (already %%), write "42.70%".
4. Present rank as a plain integer (e.g. "ranked 4th").
5. If a row is SUPPRESSED, state "data withheld — insufficient peer population."
6. Keep answers concise: 2–4 sentences for single metrics,
   one short paragraph for multi-month trends or comparisons.
7. Do NOT add interpretation, advice, or context beyond what the data shows.\
"""

_SYSTEM_PROMPT_DEF_ONLY = """\
You are a credit risk methodologist at a consumer credit bureau.
The user has asked a definition or methodology question.

RULES:
1. Answer using only the DEFINITIONS provided below.
2. Do not invent formulas or examples not present in the definitions.
3. Keep answers concise (2–4 sentences). Cite the definition heading.\
"""


# ---------------------------------------------------------------------------
# Public function
# ---------------------------------------------------------------------------

def synthesize(
    question:    str,
    rows:        list[MetricRow],
    definitions: list[RetrievedDef],
) -> Synthesis:
    """Draft the answer strictly from rows + definitions.

    Args:
        question:    Original user question.
        rows:        MetricRow objects from SemanticLayer.query().
        definitions: RetrievedDef objects from DefinitionRetriever.

    Returns:
        Synthesis with answer, grounded number claims, and citations.

    Raises:
        EnvironmentError: if OPENAI_API_KEY is not set.
    """
    llm = get_llm()
    structured = llm.with_structured_output(SynthesisOutput)

    if rows:
        rows_text = _format_rows_table(rows)
        defs_text = _format_definitions(definitions)
        user_msg = (
            f"DATA TABLE (indexed from 0):\n{rows_text}\n\n"
            f"DEFINITIONS (for context and citations only):\n{defs_text}\n\n"
            f"Question: {question}"
        )
        system_msg = _SYSTEM_PROMPT_WITH_ROWS
    else:
        # Definition-only mode: no rows, just retrieved definitions
        defs_text = _format_definitions(definitions)
        user_msg  = f"DEFINITIONS:\n{defs_text}\n\nQuestion: {question}"
        system_msg = _SYSTEM_PROMPT_DEF_ONLY

    output: SynthesisOutput = structured.invoke([
        {"role": "system", "content": system_msg},
        {"role": "user",   "content": user_msg},
    ])

    # Convert PlannerOutput NumberClaimOutputs → domain NumberClaim objects
    number_claims = [
        NumberClaim(
            label            = nc.label,
            value            = nc.value,
            source_row_index = nc.row_index,
        )
        for nc in output.number_claims
        if 0 <= nc.row_index < len(rows)   # drop out-of-bounds claims
    ]

    # Build a simple chart spec for multi-month metric queries
    chart = _maybe_build_chart(rows, output) if len(rows) > 1 else None

    return Synthesis(
        answer    = output.answer,
        numbers   = number_claims,
        citations = output.citations,
        chart     = chart,
    )


def _maybe_build_chart(rows: list[MetricRow], output: SynthesisOutput) -> ChartSpec | None:
    """Build a line chart spec if rows span multiple months for one entity."""
    months = [r.reporting_month for r in rows]
    if len(set(months)) <= 1:
        return None

    # All same entity/metric → line chart of values over time
    values = [r.value for r in rows]
    if any(v is None for v in values):
        return None

    entity_id = rows[0].entity_id
    metric_id  = rows[0].metric_id

    return ChartSpec(
        kind   = "line",
        x      = months,
        series = {entity_id: values},
        title  = f"{entity_id} — {metric_id}",
    )
