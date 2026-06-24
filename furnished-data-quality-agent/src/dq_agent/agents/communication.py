"""Communication Agent: draft the furnisher email.

Summarizes the batch's anomalies (grouped by theme) and the requested corrections
into a single professional email per furnisher. Always produces a DRAFT
(`EmailStatus.DRAFT`); `EMAIL_AUTOSEND` is false by design - a human must approve
and send.
"""

from __future__ import annotations

from dq_agent.agents.state import DQState
from dq_agent.schemas.action import FurnisherEmail


def communication_node(state: DQState) -> DQState:
    """Draft one FurnisherEmail per furnisher in the batch.

    TODO(impl): summarize triaged anomalies + approved/suggested actions into a
    grounded email body; never auto-send.
    """
    raise NotImplementedError("Communication Agent not implemented yet. See docs/05-agent-design.md")


def draft_email(batch_id: str, furnisher_id: str, anomalies, actions) -> FurnisherEmail:
    """Compose one furnisher email (stub)."""
    raise NotImplementedError
