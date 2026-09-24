"""Stage 2 Analyze - RFM scoring and segment assignment, split out of
metrics_customers.py (2E-c, over ~300 lines). The segment grid, the
single-customer rule and the populations (2B, 2E, 2E-b) are in
metrics_customers.py's module docstring; the tie rule (2E-c) is in
`score_quintile`'s own docstring below."""

from datetime import date

import numpy as np
import pandas as pd

NEEDS_ATTENTION = "Needs Attention"
# Never bought in the snapshot: only refunds (Thach, 2E-b) or, since the sale
# row needs a positive amount (2E-c), only free items or coupons. In
# Hibernating they inflated its count and dragged its money negative. Named
# "Returns only" in 2E-b; renamed (Thach, 2E-c2) because a gift-only customer
# returned nothing.
NO_PURCHASES = "No purchases in file"


def rfm_snapshot(table: pd.DataFrame, reference_date: date) -> pd.DataFrame:
    """One row per customer: last_purchase, frequency, monetary, recency_days,
    r_score, f_score, segment - over every row in `table` (already
    revenue-counted and customer-identified), anchored at `reference_date`.
    `table["sale"]` marks the rows that are orders: frequency (2E) and
    recency (2E-b) count those; monetary uses every counted row."""
    if table.empty:
        return pd.DataFrame(
            columns=["last_purchase", "frequency", "monetary", "recency_days", "r_score", "f_score", "segment"]
        )
    grouped = table.groupby("customer").agg(
        frequency=("sale", "sum"),
        monetary=("revenue", "sum"),
    )
    grouped["last_purchase"] = table[table["sale"]].groupby("customer")["date"].max()
    recency = (pd.Timestamp(reference_date) - grouped["last_purchase"]).dt.days
    never = (pd.Timestamp(reference_date) - table["date"].min()).days + 1
    grouped["recency_days"] = recency.fillna(never).astype(int)
    # Buyers-only quintiles: a buyer's R and F depend on other buyers alone.
    never_bought = grouped["frequency"] == 0
    grouped["r_score"] = 1
    grouped["f_score"] = 1
    buyers = ~never_bought
    if buyers.any():
        grouped.loc[buyers, "r_score"] = score_quintile(grouped.loc[buyers, "recency_days"],
                                                        ascending=False)
        grouped.loc[buyers, "f_score"] = score_quintile(grouped.loc[buyers, "frequency"],
                                                        ascending=True)
    grouped["segment"] = [
        NO_PURCHASES if none else assign_segment(r, f)
        for none, r, f in zip(never_bought, grouped["r_score"], grouped["f_score"], strict=True)
    ]
    return grouped


def score_quintile(values: pd.Series, *, ascending: bool) -> pd.Series:
    """Rank-based quintiles (1-5, 5 is always "best" given `ascending`).
    `ascending=False` scores the smallest raw value as 5 (Recency: fewest days
    since purchase is best); `ascending=True` scores the largest raw value as
    5 (Frequency: most orders is best). A single customer has no one to rank
    against and scores 5 (Thach's decision, Phase 2B).

    Identical customers get identical scores (Thach, 2E-c, superseding 2B's
    tie-break by position): five identical one-time buyers came out
    Hibernating to Champions by customer id, and renaming one moved her. Every
    position is scored as 2B did - five equal groups over the ranks - and a
    tied group takes the MEAN of its positions' scores, exact halves rounded
    DOWN so a tie never lifts a group. A group of one keeps its own score, so
    a file with no ties scores exactly as before; a population that ties
    throughout scores 3. Measured on Online Retail II: 32 of 5,942 customers
    change segment. Side effect (2E-c doubt-review F8): when more than 40% of
    buyers share the lowest frequency, they score F = 2, so "New" (F <= 1) is
    out of their reach - a decision recorded for Thach."""
    if len(values) == 1:
        return pd.Series([5], index=values.index)
    positions = values.rank(method="first", ascending=ascending)
    by_position = pd.qcut(positions, 5, labels=[1, 2, 3, 4, 5]).astype(int)
    mean = by_position.groupby(values).transform("mean")
    return np.ceil(mean - 0.5).astype(int)


def assign_segment(r_score: int, f_score: int) -> str:
    if r_score >= 4 and f_score >= 4:
        return "Champions"
    if r_score >= 3 and f_score >= 3:
        return "Loyal"
    if r_score <= 2 and f_score >= 3:
        return "At-risk"
    if r_score <= 2 and f_score <= 2:
        return "Hibernating"
    if r_score >= 4 and f_score <= 1:
        return "New"
    return NEEDS_ATTENTION
