"""Governance tests: entitlements, suppression, grounding (docs/06-governance.md)."""

import pytest

pytestmark = pytest.mark.skip(reason="scaffold: guardrails not implemented yet")


def test_member_cannot_read_other_member():
    """check_entity_access denies a foreign member id."""
    raise NotImplementedError


def test_self_resolves_to_claims_entity():
    """'self' resolves to the caller's entity_id and is allowed."""
    raise NotImplementedError


def test_industry_is_readable():
    """INDUSTRY aggregate is readable by any member."""
    raise NotImplementedError


def test_thin_cohort_is_suppressed():
    """Peer/ranking value over < MIN_CELL_MEMBERS members is suppressed with reason."""
    raise NotImplementedError


def test_ungrounded_number_is_blocked():
    """GroundingGuard flags a narrative number absent from returned rows."""
    raise NotImplementedError
