# Delinquency Benchmarking Agent

> A governed, conversational analytics agent over a credit-bureau **Delinquency Trend Report** (Credit Cards). Ask benchmarking questions in plain language; get grounded BI insights, peer percentiles, rankings, and charts - every number traced to a governed query and the report's own definitions.

This repository **replicates the structure** of a production bureau delinquency benchmarking workbook (Industry vs Member, Coincidence / Lagged / Roll-Rate lenses, Market Share, Ranking, indexed Relative Position) as a **synthetic dataset**, then builds an agent on top of it.

> Status: **scaffold + documentation**. Code is currently **stubs** (signatures, docstrings, and `NotImplementedError`). Implementation follows once the component design is reviewed. All data is **synthetic** - no real consumer or member data, no real institution names.

---

## Why this exists

Bureau benchmarking reports are rich but static (Excel/PDF). This project turns one into an interactive product: a lender analyst asks "how does my 30-dpd roll rate compare to industry and to three months ago, and where do I rank on 90-dpd O/S share?" and gets a grounded, cited answer in seconds - without a data scientist in the loop, and without the bureau losing control over accuracy, entitlements, or privacy.

It is the standalone, runnable counterpart to Case Study 01 / Lab 07 in the Agentic AI Handbook.

## Repository map

```text
delinquency-benchmarking-agent/
  README.md                  # this file
  pyproject.toml             # dependencies + tooling (pinned later)
  .env.example               # configuration template
  Makefile                   # common commands (generate, load, run, eval)
  docs/                      # READ THESE FIRST - design before code
    01-overview.md           # problem, the report we replicate, goals, scope
    02-architecture.md       # system architecture + component diagram
    03-data-model.md         # database/schema documentation (tables, buckets, bands, formulas)
    04-pipeline-flow.md      # data generation -> load -> semantic -> agent query flows
    05-agent-design.md       # router/planner, tools, RAG, memory, guardrails
    06-governance.md         # suppression, entitlements, grounding, audit, privacy
    07-evaluation.md         # eval harness, scorers, datasets, release gates
    08-glossary.md           # terms mapped to the report's Definition tab
  src/delinquency_agent/
    config.py                # settings
    data/                    # synthetic data: schema, generator, loader
    semantic/                # governed metric/measure layer (the "numbers")
    knowledge/               # definitions corpus + RAG retrieval (the "meaning")
    agent/                   # router, planner, orchestration graph, synthesis
    guardrails/              # numeric grounding, entitlements, suppression
    observability/           # tracing/metrics
    eval/                    # evaluation harness
    api/                     # service entrypoint
  tests/                     # test stubs mirroring eval/guardrail expectations
```

## Reading order

1. [docs/01-overview.md](docs/01-overview.md) - what we're building and why.
2. [docs/03-data-model.md](docs/03-data-model.md) - the data is the foundation; understand it first.
3. [docs/02-architecture.md](docs/02-architecture.md) and [docs/04-pipeline-flow.md](docs/04-pipeline-flow.md) - how components fit and data flows.
4. [docs/05-agent-design.md](docs/05-agent-design.md), [docs/06-governance.md](docs/06-governance.md), [docs/07-evaluation.md](docs/07-evaluation.md) - the agent, its guardrails, and how we prove it works.

## Quickstart (target - not yet implemented)

```bash
# 1. install
pip install -e ".[dev]"

# 2. generate the synthetic benchmarking dataset
make generate          # -> data/benchmark.duckdb

# 3. build the definitions RAG corpus
make corpus

# 4. run the agent API locally
make run               # -> http://localhost:8000

# 5. run the evaluation scorecard (numeric accuracy + groundedness)
make eval
```

> These commands are wired to stubs today; they define the intended developer workflow. See the `Makefile` and `docs/04-pipeline-flow.md`.

## Design principles (carried from the handbook)

- **The LLM plans and narrates; it never computes or governs.** Numbers come from the governed semantic layer; methodology comes from the report's own definitions.
- **Grounded-or-refuse.** Every figure in an answer must map to a returned query row + a citation, or it is blocked.
- **Privacy by construction.** Aggregate-only, with minimum-cell suppression and identity-based entitlements enforced in the data layer.
- **Everything is auditable.** Prompt -> plan -> query -> rows -> narrative is logged with lineage.
