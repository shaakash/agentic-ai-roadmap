"""Evaluation scorecard for the deterministic rule engine (REAL).

Loads every generated batch, runs the engine, and scores detections against the
seeded labels:

  - per-rule and overall precision / recall / F1
  - grounding completeness (every anomaly names fields + expected + observed)

The LLM-stage scorers (explanation faithfulness, draft quality) are stubs to be
added once the agents are implemented.

CLI:
    python -m dq_agent.eval.harness
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from dq_agent.config import get_settings
from dq_agent.data.load import load_batch
from dq_agent.rules.engine import run_batch


def _prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / (tp + fn) if (tp + fn) else 0.0
    f = (2 * p * r / (p + r)) if (p + r) else 0.0
    return p, r, f


def score_detection() -> dict:
    """Score the engine across all generated batches against seeded labels."""
    s = get_settings()
    batch_files = sorted(Path(s.batches_path).glob("BATCH-*.json"))
    if not batch_files:
        raise FileNotFoundError("No batches found. Run `make generate` first.")

    # Per-rule counts.
    tp = defaultdict(int)
    fp = defaultdict(int)
    fn = defaultdict(int)
    grounded = 0
    total_anoms = 0

    for bf in batch_files:
        batch_id = bf.stem
        _, records, labels = load_batch(batch_id)
        anomalies = run_batch(records, labels=labels)

        flagged_by_rule = defaultdict(set)
        for a in anomalies:
            flagged_by_rule[a.rule_id].add(a.record_id)
            total_anoms += 1
            if a.fields_involved and a.expected and a.observed:
                grounded += 1

        truth_by_rule = defaultdict(set)
        for rid, rule_id in labels.items():
            truth_by_rule[rule_id].add(rid)

        for rule_id in set(flagged_by_rule) | set(truth_by_rule):
            pred = flagged_by_rule[rule_id]
            truth = truth_by_rule[rule_id]
            tp[rule_id] += len(pred & truth)
            fp[rule_id] += len(pred - truth)
            fn[rule_id] += len(truth - pred)

    per_rule = {}
    TP = FP = FN = 0
    for rule_id in sorted(set(tp) | set(fp) | set(fn)):
        p, r, f = _prf(tp[rule_id], fp[rule_id], fn[rule_id])
        per_rule[rule_id] = {
            "tp": tp[rule_id], "fp": fp[rule_id], "fn": fn[rule_id],
            "precision": round(p, 4), "recall": round(r, 4), "f1": round(f, 4),
        }
        TP += tp[rule_id]; FP += fp[rule_id]; FN += fn[rule_id]

    op, orr, of = _prf(TP, FP, FN)
    return {
        "batches": len(batch_files),
        "overall": {"precision": round(op, 4), "recall": round(orr, 4), "f1": round(of, 4),
                    "tp": TP, "fp": FP, "fn": FN},
        "grounding_completeness": round(grounded / total_anoms, 4) if total_anoms else 1.0,
        "per_rule": per_rule,
    }


def main() -> None:
    report = score_detection()
    print("\nRule-engine evaluation scorecard")
    print("=" * 60)
    print(f"batches scored: {report['batches']}")
    o = report["overall"]
    print(f"overall: precision={o['precision']} recall={o['recall']} f1={o['f1']} "
          f"(tp={o['tp']} fp={o['fp']} fn={o['fn']})")
    print(f"grounding completeness: {report['grounding_completeness']}")
    print("-" * 60)
    print(f"{'rule':>6}  {'prec':>6}  {'recall':>6}  {'f1':>6}  {'tp':>4} {'fp':>4} {'fn':>4}")
    for rule_id, m in report["per_rule"].items():
        print(f"{rule_id:>6}  {m['precision']:>6}  {m['recall']:>6}  {m['f1']:>6}  "
              f"{m['tp']:>4} {m['fp']:>4} {m['fn']:>4}")
    print()


if __name__ == "__main__":
    main()
