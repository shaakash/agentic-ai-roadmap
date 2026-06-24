"""QuerySpec: the typed contract between the planner (LLM) and the semantic layer.

The planner emits ONLY this structure — never SQL.
The key field is `metric_id`, which references a MetricDef in the catalog.
The catalog defines the formula and defaults; the spec carries the user's
specific choices (which bucket, which months, which comparisons).

See docs/04-pipeline-flow.md for the JSON form and docs/05-agent-design.md
for how the planner constructs this.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Comparison(str, Enum):
    MARKET_SHARE = "market_share"
    RANKING      = "ranking"
    INDEX        = "index"


class EntityRef(str, Enum):
    SELF     = "self"      # resolved to caller's entity_id by the semantic layer
    INDUSTRY = "industry"


@dataclass
class QuerySpec:
    """Everything the planner knows about a question, fully typed.

    metric_id        References CATALOG in semantic/catalog.py. The planner
                     is given the catalog's metric labels and IDs in its system
                     prompt so it can resolve natural language to the right ID.

    entity           'self' (caller's own entity) or 'industry'. The semantic
                     layer resolves 'self' → claims.entity_id before the
                     compiler sees it.

    product          Must be in metric.applies_to; validated at spec validation.

    bucket           DPD bucket override. If None, uses metric.default_bucket.
                     The planner sets this when the user specifies a bucket
                     other than the metric's default (e.g. "30+" instead of "90+").

    at_or_worse      True = "bucket or worse" (e.g. "90+").
                     False = exactly that bucket (e.g. "exactly 90 dpd").

    lag_months       For lagged metrics only. Overrides metric.default_lag_months.

    months           Time window as ['YYYY-MM', ...]. The planner resolves
                     "Q2 2024" → ["2024-04", "2024-05", "2024-06"] etc.

    comparison       Which comparison views to compute alongside the base metric.
                     Must be a subset of metric.comparisons_allowed.

    index_base_month Required when Comparison.INDEX is in comparison.
                     The month (YYYY-MM) to re-base to 100.
    """
    metric_id:        str                   = "coincidence_os_pct"
    entity:           EntityRef             = EntityRef.SELF
    product:          str                   = "credit_card"
    bucket:           str | None            = None          # None → use catalog default
    at_or_worse:      bool                  = True
    lag_months:       int | None            = None          # None → use catalog default
    months:           list[str]             = field(default_factory=list)
    comparison:       list[Comparison]      = field(default_factory=list)
    index_base_month: str | None            = None


@dataclass
class SpecValidation:
    ok:     bool
    reason: str | None = None   # machine-readable; relayed to planner for repair


def validate_spec(spec: QuerySpec) -> SpecValidation:
    """Check internal consistency of a QuerySpec.

    Validation is intentionally independent of database state (no DB call).
    Entitlement checks are handled separately in guardrails/entitlements.py.
    """
    from .catalog import get_metric, FormulaType

    # ── metric must exist in catalog ─────────────────────────────────────
    try:
        metric = get_metric(spec.metric_id)
    except KeyError as e:
        return SpecValidation(ok=False, reason=str(e))

    # ── product must be supported by this metric ──────────────────────────
    if spec.product not in metric.applies_to:
        return SpecValidation(
            ok=False,
            reason=(
                f"Metric '{spec.metric_id}' does not apply to product "
                f"'{spec.product}'. Supported: {metric.applies_to}"
            ),
        )

    # ── months must be non-empty and well-formed ──────────────────────────
    if not spec.months:
        return SpecValidation(ok=False, reason="months list is empty")
    for m in spec.months:
        parts = m.split("-")
        if len(parts) != 2:
            return SpecValidation(
                ok=False, reason=f"Month '{m}' must be in YYYY-MM format"
            )
        try:
            year, month = int(parts[0]), int(parts[1])
            if not (1 <= month <= 12):
                raise ValueError
        except ValueError:
            return SpecValidation(
                ok=False, reason=f"Month '{m}' is not a valid YYYY-MM value"
            )

    # ── lagged metrics must have lag_months resolvable ────────────────────
    if metric.formula == FormulaType.LAGGED:
        effective_lag = spec.lag_months or metric.default_lag_months
        if not effective_lag or effective_lag < 1:
            return SpecValidation(
                ok=False,
                reason="Lagged metric requires lag_months >= 1 (set in spec or catalog default)"
            )

    # ── index comparison requires index_base_month ────────────────────────
    if Comparison.INDEX in spec.comparison:
        if not spec.index_base_month:
            return SpecValidation(
                ok=False,
                reason="Comparison 'index' requires index_base_month to be set"
            )
        if spec.index_base_month not in spec.months:
            return SpecValidation(
                ok=False,
                reason=(
                    f"index_base_month '{spec.index_base_month}' must be "
                    f"included in the months list"
                ),
            )

    # ── comparison types must be allowed for this metric ─────────────────
    for comp in spec.comparison:
        if comp.value not in metric.comparisons_allowed:
            return SpecValidation(
                ok=False,
                reason=(
                    f"Comparison '{comp.value}' is not allowed for metric "
                    f"'{spec.metric_id}'. Allowed: {metric.comparisons_allowed}"
                ),
            )

    return SpecValidation(ok=True)
