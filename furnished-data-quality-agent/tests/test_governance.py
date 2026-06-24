"""Governance controls: generated-code static review, grounding, sandbox scoring."""

from __future__ import annotations

from datetime import date

from dq_agent.guardrails.codereview import review_generated_code
from dq_agent.guardrails.grounding import check_grounding
from dq_agent.rules.engine import run_batch
from dq_agent.sandbox.validate import compute_metrics
from dq_agent.schemas.record import FurnishedRecord, PortfolioType

SAFE_CODE = """
def check(record):
    if record.date_closed and record.date_closed < record.date_opened:
        return True
    return False
"""

UNSAFE_IMPORT = """
import os
def check(record):
    os.system("echo hi")
    return True
"""

UNSAFE_DUNDER = """
def check(record):
    return record.__class__ is not None
"""


def test_codereview_accepts_safe_check():
    assert review_generated_code(SAFE_CODE).ok


def test_codereview_rejects_import():
    v = review_generated_code(UNSAFE_IMPORT)
    assert not v.ok


def test_codereview_rejects_dunder():
    v = review_generated_code(UNSAFE_DUNDER)
    assert not v.ok


def test_grounding_flags_invented_number():
    r = FurnishedRecord(
        record_id="R1", batch_id="B1", furnisher_id="F1", consumer_id="C1", account_number="AC1",
        portfolio_type=PortfolioType.INSTALLMENT, date_opened=date(2020, 1, 1),
        date_reported=date(2023, 1, 1), date_of_last_payment=date(2019, 1, 1),
        current_balance=1000.0, high_credit=5000.0, account_status="11", payment_rating="0",
    )
    anomaly = run_batch([r])[0]
    bad = check_grounding(anomaly, "The balance was actually 99999 which is wrong.")
    assert not bad.ok and "99999" in bad.ungrounded_numbers

    good = check_grounding(anomaly, "Last payment predates the open date; please correct.")
    assert good.ok


def test_compute_metrics_perfect():
    report = compute_metrics(
        predicted_record_ids={"R1", "R2"},
        target_rule_id="X99",
        labels={"R1": "X99", "R2": "X99", "R3": "other"},
        total_records=3,
    )
    assert report.precision == 1.0 and report.recall == 1.0
