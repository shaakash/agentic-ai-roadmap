"""Router node: classify the user's question into an Intent via LLM.

Intents:
    definition  → user wants to understand a term or formula; no data query needed.
    metric      → user wants a specific metric value for one entity.
    benchmark   → user wants a metric with comparison (market share / rank / index).
    clarify     → question is too ambiguous; return one targeted clarifying question.

The router uses `with_structured_output` (temperature 0) so the output is
always a typed object — no free-form parsing. Confidence below 0.6 triggers
"clarify" regardless of the raw intent label.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from pydantic import BaseModel, Field

from ..config import get_llm
from .state import Intent


# ---------------------------------------------------------------------------
# Structured output schema
# ---------------------------------------------------------------------------

class RouterOutput(BaseModel):
    """Schema the router LLM must emit."""

    intent: Literal["definition", "metric", "benchmark", "clarify"] = Field(
        description=(
            "Intent of the question:\n"
            "  definition  – user asks what a term/formula means\n"
            "  metric      – user wants a single metric value, no comparison\n"
            "  benchmark   – user wants a metric plus comparison to industry/peers\n"
            "  clarify     – question is ambiguous or refers to an unsupported scope"
        )
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Confidence in the assigned intent. Use clarify when below 0.6."
    )
    clarifying_question: Optional[str] = Field(
        default=None,
        description=(
            "One targeted question to resolve the ambiguity. "
            "Required when intent is 'clarify', null otherwise."
        )
    )


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are an intent classifier for a credit bureau delinquency benchmarking tool.

TOOL SCOPE — the tool can answer these question types:
  1. definition   – explaining what a metric or methodology term means.
     Examples: "What is the coincidence rate?", "How is roll rate defined?",
               "Explain the lagged view", "What does 90+ DPD mean?"

  2. metric       – returning a specific numeric metric for one entity with no
     comparison to peers or industry.
     Examples: "What is my 90+ account rate for June 2023?",
               "Show M07's roll rate in Q4 2023"

  3. benchmark    – returning a metric AND comparing it to the industry average,
     peer ranking, or a trend index.
     Examples: "How does my 90+ rate compare to industry?",
               "What is my market share of 90+ accounts?",
               "Where do I rank among peers?",
               "Show my 90+ trend re-based to January 2023"

  4. clarify      – use this when:
     • the question refers to a metric or product not in this tool's scope.
     • the time period is completely unspecified and cannot be inferred.
     • the entity ("my", "their") cannot be resolved from context.
     • the question mixes multiple incompatible dimensions.
     Set clarifying_question to ONE focused question that resolves the gap.

CONFIDENCE — if your best-guess intent has confidence below 0.6, override intent
to "clarify" and ask for the missing information.

Respond only with the structured output. Do not add explanation text.\
"""


# ---------------------------------------------------------------------------
# Public result type and function
# ---------------------------------------------------------------------------

@dataclass
class RouteResult:
    intent: Intent
    confidence: float
    clarifying_question: str | None = None


def route(question: str) -> RouteResult:
    """Classify the user's question using a schema-constrained LLM call.

    Args:
        question: Raw user question string.

    Returns:
        RouteResult with intent, confidence, and optional clarifying question.

    Raises:
        EnvironmentError: if OPENAI_API_KEY is not set.
    """
    llm = get_llm()
    structured = llm.with_structured_output(RouterOutput)

    output: RouterOutput = structured.invoke([
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user",   "content": question},
    ])

    # Downgrade low-confidence classifications to clarify
    effective_intent = output.intent
    if output.confidence < 0.6 and output.intent != "clarify":
        effective_intent = "clarify"
        if not output.clarifying_question:
            output = RouterOutput(
                intent="clarify",
                confidence=output.confidence,
                clarifying_question=(
                    "Could you please clarify what metric and time period you are "
                    "interested in?"
                ),
            )

    return RouteResult(
        intent              = Intent(effective_intent),
        confidence          = output.confidence,
        clarifying_question = output.clarifying_question,
    )
