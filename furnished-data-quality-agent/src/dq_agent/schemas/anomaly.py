"""An anomaly: one rule firing on one record.

Emitted ONLY by the deterministic rule engine. Every anomaly is fully grounded -
it names the rule, the fields, and the expected-vs-observed values - so a human (or
the Corrective Agent) never has to guess what tripped.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def rank(self) -> int:
        return {"low": 0, "medium": 1, "high": 2, "critical": 3}[self.value]


class Anomaly(BaseModel):
    """One deterministic rule firing on one record."""

    anomaly_id: str
    record_id: str
    batch_id: str
    rule_id: str
    category: str
    severity: Severity

    fields_involved: list[str]
    expected: str                          # what the rule required, in plain terms
    observed: str                          # what the record actually had
    message: str                           # short deterministic description from the rule

    # Filled later by the Corrective Agent (LLM); grounded to the fields above.
    explanation: str | None = None

    detected_at: datetime = Field(default_factory=datetime.utcnow)

    # Ground-truth labels - ONLY present in synthetic data, used by the eval harness.
    # `is_seeded` = this record was deliberately corrupted; `seeded_rule_id` = with what.
    is_seeded: bool | None = None
    seeded_rule_id: str | None = None
