# Methodology & Definitions

> Source corpus for the definitions RAG index. Each `##` section is one
> retrieval chunk. The `terms:` tag on the first line of each section maps it
> to the metric keys used in the catalog and QuerySpec. The heading text is
> the citation returned with every answer that draws from this chunk.
>
> Edit this file to update methodology explanations. Re-run `make corpus`
> (or `python -m delinquency_agent.knowledge.corpus`) to rebuild the index.

---

## Definitions 1.1 – Member and Industry
terms: entity, industry, member, entity_id

A **member** is a lender that contributes account-level data to the bureau
under a data-sharing agreement. Members receive benchmarking reports as a
benefit of participation. In this report, member identities are represented
as anonymous IDs (M01, M02, …) to preserve competitive confidentiality.

**Industry** refers to the aggregate of all participating members for a given
month and bucket. Industry figures serve as the market-wide benchmark and as
the denominator for market-share calculations. Because the bureau sums member
contributions into the industry row, `Industry = SUM(all members)` holds
exactly for every month and bucket.

---

## Definitions 1.2 – Reporting period and snapshot date
terms: reporting_month, month_index, snapshot

Each data point in this report is a **month-end snapshot**: the state of the
book as of the last day of the reporting month. Month-end is used universally
across members so comparisons are on equal footing regardless of billing-cycle
differences. The `month_index` is a zero-based integer offset from the first
month in the panel, used internally for lag arithmetic.

---

## Definitions 2.1 – Days Past Due (DPD) and delinquency buckets
terms: dpd, bucket, dpd_bucket, delinquency, b30, b60, b90, b120, b150, b180_plus, x_day, current

**Days Past Due (DPD)** is the number of calendar days since an account's
minimum payment was due but not received. Accounts are grouped into the
following atomic buckets:

| Bucket | DPD range | Meaning |
|---|---|---|
| current | 0 | No overdue balance |
| x_day | 1–29 | Informal early-delinquency bucket |
| 30 DPD | 30–59 | First formal delinquency bucket |
| 60 DPD | 60–89 | Second stage |
| 90 DPD | 90–119 | Third stage; regulatory and provisioning significance |
| 120 DPD | 120–149 | Fourth stage |
| 150 DPD | 150–179 | Fifth stage |
| 180+ DPD | 180 or more | Open-ended; accounts linger here before charge-off |
| Newly written-off | N/A | Charged off in the current period; terminal bucket |

**Rolled ranges** such as "30–179 DPD" are derived aggregates: the sum of the
atomic buckets within that range. They are computed on the fly by the semantic
layer and are not stored as separate rows.

---

## Definitions 2.2 – Risk score bands
terms: score_band, avg_score, score, band, AA, BB, CC, DD, EE, FF, GG, HH, II, JJ, NS

Account risk scores are grouped into **score bands** from AA (best risk) to
JJ (worst risk), plus NS for accounts with no score.

| Band | Score range | Risk interpretation |
|---|---|---|
| AA | 750+ | Lowest credit risk |
| BB | 724–749 | Very low risk |
| CC | 700–723 | Low risk |
| DD | 675–699 | Below-average risk |
| EE | 650–674 | Moderate risk |
| FF | 625–649 | Elevated risk |
| GG | 600–624 | High risk |
| HH | 575–599 | Very high risk |
| II | 550–574 | Near-distress |
| JJ | <550 | Highest risk |
| NS | N/A | No score assigned |

The score distribution of a delinquency bucket reveals the risk profile of the
stressed sub-portfolio. A 90-dpd book dominated by GG–HH bands indicates
accounts that were already elevated-risk at origination; a book showing FE–FF
mix may indicate recent deterioration of otherwise moderate-risk accounts.

---

## Methodology 4.1 – Coincidence view (snapshot share)
terms: coincidence, coincidence_acct_pct, coincidence_os_pct, snapshot, share, rate

The **coincidence view** is the most common benchmarking lens. It expresses
a delinquency bucket's accounts or outstanding balance (O/S) as a proportion
of the entity's total book *in the same month*. The word "coincidence" reflects
that the numerator and denominator are measured at the same point in time.

**Formula:**

```
coincidence_pct(entity, month, bucket) =
    SUM(measure in bucket, or worse)
    ─────────────────────────────────
    SUM(measure across all buckets)
```

**Example:** "90+ DPD O/S rate" = outstanding in buckets 90, 120, 150, 180+,
and newly-written-off, divided by total outstanding for that entity and month.

The coincidence view is useful for **stock comparisons**: where is my book
sitting right now relative to the industry? It does not explain how accounts
arrived in those buckets; the lagged and roll-rate views provide that context.

---

## Methodology 4.2 – Lagged view (cohort vs its own base)
terms: lagged, lagged_acct_pct, lagged_os_pct, cohort, lag, base_period

The **lagged view** measures delinquency of a cohort against the book's
own size N months earlier. This removes the effect of book growth or shrinkage:
a rising coincidence rate could be explained entirely by a shrinking denominator,
whereas the lagged view holds the denominator constant at a prior base period.

**Formula:**

```
lagged_pct(entity, month, bucket, N) =
    SUM(measure in bucket-or-worse at month t)
    ──────────────────────────────────────────
    SUM(total measure at month t − N)
```

**Common lag values:** 3 months is the default and most commonly used.
6-month and 12-month lags are used for longer-term trend analysis.

**Example:** "Lagged 90+ DPD accounts (3-month lag)" for June 2024 =
accounts in 90+ DPD in June 2024 ÷ total accounts in March 2024. This answers
"what share of my March 2024 book has deteriorated to 90+ DPD by June?"

---

## Methodology 4.3 – Roll-rate view (flow into worse buckets)
terms: roll_rate, roll_rate_30_60, roll_rate_60_90, roll_rate_90_120, roll_rate_x_30, roll_rate_to_writeoff, flow, transition, migration

The **roll-rate view** measures the **flow** of accounts from one DPD bucket
into the next-worse bucket, month over month. It is an early-warning indicator:
a rising roll rate signals worsening credit performance before it shows up
meaningfully in coincidence rates.

**Formula:**

```
roll_rate(entity, month, from_bucket, to_bucket) =
    accounts in to_bucket at month t
    ──────────────────────────────────
    accounts in from_bucket at month t − 1
```

**Example:** "30→60 roll rate" in June 2024 =
accounts in 60 DPD in June 2024 ÷ accounts in 30 DPD in May 2024.
A rate of 55% means 55 of every 100 accounts that were 30-dpd last month
have now rolled into 60-dpd this month.

**Seasonality:** Roll rates typically peak in Q1 (Jan–Mar) following holiday
spending, and trough in Q3 (Jul–Sep). Analysts should compare the same calendar
month year-over-year as well as to the trailing 12-month average.

---

## Methodology 5.1 – Market share
terms: market_share, share, industry_share

**Market share** expresses a member's delinquency measure as a proportion of
the industry total for the same measure, month, and bucket.

**Formula:**

```
market_share(member, month, measure) =
    measure_value(member, month)
    ─────────────────────────────
    measure_value(INDUSTRY, month)
```

**Example:** "M07's market share of 90+ O/S" = M07's 90+ outstanding ÷
industry total 90+ outstanding. If M07's 90+ book is $92M and industry is
$1,718M, market share = 5.35%. Combined with M07's coincidence rate this
reveals whether M07's stress level is proportionate to its book size.

A high market share of stressed accounts relative to market share of total
accounts signals that a member is disproportionately contributing to
industry delinquency.

---

## Methodology 5.2 – Ranking and percentile
terms: ranking, rank, percentile, peer, position

**Ranking** positions a member among all participating members for a given
measure and month. Rank 1 is the best (lowest delinquency rate or roll rate).
The **percentile** is the share of members at or below a member's value.

**Privacy rule:** Ranking results are subject to **minimum-cell suppression**.
If the peer cohort computing a ranking contains fewer than 5 members, the
ranking result is withheld and replaced with a suppression notice. This prevents
indirect identification of individual members.

**Interpretation:** A member ranked 4 of 18 on 90+ DPD O/S rate sits at the
82nd percentile — meaning 82% of the peer group has a higher (worse) rate.
Rankings should be read alongside the absolute rate: being ranked 1st in a
period of universal deterioration is less meaningful than an improving rank
in a stable environment.

---

## Methodology 5.3 – Relative Position Index (trend re-basing)
terms: index, index_value, relative_position_index, trend, base_month

The **Relative Position Index** re-bases a metric to 100 at a chosen base
month, making trend comparisons readable regardless of the absolute rate level.

**Formula:**

```
index(member, month, measure; base_month) =
    100 × measure_value(member, month)
    ───────────────────────────────────
    measure_value(member, base_month)
```

**Example:** With January 2024 as the base (index = 100), an index of 119.8
in June 2024 means the rate has risen 19.8% relative to January. This makes
comparing trend pace across members straightforward regardless of their
different absolute rate levels.

**Common base months:** The first month of the reporting panel, the first month
of the current year (YTD view), or the first month after a strategy change.

---

## Governance 6.1 – Privacy and suppression rules
terms: suppression, privacy, min_cell, k_anonymity, entitlement

**Aggregate-only data:** This report contains only aggregated statistics.
No account-level, consumer-level, or individual-level data is present anywhere
in the dataset or in agent responses.

**Entitlement scope:** Each member may query:
- Their own member rows (all measures for their own entity_id).
- Industry aggregates (all members combined).
- Peer comparison views (ranking, percentile, market share) — subject to suppression.

**Minimum-cell suppression:** Any peer or ranking result computed over a
cohort of fewer than 5 members is suppressed. The result is returned as
"not available — insufficient peer population." This protects against
indirect identification of individual members from thin peer cohorts.

**Grounded-or-refuse:** Every number in an agent response must trace directly
to a returned query result row. The grounding guard verifies this before any
response reaches the user. Numbers that cannot be verified are blocked and
the agent explains the limitation.
