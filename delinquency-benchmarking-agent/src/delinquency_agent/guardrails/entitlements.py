"""Entitlements and minimum-cell suppression - enforced inside the data path.

Claims are resolved by the API from the authenticated caller; the agent only
ever sees Claims, never credentials. See docs/06-governance.md.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Claims:
    """Resolved caller permissions."""
    entity_id: str          # the member the caller represents, e.g. "M07"
    scope: str = "member"   # "member" | "industry_only"


@dataclass
class EntitlementDecision:
    allowed: bool
    resolved_entity_id: str | None = None   # 'self' -> claims.entity_id
    reason: str | None = None               # when denied


def check_entity_access(requested_entity: str, claims: Claims) -> EntitlementDecision:
    """Decide whether the caller may read the requested entity.

    Rules:
      - 'self'      → allowed; resolved to claims.entity_id.
      - 'industry'  → allowed (INDUSTRY aggregate is public to all members).
      - any other id → denied (callers may not directly read another member's rows).
        Peer/ranking aggregates are handled via minimum-cell suppression,
        not via direct row access.
    """
    if claims.scope == "industry_only":
        # Restricted callers may only see INDUSTRY
        if requested_entity in ("self", "industry"):
            resolved = "INDUSTRY"
            return EntitlementDecision(allowed=True, resolved_entity_id=resolved)
        return EntitlementDecision(
            allowed=False,
            reason=f"Scope 'industry_only': cannot access entity '{requested_entity}'"
        )

    if requested_entity == "self":
        return EntitlementDecision(allowed=True, resolved_entity_id=claims.entity_id)

    if requested_entity in ("industry", "INDUSTRY"):
        return EntitlementDecision(allowed=True, resolved_entity_id="INDUSTRY")

    # Any other explicit entity_id is denied
    return EntitlementDecision(
        allowed=False,
        reason=(
            f"Caller '{claims.entity_id}' may not directly access entity "
            f"'{requested_entity}'. Peer comparisons are available via "
            "comparison='ranking' with minimum-cell suppression applied."
        ),
    )


def apply_min_cell_suppression(
    value: float | None,
    contributing_members: int,
    min_cell_members: int,
) -> tuple[float | None, str | None]:
    """Suppress a peer/ranking value computed over too few members.

    Returns (value_or_none, suppression_reason_or_none).
    When the cohort is too small, the value is withheld and a reason is
    returned so the agent can explain the suppression to the caller.
    """
    if contributing_members < min_cell_members:
        reason = (
            f"suppressed_min_cell: result computed over {contributing_members} "
            f"member(s); minimum required is {min_cell_members}"
        )
        return None, reason
    return value, None
