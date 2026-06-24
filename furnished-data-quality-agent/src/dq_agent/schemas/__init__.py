"""Shared, typed contracts for the whole system (Pydantic v2).

These are the single source of truth for every record that crosses a boundary:
the furnished data itself, the anomalies the rule engine emits, the rules
themselves, the corrective actions/emails the agents draft, and the immutable
lineage trail.
"""

from .action import CorrectiveAction, EmailStatus, FurnisherEmail, ReviewStatus
from .anomaly import Anomaly, Severity
from .lineage import LineageEvent
from .record import Batch, FurnishedRecord, PortfolioType
from .rule import CandidateRuleReport, Rule, RuleCategory, RuleStatus

__all__ = [
    "Anomaly",
    "Severity",
    "Batch",
    "FurnishedRecord",
    "PortfolioType",
    "Rule",
    "RuleCategory",
    "RuleStatus",
    "CandidateRuleReport",
    "CorrectiveAction",
    "FurnisherEmail",
    "EmailStatus",
    "ReviewStatus",
    "LineageEvent",
]
