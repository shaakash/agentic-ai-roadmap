.PHONY: help install generate corpus run eval test lint typecheck clean

help:
	@echo "Delinquency Benchmarking Agent - developer commands"
	@echo ""
	@echo "  make install    Install package + dev tooling (editable)"
	@echo "  make generate   Generate the synthetic benchmarking dataset -> DuckDB"
	@echo "  make corpus     Build the definitions RAG corpus (vector index)"
	@echo "  make run        Run the agent API locally (uvicorn)"
	@echo "  make eval       Run the evaluation scorecard (numeric accuracy + groundedness)"
	@echo "  make test       Run unit tests"
	@echo "  make lint       Ruff lint"
	@echo "  make typecheck  mypy"
	@echo "  make clean      Remove generated data + caches"

install:
	pip install -e ".[dev]"

generate:
	python -m delinquency_agent.data.generate

corpus:
	python -m delinquency_agent.knowledge.corpus

run:
	uvicorn delinquency_agent.api.app:app --reload --host $${API_HOST:-0.0.0.0} --port $${API_PORT:-8000}

eval:
	python -m delinquency_agent.eval.harness

test:
	pytest

lint:
	ruff check src tests

typecheck:
	mypy src

clean:
	rm -rf data __pycache__ .pytest_cache .ruff_cache .mypy_cache
