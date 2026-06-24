"""Rule-Author (Producer) Agent: hypothesize NEW rules and generate check code.

This is the learning loop. The agent studies patterns the current catalog does NOT
cover (e.g. recurring steward feedback, clusters of look-alike records that no rule
flags) and proposes a new rule: a description plus a self-contained Python
`check(record)` function.

Critical guarantee: generated code is NEVER trusted. The output goes to:
  1. guardrails.codereview  - static safety check (no imports, no I/O, AST allowlist)
  2. sandbox.validate       - executed in a restricted sandbox against LABELED data,
                              measuring precision/recall vs the promotion thresholds
  3. human review           - a steward promotes it to status=candidate/active

Only after all three does a candidate ever run on real batches.
"""

from __future__ import annotations

from dq_agent.agents.state import DQState
from dq_agent.schemas.rule import Rule


def author_node(state: DQState) -> DQState:
    """Propose candidate rules from uncovered patterns + steward feedback.

    TODO(impl): cluster unexplained records / mine feedback -> LLM proposes a rule
    spec + generated_code -> codereview -> sandbox.validate -> attach reports.
    """
    raise NotImplementedError("Rule-Author Agent not implemented yet. See docs/05-agent-design.md")


def hypothesize_rule(context: dict) -> Rule:
    """Produce one candidate Rule with generated_code (stub)."""
    raise NotImplementedError
