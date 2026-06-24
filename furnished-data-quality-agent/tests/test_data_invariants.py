"""The synthetic generator must produce detectable, labeled anomalies."""

from __future__ import annotations

import random

from dq_agent.data.generate import generate_batch
from dq_agent.rules.engine import run_batch


def test_generated_anomalies_are_detected():
    rng = random.Random(7)
    _, records, labels = generate_batch("BATCH-TEST", "FURN-1", n_records=400, anomaly_rate=0.1, rng=rng)

    assert len(records) == 400
    assert len(labels) > 0

    anomalies = run_batch(records, labels=labels)
    flagged_records = {a.record_id for a in anomalies}

    # Every seeded record should be flagged by at least one rule (recall == 1.0).
    missed = set(labels) - flagged_records
    assert not missed, f"seeded but undetected: {sorted(missed)[:5]}"


def test_clean_records_are_mostly_quiet():
    rng = random.Random(11)
    _, records, labels = generate_batch("BATCH-TEST2", "FURN-2", n_records=400, anomaly_rate=0.0, rng=rng)
    anomalies = run_batch(records, labels=labels)
    # With no seeded anomalies, the engine should be silent (no false positives).
    assert anomalies == []
