"""Validate an agent-authored candidate rule before a human ever sees it.

Steps:
  1. static review (guardrails.codereview)      - REAL
  2. compile + run in a restricted sandbox       - STUB (RestrictedPython)
  3. score against labeled data + thresholds     - REAL (compute_metrics)
"""

from __future__ import annotations

from dq_agent.config import get_settings
from dq_agent.guardrails.codereview import review_generated_code
from dq_agent.schemas.record import FurnishedRecord
from dq_agent.schemas.rule import CandidateRuleReport, Rule


def compute_metrics(
    predicted_record_ids: set[str],
    target_rule_id: str,
    labels: dict[str, str],
    total_records: int,
) -> CandidateRuleReport:
    """Score a candidate's predictions against the seeded labels (REAL).

    A "positive" is a record whose seeded label equals `target_rule_id`.
    """
    truth = {rid for rid, rule in labels.items() if rule == target_rule_id}
    tp = len(predicted_record_ids & truth)
    fp = len(predicted_record_ids - truth)
    fn = len(truth - predicted_record_ids)

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

    s = get_settings()
    passed = precision >= s.rule_promotion_min_precision and recall >= s.rule_promotion_min_recall

    return CandidateRuleReport(
        rule_id=target_rule_id,
        tested_on_records=total_records,
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
        precision=round(precision, 4),
        recall=round(recall, 4),
        f1=round(f1, 4),
        passed_thresholds=passed,
        static_check_passed=True,
        notes="",
    )


def run_candidate_in_sandbox(code: str, records: list[FurnishedRecord]) -> set[str]:
    """Compile `code` in a restricted sandbox and return flagged record_ids (STUB).

    TODO(impl): use RestrictedPython to compile with a safe builtins/globals set and
    a per-record timeout; collect the record_ids for which check(record) is truthy.
    """
    raise NotImplementedError("Sandbox execution not implemented yet. See docs/07-governance.md")


def validate_candidate(
    rule: Rule, records: list[FurnishedRecord], labels: dict[str, str]
) -> CandidateRuleReport:
    """Full validation of a candidate rule. Static review is enforced here."""
    if not rule.generated_code:
        raise ValueError("candidate rule has no generated_code to validate")

    verdict = review_generated_code(rule.generated_code)
    if not verdict.ok:
        return CandidateRuleReport(
            rule_id=rule.rule_id,
            tested_on_records=len(records),
            true_positives=0, false_positives=0, false_negatives=0,
            precision=0.0, recall=0.0, f1=0.0,
            passed_thresholds=False,
            static_check_passed=False,
            notes="static review failed: " + "; ".join(verdict.reasons),
        )

    predicted = run_candidate_in_sandbox(rule.generated_code, records)
    return compute_metrics(predicted, rule.rule_id, labels, len(records))
