"""Corrective Agent: explain each anomaly and draft a suggested fix.

For each anomaly the LLM produces (1) a plain-English explanation grounded ONLY in
the anomaly's fields/rule and (2) a *suggested* correction. It never edits the
record - it emits a `CorrectiveAction` with `status=PENDING` for a steward.

Grounding contract: the explanation must reference the exact `fields_involved`,
`expected`, and `observed` values from the anomaly. The grounding guardrail
(guardrails/grounding.py) rejects any draft that introduces a number or field not
present in the source anomaly.
"""

from __future__ import annotations

from dq_agent.agents.state import DQState
from dq_agent.schemas.action import CorrectiveAction
from dq_agent.schemas.anomaly import Anomaly


def corrective_node(state: DQState) -> DQState:
    """Draft a CorrectiveAction per triaged anomaly.

    TODO(impl): structured-output LLM call per anomaly -> CorrectiveAction;
    run each draft through guardrails.grounding before adding to state.
    """
    raise NotImplementedError("Corrective Agent not implemented yet. See docs/05-agent-design.md")


def draft_action(anomaly: Anomaly) -> CorrectiveAction:
    """Produce one suggested correction for one anomaly (stub)."""
    raise NotImplementedError
