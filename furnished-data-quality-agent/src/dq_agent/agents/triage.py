"""Triage Agent: prioritize and group the deterministic anomalies.

Severity ranking is deterministic; the optional LLM step only *groups* related
anomalies into themes for the furnisher email (e.g. "date-ordering issues"). It
never changes severity or invents anomalies.
"""

from __future__ import annotations

from dq_agent.agents.state import DQState
from dq_agent.config import get_settings
from dq_agent.schemas.anomaly import Severity


def triage_node(state: DQState) -> DQState:
    """Sort anomalies by severity and set the severity-block flag.

    TODO(impl): optional LLM grouping of anomalies into themes per furnisher.
    """
    raise NotImplementedError("Triage Agent not implemented yet. See docs/05-agent-design.md")


def _sort_by_severity(anomalies):
    """Deterministic helper (no LLM): highest severity first."""
    return sorted(anomalies, key=lambda a: a.severity.rank, reverse=True)


def _is_blocked(anomalies) -> bool:
    threshold = Severity(get_settings().severity_block_threshold).rank
    return any(a.severity.rank >= threshold for a in anomalies)
