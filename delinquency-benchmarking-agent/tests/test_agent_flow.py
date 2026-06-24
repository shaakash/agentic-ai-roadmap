"""Agent flow tests: routing, planning, end-to-end grounding (docs/05-agent-design.md)."""

import pytest

pytestmark = pytest.mark.skip(reason="scaffold: agent not implemented yet")


def test_router_classifies_definition():
    """A 'what does X mean' question routes to Intent.DEFINITION."""
    raise NotImplementedError


def test_router_classifies_benchmark():
    """A 'how do I rank vs peers' question routes to Intent.BENCHMARK."""
    raise NotImplementedError


def test_planner_emits_valid_spec():
    """Planner returns a QuerySpec that passes validate_spec for a metric question."""
    raise NotImplementedError


def test_end_to_end_answer_is_grounded():
    """A full ask() returns an answer with grounded=True and at least one citation."""
    raise NotImplementedError
