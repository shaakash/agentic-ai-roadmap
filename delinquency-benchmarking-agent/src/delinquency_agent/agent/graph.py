"""Orchestration graph: LangGraph StateGraph wiring all agent nodes.

Flow:
                        ┌─ definition ──► retrieve ──► synthesize ──► ground ──► END
    START ──► route ───┤
                        └─ metric/benchmark ──► plan ──► query ──► retrieve ──► synthesize ──► ground ──► END
                                                    │
                                                    └─ clarify ──► END   (planner could not map question)

If route returns "clarify", the graph exits immediately with a clarifying
question and no data call.

BenchmarkingAgent wraps the compiled graph and owns the dependencies
(SemanticLayer, DefinitionRetriever, GroundingGuard). Construct once at
startup and call .ask() for each conversation turn.
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from ..guardrails.entitlements import Claims
from ..guardrails.grounding import GroundingGuard
from ..knowledge.retrieve import DefinitionRetriever
from ..semantic.metrics import MetricRow, SemanticLayer
from ..semantic.spec import Comparison, EntityRef, QuerySpec
from .planner import PlanResult, plan
from .router import route
from .state import AgentState, Intent, NumberClaim
from .synthesize import synthesize


# ---------------------------------------------------------------------------
# Shared graph state (TypedDict — LangGraph requirement)
# ---------------------------------------------------------------------------

class GraphState(TypedDict, total=False):
    # Immutable inputs
    question:       str
    entity_id:      str         # from claims
    scope:          str         # from claims
    panel_months:   list        # sorted YYYY-MM strings from the DB

    # Set by route_node
    intent:               str
    clarifying_question:  Optional[str]

    # Set by plan_node
    spec:                 Optional[QuerySpec]

    # Set by query_node
    rows:                 list   # list[MetricRow]
    query_error:          Optional[str]

    # Set by retrieve_node
    definitions:          list   # list[RetrievedDef]

    # Set by synthesize_node
    answer:               str
    number_claims:        list   # list[NumberClaim]
    citations:            list

    # Set by ground_node
    grounded:             bool
    grounding_detail:     Optional[str]


# ---------------------------------------------------------------------------
# Node functions — each returns a partial dict that updates the state
# ---------------------------------------------------------------------------

def _route_node(state: GraphState) -> dict:
    result = route(state["question"])
    return {
        "intent":              result.intent.value,
        "clarifying_question": result.clarifying_question,
    }


def _make_plan_node(panel_months: list[str]):
    """Factory that closes over the panel months list."""
    def _plan_node(state: GraphState) -> dict:
        claims = Claims(entity_id=state["entity_id"], scope=state["scope"])
        result: PlanResult = plan(state["question"], claims, panel_months)
        if result.spec is None:
            return {
                "intent":              "clarify",
                "clarifying_question": result.clarifying_question,
                "spec":                None,
            }
        return {"spec": result.spec}
    return _plan_node


def _make_query_node(semantic_layer: SemanticLayer):
    """Factory that closes over the SemanticLayer instance."""
    def _query_node(state: GraphState) -> dict:
        spec = state.get("spec")
        if spec is None:
            return {"rows": [], "query_error": "no spec produced by planner"}

        claims = Claims(entity_id=state["entity_id"], scope=state["scope"])
        try:
            result = semantic_layer.query(spec, claims)
            return {"rows": result.rows, "query_error": None}
        except Exception as exc:
            return {"rows": [], "query_error": str(exc)}
    return _query_node


def _make_retrieve_node(retriever: DefinitionRetriever):
    """Factory that closes over the DefinitionRetriever instance."""
    def _retrieve_node(state: GraphState) -> dict:
        intent = state.get("intent", "clarify")
        if intent == "definition":
            defs = retriever.for_question(state["question"], k=3)
        else:
            spec = state.get("spec")
            if spec:
                terms = [spec.metric_id, spec.metric_id.split("_")[0]]
                for comp in spec.comparison:
                    terms.append(comp.value)
                defs = retriever.for_terms(terms, k=2)
            else:
                defs = retriever.for_question(state["question"], k=2)
        return {"definitions": defs}
    return _retrieve_node


def _synthesize_node(state: GraphState) -> dict:
    rows  = state.get("rows", [])
    defs  = state.get("definitions", [])
    result = synthesize(state["question"], rows, defs)

    # If there was a query error, prepend a notice
    answer = result.answer
    if state.get("query_error"):
        answer = (
            f"⚠️  Data query error: {state['query_error']}\n\n"
            + answer
        )

    return {
        "answer":        answer,
        "number_claims": result.numbers,
        "citations":     result.citations,
    }


def _make_ground_node(guard: GroundingGuard):
    """Factory that closes over the GroundingGuard instance."""
    def _ground_node(state: GraphState) -> dict:
        rows = state.get("rows", [])
        answer = state.get("answer", "")
        result = guard.check(answer, rows)

        final_answer = answer
        if not result.grounded and result.ungrounded_numbers:
            disclaimer = (
                "\n\n---\n"
                "*Grounding notice: one or more figures in this answer could not "
                "be directly traced to a returned data row. "
                "Please verify the numbers against the source report.*"
            )
            final_answer = answer + disclaimer

        return {
            "answer":          final_answer,
            "grounded":        result.grounded,
            "grounding_detail": result.detail,
        }
    return _ground_node


# ---------------------------------------------------------------------------
# Routing functions (used as conditional edge functions)
# ---------------------------------------------------------------------------

def _after_route(state: GraphState) -> str:
    intent = state.get("intent", "clarify")
    if intent == "definition":
        return "retrieve"
    if intent in ("metric", "benchmark"):
        return "plan"
    return "__end__"   # clarify → exit immediately


def _after_plan(state: GraphState) -> str:
    if state.get("spec") is None:
        return "__end__"   # planner requested clarification
    return "query"


# ---------------------------------------------------------------------------
# BenchmarkingAgent
# ---------------------------------------------------------------------------

class BenchmarkingAgent:
    """Compiled agent graph. Construct with dependencies, then call .ask().

    Args:
        semantic:  SemanticLayer bound to a DuckDB connection.
        retriever: DefinitionRetriever connected to the Chroma index.
        grounding: GroundingGuard for numeric verification.
        panel_months: Sorted list of YYYY-MM strings available in the DB.
            Pass this so the planner knows the data window at planning time.

    Example::

        import duckdb
        from delinquency_agent.data.load import connect
        from delinquency_agent.semantic.metrics import SemanticLayer
        from delinquency_agent.knowledge.retrieve import DefinitionRetriever
        from delinquency_agent.guardrails.grounding import GroundingGuard
        from delinquency_agent.guardrails.entitlements import Claims
        from delinquency_agent.agent.graph import BenchmarkingAgent

        conn      = connect("data/benchmark.duckdb")
        semantic  = SemanticLayer(conn)
        retriever = DefinitionRetriever()
        guard     = GroundingGuard()

        # Query DB for available months
        months = [r[0] for r in conn.execute(
            "SELECT DISTINCT reporting_month FROM dim_month ORDER BY 1"
        ).fetchall()]

        agent = BenchmarkingAgent(semantic, retriever, guard, panel_months=months)

        claims = Claims(entity_id="M07", scope="member")
        state  = agent.ask("What is my 90+ account rate for December 2024?", claims)
        print(state.draft)
    """

    def __init__(
        self,
        semantic:      SemanticLayer,
        retriever:     DefinitionRetriever,
        grounding:     GroundingGuard,
        panel_months:  list[str] | None = None,
    ) -> None:
        self._semantic     = semantic
        self._retriever    = retriever
        self._grounding    = grounding
        self._panel_months = panel_months or []
        self._app: Any     = None  # compiled graph; built lazily

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def ask(self, question: str, claims: Claims) -> AgentState:
        """Run a question end-to-end and return the final AgentState.

        Args:
            question: The user's natural-language question.
            claims:   Resolved caller permissions.

        Returns:
            AgentState with the answer in `.draft` and all provenance fields
            populated (`.numbers`, `.citations`, `.grounded`).
        """
        if self._app is None:
            self._app = self._build()

        trace_id = str(uuid.uuid4())

        initial: GraphState = {
            "question":            question,
            "entity_id":           claims.entity_id,
            "scope":               claims.scope,
            "panel_months":        self._panel_months,
            "intent":              None,
            "clarifying_question": None,
            "spec":                None,
            "rows":                [],
            "query_error":         None,
            "definitions":         [],
            "answer":              "",
            "number_claims":       [],
            "citations":           [],
            "grounded":            False,
            "grounding_detail":    None,
        }

        final: GraphState = self._app.invoke(initial)

        # Convert flat GraphState → structured AgentState
        intent_str = final.get("intent") or "clarify"
        try:
            intent = Intent(intent_str)
        except ValueError:
            intent = Intent.CLARIFY

        return AgentState(
            question           = question,
            claims             = claims,
            intent             = intent,
            clarifying_question= final.get("clarifying_question"),
            spec               = final.get("spec"),
            rows               = final.get("rows", []),
            definitions        = final.get("definitions", []),
            draft              = final.get("answer") or final.get("clarifying_question"),
            numbers            = final.get("number_claims", []),
            citations          = final.get("citations", []),
            grounded           = final.get("grounded", False),
            trace_id           = trace_id,
        )

    # ------------------------------------------------------------------
    # Graph construction
    # ------------------------------------------------------------------

    def _build(self) -> Any:
        """Construct and compile the LangGraph StateGraph."""
        graph = StateGraph(GraphState)

        # ── Node registration ────────────────────────────────────────────
        graph.add_node("route",     _route_node)
        graph.add_node("plan",      _make_plan_node(self._panel_months))
        graph.add_node("query",     _make_query_node(self._semantic))
        graph.add_node("retrieve",  _make_retrieve_node(self._retriever))
        graph.add_node("synthesize",_synthesize_node)
        graph.add_node("ground",    _make_ground_node(self._grounding))

        # ── Entry point ──────────────────────────────────────────────────
        graph.set_entry_point("route")

        # ── Edges ────────────────────────────────────────────────────────
        # route → (definition→retrieve | metric/benchmark→plan | clarify→END)
        graph.add_conditional_edges(
            "route",
            _after_route,
            {
                "retrieve":  "retrieve",
                "plan":      "plan",
                "__end__":    END,
            },
        )

        # plan → (query | clarify→END)
        graph.add_conditional_edges(
            "plan",
            _after_plan,
            {
                "query":    "query",
                "__end__":   END,
            },
        )

        # Linear tail: query → retrieve → synthesize → ground → END
        graph.add_edge("query",     "retrieve")
        graph.add_edge("retrieve",  "synthesize")
        graph.add_edge("synthesize","ground")
        graph.add_edge("ground",    END)

        return graph.compile()
