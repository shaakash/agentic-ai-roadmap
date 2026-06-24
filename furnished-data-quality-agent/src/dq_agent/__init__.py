"""Furnished Data Quality Agent.

A governed multi-agent system that detects data-quality anomalies in furnished
credit data with a deterministic rule engine, then uses LLM-backed agents to
explain issues, draft corrections and furnisher emails, and hypothesize new rules
(with sandbox-tested generated code) - all behind a human-in-the-loop gate.

The rule engine decides what is an anomaly; the LLM never flags, clears, or edits
data. See docs/ for the design. All data is synthetic.
"""

__version__ = "0.0.1"
