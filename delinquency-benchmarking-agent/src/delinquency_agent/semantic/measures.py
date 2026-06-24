"""measures.py — superseded by catalog.py + compiler.py.

The original design had one Python function per SQL formula (sql_coincidence,
sql_lagged, sql_roll_rate, ...). That approach was replaced by the metric
catalog + compiler pattern to avoid the per-metric maintenance burden.

What lives where now
--------------------
  catalog.py   – metric definitions as structured data (MetricDef, CATALOG)
  compiler.py  – SQL generation from a MetricDef + QuerySpec (compile())
  metrics.py   – governed executor: validate → resolve → compile → run → suppress

This file is kept as a pointer so import paths that reference it produce a
helpful error rather than a silent ImportError.
"""


def sql_coincidence(*_, **__):  # type: ignore[no-untyped-def]
    raise RuntimeError(
        "sql_coincidence() is removed. Use semantic.compiler.compile() with a "
        "MetricDef from semantic.catalog.CATALOG['coincidence_os_pct'] instead."
    )


def sql_lagged(*_, **__):  # type: ignore[no-untyped-def]
    raise RuntimeError(
        "sql_lagged() is removed. Use semantic.compiler.compile() with a "
        "MetricDef from semantic.catalog.CATALOG['lagged_os_pct'] instead."
    )


def sql_roll_rate(*_, **__):  # type: ignore[no-untyped-def]
    raise RuntimeError(
        "sql_roll_rate() is removed. Use semantic.compiler.compile() with a "
        "MetricDef from semantic.catalog.CATALOG['roll_rate_30_60'] (etc.) instead."
    )


def build_sql(*_, **__):  # type: ignore[no-untyped-def]
    raise RuntimeError(
        "build_sql() is removed. Use semantic.compiler.compile() directly."
    )
