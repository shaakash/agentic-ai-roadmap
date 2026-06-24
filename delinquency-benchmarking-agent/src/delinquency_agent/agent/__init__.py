"""Agent layer: router -> plan -> tools -> synthesize graph. See docs/05-agent-design.md.

The LLM has exactly three jobs here: classify intent (router), produce a typed
QuerySpec (planner), and narrate from results (synthesizer). Numbers, governance,
and retrieval are deterministic tooling.
"""
