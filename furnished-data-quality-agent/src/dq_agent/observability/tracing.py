"""OpenTelemetry tracing setup (stub).

A single tracer spans the whole batch run; each stage/agent is a child span tagged
with the correlation id, so a trace and the lineage log tell the same story.
"""

from __future__ import annotations


def init_tracing(service_name: str | None = None) -> None:
    """Configure the global tracer provider + OTLP exporter (stub)."""
    raise NotImplementedError("Tracing setup not implemented yet. See docs/07-governance.md")
