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
  shared/line_classes.py). A charge the customer paid (postage) stays a sale
  or return line, in revenue, but is no product. A discount is a deduction,
  whatever its signs. A fee or cost and an accounting adjustment are left out
  as "in" rows are (`left_out`) and reported by stage 2.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from contracts.cleaning import OrderConfirmations
from shared.dates import as_dates
from shared.line_classes import line_classes
from shared.orders import OrdersBasis, order_basis
from shared.text import customer_identity, is_blank


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
    # rows explicitly "in", and lines the user classed as a fee or cost or an
    # accounting adjustment (`left_out`, 2E-d2).
    counted: pd.Series
    # `counted` AND quantity > 0 AND a positive amount, not a discount: an
    # order (module docstring, 2E and 2E-c).
    sale: pd.Series
    # `counted` AND quantity < 0 AND a negative amount, not a discount: a
    # return line (2E-c2).
    returned: pd.Series
    # `counted` and neither of the two: a coupon, a discount, a write-off, a
    # free item, a zero-amount stock write-off (module docstring, 2E-c, 2E-c2).
    deduction: pd.Series
    # The class the user gave each line in Review, NaN for a product (2E-d2,
    # shared/line_classes.py): "charge", "discount", "cost" or "adjustment".
    line_class: pd.Series
    # `valid`, not "in", and classed a fee or cost or an adjustment: out of
    # revenue and of every figure, as an "in" row is, but reported (2E-d2).
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
                       confirmations: OrderConfirmations | None = None) -> ParsedTransactions:
    """`column_mapping` is cleaning_report.json's mapping of source column
    name -> canonical field, `confirmations` its answers from Review (None:
    nothing confirmed). Raises RequiredColumnMissingError if
    transaction_date, quantity or unit_price has no mapped column."""
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
    dates = as_dates(df[date_col], offsets="wall_clock")
    quantities, prices, counts_as_sale = line_numbers(df, reverse, quantity_col, price_col)

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
    # The user's classes (Thach, 2E-d2). A fee or cost and an accounting
    # adjustment leave revenue as an "in" row does - excluded, never
    # subtracted - and are reported. A discount is 2E-c's deduction whatever
    # its signs: a -1 @ +price discount read as a return line (2E-c2 item f).
    # A charge the customer paid stays a sale or return line: only the product
    # tables leave it (shared/products.py).
    line_class = line_classes(df, reverse, answers.line_classes)
    left_out = valid & counts_as_sale & line_class.isin(("cost", "adjustment"))
    counted = valid & counts_as_sale & ~left_out
    amounts = quantities * prices
    priced = counted & line_class.ne("discount")
    sale = priced & (quantities > 0) & (amounts > 0)
    returned = priced & (quantities < 0) & (amounts < 0)
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
                         customers, sale, returned, counted, ~counts_as_sale | left_out,
                         receipt_answer=answers.order_id_is_receipt,
                         customer_column="customer" in reverse,
                         fill=answers.customer_on_first_line_only is not False)
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


def line_numbers(df: pd.DataFrame, reverse: dict[str, str], quantity_col: str,
             price_col: str) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Quantities, prices, and whether each row counts towards revenue by its
    transaction type (not an explicit "in") - read by `parse_transactions`
    and, without dates, by stage 1's walk-in placeholder search (2E-k)."""
    quantities = pd.to_numeric(df[quantity_col], errors="coerce")
    prices = pd.to_numeric(df[price_col], errors="coerce")
    type_col = reverse.get("transaction_type")
    if type_col is None:
        counts_as_sale = pd.Series(True, index=df.index)
    else:
        # astype(object): an empty or all-missing column can read back as
        # float64, and .str only works on an object/string dtype. NaN (a
        # per-row missing type) compares False to "in", so it also defaults
        # to "out", matching the column-level default.
        counts_as_sale = ~is_stock_in(df[type_col])
    return quantities, prices, counts_as_sale


def order_ids(df: pd.DataFrame, column: str | None) -> pd.Series | None:
    """The column stripped, blank cells as NaN; None when not mapped."""
    if column is None:
        return None
    return df[column].astype(object).str.strip().where(~is_blank(df[column]))


def customers_of(df: pd.DataFrame, column: str | None) -> pd.Series:
    if column is None:
        return pd.Series(float("nan"), index=df.index, dtype=object)
    return customer_identity(df[column]).where(~is_blank(df[column]))


def require_column(reverse: dict[str, str], canonical_field: str) -> str:
    column = reverse.get(canonical_field)
    if column is None:
        raise RequiredColumnMissingError(canonical_field)
    return column


def is_stock_in(values: pd.Series) -> pd.Series:
    """Where a transaction_type cell says "in", read as revenue scope has
    always read it (2A) - one reading for revenue scope and stage 2's
    stock-in lines (2E-g). NaN is not "in"."""
    return values.astype(object).str.strip().str.lower().eq("in")
