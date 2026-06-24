"""Data-layer invariant tests (docs/07-evaluation.md).

These protect every downstream number. Marked skip until the generator lands.
"""

import pytest

pytestmark = pytest.mark.skip(reason="scaffold: generator not implemented yet")


def test_industry_equals_sum_of_members():
    """Industry == sum(members) per month/bucket in fact_delinquency."""
    raise NotImplementedError


def test_score_band_sums_to_delinquency():
    """sum(fact_score_band.num_accounts) == fact_delinquency.num_accounts per cell."""
    raise NotImplementedError


def test_bucket_cascade_is_plausible():
    """Counts fall off through worse buckets; no negative/NaN values."""
    raise NotImplementedError


def test_generation_is_reproducible():
    """Same GEN_SEED -> identical dataset hash."""
    raise NotImplementedError
