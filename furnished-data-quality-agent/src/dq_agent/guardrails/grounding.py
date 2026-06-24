"""Grounding guardrail for anomaly explanations.

An LLM explanation may only restate facts already present in the source `Anomaly`
(its fields, expected, observed, message). This catches the classic failure mode
where the model invents a plausible-but-wrong number or references a field that was
never in evidence.

The heuristic here checks that any numeric token in the explanation also appears in
the anomaly's grounded facts. A production version would add field-name and
entity-level checks; the interface is what matters for the scaffold.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from dq_agent.schemas.anomaly import Anomaly

_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


@dataclass
class GroundingResult:
    ok: bool
    ungrounded_numbers: list[str]


def _numbers(text: str) -> set[str]:
    return {m.group() for m in _NUMBER.finditer(text or "")}


def check_grounding(anomaly: Anomaly, explanation: str) -> GroundingResult:
    """Verify every number in `explanation` is traceable to the anomaly's facts."""
    grounded = _numbers(anomaly.expected) | _numbers(anomaly.observed) | _numbers(anomaly.message)
    grounded |= _numbers(" ".join(anomaly.fields_involved))
    ungrounded = sorted(_numbers(explanation) - grounded)
    return GroundingResult(ok=not ungrounded, ungrounded_numbers=ungrounded)
