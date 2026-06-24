"""Immutable lineage: one correlation id threads a batch through every stage.

Every meaningful step (a rule firing, an LLM draft, a sandbox run, a human
decision) appends a `LineageEvent`. The trail is append-only and content-hashed so
an auditor can reconstruct exactly what happened to any record and why.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class Stage(str, Enum):
    INGEST = "ingest"
    VALIDATE = "validate"          # deterministic rule engine
    TRIAGE = "triage"
    EXPLAIN = "explain"            # Corrective Agent
    COMMUNICATE = "communicate"    # Communication Agent
    LEARN = "learn"                # Rule-Author Agent
    SANDBOX = "sandbox"            # candidate-rule validation
    REVIEW = "review"              # human-in-the-loop
    PROMOTE = "promote"            # rule registry change


class Actor(str, Enum):
    SYSTEM = "system"
    RULE_ENGINE = "rule_engine"
    TRIAGE_AGENT = "triage_agent"
    CORRECTIVE_AGENT = "corrective_agent"
    COMMUNICATION_AGENT = "communication_agent"
    RULE_AUTHOR_AGENT = "rule_author_agent"
    SANDBOX = "sandbox"
    STEWARD = "steward"            # the human


class LineageEvent(BaseModel):
    """One append-only step in the audit trail."""

    event_id: str
    correlation_id: str            # constant for the whole batch run
    batch_id: str
    stage: Stage
    actor: Actor
    action: str                    # short verb phrase, e.g. "rule_fired", "drafted_email"
    record_id: str | None = None
    rule_id: str | None = None
    payload_hash: str | None = None   # sha256 of the payload this step produced
    detail: dict = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
