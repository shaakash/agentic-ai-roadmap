"""Semantic layer: the single, deterministic source of all numbers.

The LLM never computes a metric or writes SQL. It emits a typed QuerySpec
(see spec.py); this package validates it, builds governed SQL, applies
entitlements + suppression, and returns typed rows. See docs/05-agent-design.md.
"""
