"""SemanticLayer: the ONLY database touchpoint for the agent.

Pipeline per query:
  1. validate_spec(spec)          → reject with reason on failure
  2. get_metric(spec.metric_id)   → load MetricDef from catalog
  3. check_entity_access(claims)  → entitlement denial if caller out of scope
  4. resolve entity_id            → 'self' → claims.entity_id
  5. compiler.compile(...)        → CompiledQuery (SQL + params)
  6. execute SQL on DuckDB        → raw result rows
  7. apply_min_cell_suppression() → null out peer values below threshold
  8. build MetricRows             → typed, audit-ready result
  9. return QueryResult           → rows + SQL + lineage for the agent

The LLM never reaches this module. Only the agent graph (graph.py) calls it,
and only after the planner has produced a validated QuerySpec.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from ..guardrails.entitlements import Claims, check_entity_access
from .catalog import CATALOG, get_metric
from .compiler import compile as compile_query
from .spec import Comparison, EntityRef, QuerySpec, SpecValidation, validate_spec


# ---------------------------------------------------------------------------
# Result types (used by the agent and grounding guard)
# ---------------------------------------------------------------------------

@dataclass
class MetricRow:
    """One data point returned by a governed query.

    value is None when the cell was suppressed (peer cohort below threshold).
    All numeric values in the final narrative must trace back to a MetricRow.
    """
    label:              str           # human-friendly e.g. "M07 · Jun-2024 · 90+ O/S rate"
    entity_id:          str
    reporting_month:    str
    metric_id:          str
    value:              float | None  # None when suppressed
    # ── optional comparison fields (present only when requested) ──
    industry_value:     float | None = None
    market_share:       float | None = None
    rank_best_first:    int   | None = None
    total_members:      int   | None = None
    percentile:         float | None = None
    index_value:        float | None = None
    # ── provenance ────────────────────────────────────────────────
    suppressed:         bool          = False
    suppression_reason: str   | None  = None


@dataclass
class QueryResult:
    rows:    list[MetricRow]
    sql:     str
    params:  dict = field(default_factory=dict)   # for audit / lineage
    lineage: dict = field(default_factory=dict)   # trace_id, spec snapshot, etc.


# ---------------------------------------------------------------------------
# SemanticLayer
# ---------------------------------------------------------------------------

class SemanticLayer:
    """Stateless executor bound to a DuckDB connection.

    Construct once per request (or once per app startup with a persistent
    connection) and call query() for each QuerySpec. Thread-safety depends
    on the underlying DuckDB connection — use per-request connections in
    concurrent deployments.
    """

    def __init__(self, conn: Any, min_cell_members: int = 5) -> None:
        self._conn = conn
        self._min_cell = min_cell_members

    # ── public API ────────────────────────────────────────────────────────

    def query(self, spec: QuerySpec, claims: Claims) -> QueryResult:
        """Run a governed query and return typed, suppression-aware rows.

        Raises ValueError on spec validation failure (should never happen in
        production if the planner is constrained correctly; included for safety).
        """
        trace_id = str(uuid.uuid4())

        # 1. Validate spec (structure + catalog cross-check)
        validation: SpecValidation = validate_spec(spec)
        if not validation.ok:
            raise ValueError(f"Invalid QuerySpec: {validation.reason}")

        # 2. Load metric definition
        metric = get_metric(spec.metric_id)

        # 3. Resolve entity and check entitlements
        if spec.entity == EntityRef.SELF:
            decision = check_entity_access("self", claims)
        else:
            decision = check_entity_access("industry", claims)

        if not decision.allowed:
            raise PermissionError(f"Entitlement denied: {decision.reason}")

        resolved_entity_id = decision.resolved_entity_id  # 'M07' or 'INDUSTRY'

        # 4. Compile SQL from catalog definition + spec overrides
        compiled = compile_query(
            metric           = metric,
            entity_id        = resolved_entity_id,
            product          = spec.product,
            months           = spec.months,
            bucket           = spec.bucket,
            at_or_worse      = spec.at_or_worse,
            lag_months       = spec.lag_months,
            comparisons      = [c.value for c in spec.comparison],
            index_base_month = spec.index_base_month,
        )

        # 5. Execute
        raw_rows = self._conn.execute(compiled.sql).fetchall()
        col_names = compiled.result_cols

        # 6. Convert raw tuples → dicts keyed by column name
        raw_dicts = [dict(zip(col_names, row)) for row in raw_rows]

        # 7. Build MetricRows; apply suppression to peer/ranking values
        metric_rows = self._build_metric_rows(
            raw_dicts, spec, resolved_entity_id
        )

        # 8. Build lineage record
        lineage = {
            "trace_id":    trace_id,
            "metric_id":   spec.metric_id,
            "entity_id":   resolved_entity_id,
            "product":     spec.product,
            "months":      spec.months,
            "comparisons": [c.value for c in spec.comparison],
            "sql_hash":    _short_hash(compiled.sql),
        }

        return QueryResult(
            rows    = metric_rows,
            sql     = compiled.sql,
            params  = compiled.params,
            lineage = lineage,
        )

    # ── internal helpers ──────────────────────────────────────────────────

    def _build_metric_rows(
        self,
        raw_dicts:   list[dict],
        spec:        QuerySpec,
        entity_id:   str,
    ) -> list[MetricRow]:
        metric = get_metric(spec.metric_id)
        rows: list[MetricRow] = []

        for d in raw_dicts:
            month_str = str(d.get("reporting_month", ""))
            label = f"{entity_id} · {month_str} · {metric.label}"

            # Base value
            value = _safe_float(d.get("metric_value"))

            # Comparison values — suppress peer/ranking if cohort is thin
            rank    = _safe_int(d.get("rank_best_first"))
            total   = _safe_int(d.get("total_members"))
            pct     = _safe_float(d.get("percentile"))
            mkt     = _safe_float(d.get("market_share"))
            ind_val = _safe_float(d.get("industry_value"))
            idx_val = _safe_float(d.get("index_value"))

            suppressed = False
            suppression_reason = None

            # Apply minimum-cell suppression to ranking/peer metrics
            if Comparison.RANKING in spec.comparison:
                if total is not None and total < self._min_cell:
                    rank = None
                    pct  = None
                    suppressed = True
                    suppression_reason = (
                        f"suppressed_min_cell: peer cohort has {total} members "
                        f"(minimum {self._min_cell})"
                    )

            rows.append(MetricRow(
                label              = label,
                entity_id          = entity_id,
                reporting_month    = month_str,
                metric_id          = spec.metric_id,
                value              = value,
                industry_value     = ind_val,
                market_share       = mkt,
                rank_best_first    = rank,
                total_members      = total,
                percentile         = pct,
                index_value        = idx_val,
                suppressed         = suppressed,
                suppression_reason = suppression_reason,
            ))

        return rows


# ---------------------------------------------------------------------------
# Tiny utilities
# ---------------------------------------------------------------------------

def _safe_float(v: Any) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _safe_int(v: Any) -> int | None:
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _short_hash(s: str) -> str:
    import hashlib
    return hashlib.sha256(s.encode()).hexdigest()[:12]
