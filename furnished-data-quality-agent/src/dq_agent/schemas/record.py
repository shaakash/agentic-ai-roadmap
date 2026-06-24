"""The furnished credit record (a simplified, Metro 2-inspired account file).

Furnishers (lenders) report each account to the aggregator on a periodic cycle.
A *batch* is one furnisher's file for one cycle. These are the fields our rules
reason over. All synthetic.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, Field


class PortfolioType(str, Enum):
    """Metro 2-style portfolio type."""

    INSTALLMENT = "I"   # fixed term, amortizing (auto, personal loan)
    REVOLVING = "R"     # credit card / line of credit
    MORTGAGE = "M"      # mortgage
    OPEN = "O"          # open account, balance due in full


class FurnishedRecord(BaseModel):
    """One account, as furnished in one reporting cycle."""

    record_id: str
    batch_id: str
    furnisher_id: str
    consumer_id: str                       # synthetic pseudo-id
    account_number: str                    # synthetic / masked

    portfolio_type: PortfolioType
    date_opened: date
    date_reported: date                    # the "as of" date of this furnishing
    date_closed: date | None = None
    date_of_last_payment: date | None = None

    current_balance: float = Field(ge=0)
    credit_limit: float | None = Field(default=None, ge=0)
    high_credit: float | None = Field(default=None, ge=0)
    scheduled_monthly_payment: float | None = Field(default=None, ge=0)
    actual_payment_amount: float | None = Field(default=None, ge=0)

    # Status / rating (simplified Metro 2 account status codes)
    account_status: str                    # e.g. "11" current, "71" 30dpd, "DA" closed
    payment_rating: str | None = None      # e.g. "0" current, "1" 30dpd, ...
    months_reviewed: int | None = Field(default=None, ge=0)

    # Prior-cycle context the engine needs for progression checks (denormalized in
    # synthetic data; in production this comes from the previous furnishing).
    prior_balance: float | None = Field(default=None, ge=0)
    prior_actual_payment_amount: float | None = Field(default=None, ge=0)


class Batch(BaseModel):
    """One furnisher's file for one reporting cycle."""

    batch_id: str
    furnisher_id: str
    received_at: datetime
    record_count: int = Field(ge=0)
    # File-level metadata a real system would carry (cycle, format version, etc.)
    cycle: str | None = None
    format_version: str = "metro2-like-0.1"
