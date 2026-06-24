"""Sandboxed validation of agent-generated rule code.

Pipeline for a candidate rule:
  generated_code -> guardrails.codereview (static) -> compile in restricted sandbox
  -> run against LABELED data -> measure precision/recall -> CandidateRuleReport.

The static review (guardrails/codereview.py) and the metric computation
(this package's `compute_metrics`) are real; the restricted-execution step is a stub
to be implemented on RestrictedPython.
"""
