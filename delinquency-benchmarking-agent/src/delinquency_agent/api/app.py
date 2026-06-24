"""FastAPI application: authenticate caller → resolve claims → run agent → shape response.

Start with:
    uvicorn delinquency_agent.api.app:app --reload

Or via Makefile:
    make run

Startup sequence (lifespan):
    1. Connect to DuckDB (create + generate synthetic data if DB is empty).
    2. Ensure the Chroma definitions index exists (build if missing).
    3. Pull panel months from the DB for the planner.
    4. Wire SemanticLayer, DefinitionRetriever, GroundingGuard, BenchmarkingAgent.
    5. Init OTel tracing.

The API is the ONLY layer that handles caller identity.
Everything downstream receives only a resolved Claims object — never credentials.
"""

from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any

import duckdb
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..agent.graph import BenchmarkingAgent
from ..config import get_settings
from ..guardrails.entitlements import Claims
from ..guardrails.grounding import GroundingGuard
from ..knowledge.retrieve import DefinitionRetriever
from ..observability.tracing import (
    LineageRecord,
    emit_lineage,
    init_tracing,
    record_from_state,
    span,
)
from ..semantic.metrics import SemanticLayer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class AskRequest(BaseModel):
    """Body of POST /ask."""

    question: str = Field(
        min_length=3, max_length=2000,
        description="The analyst's natural-language question.",
        examples=["What is my 90+ account rate for June 2024?"],
    )
    entity_id: str | None = Field(
        default=None,
        description=(
            "Caller's member ID (e.g. 'M07'). "
            "In production this comes from the auth header X-Entity-Id. "
            "Pass it here for local development."
        ),
    )
    scope: str = Field(
        default="member",
        pattern="^(member|industry_only)$",
        description="Entitlement scope: 'member' sees own rows + industry; "
                    "'industry_only' sees only aggregates.",
    )


class NumberItem(BaseModel):
    label:     str
    value:     float
    row_index: int | None = None


class AskResponse(BaseModel):
    """Response body for POST /ask."""

    answer:              str
    grounded:            bool
    numbers:             list[NumberItem]
    citations:           list[str]
    intent:              str
    trace_id:            str
    clarifying_question: str | None = None
    suppressed_count:    int = 0
    chart:               dict | None = None


class HealthResponse(BaseModel):
    """Response body for GET /health."""

    status:        str   # "ok" | "degraded"
    duckdb_rows:   int
    chroma_docs:   int
    agent_ready:   bool
    api_key_set:   bool
    version:       str = "0.0.1"


# ---------------------------------------------------------------------------
# Startup helpers
# ---------------------------------------------------------------------------

def _ensure_duckdb(settings: Any) -> tuple[duckdb.DuckDBPyConnection, int]:
    """Open DuckDB; generate synthetic data if the file is empty or missing.

    Returns (connection, fact_row_count).
    """
    db_path = settings.duckdb_path
    os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)

    conn = duckdb.connect(db_path)

    try:
        count = conn.execute("SELECT COUNT(*) FROM fact_delinquency").fetchone()[0]
        if count > 0:
            logger.info("DuckDB: %d fact rows found at %s", count, db_path)
            return conn, count
    except Exception:
        pass

    # Empty or schema missing — generate synthetic data
    logger.info("DuckDB empty or missing schema — generating synthetic data …")
    from ..data.generate import GenConfig, generate_all
    from ..data.load import create_schema, load_all

    cfg = GenConfig(
        seed       = settings.gen_seed,
        start_month= settings.gen_start_month,
        num_months = settings.gen_num_months,
        num_members= settings.gen_num_members,
    )
    create_schema(conn)
    tables = generate_all(cfg)
    load_all(conn, tables)
    count = conn.execute("SELECT COUNT(*) FROM fact_delinquency").fetchone()[0]
    logger.info("DuckDB: generated %d fact rows", count)
    return conn, count


def _ensure_chroma(settings: Any) -> int:
    """Build the Chroma vector index if it doesn't exist. Returns doc count."""
    import chromadb

    chroma_dir = settings.chroma_path
    try:
        client = chromadb.PersistentClient(path=chroma_dir)
        col = client.get_collection("definitions")
        count = col.count()
        if count > 0:
            logger.info("Chroma: %d documents found at %s", count, chroma_dir)
            return count
    except Exception:
        pass

    # Index missing — build it
    logger.info("Chroma index not found — building from corpus …")
    from ..knowledge.corpus import build_index, load_definition_docs

    chunks = load_definition_docs(settings.corpus_path)
    build_index(chunks, chroma_dir)
    logger.info("Chroma: indexed %d chunks", len(chunks))
    return len(chunks)


def _get_panel_months(conn: duckdb.DuckDBPyConnection) -> list[str]:
    """Return sorted YYYY-MM strings from dim_month."""
    rows = conn.execute(
        "SELECT DISTINCT strftime(reporting_month, '%Y-%m') "
        "FROM dim_month ORDER BY 1"
    ).fetchall()
    return [r[0] for r in rows]


# ---------------------------------------------------------------------------
# Lifespan: startup and shutdown
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(application: FastAPI):
    """Build all components at startup; tear down cleanly at shutdown."""
    settings = get_settings()

    logger.info("=== Delinquency Benchmarking Agent starting ===")

    # 1. Tracing
    init_tracing(
        service_name   = settings.otel_service_name,
        otlp_endpoint  = settings.otel_exporter_otlp_endpoint,
    )

    # 2. Data layer
    conn, duckdb_rows = _ensure_duckdb(settings)
    application.state.conn        = conn
    application.state.duckdb_rows = duckdb_rows

    # 3. Knowledge layer
    chroma_docs = _ensure_chroma(settings)
    application.state.chroma_docs = chroma_docs

    # 4. Panel months (for the planner)
    panel_months = _get_panel_months(conn)
    logger.info("Panel: %s → %s (%d months)", panel_months[0], panel_months[-1], len(panel_months))

    # 5. Wire agent components
    semantic  = SemanticLayer(conn, min_cell_members=settings.min_cell_members)
    retriever = DefinitionRetriever(settings.chroma_path)
    guard     = GroundingGuard(rel_tolerance=settings.grounding_rel_tolerance)
    agent     = BenchmarkingAgent(semantic, retriever, guard, panel_months=panel_months)

    application.state.agent       = agent
    application.state.agent_ready = True
    application.state.settings    = settings

    logger.info("=== Agent ready. Waiting for requests. ===")

    yield  # ← app runs here

    # Shutdown
    logger.info("Shutting down — closing DuckDB connection.")
    conn.close()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title       = "Delinquency Benchmarking Agent",
    description = (
        "Governed conversational analytics over a synthetic credit-bureau "
        "delinquency benchmarking panel. "
        "Every number in every response traces back to a database row."
    ),
    version     = "0.0.1",
    lifespan    = lifespan,
)

# CORS — permissive for local dev; lock down in production
app.add_middleware(
    CORSMiddleware,
    allow_origins     = ["*"],
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------

@app.exception_handler(PermissionError)
async def permission_handler(request: Request, exc: PermissionError) -> JSONResponse:
    return JSONResponse(
        status_code = 403,
        content     = {"error": "entitlement_denied", "detail": str(exc)},
    )


@app.exception_handler(EnvironmentError)
async def env_handler(request: Request, exc: EnvironmentError) -> JSONResponse:
    return JSONResponse(
        status_code = 503,
        content     = {
            "error":  "llm_not_configured",
            "detail": str(exc),
            "hint":   "Set OPENAI_API_KEY in your .env file or environment.",
        },
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse, tags=["ops"])
def health(request: Request) -> HealthResponse:
    """Liveness + readiness probe.

    Returns component health: DuckDB row count, Chroma document count,
    agent compilation status, and whether the LLM API key is set.
    """
    state = request.app.state
    return HealthResponse(
        status      = "ok" if getattr(state, "agent_ready", False) else "degraded",
        duckdb_rows = getattr(state, "duckdb_rows", 0),
        chroma_docs = getattr(state, "chroma_docs", 0),
        agent_ready = getattr(state, "agent_ready", False),
        api_key_set = bool(os.environ.get("OPENAI_API_KEY")),
    )


@app.post("/ask", response_model=AskResponse, tags=["agent"])
def ask(
    body:         AskRequest,
    request:      Request,
    x_entity_id:  str | None = Header(None, description="Member ID from auth gateway"),
) -> AskResponse:
    """Ask the agent a natural-language question about delinquency benchmarking data.

    Identity resolution order (first non-null wins):
      1. `X-Entity-Id` HTTP header  (production: set by auth gateway from JWT)
      2. `entity_id` in request body (local dev convenience)
      3. Falls back to `DEFAULT_ENTITLEMENT` scope (industry_only)

    Every response includes:
      - `answer`: the narrative
      - `grounded`: whether every stated percentage was verified against a data row
      - `numbers`: provenance receipts linking each number to its source row
      - `citations`: definition sections used
      - `trace_id`: for log correlation and lineage lookup
    """
    agent:    BenchmarkingAgent = request.app.state.agent

    # ── Resolve caller identity ────────────────────────────────────────────
    resolved_entity_id = x_entity_id or body.entity_id
    if not resolved_entity_id:
        # No identity supplied: restrict to industry-only view
        claims = Claims(entity_id="ANONYMOUS", scope="industry_only")
    else:
        claims = Claims(entity_id=resolved_entity_id, scope=body.scope)

    # ── Run the agent ──────────────────────────────────────────────────────
    t0 = time.perf_counter()

    with span("api.ask", entity_id=claims.entity_id, question_len=str(len(body.question))):
        agent_state = agent.ask(body.question, claims)

    duration_ms = (time.perf_counter() - t0) * 1000

    # ── Emit lineage ───────────────────────────────────────────────────────
    try:
        rec = record_from_state(agent_state, duration_ms=duration_ms)
        emit_lineage(rec)
    except Exception as exc:
        logger.warning("lineage emit failed: %s", exc)

    # ── Build response ─────────────────────────────────────────────────────
    numbers = [
        NumberItem(
            label     = n.label,
            value     = n.value,
            row_index = n.source_row_index,
        )
        for n in agent_state.numbers
    ]

    suppressed_count = sum(
        1 for r in agent_state.rows if getattr(r, "suppressed", False)
    )

    # Build chart dict if the synthesizer produced one
    chart: dict | None = None
    # (The graph returns synthesize.ChartSpec; we carry it via AgentState.draft
    # for now — chart rendering is left to the frontend.)

    return AskResponse(
        answer              = agent_state.draft or "",
        grounded            = agent_state.grounded,
        numbers             = numbers,
        citations           = agent_state.citations,
        intent              = agent_state.intent.value if agent_state.intent else "clarify",
        trace_id            = agent_state.trace_id or "",
        clarifying_question = agent_state.clarifying_question,
        suppressed_count    = suppressed_count,
        chart               = chart,
    )


# ---------------------------------------------------------------------------
# Programmatic helper (kept for test harness + eval scripts)
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    """Return the module-level FastAPI app (for programmatic use in tests)."""
    return app
