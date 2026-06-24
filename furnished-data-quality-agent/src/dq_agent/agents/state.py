"""Shared state passed between graph nodes."""

from __future__ import annotations

from typing import TypedDict

from dq_agent.schemas.action import CorrectiveAction, FurnisherEmail
from dq_agent.schemas.anomaly import Anomaly
from dq_agent.schemas.record import FurnishedRecord
from dq_agent.schemas.rule import CandidateRuleReport, Rule


class DQState(TypedDict, total=False):
    """The object that flows through the LangGraph pipeline for one batch."""

    # Inputs / context
    batch_id: str
    correlation_id: str
    records: list[FurnishedRecord]
    labels: dict[str, str]

    # Deterministic stage output
    anomalies: list[Anomaly]

    # Triage
    triaged: list[Anomaly]            # prioritized / grouped
    severity_blocked: bool            # any anomaly at/above the block threshold

    # Agent drafts (all pending human review)
    actions: list[CorrectiveAction]
    emails: list[FurnisherEmail]

    # Learning loop
    candidate_rules: list[Rule]
    candidate_reports: list[CandidateRuleReport]

    # HITL
    awaiting_review: bool
    review_notes: str
