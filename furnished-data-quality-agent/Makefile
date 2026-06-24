.PHONY: help install generate run pipeline eval api test lint typecheck clean

help:
	@echo "Furnished Data Quality Agent - developer commands"
	@echo ""
	@echo "  make install     Install package + dev tooling (editable)"
	@echo "  make generate    Generate synthetic furnished batches (with labeled anomalies)"
	@echo "  make run         Run the deterministic rule engine over one batch (BATCH=BATCH-0001)"
	@echo "  make pipeline    Run the full multi-agent pipeline over one batch (stubs today)"
	@echo "  make eval        Run the evaluation scorecard (rule precision/recall, grounding)"
	@echo "  make api         Run the service API (uvicorn) -> :8000"
	@echo "  make test        Run unit tests"
	@echo "  make lint        Ruff lint"
	@echo "  make typecheck   mypy"
	@echo "  make clean       Remove generated data + caches"

install:
	pip install -e ".[dev]"

generate:
	python -m dq_agent.data.generate

# Deterministic core - real and runnable.
run:
	python -m dq_agent.rules.engine --batch $${BATCH:-BATCH-0001}

# Full agent pipeline (triage -> explain -> communicate -> learn -> HITL) - stubs today.
pipeline:
	python -m dq_agent.agents.graph --batch $${BATCH:-BATCH-0001}

eval:
	python -m dq_agent.eval.harness

api:
	uvicorn dq_agent.api.app:app --reload --host $${API_HOST:-0.0.0.0} --port $${API_PORT:-8000}

test:
	pytest

lint:
	ruff check src tests

typecheck:
	mypy src

clean:
	rm -rf data __pycache__ .pytest_cache .ruff_cache .mypy_cache
