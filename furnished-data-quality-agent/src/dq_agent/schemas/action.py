"""Outputs the agents *draft* for a human: corrective actions and furnisher emails.

Nothing here is applied or sent automatically. A `CorrectiveAction` is a *suggested*
fix for one anomaly; a `FurnisherEmail` is a *draft* note to the furnisher. Both
carry a review status and stay inert until a data steward approves them.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ReviewStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class EmailStatus(str, Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    SENT = "sent"               # only ever set after an explicit human send action


class CorrectiveAction(BaseModel):
    """A suggested remediation for one anomaly (drafted by the Corrective Agent)."""

    action_id: str
    anomaly_id: str
    record_id: str
    suggested_fix: str                       # plain-English description of the fix
    field_changes: dict[str, str] | None = None  # suggested field -> new value (never auto-applied)
    rationale: str                            # grounded in the anomaly's fields/rule
    confidence: float | None = Field(default=None, ge=0, le=1)

    status: ReviewStatus = ReviewStatus.PENDING
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class FurnisherEmail(BaseModel):
    """A draft email to a furnisher summarizing issues + requested fixes."""

    email_id: str
    batch_id: str
    furnisher_id: str
    subject: str
    body: str
    anomaly_ids: list[str]

    status: EmailStatus = EmailStatus.DRAFT
    reviewed_by: str | None = None
    sent_at: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
