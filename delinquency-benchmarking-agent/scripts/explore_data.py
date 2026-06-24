"""Data-model walkthrough script.

Generates the synthetic dataset (in-memory DuckDB) and walks through:

  PART 0 – TABLE TOUR
    Individual row samples from every table + relationship drill-downs
    showing exactly how the foreign keys connect.

  PART 1 – EXAMPLES (end-to-end analytical queries)
    Example 1 – COINCIDENCE VIEW
      "What is Member 07's 90+ DPD outstanding share vs Industry in June 2024,
       and what is their market share?"
    Example 2 – ROLL-RATE VIEW
      "What was the 30→60 roll rate for Industry across the panel,
       and which month had the highest roll rate?"
    Example 3 – RANKING / BENCHMARK
      "Where does Member 07 rank on 90+ DPD O/S rate among all members
       in June 2024, and which score-band makes up most of their 90+ book?"

Run:
    cd delinquency-benchmarking-agent
    python scripts/explore_data.py
"""

from __future__ import annotations

import sys
import os

# Make the src package importable without pip install
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from delinquency_agent.data.generate import GenConfig, generate_all
from delinquency_agent.data.load import connect, create_schema, load_all

# ── helpers ─────────────────────────────────────────────────────────────────

def _header(text: str) -> None:
    width = 72
    print()
    print("=" * width)
    print(f"  {text}")
    print("=" * width)


def _section(text: str) -> None:
    print()
    print(f"  ── {text}")
    print()


def _table(rows: list[tuple], headers: list[str], col_widths: list[int] | None = None) -> None:
    if not rows:
        print("  (no rows)")
        return
    if col_widths is None:
        col_widths = [
            max(len(str(h)), max(len(str(r[i])) for r in rows))
            for i, h in enumerate(headers)
        ]
    fmt = "  " + "  ".join(f"{{:<{w}}}" for w in col_widths)
    sep = "  " + "  ".join("-" * w for w in col_widths)
    print(fmt.format(*headers))
    print(sep)
    for row in rows:
        print(fmt.format(*[str(x) for x in row]))


def _pct(value: float, decimals: int = 2) -> str:
    return f"{value * 100:.{decimals}f}%"


# ── setup ────────────────────────────────────────────────────────────────────

def setup_db():
    cfg = GenConfig(seed=42, start_month="2023-01", num_months=24, num_members=18)
    print(f"Generating synthetic panel: {cfg.num_months} months, {cfg.num_members} members...")
    tables = generate_all(cfg)

    total = sum(len(v) for v in tables.items() if isinstance(v, list))
    fact_delq = len(tables["fact_delinquency"])
    fact_band = len(tables["fact_score_band"])
    print(f"  fact_delinquency rows : {fact_delq:,}  "
          f"({cfg.num_members + 1} entities × {cfg.num_months} months × 9 buckets)")
    print(f"  fact_score_band rows  : {fact_band:,}  (same × 11 bands)")

    conn = connect(":memory:")  # in-memory; no file written for this walkthrough
    create_schema(conn)
    load_all(conn, tables)
    print("  Loaded into in-memory DuckDB. Ready.")
    return conn


# ── PART 0: Table tour ───────────────────────────────────────────────────

def part0_table_tour(conn) -> None:
    _header("PART 0 – TABLE TOUR  (individual samples + relationships)")

    # ── 0.1 dim_entity ────────────────────────────────────────────────────
    _section("Table 1 of 6 – dim_entity")
    print("""
  Purpose : Every entity that ever appears in a fact row lives here first.
            An entity is either the whole market ("INDUSTRY") or one lender
            ("member").  The fact tables reference this via entity_id (FK).

  Grain   : One row per entity.
""")
    rows = conn.execute("""
        SELECT entity_id, entity_type, display_name
        FROM dim_entity
        ORDER BY entity_type DESC, entity_id
        LIMIT 6
    """).fetchall()
    _table(rows, ["entity_id", "entity_type", "display_name"])

    total = conn.execute("SELECT COUNT(*) FROM dim_entity").fetchone()[0]
    print(f"\n  (showing 6 of {total} rows: 1 industry + {total-1} members)\n")

    print("""  Key design decision:
  ┌──────────────────────────────────────────────────────────────────┐
  │  INDUSTRY is stored as a regular entity, not a computed view.   │
  │  The generator guarantees INDUSTRY = SUM(members) per month/    │
  │  bucket, so queries don't need runtime aggregation for it.      │
  └──────────────────────────────────────────────────────────────────┘
""")

    # ── 0.2 dim_month ─────────────────────────────────────────────────────
    _section("Table 2 of 6 – dim_month")
    print("""
  Purpose : Every reporting snapshot date. month_index (0-based offset
            from the first generated month) is used for lag arithmetic:
            "3 months ago" = month_index - 3, no date math needed.

  Grain   : One row per month-end date.
""")
    rows = conn.execute("""
        SELECT reporting_month, year, month, month_index
        FROM dim_month
        ORDER BY month_index
        LIMIT 6
    """).fetchall()
    _table(rows, ["reporting_month", "year", "month", "month_index"])

    total = conn.execute("SELECT COUNT(*) FROM dim_month").fetchone()[0]
    print(f"\n  ... and {total - 6} more months (through {conn.execute('SELECT MAX(reporting_month) FROM dim_month').fetchone()[0]})\n")

    print("""  How month_index is used in roll-rate queries:
      JOIN dim_month curr  ON curr.reporting_month = f.reporting_month
      JOIN dim_month prev  ON prev.month_index     = curr.month_index - 1
  No DATEADD or interval arithmetic; always exact.
""")

    # ── 0.3 dim_dpd_bucket ────────────────────────────────────────────────
    _section("Table 3 of 6 – dim_dpd_bucket")
    print("""
  Purpose : The 9 atomic delinquency buckets in progression order.
            sort_order drives the "at or worse" filter:
            "90+" = WHERE sort_order >= 4.
            is_writeoff flags the terminal charge-off bucket.

  Grain   : One row per bucket.
""")
    rows = conn.execute("""
        SELECT bucket_id, sort_order, dpd_low, dpd_high, is_writeoff
        FROM dim_dpd_bucket
        ORDER BY sort_order
    """).fetchall()
    _table(rows, ["bucket_id", "sort_order", "dpd_low", "dpd_high", "is_writeoff"])

    print("""
  Reading the sort_order column:
    current       = 0   → no days overdue
    x_day         = 1   → 1–29 days (informal "X-day" bucket)
    b30 ... b150  = 2–6 → 30-day steps
    b180_plus     = 7   → 180 or more days (open-ended)
    newly_writeoff= 8   → charged off this period (terminal)

  "90+ DPD" in a query becomes:  dpd_bucket IN ('b90','b120','b150','b180_plus','newly_writeoff')
  Or equivalently via the join:  d.sort_order >= 4
""")

    # ── 0.4 dim_score_band ────────────────────────────────────────────────
    _section("Table 4 of 6 – dim_score_band")
    print("""
  Purpose : Risk-score bands from AA (best) to JJ (worst), plus NS
            (no score).  Used only by fact_score_band to break down
            each bucket's accounts by the borrower's risk score.

  Grain   : One row per band.
""")
    rows = conn.execute("""
        SELECT band_id, sort_order, score_low, score_high
        FROM dim_score_band
        ORDER BY sort_order
    """).fetchall()
    _table(rows, ["band_id", "sort_order", "score_low", "score_high"])

    print("""
  Rule: worse bucket → accounts concentrate in worse bands (GG–JJ).
        current bucket → accounts concentrate in better bands (AA–CC).
        This is enforced by the generator using a Gaussian distribution
        centred on a bucket's mean score.
""")

    # ── 0.5 fact_delinquency ──────────────────────────────────────────────
    _section("Table 5 of 6 – fact_delinquency  (the primary fact)")
    print("""
  Purpose : Aggregate snapshot of account counts and outstanding (O/S)
            for every entity × month × product × bucket combination.
            Also stores average risk scores for the cohort (current +
            3 lags) to support lagged-score analysis.

  Grain   : 1 row per (entity_id, reporting_month, product, dpd_bucket).
  Scale   : 19 entities × 24 months × 9 buckets = 4,104 rows total.

  ALL NUMBERS ARE AGGREGATES. No account-level or consumer-level data.
""")

    # Show a single entity/month slice so the reader sees all 9 buckets
    rows = conn.execute("""
        SELECT
            f.entity_id,
            f.reporting_month,
            f.dpd_bucket,
            f.num_accounts,
            ROUND(f.os_amount_mn, 2)  AS os_mn,
            ROUND(f.avg_score, 0)     AS avg_score,
            ROUND(f.avg_score_lag1,0) AS score_1m_ago,
            ROUND(f.avg_score_lag3,0) AS score_3m_ago
        FROM fact_delinquency f
        JOIN dim_dpd_bucket d ON d.bucket_id = f.dpd_bucket
        WHERE f.entity_id = 'M07'
          AND f.reporting_month = DATE '2024-06-30'
          AND f.product = 'credit_card'
        ORDER BY d.sort_order
    """).fetchall()
    _table(rows, ["entity", "month", "bucket", "accounts", "O/S $M",
                  "avg_score", "score_1m_ago", "score_3m_ago"])

    print("""
  Column notes:
  ┌──────────────────┬──────────────────────────────────────────────────┐
  │  num_accounts    │ active accounts in this bucket this month        │
  │  os_amount_mn    │ outstanding balance, millions USD                │
  │  avg_score       │ mean risk score of those accounts now            │
  │  avg_score_lag1  │ mean score of the SAME cohort 1 month ago        │
  │  avg_score_lag3  │ mean score of the SAME cohort 3 months ago       │
  └──────────────────┴──────────────────────────────────────────────────┘

  Observation: avg_score_lag3 > avg_score  (e.g. ~634 vs ~598 for b90).
  This makes sense: accounts now in b90 had better scores 3 months ago,
  before they deteriorated through b30 → b60 → b90.
""")

    # ── 0.6 fact_score_band ───────────────────────────────────────────────
    _section("Table 6 of 6 – fact_score_band  (the score-mix fact)")
    print("""
  Purpose : Breaks each fact_delinquency cell down by score band.
            Answers "what is the risk-score composition of M07's b90 book?"

  Grain   : 1 row per (entity_id, reporting_month, product, dpd_bucket, score_band).
  Scale   : ~40,000 rows  (fact_delinquency rows × up to 11 bands each).

  Key invariant: SUM(fact_score_band.num_accounts) per (entity, month, bucket)
                 must equal fact_delinquency.num_accounts for the same cell.
""")

    rows = conn.execute("""
        SELECT
            sb.score_band,
            db.sort_order,
            sb.num_accounts,
            ROUND(sb.os_amount_mn, 3) AS os_mn,
            ROUND(sb.num_accounts * 100.0
                  / SUM(sb.num_accounts) OVER (), 1) AS pct
        FROM fact_score_band sb
        JOIN dim_score_band db ON db.band_id = sb.score_band
        WHERE sb.entity_id = 'M07'
          AND sb.reporting_month = DATE '2024-06-30'
          AND sb.product   = 'credit_card'
          AND sb.dpd_bucket = 'b90'
        ORDER BY db.sort_order
    """).fetchall()
    _table(rows, ["score_band", "sort_order", "accounts", "O/S $M", "% of b90"])

    # Verify the invariant live
    fact_n = conn.execute("""
        SELECT num_accounts FROM fact_delinquency
        WHERE entity_id='M07' AND reporting_month=DATE '2024-06-30'
          AND product='credit_card' AND dpd_bucket='b90'
    """).fetchone()[0]
    band_n = conn.execute("""
        SELECT SUM(num_accounts) FROM fact_score_band
        WHERE entity_id='M07' AND reporting_month=DATE '2024-06-30'
          AND product='credit_card' AND dpd_bucket='b90'
    """).fetchone()[0]
    match = "✓ MATCH" if fact_n == band_n else "✗ MISMATCH"
    print(f"\n  Invariant check for M07 / Jun-2024 / b90:")
    print(f"    fact_delinquency.num_accounts = {fact_n:,}")
    print(f"    SUM(fact_score_band.num_accounts) = {band_n:,}   {match}")

    # ── 0.7 Relationships: how the tables join ─────────────────────────────
    _header("PART 0 – RELATIONSHIPS BETWEEN TABLES")
    print("""
  Schema diagram (simplified):

      dim_entity ──────────────────────────────────────────────────┐
         entity_id (PK)                                            │
                                                                   │
      dim_month  ──────────────────────────────────────────────────┤
         reporting_month (PK)                                      │
         month_index   ← used for lag joins (month_index - N)     │
                                                                   ↓
      dim_product                              fact_delinquency ───┤
         product_id (PK) ──────────────────→   entity_id      (FK)│
                                               reporting_month (FK)│
      dim_dpd_bucket                           product        (FK) │
         bucket_id (PK)  ──────────────────→   dpd_bucket     (FK)│
         sort_order       ← "at or worse"      num_accounts       │
                                               os_amount_mn       │
      dim_score_band                           avg_score          │
         band_id (PK)    ──────────┐           avg_score_lag1/2/3 │
         sort_order                │                               │
                                   ↓                               │
                          fact_score_band ←────────────────────────┘
                             entity_id      (FK → dim_entity)
                             reporting_month(FK → dim_month)
                             product        (FK → dim_product)
                             dpd_bucket     (FK → dim_dpd_bucket)
                             score_band     (FK → dim_score_band)
                             num_accounts
                             os_amount_mn

  Key relationships to remember:

  1.  fact_delinquency  ←(1:N)→  fact_score_band
      One delinquency cell (entity/month/bucket) expands into up to 11
      score-band rows. SUM(fact_score_band) = fact_delinquency per cell.

  2.  dim_entity: INDUSTRY row
      INDUSTRY is not stored separately — it IS a regular entity_id in
      fact_delinquency. Its values = exact SUM of all member rows.

  3.  dim_month.month_index → lag arithmetic
      roll_rate(t) joins  prev ON prev.month_index = curr.month_index - 1
      lagged_pct(t, N) joins base ON base.month_index = curr.month_index - N

  4.  dim_dpd_bucket.sort_order → "at or worse" filter
      "90+ dpd" = WHERE sort_order >= 4   (no hardcoded list of bucket names)
""")

    # Live join demo: fact_delinquency + dim_entity + dim_dpd_bucket
    _section("Live join demo – fact_delinquency + all dimension tables for one cell")
    print("""  Query: pull all dimension labels for a single fact row to see what
  a fully-joined row looks like. This is what the semantic layer does
  before computing rates.
""")
    rows = conn.execute("""
        SELECT
            e.entity_id,
            e.entity_type,
            m.reporting_month,
            m.month_index,
            p.product_id,
            p.display_name   AS product_name,
            d.bucket_id,
            d.sort_order     AS bucket_order,
            d.dpd_low,
            d.dpd_high,
            f.num_accounts,
            ROUND(f.os_amount_mn, 2) AS os_mn,
            ROUND(f.avg_score, 0)    AS avg_score
        FROM fact_delinquency f
        JOIN dim_entity       e ON e.entity_id       = f.entity_id
        JOIN dim_month        m ON m.reporting_month = f.reporting_month
        JOIN dim_product      p ON p.product_id      = f.product
        JOIN dim_dpd_bucket   d ON d.bucket_id       = f.dpd_bucket
        WHERE f.entity_id = 'M07'
          AND f.reporting_month = DATE '2024-06-30'
          AND f.dpd_bucket = 'b90'
    """).fetchall()
    _table(rows,
           ["entity_id","entity_type","month","idx","product","product_name",
            "bucket","order","dpd_lo","dpd_hi","accounts","O/S $M","avg_score"])

    print("""
  Every column needed to answer "M07, June 2024, 90-dpd" is right there.
  The semantic layer adds one more step: compute the RATE by dividing this
  row's os_amount_mn by the SUM across all buckets for M07/Jun-2024.
""")


# ── Example 1: Coincidence view ───────────────────────────────────────────

def example1_coincidence(conn) -> None:
    _header("EXAMPLE 1 – COINCIDENCE (SNAPSHOT) VIEW")
    print("""
  Question: "What is Member 07's 90+ DPD outstanding share vs Industry in
             June 2024, and what is their market share of industry 90+ O/S?"

  This is the most common benchmarking question. We:
    1. Look at a single month (June 2024).
    2. For each entity, compute 90+ dpd O/S share = sum(os for buckets >= b90) /
       sum(os for ALL buckets).  <-- this is the COINCIDENCE formula.
    3. Derive market share = member value / industry value.
""")

    TARGET_MONTH = "2024-06-30"
    MEMBER = "M07"
    AT_OR_WORSE_BUCKETS = "('b90','b120','b150','b180_plus','newly_writeoff')"

    _section("Step 1 – Raw fact_delinquency rows for M07 in June 2024")
    q1 = f"""
        SELECT
            dpd_bucket,
            d.sort_order,
            f.num_accounts,
            ROUND(f.os_amount_mn, 2) AS os_mn
        FROM fact_delinquency f
        JOIN dim_dpd_bucket d USING (bucket_id = dpd_bucket)
        WHERE f.entity_id = '{MEMBER}'
          AND f.reporting_month = DATE '{TARGET_MONTH}'
          AND f.product = 'credit_card'
        ORDER BY d.sort_order
    """
    # DuckDB USING doesn't support that syntax; use explicit ON
    q1 = f"""
        SELECT
            f.dpd_bucket,
            d.sort_order,
            f.num_accounts,
            ROUND(f.os_amount_mn, 2) AS os_mn
        FROM fact_delinquency f
        JOIN dim_dpd_bucket d ON d.bucket_id = f.dpd_bucket
        WHERE f.entity_id = '{MEMBER}'
          AND f.reporting_month = DATE '{TARGET_MONTH}'
          AND f.product = 'credit_card'
        ORDER BY d.sort_order
    """
    rows = conn.execute(q1).fetchall()
    _table(rows, ["bucket", "sort_order", "num_accounts", "os_mn ($M)"])

    _section("Step 2 – Compute 90+ DPD O/S coincidence rate for M07 and Industry")
    q2 = f"""
        SELECT
            f.entity_id,
            ROUND(
                SUM(CASE WHEN f.dpd_bucket IN {AT_OR_WORSE_BUCKETS} THEN f.os_amount_mn ELSE 0 END)
                / NULLIF(SUM(f.os_amount_mn), 0)
                * 100, 4
            ) AS dpd90_plus_os_pct,
            ROUND(
                SUM(CASE WHEN f.dpd_bucket IN {AT_OR_WORSE_BUCKETS} THEN f.os_amount_mn ELSE 0 END),
                2
            ) AS os_90plus_mn,
            ROUND(SUM(f.os_amount_mn), 2) AS total_os_mn
        FROM fact_delinquency f
        WHERE f.entity_id IN ('{MEMBER}', 'INDUSTRY')
          AND f.reporting_month = DATE '{TARGET_MONTH}'
          AND f.product = 'credit_card'
        GROUP BY f.entity_id
        ORDER BY f.entity_id
    """
    rows = conn.execute(q2).fetchall()
    _table(rows, ["entity", "90+ dpd O/S %", "90+ O/S ($M)", "Total O/S ($M)"])

    # Parse for market share
    m07_row = next((r for r in rows if r[0] == MEMBER), None)
    ind_row  = next((r for r in rows if r[0] == "INDUSTRY"), None)

    if m07_row and ind_row and ind_row[2]:
        mkt_share = m07_row[2] / ind_row[2] * 100
        _section("Step 3 – Market share and interpretation")
        print(f"  M07 90+ O/S rate  : {m07_row[1]}%")
        print(f"  Industry 90+ rate : {ind_row[1]}%")
        print(f"  M07 market share of 90+ O/S: {mkt_share:.2f}%")
        print()
        m07_val = float(m07_row[1])
        ind_val = float(ind_row[1])
        if m07_val < ind_val:
            print(f"  → M07 is BELOW industry average by "
                  f"{ind_val - m07_val:.4f}pp. Healthier than peers on this measure.")
        else:
            print(f"  → M07 is ABOVE industry average by "
                  f"{m07_val - ind_val:.4f}pp. Runs hotter than peers on this measure.")

    print("""
  What happened:
  ┌─────────────────────────────────────────────────────────────────┐
  │  Data path: fact_delinquency → bucket filter → aggregate SUM   │
  │  Formula:   os(b90..writeoff) / os(all buckets)  × 100         │
  │  No LLM involved. The semantic layer runs exactly this SQL.     │
  └─────────────────────────────────────────────────────────────────┘
""")


# ── Example 2: Roll-rate view ─────────────────────────────────────────────

def example2_roll_rate(conn) -> None:
    _header("EXAMPLE 2 – ROLL-RATE (FLOW) VIEW")
    print("""
  Question: "What was the 30→60 roll rate for Industry across the 24-month
             panel, and which month had the highest roll rate?"

  Roll rate = accounts in bucket B at month t  /  accounts in bucket B-1
              at month t-1.  It measures the FLOW of accounts into the next
              worse bucket.  A rising roll rate is an early warning signal.

  Here: roll_rate_30_60(t) = num_accounts(INDUSTRY, b60, t)
                              / num_accounts(INDUSTRY, b30, t-1)
""")

    _section("Step 1 – Raw counts: INDUSTRY b30 and b60 (first 6 months)")
    q3 = """
        SELECT
            m.reporting_month,
            SUM(CASE WHEN f.dpd_bucket = 'b30' THEN f.num_accounts ELSE 0 END) AS b30_accts,
            SUM(CASE WHEN f.dpd_bucket = 'b60' THEN f.num_accounts ELSE 0 END) AS b60_accts
        FROM fact_delinquency f
        JOIN dim_month m ON m.reporting_month = f.reporting_month
        WHERE f.entity_id = 'INDUSTRY'
          AND f.product = 'credit_card'
          AND f.dpd_bucket IN ('b30', 'b60')
        GROUP BY m.reporting_month, m.month_index
        ORDER BY m.month_index
        LIMIT 6
    """
    rows = conn.execute(q3).fetchall()
    _table(rows, ["month", "b30 accounts", "b60 accounts"])

    _section("Step 2 – 30→60 roll rate across all months (lag join)")
    q4 = """
        WITH monthly_counts AS (
            SELECT
                m.reporting_month,
                m.month_index,
                SUM(CASE WHEN f.dpd_bucket = 'b30' THEN f.num_accounts ELSE 0 END) AS b30_n,
                SUM(CASE WHEN f.dpd_bucket = 'b60' THEN f.num_accounts ELSE 0 END) AS b60_n
            FROM fact_delinquency f
            JOIN dim_month m ON m.reporting_month = f.reporting_month
            WHERE f.entity_id = 'INDUSTRY'
              AND f.product = 'credit_card'
              AND f.dpd_bucket IN ('b30', 'b60')
            GROUP BY m.reporting_month, m.month_index
        )
        SELECT
            curr.reporting_month,
            prev.b30_n                              AS prior_b30,
            curr.b60_n                              AS curr_b60,
            ROUND(curr.b60_n * 100.0 / NULLIF(prev.b30_n, 0), 2) AS roll_rate_pct
        FROM monthly_counts curr
        JOIN monthly_counts prev ON prev.month_index = curr.month_index - 1
        ORDER BY curr.month_index
    """
    rows = conn.execute(q4).fetchall()
    _table(rows, ["month", "prior b30", "curr b60", "roll rate %"])

    # Find worst month
    if rows:
        worst = max(rows, key=lambda r: float(r[3]) if r[3] else 0)
        _section("Step 3 – Worst roll-rate month")
        print(f"  Worst 30→60 roll rate: {worst[3]}% in {worst[0]}")
        print(f"  Accounts in b30 prior month : {worst[1]:,}")
        print(f"  Accounts in b60 this month  : {worst[2]:,}")
        print()
        best = min(rows, key=lambda r: float(r[3]) if r[3] else 999)
        print(f"  Best  30→60 roll rate: {best[3]}% in {best[0]}   (seasonal trough)")

    print("""
  What happened:
  ┌─────────────────────────────────────────────────────────────────┐
  │  Data path: self-join of fact_delinquency on month_index lag=1  │
  │  Formula:   b60(t) / b30(t-1)  × 100                           │
  │  Seasonal + trend signal is visible in the series.             │
  └─────────────────────────────────────────────────────────────────┘
""")


# ── Example 3: Ranking / Benchmark ───────────────────────────────────────

def example3_ranking(conn) -> None:
    _header("EXAMPLE 3 – RANKING + SCORE-BAND BREAKDOWN")
    print("""
  Question: "Where does M07 rank on 90+ DPD O/S rate among all 18 members
             in June 2024? And what score band makes up most of their 90+ book?"

  Ranking = position of M07's rate among all member rates (1 = best = lowest).
  Score band = from fact_score_band, sum b90+ accounts/O/S by band for M07.
""")

    TARGET_MONTH = "2024-06-30"
    MEMBER = "M07"
    AT_OR_WORSE = "('b90','b120','b150','b180_plus','newly_writeoff')"

    _section("Step 1 – All 18 members ranked by 90+ DPD O/S rate (June 2024)")
    q5 = f"""
        SELECT
            entity_id,
            ROUND(
                SUM(CASE WHEN dpd_bucket IN {AT_OR_WORSE} THEN os_amount_mn ELSE 0 END)
                / NULLIF(SUM(os_amount_mn), 0) * 100, 4
            ) AS rate_pct,
            RANK() OVER (
                ORDER BY
                    SUM(CASE WHEN dpd_bucket IN {AT_OR_WORSE} THEN os_amount_mn ELSE 0 END)
                    / NULLIF(SUM(os_amount_mn), 0) ASC
            ) AS rank_best_first
        FROM fact_delinquency
        WHERE entity_id != 'INDUSTRY'
          AND reporting_month = DATE '{TARGET_MONTH}'
          AND product = 'credit_card'
        GROUP BY entity_id
        ORDER BY rate_pct ASC
    """
    rows = conn.execute(q5).fetchall()
    # Highlight M07
    display = [(r[0], r[1], r[2], "<-- M07" if r[0] == MEMBER else "") for r in rows]
    _table(display, ["member", "90+ O/S rate %", "rank (1=best)", ""])

    # Find M07 position
    m07_rank = next((r[2] for r in rows if r[0] == MEMBER), None)
    n_members = len(rows)
    if m07_rank:
        percentile = (n_members - m07_rank) / (n_members - 1) * 100 if n_members > 1 else 50
        _section("Step 2 – M07 summary position")
        print(f"  M07 rank   : {m07_rank} of {n_members}")
        print(f"  Percentile : {percentile:.0f}th  "
              f"({'above' if percentile >= 50 else 'below'} median)")

    _section("Step 3 – Score-band breakdown of M07's 90+ book (June 2024)")
    q6 = f"""
        SELECT
            sb.score_band,
            db.sort_order AS band_sort,
            SUM(sb.num_accounts) AS accts,
            ROUND(SUM(sb.os_amount_mn), 2) AS os_mn,
            ROUND(SUM(sb.num_accounts) * 100.0 / NULLIF(SUM(SUM(sb.num_accounts)) OVER (), 0), 1)
                AS pct_of_90plus_book
        FROM fact_score_band sb
        JOIN dim_score_band db ON db.band_id = sb.score_band
        WHERE sb.entity_id = '{MEMBER}'
          AND sb.reporting_month = DATE '{TARGET_MONTH}'
          AND sb.product = 'credit_card'
          AND sb.dpd_bucket IN {AT_OR_WORSE}
        GROUP BY sb.score_band, db.sort_order
        ORDER BY db.sort_order
    """
    rows6 = conn.execute(q6).fetchall()
    _table(rows6, ["score_band", "sort", "accounts", "O/S ($M)", "% of 90+ book"])

    if rows6:
        dominant = max(rows6, key=lambda r: float(r[4]) if r[4] else 0)
        print()
        print(f"  Dominant band in 90+ book: {dominant[0]}  ({dominant[4]}% of accounts)")
        print(f"  This tells us the risk profile of M07's stressed book.")

    print("""
  What happened:
  ┌─────────────────────────────────────────────────────────────────┐
  │  Ranking: RANK() OVER () on the coincidence rate → peer rank   │
  │  Score band: fact_score_band filtered to 90+ buckets → mix     │
  │  In production these would be suppressed if peer cohort < 5.   │
  └─────────────────────────────────────────────────────────────────┘
""")


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    print()
    print("╔══════════════════════════════════════════════════════════════════╗")
    print("║     DELINQUENCY BENCHMARKING AGENT – DATA MODEL WALKTHROUGH     ║")
    print("║                                                                  ║")
    print("║  PART 0 – Table tour: individual samples + relationships        ║")
    print("║  PART 1 – Examples: coincidence, roll-rate, ranking             ║")
    print("╚══════════════════════════════════════════════════════════════════╝")

    conn = setup_db()
    part0_table_tour(conn)
    example1_coincidence(conn)
    example2_roll_rate(conn)
    example3_ranking(conn)

    _header("SUMMARY – THE DATA MODEL IN ONE PICTURE")
    print("""
  ┌──────────────────────────────────────────────────────────────────┐
  │  Tables                   What they hold                         │
  │  ─────────────────────    ────────────────────────────────────── │
  │  dim_entity               INDUSTRY + 18 synthetic Members        │
  │  dim_month                24 month-end dates (Jan 2023-Dec 2024) │
  │  dim_dpd_bucket           9 buckets: current → 180+ → write-off  │
  │  dim_score_band           AA (best) → JJ (worst) + NS            │
  │  fact_delinquency         accounts + O/S per entity/month/bucket │
  │  fact_score_band          accounts + O/S per …/bucket/band       │
  │                                                                   │
  │  Three lenses the semantic layer computes:                        │
  │  • Coincidence: bucket share of total book (same month)          │
  │  • Lagged     : cohort vs its own book N months earlier          │
  │  • Roll-rate  : flow from bucket B to B+1, month over month      │
  │                                                                   │
  │  Three comparison views layered on top:                           │
  │  • Market share : member / industry                               │
  │  • Ranking      : position among all members (with suppression)  │
  │  • Index        : re-based to 100 at a chosen base month         │
  └──────────────────────────────────────────────────────────────────┘
""")
    conn.close()


if __name__ == "__main__":
    main()
