"""Append-only lineage log.

Every stage appends a `LineageEvent` under one correlation id. The log is JSONL
(one event per line) so it is trivially append-only and auditable. Content hashing
lets an auditor detect tampering.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path

from dq_agent.schemas.lineage import Actor, LineageEvent, Stage


def payload_hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


class LineageLog:
    """A thin append-only writer over a JSONL file."""

    def __init__(self, path: str = "lineage.jsonl"):
        self.path = Path(path)

    def record(
        self,
        correlation_id: str,
        batch_id: str,
        stage: Stage,
        actor: Actor,
        action: str,
        *,
        record_id: str | None = None,
        rule_id: str | None = None,
        detail: dict | None = None,
    ) -> LineageEvent:
        detail = detail or {}
        event = LineageEvent(
            event_id="EVT-" + uuid.uuid4().hex[:12],
            correlation_id=correlation_id,
            batch_id=batch_id,
            stage=stage,
            actor=actor,
            action=action,
            record_id=record_id,
            rule_id=rule_id,
            payload_hash=payload_hash(detail) if detail else None,
            detail=detail,
        )
        with self.path.open("a") as fh:
            fh.write(event.model_dump_json() + "\n")
        return event
