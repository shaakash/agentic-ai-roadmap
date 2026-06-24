"""Guardrails: the controls that make agent output safe to trust.

  grounding.py   - every anomaly explanation must cite only the source fields/values
  codereview.py  - static safety check on agent-generated rule code (AST allowlist)
  hitl.py        - human-in-the-loop review queue for actions, emails, and rules
"""
