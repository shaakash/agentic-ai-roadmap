# Furnished Data Quality Agent

> A governed, **multi-agent** system that finds and helps remediate data-quality
> problems in **furnished credit data** — the account files lenders ("furnishers")
> send to a credit data aggregator/bureau. It runs a **deterministic rule engine**
> over each batch to flag anomalies, then uses LLM-backed agents to **explain** each
> issue in plain English, **draft a correction**, **draft the furnisher email**, and
> **hypothesize new rules** (with generated, sandbox-tested code) — all behind a
> **human-in-the-loop** review gate. The machine detects and drafts; a data steward
> decides.

It mirrors the workflow of a furnished-data quality copilot: the slow part — reading
raw records, spotting inconsistencies, writing up what's wrong and why, and chasing
furnishers — is automated, while the **judgment** (is this really an error? should we
ship this rule? send this email?) stays with a person, and the **detection** stays in
deterministic code.

> Status: **scaffold + documentation**. The **deterministic core is real and runnable**
> (rule engine, rule catalog, synthetic data generator, smoke test). The **LLM agents
> are stubs** (signatures, docstrings, `NotImplementedError`) to be implemented once the
> design is reviewed. Everything is **synthetic and public-safe** — Metro 2-style fields
> on fabricated accounts, no real consumer/furnisher data, no real institution names.

---

## Why this exists

A credit data aggregator is only as good as the data furnishers send it. Furnished
files (commonly in the industry-standard **Metro 2** format) routinely contain
inconsistencies that, left unchecked, corrupt scores and attributes downstream:

- a *date of last payment* that falls **before** the account *open date*
- a *closed date* before the *open date*
- a balance that **drops** in a month with **no payment** (it should hold or grow with interest/fees)
- duplicate rows that double-count an account
- a *date reported* in the future, a balance over the credit limit, status/rating contradictions

Today this is caught by analysts reading files by hand — slow, inconsistent, and reactive.

This project automates the **detection and the first-draft remediation** while keeping
the **decision** with a human and the **detection logic** in deterministic, testable code:

- A **rule engine** (not an LLM) decides what is and isn't an anomaly — every flag cites the record, the fields, and the rule id.
- A **Corrective Agent** writes a grounded, plain-English explanation and a *suggested* correction per anomaly (it never edits data).
- A **Communication Agent** drafts the furnisher email; nothing is sent without a human.
- A **Rule-Author Agent** studies patterns and **hypothesizes new rules**, generating Python check code that is **static-checked and sandbox-tested against labeled data** before any human is asked to approve it.
- A **data steward** reviews and approves corrective actions, emails, and new rules — the human-in-the-loop gate.
- Every step is **traced** end to end (batch → record → rule fire → anomaly → action → email → human decision) under one correlation id.

It is a standalone, runnable counterpart to the data-quality / multi-agent material in
the Agentic AI Handbook (`industry-use-cases/bfsi-agents.md`).

## Repository map

```text
furnished-data-quality-agent/
  README.md                  # this file
  pyproject.toml             # dependencies + tooling (pinned later)
  .env.example               # configuration template
  Makefile                   # common commands (generate, run, eval)
  docs/                      # READ THESE FIRST - design before code
    00-plain-english-walkthrough.md   # layman on-ramp: one batch through every stage
    00b-rules-and-learning-walkthrough.md # layman deep-dive: the deterministic core + the rule-learning loop
    00c-multi-agent-walkthrough.md    # layman deep-dive: the agents + the human-in-the-loop gate
    01-overview.md           # problem, the workflow we replicate, goals, scope
    02-architecture.md       # system architecture + component diagram
    03-data-model.md         # furnished record model (Metro 2-style), anomaly, rule, action
    04-pipeline-flow.md      # ingest -> validate -> triage -> explain -> communicate -> learn -> HITL
    05-agent-design.md       # the multi-agent graph, nodes, shared state, roles
    06-rules-engine.md       # the deterministic core: rule DSL, categories, the catalog
    07-governance.md         # HITL, sandboxing generated code, grounding, lineage, model risk
    08-evaluation.md         # eval harness, scorers (precision/recall, grounding), datasets
    09-glossary.md           # furnished-data + Metro 2 terms
    10-interview-qa.md       # interview prep (pitch -> domain -> agent/governance debugging -> curveballs)
  src/dq_agent/
    config.py                # settings
    schemas/                 # shared pydantic contracts (record, anomaly, rule, action, lineage)
    data/                    # synthetic furnished batches with injected, labeled anomalies
    rules/                   # deterministic rule engine + check functions + rule catalog (YAML)
    agents/                  # multi-agent graph: triage, corrective, rule-author, communication
    sandbox/                 # static-check + sandboxed validation of generated rule code
    guardrails/              # grounding, generated-code review, human-in-the-loop gate
    observability/           # tracing + lineage
    eval/                    # evaluation harness
    api/                     # service entrypoint
  eval/                      # evaluation datasets
  tests/                     # tests for the rule engine, data invariants, governance
```

## Reading order

0. **New to furnished credit data? Start with the plain-English walkthroughs:**
   [docs/00-plain-english-walkthrough.md](docs/00-plain-english-walkthrough.md) (one batch through every stage),
   then [docs/00b-rules-and-learning-walkthrough.md](docs/00b-rules-and-learning-walkthrough.md) (the deterministic core + the learning loop)
   and [docs/00c-multi-agent-walkthrough.md](docs/00c-multi-agent-walkthrough.md) (the agents + the human gate).
1. [docs/01-overview.md](docs/01-overview.md) — what we're building and why.
2. [docs/03-data-model.md](docs/03-data-model.md) — the furnished record + anomaly/rule model; the data is the foundation.
3. [docs/02-architecture.md](docs/02-architecture.md) and [docs/04-pipeline-flow.md](docs/04-pipeline-flow.md) — how components fit and how a batch flows through them.
4. [docs/05-agent-design.md](docs/05-agent-design.md), [docs/06-rules-engine.md](docs/06-rules-engine.md), [docs/07-governance.md](docs/07-governance.md) — the agents, the deterministic core, and the controls.
5. [docs/10-interview-qa.md](docs/10-interview-qa.md) — interview prep.

## Quickstart

```bash
# 1. install
pip install -e ".[dev]"

# 2. generate synthetic furnished batches (with injected, labeled anomalies)
make generate          # -> data/batches/

# 3. run the rule engine over one batch and print the anomaly report (deterministic core - real)
make run BATCH=BATCH-0001

# 4. run the full multi-agent pipeline (explain + draft + learn + HITL) - stubs today
make pipeline BATCH=BATCH-0001

# 5. run the evaluation scorecard (rule precision/recall, grounding) - stubs today
make eval
```

> The deterministic core (steps 2–3) runs today. The LLM agent steps are wired to
> stubs that define the intended developer workflow. See the `Makefile` and
> `docs/04-pipeline-flow.md`.

## Design principles

- **Deterministic detection; probabilistic assistance.** The rule engine decides what is an anomaly. The LLM only explains, drafts, and proposes — it never flags, clears, or edits data.
- **Generated code is guilty until proven safe.** Any rule code the Rule-Author Agent writes is static-checked and **sandbox-tested against labeled data** (precision/recall measured) before a human is even asked to approve it. Nothing is hot-loaded.
- **The machine drafts; the human decides.** Corrective actions, furnisher emails, and new rules are all *drafts* until a data steward approves them.
- **Grounded-or-flagged.** Every anomaly explanation cites the record id, the exact fields, the rule id, and expected-vs-actual — or it isn't shown.
- **Everything is auditable.** One correlation id threads batch → record → rule fire → anomaly → corrective action → email → human decision into immutable lineage.
- **Privacy by construction.** Synthetic, aggregate-safe, data-minimized; no real accounts, furnishers, or institutions.
