"""Metric catalog: loads MetricDef objects from metrics.yaml.

metrics.yaml is the single source of truth for business-logic metadata.
Adding a metric, supporting a new product, or changing a default requires
editing only that file — no Python changes needed.

Public interface (unchanged by the YAML migration):
    CATALOG          dict[str, MetricDef]  — all metrics keyed by metric_id
    get_metric(id)   → MetricDef           — raises KeyError with helpful message
    list_metrics(product?) → [MetricDef]  — optionally filtered by product
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml  # pyyaml


# ---------------------------------------------------------------------------
# Enums (still in code — the compiler imports these directly)
# ---------------------------------------------------------------------------

class FormulaType(str, Enum):
    """The three analytical lenses from docs/03-data-model.md."""
    COINCIDENCE = "coincidence"
    LAGGED      = "lagged"
    ROLL_RATE   = "roll_rate"
    AVG_SCORE   = "avg_score"


class MeasureCol(str, Enum):
    """Which column the formula aggregates."""
    NUM_ACCOUNTS = "num_accounts"
    OS_AMOUNT_MN = "os_amount_mn"


# ---------------------------------------------------------------------------
# MetricDef dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MetricDef:
    metric_id:           str
    label:               str
    formula:             FormulaType
    measure_col:         MeasureCol
    default_bucket:      str | None            = None
    default_at_or_worse: bool                  = True
    default_lag_months:  int | None            = None
    from_bucket:         str | None            = None
    to_bucket:           str | None            = None
    applies_to:          tuple[str, ...]       = ("credit_card",)
    comparisons_allowed: tuple[str, ...]       = ("market_share", "ranking", "index")


# ---------------------------------------------------------------------------
# YAML loader
# ---------------------------------------------------------------------------

_YAML_PATH = Path(__file__).parent / "metrics.yaml"


def _load_catalog(yaml_path: Path = _YAML_PATH) -> dict[str, MetricDef]:
    """Parse metrics.yaml and return a dict keyed by metric_id.

    Called once at module import. The YAML path can be overridden for testing.
    """
    with yaml_path.open(encoding="utf-8") as fh:
        raw: dict[str, Any] = yaml.safe_load(fh)

    catalog: dict[str, MetricDef] = {}
    for entry in raw.get("metrics", []):
        metric_id = entry["metric_id"]
        catalog[metric_id] = MetricDef(
            metric_id           = metric_id,
            label               = entry["label"],
            formula             = FormulaType(entry["formula"]),
            measure_col         = MeasureCol(entry["measure_col"]),
            default_bucket      = entry.get("default_bucket"),
            default_at_or_worse = entry.get("default_at_or_worse", True),
            default_lag_months  = entry.get("default_lag_months"),
            from_bucket         = entry.get("from_bucket"),
            to_bucket           = entry.get("to_bucket"),
            applies_to          = tuple(entry.get("applies_to", ["credit_card"])),
            comparisons_allowed = tuple(
                entry.get("comparisons_allowed", ["market_share", "ranking", "index"])
            ),
        )
    return catalog


# Module-level catalog — loaded once at import, shared across all callers.
CATALOG: dict[str, MetricDef] = _load_catalog()


# ---------------------------------------------------------------------------
# Public helpers (interface unchanged from the old hardcoded version)
# ---------------------------------------------------------------------------

def get_metric(metric_id: str) -> MetricDef:
    """Retrieve a metric definition or raise KeyError with a useful message."""
    if metric_id not in CATALOG:
        available = ", ".join(sorted(CATALOG))
        raise KeyError(
            f"Unknown metric_id '{metric_id}'. "
            f"Available (from metrics.yaml): {available}"
        )
    return CATALOG[metric_id]


def list_metrics(product: str | None = None) -> list[MetricDef]:
    """Return all metrics, optionally filtered to those applicable to a product."""
    metrics = list(CATALOG.values())
    if product:
        metrics = [m for m in metrics if product in m.applies_to]
    return metrics


def reload_catalog(yaml_path: Path = _YAML_PATH) -> None:
    """Force-reload the catalog from disk (useful after editing metrics.yaml
    without restarting the process — e.g. in a long-running API server)."""
    global CATALOG
    CATALOG = _load_catalog(yaml_path)
