"""MetricCompiler: reads a MetricDef from the catalog and generates governed SQL.

This module contains ALL the SQL business logic. Nothing else in the codebase
writes SQL. The compiler is the single place to understand how a metric is
computed and how comparisons are layered on top.

Design contract
---------------
- Input : MetricDef (from catalog) + resolved QuerySpec (entity_id resolved,
          months converted to date strings, bucket/lag overrides applied).
- Output: A CompiledQuery containing the SQL string + the params dict used to
          build it (for lineage/audit), + the result column names.

Comparison layers (market_share, ranking, index) are built as additional CTEs
on top of the base metric CTE. Adding a new comparison type means adding one
CTE builder here — no changes anywhere else.

SQL is built with validated, type-safe values. The LLM never reaches this
module; the spec is fully validated before compile() is called.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field

from .catalog import FormulaType, MetricDef


# ---------------------------------------------------------------------------
# Output types
# ---------------------------------------------------------------------------

@dataclass
class CompiledQuery:
    sql:          str
    params:       dict          = field(default_factory=dict)  # for audit lineage
    result_cols:  list[str]     = field(default_factory=list)  # column names to expect


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _month_end(ym: str) -> str:
    """Convert 'YYYY-MM' to its month-end DATE string 'YYYY-MM-DD'."""
    year, month = map(int, ym.split("-"))
    last_day = calendar.monthrange(year, month)[1]
    return f"{year:04d}-{month:02d}-{last_day:02d}"


def _months_in_clause(months: list[str]) -> str:
    """Build a SQL IN literal from a list of YYYY-MM month strings."""
    date_strs = ", ".join(f"DATE '{_month_end(m)}'" for m in months)
    return f"({date_strs})"


def _bucket_sort_order(bucket_id: str) -> int:
    """Return the sort_order for a bucket_id (mirrors dim_dpd_bucket)."""
    order = {
        "current": 0, "x_day": 1, "b30": 2, "b60": 3, "b90": 4,
        "b120": 5, "b150": 6, "b180_plus": 7, "newly_writeoff": 8,
    }
    if bucket_id not in order:
        raise ValueError(f"Unknown bucket_id '{bucket_id}'")
    return order[bucket_id]


def _bucket_filter(bucket: str, at_or_worse: bool) -> str:
    """Return a SQL WHERE fragment selecting a bucket or all worse ones."""
    if at_or_worse:
        sort = _bucket_sort_order(bucket)
        return f"d.sort_order >= {sort}"
    else:
        return f"f.dpd_bucket = '{bucket}'"


# ---------------------------------------------------------------------------
# Base metric SQL builders (one per FormulaType)
# ---------------------------------------------------------------------------

def _compile_coincidence(
    metric: MetricDef,
    entity_id: str,
    product: str,
    bucket: str,
    at_or_worse: bool,
    months: list[str],
) -> tuple[str, dict]:
    """
    coincidence_pct = SUM(measure_col where bucket >= threshold)
                      / SUM(measure_col all buckets)
    per entity, per month.
    """
    col = metric.measure_col.value
    bucket_flt = _bucket_filter(bucket, at_or_worse)
    months_in = _months_in_clause(months)

    # metric_value FIRST so column order matches result_cols contract.
    sql = f"""
WITH base_metric AS (
    SELECT
        f.entity_id,
        f.reporting_month,
        SUM(CASE WHEN {bucket_flt} THEN f.{col} ELSE 0 END)
            / NULLIF(SUM(f.{col}), 0)                         AS metric_value,
        SUM(CASE WHEN {bucket_flt} THEN f.{col} ELSE 0 END)   AS numerator,
        SUM(f.{col})                                           AS denominator
    FROM fact_delinquency f
    JOIN dim_dpd_bucket d ON d.bucket_id = f.dpd_bucket
    WHERE f.entity_id  = '{entity_id}'
      AND f.product    = '{product}'
      AND f.reporting_month IN {months_in}
    GROUP BY f.entity_id, f.reporting_month
)"""
    params = {
        "formula": "coincidence", "entity_id": entity_id, "product": product,
        "bucket": bucket, "at_or_worse": at_or_worse, "months": months,
    }
    return sql, params


def _compile_lagged(
    metric: MetricDef,
    entity_id: str,
    product: str,
    bucket: str,
    at_or_worse: bool,
    lag_months: int,
    months: list[str],
) -> tuple[str, dict]:
    """
    lagged_pct = SUM(measure_col in bucket at month t)
                 / SUM(measure_col all buckets at month t - lag_months)
    """
    col = metric.measure_col.value
    bucket_flt = _bucket_filter(bucket, at_or_worse)
    months_in = _months_in_clause(months)

    sql = f"""
WITH all_monthly AS (
    SELECT
        f.entity_id,
        m.reporting_month,
        m.month_index,
        SUM(CASE WHEN {bucket_flt} THEN f.{col} ELSE 0 END) AS delq_val,
        SUM(f.{col})                                          AS total_val
    FROM fact_delinquency f
    JOIN dim_dpd_bucket d ON d.bucket_id       = f.dpd_bucket
    JOIN dim_month      m ON m.reporting_month = f.reporting_month
    WHERE f.entity_id = '{entity_id}'
      AND f.product   = '{product}'
    GROUP BY f.entity_id, m.reporting_month, m.month_index
),
base_metric AS (
    SELECT
        curr.entity_id,
        curr.reporting_month,
        curr.delq_val / NULLIF(base.total_val, 0)       AS metric_value,
        curr.delq_val                                    AS numerator,
        base.total_val                                   AS denominator
    FROM all_monthly curr
    JOIN all_monthly base
      ON base.entity_id   = curr.entity_id
     AND base.month_index = curr.month_index - {lag_months}
    WHERE curr.reporting_month IN {months_in}
)"""
    params = {
        "formula": "lagged", "entity_id": entity_id, "product": product,
        "bucket": bucket, "at_or_worse": at_or_worse, "lag_months": lag_months,
        "months": months,
    }
    return sql, params


def _compile_roll_rate(
    metric: MetricDef,
    entity_id: str,
    product: str,
    months: list[str],
) -> tuple[str, dict]:
    """
    roll_rate = accounts in to_bucket at month t
                / accounts in from_bucket at month t-1
    """
    from_b = metric.from_bucket
    to_b   = metric.to_bucket
    col    = metric.measure_col.value
    months_in = _months_in_clause(months)

    sql = f"""
WITH monthly_counts AS (
    SELECT
        f.entity_id,
        m.reporting_month,
        m.month_index,
        SUM(CASE WHEN f.dpd_bucket = '{from_b}' THEN f.{col} ELSE 0 END) AS from_n,
        SUM(CASE WHEN f.dpd_bucket = '{to_b}'   THEN f.{col} ELSE 0 END) AS to_n
    FROM fact_delinquency f
    JOIN dim_month m ON m.reporting_month = f.reporting_month
    WHERE f.entity_id = '{entity_id}'
      AND f.product   = '{product}'
    GROUP BY f.entity_id, m.reporting_month, m.month_index
),
base_metric AS (
    SELECT
        curr.entity_id,
        curr.reporting_month,
        curr.to_n / NULLIF(prev.from_n, 0)       AS metric_value,
        curr.to_n                                 AS numerator,
        prev.from_n                               AS denominator
    FROM monthly_counts curr
    JOIN monthly_counts prev
      ON prev.entity_id   = curr.entity_id
     AND prev.month_index = curr.month_index - 1
    WHERE curr.reporting_month IN {months_in}
)"""
    params = {
        "formula": "roll_rate", "entity_id": entity_id, "product": product,
        "from_bucket": from_b, "to_bucket": to_b, "months": months,
    }
    return sql, params


def _compile_avg_score(
    metric: MetricDef,
    entity_id: str,
    product: str,
    bucket: str,
    at_or_worse: bool,
    months: list[str],
) -> tuple[str, dict]:
    """Weighted-average risk score for accounts in a bucket."""
    bucket_flt = _bucket_filter(bucket, at_or_worse)
    months_in = _months_in_clause(months)

    sql = f"""
WITH base_metric AS (
    SELECT
        f.entity_id,
        f.reporting_month,
        SUM(f.avg_score * f.num_accounts)
            / NULLIF(SUM(f.num_accounts), 0)   AS metric_value,
        NULL::DOUBLE                            AS numerator,
        SUM(f.num_accounts)                    AS denominator
    FROM fact_delinquency f
    JOIN dim_dpd_bucket d ON d.bucket_id = f.dpd_bucket
    WHERE f.entity_id  = '{entity_id}'
      AND f.product    = '{product}'
      AND f.reporting_month IN {months_in}
      AND {bucket_flt}
    GROUP BY f.entity_id, f.reporting_month
)"""
    params = {
        "formula": "avg_score", "entity_id": entity_id, "product": product,
        "bucket": bucket, "at_or_worse": at_or_worse, "months": months,
    }
    return sql, params


# ---------------------------------------------------------------------------
# Comparison CTE builders
# ---------------------------------------------------------------------------

def _cte_market_share(
    metric: MetricDef,
    product: str,
    bucket: str,
    at_or_worse: bool,
    lag_months: int | None,
    months: list[str],
) -> str:
    """Append CTEs that compute the industry value and market_share."""
    col = metric.measure_col.value
    months_in = _months_in_clause(months)

    if metric.formula in (FormulaType.COINCIDENCE, FormulaType.LAGGED, FormulaType.AVG_SCORE):
        bucket_flt = _bucket_filter(bucket or "b90", at_or_worse)
        industry_cte = f"""
,
industry_metric AS (
    SELECT
        f.reporting_month,
        SUM(CASE WHEN {bucket_flt} THEN f.{col} ELSE 0 END)
            / NULLIF(SUM(f.{col}), 0) AS metric_value
    FROM fact_delinquency f
    JOIN dim_dpd_bucket d ON d.bucket_id = f.dpd_bucket
    WHERE f.entity_id = 'INDUSTRY'
      AND f.product   = '{product}'
      AND f.reporting_month IN {months_in}
    GROUP BY f.reporting_month
)"""
    else:  # ROLL_RATE
        from_b = metric.from_bucket
        to_b   = metric.to_bucket
        industry_cte = f"""
,
industry_monthly AS (
    SELECT
        m.reporting_month,
        m.month_index,
        SUM(CASE WHEN f.dpd_bucket = '{from_b}' THEN f.{col} ELSE 0 END) AS from_n,
        SUM(CASE WHEN f.dpd_bucket = '{to_b}'   THEN f.{col} ELSE 0 END) AS to_n
    FROM fact_delinquency f
    JOIN dim_month m ON m.reporting_month = f.reporting_month
    WHERE f.entity_id = 'INDUSTRY'
      AND f.product   = '{product}'
    GROUP BY m.reporting_month, m.month_index
),
industry_metric AS (
    SELECT
        curr.reporting_month,
        curr.to_n / NULLIF(prev.from_n, 0) AS metric_value
    FROM industry_monthly curr
    JOIN industry_monthly prev ON prev.month_index = curr.month_index - 1
    WHERE curr.reporting_month IN {months_in}
)"""

    market_share_cte = """
,
with_market_share AS (
    SELECT
        b.entity_id,
        b.reporting_month,
        b.metric_value,
        b.numerator,
        b.denominator,
        i.metric_value                              AS industry_value,
        b.metric_value / NULLIF(i.metric_value, 0) AS market_share
    FROM base_metric b
    LEFT JOIN industry_metric i ON i.reporting_month = b.reporting_month
)"""
    return industry_cte + market_share_cte


def _cte_ranking(
    metric: MetricDef,
    product: str,
    bucket: str,
    at_or_worse: bool,
    lag_months: int | None,
    months: list[str],
    entity_id: str,
) -> str:
    """Append CTEs that compute ranking + percentile across all members."""
    col = metric.measure_col.value
    months_in = _months_in_clause(months)

    if metric.formula == FormulaType.COINCIDENCE:
        bucket_flt = _bucket_filter(bucket, at_or_worse)
        all_members_cte = f"""
,
all_members AS (
    SELECT
        f.entity_id,
        f.reporting_month,
        SUM(CASE WHEN {bucket_flt} THEN f.{col} ELSE 0 END)
            / NULLIF(SUM(f.{col}), 0) AS peer_value
    FROM fact_delinquency f
    JOIN dim_dpd_bucket  d ON d.bucket_id       = f.dpd_bucket
    JOIN dim_entity      e ON e.entity_id        = f.entity_id
    WHERE e.entity_type = 'member'
      AND f.product     = '{product}'
      AND f.reporting_month IN {months_in}
    GROUP BY f.entity_id, f.reporting_month
)"""
    elif metric.formula == FormulaType.ROLL_RATE:
        from_b = metric.from_bucket
        to_b   = metric.to_bucket
        all_members_cte = f"""
,
all_members_monthly AS (
    SELECT
        f.entity_id,
        m.reporting_month,
        m.month_index,
        SUM(CASE WHEN f.dpd_bucket = '{from_b}' THEN f.{col} ELSE 0 END) AS from_n,
        SUM(CASE WHEN f.dpd_bucket = '{to_b}'   THEN f.{col} ELSE 0 END) AS to_n
    FROM fact_delinquency f
    JOIN dim_month  m ON m.reporting_month = f.reporting_month
    JOIN dim_entity e ON e.entity_id       = f.entity_id
    WHERE e.entity_type = 'member'
      AND f.product     = '{product}'
    GROUP BY f.entity_id, m.reporting_month, m.month_index
),
all_members AS (
    SELECT
        curr.entity_id,
        curr.reporting_month,
        curr.to_n / NULLIF(prev.from_n, 0) AS peer_value
    FROM all_members_monthly curr
    JOIN all_members_monthly prev
      ON prev.entity_id   = curr.entity_id
     AND prev.month_index = curr.month_index - 1
    WHERE curr.reporting_month IN {months_in}
)"""
    else:
        bucket_flt = _bucket_filter(bucket or "b90", at_or_worse)
        all_members_cte = f"""
,
all_members AS (
    SELECT
        f.entity_id,
        f.reporting_month,
        SUM(CASE WHEN {bucket_flt} THEN f.{col} ELSE 0 END)
            / NULLIF(SUM(f.{col}), 0) AS peer_value
    FROM fact_delinquency f
    JOIN dim_dpd_bucket d ON d.bucket_id = f.dpd_bucket
    JOIN dim_entity     e ON e.entity_id = f.entity_id
    WHERE e.entity_type = 'member'
      AND f.product = '{product}'
      AND f.reporting_month IN {months_in}
    GROUP BY f.entity_id, f.reporting_month
)"""

    ranked_cte = f"""
,
ranked_members AS (
    SELECT
        entity_id,
        reporting_month,
        peer_value,
        RANK()  OVER (PARTITION BY reporting_month ORDER BY peer_value ASC) AS rank_best_first,
        COUNT(*) OVER (PARTITION BY reporting_month)                         AS total_members
    FROM all_members
),
with_ranking AS (
    SELECT
        b.entity_id,
        b.reporting_month,
        b.metric_value,
        b.numerator,
        b.denominator,
        r.rank_best_first,
        r.total_members,
        ROUND(
            (r.total_members - r.rank_best_first) * 100.0
            / NULLIF(r.total_members - 1, 0), 1
        ) AS percentile
    FROM base_metric b
    LEFT JOIN ranked_members r
           ON r.entity_id       = b.entity_id
          AND r.reporting_month = b.reporting_month
)"""
    return all_members_cte + ranked_cte


def _cte_index(base_month: str) -> str:
    """Append a CTE that re-bases metric_value to 100 at base_month."""
    base_date = f"DATE '{_month_end(base_month)}'"
    return f"""
,
base_value AS (
    SELECT metric_value AS base_val
    FROM base_metric
    WHERE reporting_month = {base_date}
    LIMIT 1
),
with_index AS (
    SELECT
        b.entity_id,
        b.reporting_month,
        b.metric_value,
        b.numerator,
        b.denominator,
        100.0 * b.metric_value / NULLIF(bv.base_val, 0) AS index_value
    FROM base_metric b
    CROSS JOIN base_value bv
)"""


# ---------------------------------------------------------------------------
# Public compile() entry point
# ---------------------------------------------------------------------------

def compile(
    metric:       MetricDef,
    entity_id:    str,           # already resolved from claims ('self' → 'M07')
    product:      str,
    months:       list[str],     # ["2024-04", "2024-05", ...]
    bucket:       str | None     = None,
    at_or_worse:  bool           = True,
    lag_months:   int | None     = None,
    comparisons:  list[str]      = (),
    index_base_month: str | None = None,
) -> CompiledQuery:
    """Generate a complete governed SQL query for a metric + optional comparisons.

    Parameters
    ----------
    metric          MetricDef from the catalog.
    entity_id       Resolved entity ('M07', 'INDUSTRY' – never 'self').
    product         Product code validated against metric.applies_to.
    months          List of 'YYYY-MM' strings for the time window.
    bucket          DPD bucket override (uses metric.default_bucket if None).
    at_or_worse     Whether to use >= filter (uses metric.default_at_or_worse if None).
    lag_months      Lag override for LAGGED formula.
    comparisons     Subset of metric.comparisons_allowed to compute.
    index_base_month Required when 'index' in comparisons.

    Returns
    -------
    CompiledQuery with .sql (ready to execute) and .params (for lineage).
    """
    # ── resolve defaults from catalog ────────────────────────────────────
    bucket     = bucket     or metric.default_bucket or "b90"
    lag_months = lag_months or metric.default_lag_months or 3

    # ── build base metric CTE ────────────────────────────────────────────
    if metric.formula == FormulaType.COINCIDENCE:
        base_cte, params = _compile_coincidence(
            metric, entity_id, product, bucket, at_or_worse, months
        )
    elif metric.formula == FormulaType.LAGGED:
        base_cte, params = _compile_lagged(
            metric, entity_id, product, bucket, at_or_worse, lag_months, months
        )
    elif metric.formula == FormulaType.ROLL_RATE:
        base_cte, params = _compile_roll_rate(metric, entity_id, product, months)
    elif metric.formula == FormulaType.AVG_SCORE:
        base_cte, params = _compile_avg_score(
            metric, entity_id, product, bucket, at_or_worse, months
        )
    else:
        raise ValueError(f"Unsupported formula type: {metric.formula}")

    # ── layer comparison CTEs ────────────────────────────────────────────
    comparison_ctes = ""
    final_table = "base_metric"

    if "market_share" in comparisons:
        comparison_ctes += _cte_market_share(
            metric, product, bucket, at_or_worse, lag_months, months
        )
        final_table = "with_market_share"

    if "ranking" in comparisons:
        comparison_ctes += _cte_ranking(
            metric, product, bucket, at_or_worse, lag_months, months, entity_id
        )
        final_table = "with_ranking"

    if "index" in comparisons:
        if not index_base_month:
            raise ValueError("'index' comparison requires index_base_month")
        comparison_ctes += _cte_index(index_base_month)
        final_table = "with_index"

    # ── final SELECT ─────────────────────────────────────────────────────
    final_sql = (
        base_cte
        + comparison_ctes
        + f"\nSELECT * FROM {final_table} ORDER BY reporting_month"
    )

    # Determine result columns for the caller
    result_cols = ["entity_id", "reporting_month", "metric_value", "numerator", "denominator"]
    if "market_share" in comparisons:
        result_cols += ["industry_value", "market_share"]
    if "ranking" in comparisons:
        result_cols += ["rank_best_first", "total_members", "percentile"]
    if "index" in comparisons:
        result_cols += ["index_value"]

    params.update({
        "metric_id": metric.metric_id,
        "comparisons": list(comparisons),
        "index_base_month": index_base_month,
    })

    return CompiledQuery(sql=final_sql, params=params, result_cols=result_cols)
