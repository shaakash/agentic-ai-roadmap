"""Built-in, vetted check functions - the deterministic detection logic.

Each record-level check is a pure function `check(record) -> CheckResult | None`:
return a `CheckResult` if the record violates the rule, else `None`. Checks must be
deterministic and side-effect free so they are trivially unit-testable and so the
exact same logic can run in the eval harness.

Batch-level checks (e.g. duplicate detection) need to see the whole batch and live
at the bottom of this module with a different signature.

The mapping from a `check_ref` string (in rules.yaml) to a function lives in
`RECORD_CHECKS` / `BATCH_CHECKS` at the end.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from dq_agent.schemas.record import FurnishedRecord, PortfolioType

# Account-status codes we treat as "closed / paid" (simplified Metro 2).
CLOSED_STATUSES = {"13", "DA"}
# Account-status codes we treat as "current / paying as agreed".
CURRENT_STATUSES = {"11"}
# Payment ratings that indicate delinquency (1=30dpd, 2=60dpd, ...).
DELINQUENT_RATINGS = {"1", "2", "3", "4", "5", "6"}
ALLOWED_STATUSES = {"11", "71", "78", "80", "82", "83", "84", "93", "97", "13", "DA"}
ALLOWED_RATINGS = {"0", "1", "2", "3", "4", "5", "6", None}

# Tolerance for balance-over-limit before we flag (10%).
OVER_LIMIT_TOLERANCE = 0.10


@dataclass
class CheckResult:
    """A single rule violation on one record, fully grounded."""

    fields_involved: list[str]
    expected: str
    observed: str
    message: str
    extra: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Record-level checks
# --------------------------------------------------------------------------- #

def dlp_before_open(r: FurnishedRecord) -> CheckResult | None:
    """Date of last payment cannot precede the date the account was opened."""
    if r.date_of_last_payment and r.date_of_last_payment < r.date_opened:
        return CheckResult(
            fields_involved=["date_of_last_payment", "date_opened"],
            expected=f"date_of_last_payment >= date_opened ({r.date_opened})",
            observed=f"date_of_last_payment = {r.date_of_last_payment}",
            message="Last payment date is before the account open date.",
        )
    return None


def closed_before_open(r: FurnishedRecord) -> CheckResult | None:
    """An account cannot be closed before it was opened."""
    if r.date_closed and r.date_closed < r.date_opened:
        return CheckResult(
            fields_involved=["date_closed", "date_opened"],
            expected=f"date_closed >= date_opened ({r.date_opened})",
            observed=f"date_closed = {r.date_closed}",
            message="Closed date is before the account open date.",
        )
    return None


def reported_before_open(r: FurnishedRecord) -> CheckResult | None:
    """You cannot furnish an as-of date earlier than the account existed."""
    if r.date_reported < r.date_opened:
        return CheckResult(
            fields_involved=["date_reported", "date_opened"],
            expected=f"date_reported >= date_opened ({r.date_opened})",
            observed=f"date_reported = {r.date_reported}",
            message="Reported (as-of) date is before the account open date.",
        )
    return None


def dlp_after_reported(r: FurnishedRecord) -> CheckResult | None:
    """Last payment cannot be after the as-of (reported) date of the file."""
    if r.date_of_last_payment and r.date_of_last_payment > r.date_reported:
        return CheckResult(
            fields_involved=["date_of_last_payment", "date_reported"],
            expected=f"date_of_last_payment <= date_reported ({r.date_reported})",
            observed=f"date_of_last_payment = {r.date_of_last_payment}",
            message="Last payment date is after the reported (as-of) date.",
        )
    return None


def balance_drop_no_payment(r: FurnishedRecord) -> CheckResult | None:
    """Balance fell versus the prior cycle but no payment was reported.

    With no payment, a balance should hold or grow (interest/fees) - a drop with
    zero payment is internally inconsistent.
    """
    if r.prior_balance is None:
        return None
    no_payment = not r.actual_payment_amount  # None or 0
    if no_payment and r.current_balance < r.prior_balance:
        return CheckResult(
            fields_involved=["current_balance", "prior_balance", "actual_payment_amount"],
            expected=f"current_balance >= prior_balance ({r.prior_balance}) when no payment made",
            observed=(
                f"current_balance = {r.current_balance}, "
                f"actual_payment_amount = {r.actual_payment_amount}"
            ),
            message="Balance decreased with no payment reported this cycle.",
        )
    return None


def balance_over_limit(r: FurnishedRecord) -> CheckResult | None:
    """Revolving balance materially exceeds the stated credit limit."""
    if r.portfolio_type != PortfolioType.REVOLVING or not r.credit_limit:
        return None
    ceiling = r.credit_limit * (1 + OVER_LIMIT_TOLERANCE)
    if r.current_balance > ceiling:
        return CheckResult(
            fields_involved=["current_balance", "credit_limit"],
            expected=f"current_balance <= credit_limit*{1 + OVER_LIMIT_TOLERANCE:.2f} ({ceiling:.0f})",
            observed=f"current_balance = {r.current_balance}, credit_limit = {r.credit_limit}",
            message="Revolving balance exceeds the credit limit beyond tolerance.",
        )
    return None


def closed_with_balance(r: FurnishedRecord) -> CheckResult | None:
    """A closed / paid account should not carry a positive balance."""
    if r.account_status in CLOSED_STATUSES and r.current_balance > 0:
        return CheckResult(
            fields_involved=["account_status", "current_balance"],
            expected="current_balance == 0 when account_status is closed/paid",
            observed=f"account_status = {r.account_status}, current_balance = {r.current_balance}",
            message="Account is closed/paid but still reports a positive balance.",
        )
    return None


def status_rating_mismatch(r: FurnishedRecord) -> CheckResult | None:
    """Status says current, but the payment rating says delinquent."""
    if r.account_status in CURRENT_STATUSES and r.payment_rating in DELINQUENT_RATINGS:
        return CheckResult(
            fields_involved=["account_status", "payment_rating"],
            expected="payment_rating indicates current (0) when account_status is current (11)",
            observed=f"account_status = {r.account_status}, payment_rating = {r.payment_rating}",
            message="Account status is current but the payment rating shows delinquency.",
        )
    return None


def invalid_status_code(r: FurnishedRecord) -> CheckResult | None:
    """Account status / payment rating must be within the allowed code domain."""
    bad_status = r.account_status not in ALLOWED_STATUSES
    bad_rating = r.payment_rating not in ALLOWED_RATINGS
    if bad_status or bad_rating:
        return CheckResult(
            fields_involved=["account_status", "payment_rating"],
            expected="account_status and payment_rating within the allowed code set",
            observed=f"account_status = {r.account_status}, payment_rating = {r.payment_rating}",
            message="Account status or payment rating is outside the allowed code domain.",
        )
    return None


# --------------------------------------------------------------------------- #
# Batch-level checks
# --------------------------------------------------------------------------- #

def duplicate_record(records: list[FurnishedRecord]) -> dict[str, CheckResult]:
    """Detect duplicate / double-counted rows within a batch.

    Two rows are considered duplicates when consumer, account, as-of date and
    balance all match. Returns a map of record_id -> CheckResult for every record
    that is part of a duplicate group (the first occurrence is treated as canonical
    and not flagged).
    """
    seen: dict[tuple, str] = {}
    flagged: dict[str, CheckResult] = {}
    for r in records:
        key = (r.consumer_id, r.account_number, r.date_reported, round(r.current_balance, 2))
        if key in seen:
            flagged[r.record_id] = CheckResult(
                fields_involved=["consumer_id", "account_number", "date_reported", "current_balance"],
                expected="each (consumer, account, as-of date, balance) reported once per batch",
                observed=f"duplicate of record {seen[key]}",
                message="Duplicate account row within the same batch.",
                extra={"duplicate_of": seen[key]},
            )
        else:
            seen[key] = r.record_id
    return flagged


# --------------------------------------------------------------------------- #
# check_ref -> function maps (referenced from rules.yaml)
# --------------------------------------------------------------------------- #

RECORD_CHECKS = {
    "dlp_before_open": dlp_before_open,
    "closed_before_open": closed_before_open,
    "reported_before_open": reported_before_open,
    "dlp_after_reported": dlp_after_reported,
    "balance_drop_no_payment": balance_drop_no_payment,
    "balance_over_limit": balance_over_limit,
    "closed_with_balance": closed_with_balance,
    "status_rating_mismatch": status_rating_mismatch,
    "invalid_status_code": invalid_status_code,
}

BATCH_CHECKS = {
    "duplicate_record": duplicate_record,
}
