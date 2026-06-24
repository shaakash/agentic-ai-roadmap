"""Human-in-the-loop review gate.

Corrective actions, furnisher emails, and candidate rules are all *drafts* until a
steward approves them. This module defines the review queue interface the pipeline
pauses on. The actual UI/persistence is out of scope for the scaffold; the contract
(what can be reviewed, the allowed transitions) is what matters.
"""

from __future__ import annotations

from dq_agent.schemas.action import CorrectiveAction, EmailStatus, FurnisherEmail, ReviewStatus
from dq_agent.schemas.rule import Rule


def submit_for_review(items: list) -> str:
    """Enqueue a set of drafts for a steward and return a review ticket id (stub)."""
    raise NotImplementedError("HITL review queue not implemented yet. See docs/07-governance.md")


def apply_decision(item, decision: ReviewStatus, steward: str):
    """Apply a steward's approve/reject to a draft (stub).

    Allowed transitions:
      CorrectiveAction: PENDING -> APPROVED | REJECTED
      FurnisherEmail:   DRAFT   -> APPROVED -> SENT (send is a separate human action)
      Rule (candidate): only promoted to ACTIVE after explicit approval
    """
    raise NotImplementedError
