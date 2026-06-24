"""The deterministic rule engine - the source of truth for anomaly detection.

`checks.py`   - vetted, built-in check functions (pure, testable).
`rules.yaml`  - the rule catalog as data (id, category, severity, which check).
`registry.py` - loads the catalog into typed `Rule` objects.
`engine.py`   - runs active rules over a batch and emits `Anomaly` records.

No LLM is involved here. The LLM-backed agents (see `dq_agent.agents`) consume the
anomalies this engine produces; they never produce anomalies themselves.
"""
