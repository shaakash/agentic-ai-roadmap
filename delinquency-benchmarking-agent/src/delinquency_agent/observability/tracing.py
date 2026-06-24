"""OpenTelemetry tracing helpers + the lineage audit record.

Every /ask request produces:
  1. An OTel trace with child spans for each agent node (route, plan, query, …).
     Exported to the OTLP endpoint in OTEL_EXPORTER_OTLP_ENDPOINT, or to the
     console if that variable is empty.
  2. A LineageRecord appended to data/lineage.jsonl — a permanent, queryable
     audit trail that maps every answer back to its source SQL, spec, and
     grounding result.

Graceful degradation: if OTel packages are missing or misconfigured, tracing
silently no-ops so the API stays alive. Lineage writing always happens
regardless of OTel state.
"""

from __future__ import annotations

import json
import logging
import os
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lineage record — permanent audit entry, one per /ask call
# ---------------------------------------------------------------------------

@dataclass
class LineageRecord:
    """One audit entry per answered question.

    Persisted to data/lineage.jsonl so any answer can be reconstructed
    post-hoc: question → spec → SQL → rows → grounding result.
    """
    trace_id:    str
    timestamp:   str
    question:    str
    entity_id:   str               # claims only — no credentials
    intent:      str | None = None
    spec:        dict = field(default_factory=dict)   # QuerySpec as dict
    grounded:    bool | None = None
    citations:   list[str] = field(default_factory=list)
    row_count:   int = 0
    suppressed_count: int = 0
    duration_ms: float | None = None


def emit_lineage(record: LineageRecord, lineage_path: str | Path | None = None) -> None:
    """Append the lineage record as a JSON line to data/lineage.jsonl.

    Thread-safe for single-process deployments (file append is atomic on
    most OS/filesystems for small payloads). For multi-process, use a
    structured log sink (Datadog, CloudWatch) instead of a file.
    """
    path = Path(lineage_path) if lineage_path else _default_lineage_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        line = json.dumps(asdict(record), default=str)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception as exc:
        logger.warning("emit_lineage failed: %s", exc)


def _default_lineage_path() -> Path:
    # Resolve relative to the project root (4 levels up from this file)
    return (
        Path(__file__).parent.parent.parent.parent  # …/delinquency-benchmarking-agent
        / "data" / "lineage.jsonl"
    )


# ---------------------------------------------------------------------------
# OpenTelemetry tracer — set up once per process
# ---------------------------------------------------------------------------

_tracer = None          # the global tracer; None until init_tracing() is called
_noop_mode = False      # True when OTel could not be set up


def init_tracing(
    service_name: str  = "delinquency-benchmarking-agent",
    otlp_endpoint: str = "",
) -> None:
    """Configure the global OTel tracer. Safe to call multiple times (idempotent).

    Args:
        service_name:   Shown in traces and dashboards.
        otlp_endpoint:  OTLP gRPC endpoint (e.g. 'http://localhost:4317').
                        Empty string → ConsoleSpanExporter (local dev).
    """
    global _tracer, _noop_mode

    try:
        from opentelemetry import trace as otel_trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import (
            BatchSpanProcessor,
            ConsoleSpanExporter,
        )

        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)

        if otlp_endpoint:
            try:
                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                    OTLPSpanExporter,
                )
                exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
                provider.add_span_processor(BatchSpanProcessor(exporter))
                logger.info("OTel: exporting to OTLP at %s", otlp_endpoint)
            except ImportError:
                logger.warning(
                    "opentelemetry-exporter-otlp-proto-grpc not installed; "
                    "falling back to ConsoleSpanExporter"
                )
                provider.add_span_processor(
                    BatchSpanProcessor(ConsoleSpanExporter())
                )
        else:
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
            logger.info("OTel: ConsoleSpanExporter active (no OTLP endpoint set)")

        otel_trace.set_tracer_provider(provider)
        _tracer = otel_trace.get_tracer("delinquency_agent")
        _noop_mode = False

    except ImportError:
        logger.warning(
            "opentelemetry-sdk not installed — tracing disabled. "
            "Lineage recording is unaffected."
        )
        _noop_mode = True
    except Exception as exc:
        logger.warning("OTel init failed (%s) — tracing disabled.", exc)
        _noop_mode = True


@contextmanager
def span(name: str, **attributes: str) -> Iterator[dict]:
    """Context manager that wraps work in an OTel span.

    Always yields a dict with 'span_id'; safe to use even when OTel is
    not configured (returns a no-op dict in that case).

    Usage::

        with span("agent.plan", question_len=str(len(question))) as s:
            spec = plan(question, claims)
            # span ends here automatically
    """
    if _noop_mode or _tracer is None:
        yield {"span_id": "noop"}
        return

    with _tracer.start_as_current_span(name) as s:
        for k, v in attributes.items():
            s.set_attribute(k, v)
        ctx = s.get_span_context()
        yield {"span_id": format(ctx.span_id, "016x") if ctx else "unknown"}


# ---------------------------------------------------------------------------
# Convenience: build a LineageRecord from the AgentState after a call
# ---------------------------------------------------------------------------

def record_from_state(state: "AgentState", duration_ms: float | None = None) -> LineageRecord:  # noqa: F821
    """Construct a LineageRecord from a completed AgentState."""
    spec_dict: dict = {}
    if state.spec is not None:
        from dataclasses import asdict as _asdict
        try:
            spec_dict = _asdict(state.spec)
            # Enums → their string values
            spec_dict = json.loads(json.dumps(spec_dict, default=str))
        except Exception:
            pass

    suppressed = sum(1 for r in state.rows if getattr(r, "suppressed", False))

    return LineageRecord(
        trace_id         = state.trace_id or "",
        timestamp        = datetime.now(tz=timezone.utc).isoformat(),
        question         = state.question,
        entity_id        = state.claims.entity_id,
        intent           = state.intent.value if state.intent else None,
        spec             = spec_dict,
        grounded         = state.grounded,
        citations        = state.citations,
        row_count        = len(state.rows),
        suppressed_count = suppressed,
        duration_ms      = duration_ms,
    )
