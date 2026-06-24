"""The deterministic rule engine.

Runs the active rule catalog over a batch and emits `Anomaly` records. This is the
*only* component allowed to decide that something is an anomaly. It is pure,
deterministic, and fully grounded - no LLM, no network.

CLI:
    python -m dq_agent.rules.engine --batch BATCH-0001
"""

from __future__ import annotations

import argparse
import hashlib
from collections import Counter

from dq_agent.rules import checks
from dq_agent.rules.registry import active_rules
from dq_agent.schemas.anomaly import Anomaly, Severity
from dq_agent.schemas.record import FurnishedRecord
from dq_agent.schemas.rule import Rule


def _anomaly_id(batch_id: str, rule_id: str, record_id: str) -> str:
    raw = f"{batch_id}:{rule_id}:{record_id}".encode()
    return "ANOM-" + hashlib.sha1(raw).hexdigest()[:12]


def _to_anomaly(
    rule: Rule,
    record: FurnishedRecord,
    result: checks.CheckResult,
    labels: dict[str, str] | None,
) -> Anomaly:
    seeded_rule_id = (labels or {}).get(record.record_id)
    return Anomaly(
        anomaly_id=_anomaly_id(record.batch_id, rule.rule_id, record.record_id),
        record_id=record.record_id,
        batch_id=record.batch_id,
        rule_id=rule.rule_id,
        category=rule.category.value,
        severity=Severity(rule.severity),
        fields_involved=result.fields_involved,
        expected=result.expected,
        observed=result.observed,
        message=result.message,
        is_seeded=None if labels is None else seeded_rule_id is not None,
        seeded_rule_id=seeded_rule_id,
    )


def run_batch(
    records: list[FurnishedRecord],
    rules: list[Rule] | None = None,
    labels: dict[str, str] | None = None,
) -> list[Anomaly]:
    """Run all active rules over `records` and return the anomalies found.

    `labels` (record_id -> seeded_rule_id) is optional ground truth used only to
    annotate anomalies for the eval harness; it never influences detection.
    """
    rules = rules if rules is not None else active_rules()
    anomalies: list[Anomaly] = []

    record_rules = [r for r in rules if r.check_ref in checks.RECORD_CHECKS]
    batch_rules = [r for r in rules if r.check_ref in checks.BATCH_CHECKS]

    # Record-level checks.
    for record in records:
        for rule in record_rules:
            fn = checks.RECORD_CHECKS[rule.check_ref]  # type: ignore[index]
            result = fn(record)
            if result is not None:
                anomalies.append(_to_anomaly(rule, record, result, labels))

    # Batch-level checks.
    by_id = {r.record_id: r for r in records}
    for rule in batch_rules:
        fn = checks.BATCH_CHECKS[rule.check_ref]  # type: ignore[index]
        flagged = fn(records)
        for record_id, result in flagged.items():
            anomalies.append(_to_anomaly(rule, by_id[record_id], result, labels))

    return anomalies


def summarize(anomalies: list[Anomaly]) -> dict:
    """A compact, printable summary of a run."""
    by_rule = Counter(a.rule_id for a in anomalies)
    by_sev = Counter(a.severity.value for a in anomalies)
    return {
        "total_anomalies": len(anomalies),
        "by_rule": dict(by_rule),
        "by_severity": dict(by_sev),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the deterministic rule engine over a batch.")
    parser.add_argument("--batch", default="BATCH-0001", help="Batch id (see data/batches/).")
    parser.add_argument("--limit", type=int, default=15, help="Max anomalies to print.")
    args = parser.parse_args()

    # Local import so the engine module has no hard dependency on the data loader.
    from dq_agent.data.load import load_batch

    batch, records, labels = load_batch(args.batch)
    anomalies = run_batch(records, labels=labels)
    summary = summarize(anomalies)

    print(f"\nBatch {batch.batch_id} (furnisher {batch.furnisher_id}) - {batch.record_count} records")
    print("=" * 70)
    print(f"Anomalies found: {summary['total_anomalies']}")
    print(f"  by severity: {summary['by_severity']}")
    print(f"  by rule:     {summary['by_rule']}")
    print("-" * 70)
    for a in anomalies[: args.limit]:
        print(f"[{a.severity.value.upper():8}] {a.rule_id} {a.record_id}: {a.message}")
        print(f"           expected: {a.expected}")
        print(f"           observed: {a.observed}")
    if len(anomalies) > args.limit:
        print(f"... and {len(anomalies) - args.limit} more")
    print()


if __name__ == "__main__":
    main()
