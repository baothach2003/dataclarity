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
  of a negative-quantity sale line - and, since 2E-c2, a negative amount (see
  RETURN LINE below). The canonical schema has no returns field, so this is
  the one signal available, and it does not depend on transaction_type being
  mapped.
- An ORDER is a sale row: a counted row with positive quantity (Thach, session
  2E) AND a positive line amount (Thach, 2E-c). Without the optional
  `order_id` a row is the unit of purchase; with it, the order id is
  (shared/orders.py, 2E-e); a return line sold nothing, and neither
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
- A RETURN LINE is a counted row with quantity < 0 AND a negative amount
  (Thach, 2E-c2 - symmetric with the sale row). A zero-amount negative-
  quantity line is a stock write-off, not a customer return: on Online
  Retail II 3,393 such lines ("check", "damaged", "missing", "thrown away")
  inflated return_rate by 7% to 78% a month, refused B2, and opened
  purchase histories with a "refund" of no money.
- A DEDUCTION is a counted row that is neither a sale nor a return (2E-c):
  its money stays in net revenue, and stage 3's returns lens carries it as a
  term of its own. Its quantity is not a unit sold: `units` counts sale and
  return lines only. Summed over every row, a free gift line a day took
  units per order from 3.0 to 4.0 while every paid basket held 3 units, and
  B2 headlined "baskets got bigger" over a price rise (2E-c doubt-review F1).
- NON-PRODUCT LINES are the lines the user classed in Review (Thach, 2E-d2;
  shared/line_classes.py). A charge the customer paid (postage) stays in
  revenue but is no order, no return and no product (`charge`; Thach, 2E-l:
  an invoice holding only charges is no purchase). A discount is a
  deduction, whatever its signs. Pooled items (many under one code) are sale
  and return lines ranked as no product. A fee or cost, an accounting
  adjustment and a gift card (2E-t1) are left out as "in" rows are
  (`left_out`), reported by stage 2.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from contracts.cleaning import OrderConfirmations
from shared.date_evidence import answered_order, month_grain
from shared.dates import as_dates
from shared.line_classes import line_classes
from shared.line_effects import COUNTED, DEDUCTIONS, GROSS, LEFT_OUT, RETURNS
from shared.line_numbers import (  # noqa: F401  # one definition, read here as it always was
    LineClassColumnsError,
    RequiredColumnMissingError,
    is_stock_in,
    line_numbers,
    require_column,
)
from shared.line_taxonomy import read_classes
from shared.orders import OrdersBasis, order_basis
from shared.text import customer_identity, identifier_text, is_blank


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
    # Each line's class of the line taxonomy (2E-t2, docs/LINE_TAXONOMY.md):
    # stage 1's `line_class`, `class_source` and `suggested_class`, read from
    # cleaned.csv - or, for a frame without them, classified here by the same
    # function (`shared/line_taxonomy.py`). Every set below derives from the
    # class through `shared/line_effects.py`.
    classes: pd.Series
    class_source: pd.Series
    suggested: pd.Series
    # A counted class, dated (docs/LINE_TAXONOMY.md section 3).
    counted: pd.Series
    # `counted` AND quantity > 0 AND a positive amount, not a discount or a
    # charge: an order (module docstring, 2E and 2E-c; 2E-l).
    sale: pd.Series
    # `counted` AND quantity < 0 AND a negative amount, not a discount or a
    # charge: a return line (2E-c2).
    returned: pd.Series
    # `counted` and classed a charge the customer paid (postage): its money
    # is revenue, but it is no order and no return - an invoice holding only
    # charges is no purchase (Thach, 2E-l).
    charge: pd.Series
    # `counted` and none of the three: a coupon, a discount, a write-off, a
    # free item, a zero-amount stock write-off (module docstring, 2E-c, 2E-c2).
    deduction: pd.Series
    # The ITEM the user gave each line's key in Review, NaN for a product
    # (`shared/line_classes.line_classes`; contracts.profile.LineClass), on
    # every line of the key. A pooled line is an ordinary sale or return
    # line, ranked as no product (2E-l).
    line_class: pd.Series
    # `valid`, not "in", and classed a fee or cost, an adjustment or a gift
    # card: out of revenue and every figure, as an "in" row is, but reported.
    left_out: pd.Series
    # Net units: the quantity of sale and return lines, 0 elsewhere (2E-c).
    units: pd.Series
    # The order each row belongs to, and whether that is a real order id or
    # the row itself (shared/orders.py, 2E-e). `orders_basis_reason` says why
    # a mapped order_id was not used.
    order_key: pd.Series
    orders_basis: OrdersBasis
    orders_basis_reason: str | None
    # The customer of each row - the normalised identity, NaN where there is
    # none - for every reader in stages 2 and 3 (2E-f). With a trusted order
    # id a blank cell takes its receipt's one named customer: read raw, a
    # header-style export gave each customer only a receipt's first line
    # (Online Retail II rewritten so: new revenue 8,783.75 against 79,845.90).
    # Unless the user answered in Review that the customer is not written on
    # a receipt's first line only (2E-e2).
    customers: pd.Series
    # The counted lines with no customer that the fill gives, or would give,
    # their receipt's customer - confirmed or not (2E-e2).
    receipt_fillable: pd.Series
    # Lines whose customer value the user confirmed in Review as a walk-in
    # placeholder: they have no customer (2E-k).
    placeholder: pd.Series
    # Whether the order-id check could read dates only (2E-k; for stage 1).
    order_id_date_only: bool


def parse_transactions(df: pd.DataFrame, column_mapping: dict[str, str],
                       confirmations: OrderConfirmations | None = None, *, raw: bool = False
                       ) -> ParsedTransactions:
    """`column_mapping` is cleaning_report.json's mapping of source column
    name -> canonical field, `confirmations` its answers as applied (with
    stage 1's date order; None: nothing). `raw`: the file as uploaded (stage
    1's order checks), classified here, never read for stage 1's columns.
    Raises RequiredColumnMissingError if transaction_date, quantity or
    unit_price has no mapped column, LineClassColumnsError if cleaned.csv's
    line classes are not stage 1's."""
    reverse = {field: source for source, field in column_mapping.items()}
    answers = confirmations or OrderConfirmations()

    date_col = require_column(reverse, "transaction_date")
    quantity_col = require_column(reverse, "quantity")
    price_col = require_column(reverse, "unit_price")

    # 1F's rule, always (Thach, 2E-h): the date and time as written, the
    # offset dropped, and "now", a bare time or a year outside 1900-2100 no
    # date. Read as UTC, a +10:00 shop's current month, the sign of its change
    # and its closed weekday all moved, and "now" dated a sale the day of the
    # run (2E-f doubt-review cycle 4 F3). shared/dates.py is stage 1's reader.
    # A day-month-year cell in stage 1's order (2E-j); none recorded (no such
    # cell, or a report from before 2E-j): as before.
    dates = as_dates(df[date_col], offsets="wall_clock", order=answered_order(answers.dates_day_first))
    quantities, prices, counts_as_sale = line_numbers(df, reverse, quantity_col, price_col)
    classes, class_source, suggested = read_classes(df, column_mapping, answers, raw=raw, dated=dates.notna())

    # A row with no parseable date, quantity or price cannot be measured or
    # placed in a period; it is left out rather than guessed at. np.isfinite,
    # not notna: "inf" parses into a real float that no sum survives (3C
    # doubt-review C2). The class says the rest (2E-t2): an amount too large
    # to add is unmeasurable too, and "in" lines are stock received.
    valid = dates.notna() & np.isfinite(quantities) & np.isfinite(prices)
    dated = dates.notna()
    with np.errstate(over="ignore", invalid="ignore"):
        amounts = quantities * prices
    counted = classes.isin(COUNTED) & dated
    sale = classes.isin(GROSS) & dated
    returned = classes.isin(RETURNS) & dated
    charge = classes.eq("charge") & dated
    # Outside revenue by the user's answer - a fee or cost, an adjustment, a
    # gift card (2E-d2, 2E-t1): excluded, never subtracted, and reported.
    left_out = classes.isin(LEFT_OUT) & dated
    # The item the user gave the line's key in Review, on EVERY line of the
    # key: read from the class, a charge's "in" or unpriced line lost its item
    # and became a product that renamed a real one (2E-t2 review 2 #1). The
    # name-only vote reads the lines that would be sales if nothing were
    # classed, as stage 1's classifier does (E7).
    line_class = line_classes(df, reverse, answers.line_classes,
                              valid & counts_as_sale & (quantities > 0) & (amounts > 0))
    customers = customers_of(df, reverse.get("customer"))
    # A value the user confirmed as a placeholder for walk-ins ("Guest",
    # "Walk-in", "0") names no one (Thach, 2E-k): compared by identity.
    placeholders = set(customer_identity(pd.Series(answers.customer_placeholders, dtype=object)))
    placeholder = customers.isin(placeholders)
    customers = customers.mask(placeholder)
    # The fill happens unless the user answered No (2E-e2 review A): withheld
    # by default, a header-style receipt's unnamed purchase lines lost their
    # customer while its credit note's named line kept it, and a first-time
    # buyer's history "opened with a refund". Filling on no answer is 2E-f's
    # rule and its known limit L1, which Thach accepted as rare.
    # A left-out line is out as an "in" row is: it names no receipt's other
    # lines either (2E-d2 doubt-review F9: a bad debt under Dee named a
    # receipt's walk-in line).
    orders = order_basis(order_ids(df, reverse.get("order_id")), dates.dt.normalize(),
                         customers, sale, returned, counted, classes.eq("stock_in") | left_out,
                         receipt_answer=answers.order_id_is_receipt,
                         customer_column="customer" in reverse,
                         fill=answers.customer_on_first_line_only is not False,
                         month_grain=month_grain(dates[counted]))
    return ParsedTransactions(
        reverse=reverse,
        dates=dates,
        quantities=quantities,
        prices=prices,
        revenue_amounts=amounts,
        valid=valid,
        classes=classes,
        class_source=class_source,
        suggested=suggested,
        counted=counted,
        sale=sale,
        returned=returned,
        charge=charge,
        deduction=classes.isin(DEDUCTIONS) & dated,
        line_class=line_class,
        left_out=left_out,
        units=quantities.where(sale | returned, 0.0),
        order_key=orders.key,
        orders_basis=orders.basis,
        orders_basis_reason=orders.reason,
        customers=orders.customers,
        receipt_fillable=orders.fillable,
        placeholder=placeholder,
        order_id_date_only=orders.date_only,
    )


def order_ids(df: pd.DataFrame, column: str | None) -> pd.Series | None:
    """The column as a reader tells ids apart (`identifier_text`, case kept),
    blank cells as NaN; None when not mapped. "INV1" and "INV1" with a
    trailing zero-width space were two orders (Thach, 2E-i)."""
    if column is None:
        return None
    return identifier_text(df[column]).where(~is_blank(df[column]))


def customers_of(df: pd.DataFrame, column: str | None) -> pd.Series:
    if column is None:
        return pd.Series(float("nan"), index=df.index, dtype=object)
    return customer_identity(df[column]).where(~is_blank(df[column]))
