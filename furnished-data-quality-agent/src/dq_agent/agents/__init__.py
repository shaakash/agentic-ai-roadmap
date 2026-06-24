"""The multi-agent layer (LLM-backed) that consumes deterministic anomalies.

Roles (see docs/05-agent-design.md):
  - Triage Agent        - groups/prioritizes anomalies (deterministic scoring + optional LLM grouping)
  - Corrective Agent     - writes grounded explanations + suggested fixes
  - Communication Agent  - drafts furnisher emails
  - Rule-Author Agent    - hypothesizes NEW rules and generates check code (sandbox-tested)

None of these decide what is an anomaly - that is the deterministic rule engine.
These are stubs today (`NotImplementedError`); the graph wiring is real.
"""
