"""Numeric grounding guard — the last gate before a response reaches the user.

Every percentage or number stated in the narrative must trace to a value in
the returned rows within tolerance. If it cannot be traced, the answer is
flagged (grounded-or-refuse pattern from docs/06-governance.md).

Design:
    The synthesizer is instructed to only use numbers from the data table.
    This guard verifies that instruction was followed — it cannot be
    prompted away because it runs after the LLM, in deterministic code.

Extraction scope:
    Only percentage values ("4.13%") are extracted and checked against row
    values.  Plain integers (e.g. ranking "4 of 18") and scores (e.g. "680")
    are accepted without verification because they are self-evidently bounded
    to the data table by the synthesizer prompt. This keeps false-positive
    rates low while still catching the most dangerous category of hallucinated
    numbers: fabricated rates.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..semantic.metrics import MetricRow


# Matches "4.13%" or "42%" — the most safety-critical number form
_PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)%")


@dataclass
class GroundingResult:
    grounded: bool
    ungrounded_numbers: list[float] = field(default_factory=list)
    detail: str | None = None


class GroundingGuard:
    """Verify that every percentage in a narrative traces to a returned row.

    Args:
        rel_tolerance: Maximum relative difference allowed between a stated
            percentage and the closest row value expressed as a percentage.
            Default 0.01 means ±1% relative, which accommodates rounding to
            one or two decimal places.
        abs_floor: Minimum absolute tolerance in percentage points.
            Prevents over-strictness for very small rates (e.g. 0.05%).
    """

    def __init__(
        self,
        rel_tolerance: float = 0.01,
        abs_floor: float = 0.05,
    ) -> None:
        self._rel_tol  = rel_tolerance
        self._abs_floor = abs_floor

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def extract_numbers(self, narrative: str) -> list[float]:
        """Parse all percentage claims from the narrative text.

        Returns values as raw floats, e.g. "4.13%" → 4.13.
        """
        return [float(m) for m in _PERCENT_RE.findall(narrative)]

    def check(self, narrative: str, rows: list[MetricRow]) -> GroundingResult:
        """Verify each extracted percentage matches some row value within tolerance.

        Row values stored as rates (e.g. 0.0413) are converted to percentage
        form (4.13) before comparison. Market-share, percentile, and index
        values are also included in the candidate set.

        If rows is empty (definition-only answer), any percentage in the
        narrative is considered ungrounded.
        """
        extracted = self.extract_numbers(narrative)
        if not extracted:
            return GroundingResult(grounded=True, detail="no percentages to check")

        # Build the set of valid percentage values from all row fields
        valid_pcts: set[float] = set()
        for row in rows:
            for raw_val in (
                row.value,
                row.industry_value,
                row.market_share,
                row.percentile,
                row.index_value,
            ):
                if raw_val is None:
                    continue
                # Store both raw form and ×100 (rate → percentage)
                valid_pcts.add(raw_val)
                valid_pcts.add(raw_val * 100)

        if not valid_pcts:
            # Rows exist but all values are suppressed / None
            return GroundingResult(
                grounded=False,
                ungrounded_numbers=extracted,
                detail="all row values suppressed; cannot verify any percentage",
            )

        ungrounded: list[float] = []
        for stated in extracted:
            if not self._matches_any(stated, valid_pcts):
                ungrounded.append(stated)

        if ungrounded:
            detail = (
                f"{len(ungrounded)} percentage(s) could not be traced to a row: "
                + ", ".join(f"{v}%" for v in ungrounded)
            )
        else:
            detail = f"all {len(extracted)} percentage(s) verified"

        return GroundingResult(
            grounded=len(ungrounded) == 0,
            ungrounded_numbers=ungrounded,
            detail=detail,
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _matches_any(self, stated: float, candidates: set[float]) -> bool:
        for c in candidates:
            tol = max(self._rel_tol * abs(c), self._abs_floor)
            if abs(stated - c) <= tol:
                return True
        return False
