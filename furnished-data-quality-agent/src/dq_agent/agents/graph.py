"""The multi-agent orchestration graph (LangGraph).

Wiring (see docs/04-pipeline-flow.md and docs/05-agent-design.md):

    ingest -> validate -> triage -> corrective -> communication -> author -> review

`validate` is the deterministic rule engine and is fully implemented. The remaining
nodes are LLM-backed agents (stubs today). `main()` runs the real deterministic
stage and reports which agent stages remain to be implemented, without crashing.

CLI:
    python -m dq_agent.agents.graph --batch BATCH-0001
"""

from __future__ import annotations

import argparse
import uuid

from dq_agent.agents.state import DQState
from dq_agent.agents.triage import _is_blocked, _sort_by_severity
from dq_agent.rules.engine import run_batch, summarize


def validate_node(state: DQState) -> DQState:
    """Deterministic stage: run the rule engine over the batch (REAL)."""
    anomalies = run_batch(state["records"], labels=state.get("labels"))
    state["anomalies"] = anomalies
    state["triaged"] = _sort_by_severity(anomalies)
    state["severity_blocked"] = _is_blocked(anomalies)
    return state


def build_graph():
    """Construct the StateGraph. Agent nodes are stubs; wiring is real."""
    from langgraph.graph import END, START, StateGraph

    from dq_agent.agents.communication import communication_node
    from dq_agent.agents.corrective import corrective_node
    from dq_agent.agents.author import author_node
    from dq_agent.agents.triage import triage_node

    g = StateGraph(DQState)
    g.add_node("validate", validate_node)
    g.add_node("triage", triage_node)
    g.add_node("corrective", corrective_node)
    g.add_node("communication", communication_node)
    g.add_node("author", author_node)

    g.add_edge(START, "validate")
    g.add_edge("validate", "triage")
    g.add_edge("triage", "corrective")
    g.add_edge("corrective", "communication")
    g.add_edge("communication", "author")
    g.add_edge("author", END)
    return g.compile()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the multi-agent DQ pipeline over a batch.")
    parser.add_argument("--batch", default="BATCH-0001")
    args = parser.parse_args()

    from dq_agent.data.load import load_batch

    batch, records, labels = load_batch(args.batch)
    state: DQState = {
        "batch_id": batch.batch_id,
        "correlation_id": str(uuid.uuid4()),
        "records": records,
        "labels": labels,
    }

    # Deterministic stage (real).
    state = validate_node(state)
    summary = summarize(state["anomalies"])
    print(f"\n[validate] {batch.batch_id}: {summary['total_anomalies']} anomalies "
          f"({summary['by_severity']})")
    print(f"[validate] severity_blocked = {state['severity_blocked']}")
    print("\nAgent stages are stubs in this scaffold:")
    print("  [triage]        prioritize/group anomalies         -> NotImplementedError")
    print("  [corrective]    explain + suggest fixes            -> NotImplementedError")
    print("  [communication] draft furnisher email              -> NotImplementedError")
    print("  [author]        hypothesize new rules (+ sandbox)  -> NotImplementedError")
    print("  [review]        human-in-the-loop approval gate    -> NotImplementedError")
    print("\nSee docs/05-agent-design.md for the intended implementation.\n")


if __name__ == "__main__":
    main()
