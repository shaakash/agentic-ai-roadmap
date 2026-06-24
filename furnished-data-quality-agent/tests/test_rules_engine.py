"""Tests for the deterministic rule engine and its checks."""

from __future__ import annotations

from datetime import date

from dq_agent.rules import checks
from dq_agent.rules.engine import run_batch
from dq_agent.rules.registry import active_rules
from dq_agent.schemas.record import FurnishedRecord, PortfolioType


def _record(**overrides) -> FurnishedRecord:
    base = dict(
        record_id="R1",
        batch_id="B1",
        furnisher_id="F1",
        consumer_id="C1",
        account_number="AC1",
        portfolio_type=PortfolioType.INSTALLMENT,
        date_opened=date(2020, 1, 1),
        date_reported=date(2023, 1, 1),
        date_closed=None,
        date_of_last_payment=date(2022, 12, 1),
        current_balance=1000.0,
        credit_limit=None,
        high_credit=5000.0,
        scheduled_monthly_payment=100.0,
        actual_payment_amount=100.0,
        account_status="11",
        payment_rating="0",
        months_reviewed=12,
        prior_balance=1100.0,
        prior_actual_payment_amount=100.0,
    )
    base.update(overrides)
    return FurnishedRecord(**base)


def test_clean_record_trips_nothing():
    assert run_batch([_record()]) == []


def test_dlp_before_open():
    r = _record(date_of_last_payment=date(2019, 6, 1))
    assert checks.dlp_before_open(r) is not None


def test_closed_before_open():
    r = _record(date_closed=date(2019, 6, 1), account_status="13", current_balance=0.0)
    assert checks.closed_before_open(r) is not None


def test_balance_drop_no_payment():
    r = _record(actual_payment_amount=0.0, prior_balance=2000.0, current_balance=1500.0)
    assert checks.balance_drop_no_payment(r) is not None


def test_balance_over_limit():
    r = _record(portfolio_type=PortfolioType.REVOLVING, credit_limit=1000.0, current_balance=2000.0)
    assert checks.balance_over_limit(r) is not None


def test_closed_with_balance():
    r = _record(account_status="13", current_balance=500.0)
    assert checks.closed_with_balance(r) is not None


def test_status_rating_mismatch():
    r = _record(account_status="11", payment_rating="3")
    assert checks.status_rating_mismatch(r) is not None


def test_invalid_status_code():
    assert checks.invalid_status_code(_record(account_status="ZZ")) is not None


def test_duplicate_detection_flags_second_row():
    r1 = _record(record_id="R1")
    r2 = _record(record_id="R2")  # identical key
    flagged = checks.duplicate_record([r1, r2])
    assert "R2" in flagged and "R1" not in flagged


def test_engine_emits_grounded_anomalies():
    r = _record(date_of_last_payment=date(2019, 6, 1))
    anomalies = run_batch([r])
    assert len(anomalies) == 1
    a = anomalies[0]
    assert a.rule_id == "T01"
    assert a.fields_involved and a.expected and a.observed


def test_active_rules_load():
    rules = active_rules()
    assert any(r.rule_id == "T01" for r in rules)
