"""Rules: the deterministic detection logic, as data.

A rule is either **built-in** (its `check_ref` names a vetted function in
`rules/checks.py`) or **agent-authored** (a *candidate* carrying `generated_code`
that must pass static review + sandbox validation before a human can promote it).
The engine only ever runs `active` rules.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class RuleCategory(str, Enum):
    TEMPORAL = "temporal"          # date ordering: DLP before open, closed before open, future dates
    BALANCE = "balance"            # balance progression / limit consistency
    DUPLICATE = "duplicate"        # duplicate / double-counted rows
    REFERENTIAL = "referential"    # cross-field consistency (status vs rating, etc.)
    FORMAT = "format"              # value-domain / format validity


class RuleStatus(str, Enum):
    ACTIVE = "active"              # vetted; run on every batch
    CANDIDATE = "candidate"       # agent-proposed; not yet promoted
    RETIRED = "retired"           # superseded / turned off


class Rule(BaseModel):
    """A single detection rule."""

    rule_id: str
    name: str
    category: RuleCategory
    description: str
    severity: str                  # "low" | "medium" | "high" | "critical" (see Severity)
    status: RuleStatus = RuleStatus.ACTIVE
    version: str = "1.0.0"
    author: str = "system"         # "system" | "rule-author-agent" | a steward's name

    # Exactly one of these is set:
    check_ref: str | None = None        # built-in: name of a function in rules/checks.py
    generated_code: str | None = None   # agent-authored: a self-contained check(record)->bool|None

    enabled: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class CandidateRuleReport(BaseModel):
    """The sandbox validation result for an agent-authored candidate rule.

    Produced BEFORE a human is asked to approve - if the candidate can't beat the
    promotion thresholds on labeled data, the steward never even sees it.
    """

    rule_id: str
    tested_on_records: int
    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float
    recall: float
    f1: float
    passed_thresholds: bool
    static_check_passed: bool
    notes: str = ""
