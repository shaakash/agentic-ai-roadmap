"""Evaluation harness: run the agent over labeled datasets and score it.

Ground truth is computed directly in SQL from the deterministic synthetic data
(seeded), so expected values are exact. Emits a scorecard and pass/fail against
the release gates in docs/07-evaluation.md. Wired to `make eval` / `delq-eval`.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EvalCase:
    question: str
    gold_intent: str
    gold_spec: dict | None = None
    expected_values: dict = field(default_factory=dict)  # label -> value
    entity_id: str = "M07"


@dataclass
class Scorecard:
    numeric_accuracy: float = 0.0
    groundedness: float = 0.0
    routing_accuracy: float = 0.0
    spec_correctness: float = 0.0
    entitlement_safety: float = 0.0
    suppression_correctness: float = 0.0
    passed_gates: bool = False
    details: dict = field(default_factory=dict)


def load_cases(path: str) -> list[EvalCase]:
    """Load a JSONL eval dataset (eval/datasets/*.jsonl)."""
    raise NotImplementedError


def ground_truth(case: EvalCase) -> dict:
    """Compute exact expected values via direct SQL on the synthetic DuckDB."""
    raise NotImplementedError


def score(cases: list[EvalCase]) -> Scorecard:
    """Run the agent on each case and score every dimension; check gates."""
    raise NotImplementedError


def main() -> None:
    """CLI entrypoint: load datasets, score, print scorecard, exit nonzero on gate fail."""
    raise NotImplementedError


if __name__ == "__main__":
    main()
