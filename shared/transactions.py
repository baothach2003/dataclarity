"""Reading cleaned.csv's transaction columns: one definition, shared by every
stage that measures them.

Infrastructure, not analysis (CLAUDE.md section 4): this module decides what a
row *is* - whether its date, quantity and price parse, and whether it counts
towards revenue - and nothing about what any KPI means. Stage 2 computes
metrics.json from it (`stages/analyze/`), stage 3 recomputes the same figures
while diagnosing (`stages/diagnose/`), and the two must agree exactly; a stage
may not import another stage (CLAUDE.md 3.1, docs/adr/0001), so the definition
lives here rather than in either of them.

The revenue-scope rules below were decided in Phase 2A against
docs/SPECS.md section 9 and docs/AI_PIPELINE.md section 5, and moved here
unchanged in Phase 3 session 3B:

- `transaction_type` is stock movement direction only, never a returns concept.
  A row counts towards revenue only when its type is not explicitly "in":
  "in" rows (stock coming back, e.g. a supplier restock) are excluded from
  revenue entirely, never subtracted. No mapped column at all, or an
  unrecognised per-row value, defaults to "out" (SPECS section 9:
  "in|out, default out").
- A return is a counted row with negative quantity, the common POS convention
  of a negative-quantity sale line. The canonical schema has no returns field,
  so this is the one signal available, and it does not depend on
  transaction_type being mapped.
- An ORDER is a sale row: a counted row with positive quantity (Thach, session
  2E) AND a positive line amount (Thach, 2E-c). The schema has no invoice id,
  so a row is the unit of purchase; a return line sold nothing, and neither
  did a zero-quantity line. Counting every counted row made a month with
  refunds look like smaller baskets and rarer purchases in both stages (3E1
  doubt-review). A zero-amount line is not a purchase either - on Online
  Retail II 2,561 of 2,631 carry no customer (stock bookkeeping) and 61 of
  the other 70 ride on an invoice with a paid line - nor is a line with a
  negative amount (a coupon, a discount, a bad-debt write-off): counted as
  orders, forty coupon lines made customers "buy more often" and a refund at
  a negative price a "price cut" (2E-b review F1, P1). Every figure built on
  orders - orders, AOV, return rate, units per order, purchase frequency, RFM
  frequency and recency, buyers, D1's trading days, the product lens -
  counts `sale` rows, in stage 2 and stage 3 alike.
- A DEDUCTION is a counted row that is neither a sale nor a return (2E-c):
  its money stays in net revenue, and stage 3's returns lens carries it as a
  term of its own. Its quantity is not a unit sold: `units` counts sale and
  return lines only. Summed over every row, a free gift line a day took
  units per order from 3.0 to 4.0 while every paid basket held 3 units, and
  B2 headlined "baskets got bigger" over a price rise (2E-c doubt-review F1).
"""

from dataclasses import dataclass
from typing import NamedTuple

import numpy as np
import pandas as pd

from shared.numbers import is_negligible


class RequiredColumnMissingError(ValueError):
    """cleaned.csv has no column mapped to a canonical field a stage needs.
    transaction_date and quantity are stage 1 required fields, so raising for
    them is defensive; unit_price is not required by stage 1
    (docs/AI_PIPELINE.md section 11), so it is the realistic case.

    `canonical_field` is structured (not just the message text) so a caller
    outside the stage - the API endpoints - can report which field is missing
    without parsing a sentence."""

    def __init__(self, canonical_field: str) -> None:
        self.canonical_field = canonical_field
        super().__init__(
            f"cleaned.csv has no column mapped to '{canonical_field}'; "
            "metrics cannot be computed without it"
        )


@dataclass(frozen=True)
class ParsedTransactions:
    """cleaned.csv's transaction columns, parsed once and typed."""

    reverse: dict[str, str]  # canonical field -> source column name
    dates: pd.Series  # tz-naive datetime64, NaT where unparseable
    quantities: pd.Series  # float, NaN where unparseable
    prices: pd.Series  # float, NaN where unparseable
    revenue_amounts: pd.Series  # quantities * prices
    # date/quantity/price all present, regardless of transaction_type.
    valid: pd.Series
    # `valid` AND counts towards revenue per the module docstring: excludes
    # only rows explicitly "in". `valid & ~counted` is every explicit "in"
    # row (metrics_products.py's stock-in side).
    counted: pd.Series
    # `counted` AND quantity > 0 AND a positive amount: an order (module
    # docstring, 2E and 2E-c).
    sale: pd.Series
    # `counted` AND quantity < 0: a return line.
    returned: pd.Series
    # `counted` and neither of the two: a coupon, a discount, a write-off, a
    # free item (module docstring, 2E-c).
    deduction: pd.Series
    # Net units: the quantity of sale and return lines, 0 elsewhere (2E-c).
    units: pd.Series


def parse_transactions(df: pd.DataFrame, column_mapping: dict[str, str]) -> ParsedTransactions:
    """`column_mapping` is cleaning_report.json's mapping of source column
    name -> canonical field. Raises RequiredColumnMissingError if
    transaction_date, quantity or unit_price has no mapped column."""
    reverse = {field: source for source, field in column_mapping.items()}

    date_col = require_column(reverse, "transaction_date")
    quantity_col = require_column(reverse, "quantity")
    price_col = require_column(reverse, "unit_price")

    # utc=True avoids a crash on a file mixing offset and offset-less
    # datetimes (pandas otherwise refuses to build one Series from both); the
    # result is dropped back to naive for period/month grouping.
    dates = pd.to_datetime(df[date_col], format="mixed", errors="coerce", utc=True).dt.tz_localize(None)
    quantities = pd.to_numeric(df[quantity_col], errors="coerce")
    prices = pd.to_numeric(df[price_col], errors="coerce")

    # A row with no parseable date, quantity or price cannot be measured or
    # placed in a period; it is left out rather than guessed at.
    #
    # np.isfinite, not notna: `pd.to_numeric` parses the strings "inf",
    # "-inf" and "Infinity" into real floats, which are not missing and so
    # passed a notna() check. One such cell then propagated through every sum
    # that touched it, and because JSON cannot represent infinity, pydantic
    # serialised the result as `null` in contract fields typed as a required
    # float - a metrics.json or diagnosis.json that will not validate when read
    # back (3C doubt-review C2). An unrepresentable number is not a measurement,
    # so it is excluded here exactly like an unparseable one.
    valid = dates.notna() & np.isfinite(quantities) & np.isfinite(prices)

    type_col = reverse.get("transaction_type")
    if type_col is None:
        counts_as_sale = pd.Series(True, index=df.index)
    else:
        # astype(object): an empty or all-missing column can read back as
        # float64, and .str only works on an object/string dtype. NaN (a
        # per-row missing type) compares False to "in", so it also defaults
        # to "out", matching the column-level default.
        counts_as_sale = ~df[type_col].astype(object).str.strip().str.lower().eq("in")

    counted = valid & counts_as_sale
    amounts = quantities * prices
    sale = counted & (quantities > 0) & (amounts > 0)
    returned = counted & (quantities < 0)
    return ParsedTransactions(
        reverse=reverse,
        dates=dates,
        quantities=quantities,
        prices=prices,
        revenue_amounts=amounts,
        valid=valid,
        counted=counted,
        sale=sale,
        returned=returned,
        deduction=counted & ~sale & ~returned,
        units=quantities.where(sale | returned, 0.0),
    )


def require_column(reverse: dict[str, str], canonical_field: str) -> str:
    column = reverse.get(canonical_field)
    if column is None:
        raise RequiredColumnMissingError(canonical_field)
    return column


def is_blank(values: pd.Series) -> pd.Series:
    """True where a cell is missing or holds only whitespace - the same
    definition of "missing" docs/AI_PIPELINE.md section 6 uses for
    drop_rows_missing, applied to optional columns (`customer`, `sku`,
    `category`) stage 1 has no reason to have trimmed."""
    return values.isna() | (values.astype(object).str.strip() == "")


class PctChange(NamedTuple):
    """A percentage change, or why there is none."""

    value: float | None
    reason: str | None


def pct_change(current: float, previous: float, *magnitudes: float) -> PctChange:
    """Signed percentage change against a positive base; otherwise
    unavailable, with the reason (Thach, session 2E).

    Against a negative base the sign inverts: -100 -> -200 read +100% (a
    doubled loss as growth) and -100 -> +500 read -600% (a recovery as a
    collapse). Against zero there is nothing to divide by - 2A reported 0.0,
    "nothing moved", which is false when revenue appeared from nothing.
    Against residue the figure is astronomical and meaningless.

    `magnitudes` is the money that moved to produce the two figures (their
    gross): residue is judged against it. Judged only against the two nets, a
    residue base next to a month that also netted to residue was never
    negligible, and 0.1 + 0.2 - 0.3 -> 0 read -100% (2E doubt-review F6)."""
    if previous == 0:
        return PctChange(None, "there is no previous value to compare against, so there "
                               "is no percentage")
    # Residue of either sign before the sign test: a residue base is not a
    # loss, and calling -1e-17 "negative" misdescribed it (F9).
    if is_negligible(previous, current, previous, *magnitudes):
        # "Negligible", not only "residue": a real 0.01 against 31,000,000 is
        # no base either, and calling it float residue was false (F5).
        return PctChange(None, f"the previous value ({previous:.3g}) is floating-point "
                               "residue next to the money compared (under a billionth of "
                               "it), so it is no base for a percentage")
    if previous < 0:
        return PctChange(None, f"the previous value ({previous:,.2f}) is negative, so a "
                               "percentage change against it would invert its sign")
    return PctChange((current - previous) / previous * 100, None)


def normalize_text(values: pd.Series) -> pd.Series:
    """Strip and case-fold for grouping. astype(object): an all-missing column
    can read back as float64, and .str only works on an object/string dtype.
    NaN propagates through strip/lower/concat unharmed."""
    return values.astype(object).str.strip().str.lower()


def customer_identity(values: pd.Series) -> pd.Series:
    """The key that decides whether two rows are the same customer.

    Stripped and case-folded, so "CUST_01", " cust_01" and "Cust_01 " are one
    person - the same treatment `product_identity` has given product keys
    since 2C, applied to the other identity column for the same reason
    (Thach, session 3C2). Blank values stay blank, so `is_blank` still selects
    the unattributed rows afterwards.

    Why the asymmetry of the risk decides it: grouping raw *splits* one
    customer into several, and 3C reproduced what that does - one customer
    written three ways, buying the same amount each month, reads as
    `new = 200 / lapsed = -200`, which is "we lost everyone and gained a
    whole new base" printed on a flat month. That fabrication comes from
    ordinary data entry and feeds the C-family hypotheses and possibly the
    headline. The opposite error needs two genuinely different ids differing
    only by case or whitespace, which is rare for POS codes.

    Deliberately no further normalisation - no leading-zero stripping, no
    punctuation rules (Thach, 3C2). Those would start merging ids that a POS
    really does distinguish, and this helper's whole justification is that its
    error direction is the safe one.
    """
    return normalize_text(values)


def merged_identity_count(values: pd.Series) -> int:
    """How many distinct raw values `customer_identity` collapsed away.

    Distinct raw values minus distinct identities, over the rows passed in: a
    customer written three ways contributes 2. Zero means normalisation
    changed no grouping at all, which is what a clean file should show.
    """
    identity = customer_identity(values)
    usable = ~is_blank(identity)
    return int(values[usable].nunique() - identity[usable].nunique())


def product_identity(
    df: pd.DataFrame, product_name_col: str, sku_col: str | None
) -> pd.Series:
    """The key that decides whether two rows are the same product: this row's
    `sku` when it has one, else its `product_name` (docs/AI_PIPELINE.md
    section 11's business-key precedent, extended to a per-row fallback since a
    mapped sku column can still have blank cells row by row).

    Values are stripped and case-folded, so "SKU1", " SKU1" and "sku1" are one
    product; the sku-sourced and name-sourced halves live in separate
    namespaces (`sku:`/`name:`) so a SKU that happens to read the same as an
    unrelated product's name can never merge them. Both fixes came out of 2C's
    doubt-review. The key is never displayed - callers resolve a human-readable
    name separately."""
    normalized_name = "name:" + normalize_text(df[product_name_col])
    if sku_col is None:
        return normalized_name
    sku = df[sku_col]
    return ("sku:" + normalize_text(sku)).where(~is_blank(sku), normalized_name)
