"""Session 2E-f (Thach, after 2E-e), shared definitions, written before the
change.

1. Per-product same-day netting for "new" (decision 1, N2). On the opening
   day each PRODUCT nets on its own: a customer whose every product returned
   that day was bought that day, in at least as many units, is still new.
   Returning more than was bought that day - or a product not bought that
   day - is evidence of a purchase before the file. A return whose product
   is unknown cannot be matched, so it opens the history with a refund.
   Measured on Online Retail II: 96 customers get back the chance to be new,
   none lose it; N1 (any purchase of the product) would free 10 more who
   returned more units than they bought that day.
2. One per-row customer, shared by every reader (decision 4). When order_id
   is trusted, a blank customer takes its receipt's one named customer that
   day. The receipt's customer is read from its sale and return lines (2E-e
   F4); only a receipt none of whose sale or return lines is named reads its
   other lines. Two different names leave the blank line unattributed. No
   fill without a trusted order id.
"""

import pandas as pd

from shared.first_purchase import first_purchase_months, product_keys
from shared.orders import IdCheck
from shared.transactions import order_id_spanning, parse_transactions

MAPPING = {"Date": "transaction_date", "Qty": "quantity", "Price": "unit_price",
           "Cust": "customer", "Product": "product_name", "Sku": "sku"}


def _months(rows, mapping=MAPPING):
    df = pd.DataFrame(rows, columns=["Date", "Qty", "Price", "Cust", "Product", "Sku"])
    parsed = parse_transactions(df, mapping)
    return first_purchase_months(df["Cust"], parsed.dates, parsed.sale, parsed.returned,
                                 products=product_keys(df, parsed.reverse), units=parsed.units)


def test_a_product_bought_and_returned_on_the_opening_day_keeps_the_customer_new() -> None:
    """Bought 2 mugs and returned 1 the same day: nothing predates the file.
    Was None under 2E-c2's "any return line on the first day"."""
    months = _months([("2026-08-07", "2", "10", "x", "Mug", None),
                      ("2026-08-07", "-1", "10", "x", "Mug", None)])

    assert months["x"] == "2026-08"


def test_the_chair_bought_before_the_file_still_opens_with_a_refund() -> None:
    """10 pens bought, a 500 chair returned on the first day: the chair was
    not bought that day, so it was bought before the file."""
    months = _months([("2026-08-07", "10", "1", "x", "Pen", None),
                      ("2026-08-07", "-1", "500", "x", "Chair", None)])

    assert months["x"] is None


def test_returning_more_units_than_were_bought_that_day_opens_with_a_refund() -> None:
    """Bought 2 of product 21549 and returned 4 (Online Retail II customer
    15015): two of them predate the file. N1 called this customer new."""
    months = _months([("2026-08-07", "2", "10", "x", "Cake stand", None),
                      ("2026-08-07", "-4", "10", "x", "Cake stand", None)])

    assert months["x"] is None


def test_every_returned_product_must_be_covered() -> None:
    """Mug bought and returned, and a lamp returned that was not bought."""
    months = _months([("2026-08-07", "1", "10", "x", "Mug", None),
                      ("2026-08-07", "-1", "10", "x", "Mug", None),
                      ("2026-08-07", "-1", "30", "x", "Lamp", None)])

    assert months["x"] is None


def test_a_return_with_no_product_cannot_be_matched() -> None:
    """A nameless line bought and a nameless line returned: the two cannot be
    shown to be the same product, so the safe side - not new."""
    months = _months([("2026-08-07", "1", "10", "x", "  ", None),
                      ("2026-08-07", "-1", "10", "x", None, None)])

    assert months["x"] is None


def test_the_sku_decides_the_product() -> None:
    """Same SKU, the name written differently on the return: one product."""
    months = _months([("2026-08-07", "1", "10", "x", "Mug", "SKU1"),
                      ("2026-08-07", "-1", "10", "x", "mug - damaged", " sku1")])

    assert months["x"] == "2026-08"


def test_a_line_with_a_sku_and_no_name_is_a_known_product() -> None:
    """Mutation check (2E-f): the name is blank on both lines, the SKU is
    not - one product, bought and returned the same day."""
    months = _months([("2026-08-07", "2", "10", "x", None, "SKU1"),
                      ("2026-08-07", "-1", "10", "x", "  ", "SKU1")])

    assert months["x"] == "2026-08"


def test_a_same_name_under_two_skus_is_two_products() -> None:
    """Two SKUs both called "Mug": the returned one was not bought that day."""
    months = _months([("2026-08-07", "1", "10", "x", "Mug", "SKU1"),
                      ("2026-08-07", "-1", "10", "x", "Mug", "SKU2")])

    assert months["x"] is None


def test_floating_point_residue_is_not_an_over_return_in_any_row_order() -> None:
    """Bought 0.3 kg, returned 0.1 + 0.2 kg: the returned sum is
    0.30000000000000004 - residue, not a unit bought before the file - and
    both row orders read the same."""
    rows = [("2026-08-07", "0.3", "10", "a", "Flour", None),
            ("2026-08-07", "-0.1", "10", "a", "Flour", None),
            ("2026-08-07", "-0.2", "10", "a", "Flour", None),
            ("2026-08-07", "-0.2", "10", "b", "Flour", None),
            ("2026-08-07", "-0.1", "10", "b", "Flour", None),
            ("2026-08-07", "0.3", "10", "b", "Flour", None)]
    months = _months(rows)

    assert (months["a"], months["b"]) == ("2026-08", "2026-08")


def test_only_the_opening_day_nets() -> None:
    """The history opens on 3 August with a lamp returned that was not bought
    that day; the lamp bought on the 4th does not reach back."""
    months = _months([("2026-08-03", "-1", "30", "x", "Lamp", None),
                      ("2026-08-04", "1", "30", "x", "Lamp", None)])

    assert months["x"] is None


def test_a_product_returned_in_full_the_same_day_keeps_the_customer_new() -> None:
    """Bought 1, returned 1 of the same product: nothing is left over."""
    months = _months([("2026-08-07", "1", "10", "x", "Mug", None),
                      ("2026-08-07", "-1", "10", "x", "Mug", None)])

    assert months["x"] == "2026-08"


def test_with_only_a_sku_mapped_the_sku_is_the_product() -> None:
    """Mutation check (2E-f): product_name unmapped, sku mapped."""
    mapping = {k: v for k, v in MAPPING.items() if v != "product_name"}
    months = _months([("2026-08-07", "2", "10", "x", None, "SKU1"),
                      ("2026-08-07", "-1", "10", "x", None, "sku1"),
                      ("2026-08-07", "2", "10", "y", None, "SKU1"),
                      ("2026-08-07", "-1", "10", "y", None, "SKU2")], mapping)

    assert (months["x"], months["y"]) == ("2026-08", None)


def test_with_no_product_column_every_first_day_return_opens_with_a_refund() -> None:
    """product_name is required by stage 1, but a file without it keeps the
    2E-c2 rule: nothing can be matched."""
    mapping = {k: v for k, v in MAPPING.items() if v not in ("product_name", "sku")}
    months = _months([("2026-08-07", "2", "10", "x", "Mug", None),
                      ("2026-08-07", "-1", "10", "x", "Mug", None)], mapping)

    assert months["x"] is None


# --- the per-row customer (decision 4) --------------------------------------------

CUSTOMER_MAPPING = {"Date": "transaction_date", "Qty": "quantity", "Price": "unit_price",
                    "Cust": "customer", "Inv": "order_id"}


def _customers(rows, mapping=CUSTOMER_MAPPING):
    df = pd.DataFrame(rows, columns=["Date", "Qty", "Price", "Cust", "Inv"])
    return parse_transactions(df, mapping)


def test_a_blank_customer_takes_its_receipts_named_customer() -> None:
    """Header-style: "Ann" on the first line of receipt 1 only. Every line of
    it is Ann's, normalised as the identity always is."""
    parsed = _customers([("2026-08-03", "1", "10", " Ann", "1"),
                         ("2026-08-03", "2", "10", None, "1"),
                         ("2026-08-03", "1", "5", "", "1")])

    assert parsed.orders_basis == "order_id"
    assert parsed.customers.tolist() == ["ann", "ann", "ann"]


# Ten clean one-line receipts, so one odd receipt in eleven (9.1%) stays
# within stage 1's 10% check and order_id is still trusted.
PADDING = [("2026-08-10", "1", "10", f"Pad{i}", f"p{i}") for i in range(10)]


def test_two_named_customers_on_a_receipt_leave_its_blank_lines_unattributed() -> None:
    parsed = _customers([("2026-08-03", "1", "10", "Ann", "1"),
                         ("2026-08-03", "1", "10", "Bob", "1"),
                         ("2026-08-03", "1", "10", None, "1")] + PADDING)

    assert parsed.orders_basis == "order_id"
    assert parsed.customers.tolist()[:2] == ["ann", "bob"]
    assert pd.isna(parsed.customers.iloc[2])


def test_the_receipts_customer_is_read_from_its_sale_and_return_lines() -> None:
    """2E-e F4: a free item (1 @ 0) carries another name. The sale lines name
    Ann, so the blank sale line is Ann's and the receipt is ONE order."""
    parsed = _customers([("2026-08-03", "1", "10", "Ann", "1"),
                         ("2026-08-03", "1", "0", "Bob", "1"),
                         ("2026-08-03", "1", "10", None, "1")])

    assert parsed.customers.iloc[2] == "ann"
    assert parsed.order_key[parsed.sale].nunique() == 1


def test_a_receipt_with_no_named_sale_line_reads_its_other_lines() -> None:
    """The name sits on the receipt's coupon line only."""
    parsed = _customers([("2026-08-03", "1", "-5", "Ann", "1"),
                         ("2026-08-03", "1", "10", None, "1")])

    assert parsed.customers.iloc[1] == "ann"


def test_the_fill_stays_within_the_receipts_day() -> None:
    """Receipt 1 reused the next day with no name: Ann is not carried over."""
    parsed = _customers([("2026-08-03", "1", "10", "Ann", "1"),
                         ("2026-08-04", "1", "10", None, "1")] + PADDING)

    assert parsed.orders_basis == "order_id"
    assert pd.isna(parsed.customers.iloc[1])


def test_no_fill_without_a_trusted_order_id() -> None:
    """A blank id on a sale line makes the file count lines (2E-e): there is
    no receipt to inherit a customer from."""
    parsed = _customers([("2026-08-03", "1", "10", "Ann", "1"),
                         ("2026-08-03", "1", "10", None, "1"),
                         ("2026-08-03", "1", "10", "Bob", None)])

    assert parsed.orders_basis == "lines"
    assert pd.isna(parsed.customers.iloc[1])


def test_a_blank_date_on_a_named_line_does_not_break_the_fill() -> None:
    """2E-f doubt-review F1: a named line with an order id and no parseable
    date crashed parse_transactions (TypeError in the fill), so stages 1-3
    failed on a file HEAD read. The dateless line is simply not filled."""
    parsed = _customers([("2026-08-03", "1", "10", "Ann", "1"),
                         ("2026-08-03", "1", "10", None, "1"),
                         (None, "1", "10", "Bob", "2")] + PADDING)

    assert parsed.orders_basis == "order_id"
    assert parsed.customers.iloc[1] == "ann"


def test_stage_1_reads_an_order_id_on_dates_only_cleaning_parses() -> None:
    """2E-f doubt-review F1, stage 1: the raw upload's dates do not parse
    yet; the check must find nothing to judge, not crash."""
    df = pd.DataFrame([("03.08.2026 kl. 14", "1", "10", "Ann", "INV1"),
                       ("03.08.2026 kl. 14", "2", "10", None, "INV1")],
                      columns=["Date", "Qty", "Price", "Cust", "Inv"])

    assert order_id_spanning(df, CUSTOMER_MAPPING) == IdCheck(0, 0)


def test_an_id_that_spans_days_is_not_a_receipt_to_fill_from() -> None:
    """2E-f doubt-review F2: cash sales all rung under id "0" on several
    days (one id in eleven - within the file's 10%). On one day Ann is named
    on one line and walk-ins buy on unnamed lines: "0" is not a receipt, so
    the walk-ins stay unattributed instead of becoming Ann's revenue."""
    parsed = _customers([("2026-08-03", "1", "20", None, "0"),
                         ("2026-08-04", "1", "10", "Ann", "0"),
                         ("2026-08-04", "1", "20", None, "0")] + PADDING)

    assert parsed.orders_basis == "order_id"
    assert pd.isna(parsed.customers.iloc[2])


def test_an_id_that_spans_on_return_lines_is_not_a_receipt_either() -> None:
    """2E-f doubt-review F2: a returns desk rings every refund under "RET".
    The file-level check reads sale lines only, so "RET" spanning days was
    never judged, and a walk-in's refund of a 500 TV became Ann's."""
    parsed = _customers([("2026-08-03", "-1", "30", "Bob", "RET"),
                         ("2026-08-04", "-1", "10", "Ann", "RET"),
                         ("2026-08-04", "-1", "500", None, "RET")] + PADDING)

    assert parsed.orders_basis == "order_id"
    assert pd.isna(parsed.customers.iloc[2])


def test_a_refund_under_the_original_receipt_number_keeps_the_fill() -> None:
    """2E-f doubt-review cycle 2, F1: many tills ring a refund under the
    receipt it refunds. Receipt 100 sold on 3 August (Ann named on its first
    line) and one item came back under 100 on the 10th. Judged on its
    return lines too, 100 "spanned" days and was not filled: Ann's new
    revenue read 0 instead of 50, and the receipt split into two orders."""
    parsed = _customers([("2026-08-03", "1", "10", "Ann", "100"),
                         ("2026-08-03", "1", "20", None, "100"),
                         ("2026-08-03", "1", "30", None, "100"),
                         ("2026-08-10", "-1", "10", "Ann", "100")] + PADDING)

    assert parsed.orders_basis == "order_id"
    assert parsed.customers.tolist()[:3] == ["ann", "ann", "ann"]
    assert parsed.order_key[:3].nunique() == 1


def test_the_order_key_keeps_2ee_orders_when_an_id_is_not_filled() -> None:
    """2E-f doubt-review cycle 2, F1: the exclusion of ids that are not one
    receipt decides who the REVENUE belongs to; it must not change how
    orders are counted (2E-e). Cash id "0" on 4 August: Ann's line and a
    walk-in's are one order key, as in 2E-e, while the walk-in's revenue
    stays unattributed."""
    parsed = _customers([("2026-08-03", "1", "20", None, "0"),
                         ("2026-08-04", "1", "10", "Ann", "0"),
                         ("2026-08-04", "1", "20", None, "0")] + PADDING)

    assert pd.isna(parsed.customers.iloc[2])
    assert parsed.order_key.iloc[1] == parsed.order_key.iloc[2]


def test_an_exchange_line_does_not_make_a_returns_desk_id_a_receipt() -> None:
    """2E-f doubt-review cycle 3, F1: one exchange sale line under "RET" had
    RET judged on its sale lines alone (one day, one name), and the
    walk-in's 500 refund on another day went to Ann again. Only the
    receipt's own day - the day of its sale lines - is filled."""
    parsed = _customers([("2026-08-03", "-1", "30", "Bob", "RET"),
                         ("2026-08-04", "-1", "10", "Ann", "RET"),
                         ("2026-08-04", "-1", "500", None, "RET"),
                         ("2026-08-03", "1", "30", "Bob", "RET")] + PADDING)

    assert parsed.orders_basis == "order_id"
    assert pd.isna(parsed.customers.iloc[2])


def test_an_exchange_on_the_named_customers_day_does_not_make_ret_a_receipt() -> None:
    """2E-f doubt-review cycle 4, F1: the exchange line rung on ANN's day
    made that day RET's "receipt day" (its only sale line), and the walk-in's
    500 refund that day went to Ann. RET's return lines fall before that day
    and name two customers: it is not one receipt."""
    parsed = _customers([("2026-08-03", "-1", "30", "Bob", "RET"),
                         ("2026-08-04", "-1", "10", "Ann", "RET"),
                         ("2026-08-04", "1", "30", "Ann", "RET"),
                         ("2026-08-04", "-1", "500", None, "RET")] + PADDING)

    assert parsed.orders_basis == "order_id"
    assert pd.isna(parsed.customers.iloc[3])


def test_a_second_name_on_a_later_day_also_refuses_the_receipt() -> None:
    """2E-f doubt-review cycle 4, case C (mutation check RD9): nothing of RET
    falls before Ann's day, but Bob's return two days later is rung under
    it too - two customers, so RET is not one receipt and the walk-in's 500
    refund on Ann's day is not hers."""
    parsed = _customers([("2026-08-04", "-1", "10", "Ann", "RET"),
                         ("2026-08-04", "1", "30", "Ann", "RET"),
                         ("2026-08-04", "-1", "500", None, "RET"),
                         ("2026-08-06", "-1", "30", "Bob", "RET")] + PADDING)

    assert parsed.orders_basis == "order_id"
    assert pd.isna(parsed.customers.iloc[2])


def test_coupons_read_as_returns_around_one_reversal_are_not_a_receipt() -> None:
    """2E-f doubt-review cycle 4, F1: coupons rung -1 x 5 are return lines,
    on three days under "DISC", with one +1 x 5 reversal on Ann's day. The
    walk-in's coupon that day is not Ann's."""
    parsed = _customers([("2026-08-03", "-1", "5", None, "DISC"),
                         ("2026-08-04", "-1", "5", "Ann", "DISC"),
                         ("2026-08-04", "1", "5", "Ann", "DISC"),
                         ("2026-08-04", "-10", "5", None, "DISC"),
                         ("2026-08-05", "-1", "5", None, "DISC")] + PADDING)

    assert parsed.orders_basis == "order_id"
    assert pd.isna(parsed.customers.iloc[3])


def test_an_unnamed_refund_days_later_leaves_the_receipt_filled() -> None:
    """The receipt day's lines are still Ann's when an unnamed refund comes
    back under the receipt number a week later."""
    parsed = _customers([("2026-08-03", "1", "10", "Ann", "100"),
                         ("2026-08-03", "1", "20", None, "100"),
                         ("2026-08-10", "-1", "10", None, "100")] + PADDING)

    assert parsed.customers.iloc[1] == "ann"


def test_an_id_of_coupons_over_several_days_is_not_a_receipt() -> None:
    """2E-f doubt-review cycle 3, F2: coupons under a shared "DISC" id on
    three days; the walk-in's -50 coupon went to Ann, the one name that day."""
    parsed = _customers([("2026-08-04", "1", "100", "Ann", "100"),
                         ("2026-08-03", "1", "-5", None, "DISC"),
                         ("2026-08-04", "1", "-5", "Ann", "DISC"),
                         ("2026-08-04", "1", "-50", None, "DISC"),
                         ("2026-08-05", "1", "-5", None, "DISC")] + PADDING)

    assert parsed.orders_basis == "order_id"
    assert pd.isna(parsed.customers.iloc[3])


def test_a_cash_id_named_on_its_first_day_is_still_not_a_receipt() -> None:
    """Mutation check (2E-f, RD5): cash id "0" names Ann on its first day and
    sells to walk-ins on a later day. Its sale lines span two days, so no
    day of it is a receipt day - not even Ann's."""
    parsed = _customers([("2026-08-03", "1", "10", "Ann", "0"),
                         ("2026-08-03", "1", "20", None, "0"),
                         ("2026-08-05", "1", "20", None, "0")] + PADDING)

    assert parsed.orders_basis == "order_id"
    assert pd.isna(parsed.customers.iloc[1])


def test_an_id_with_no_sale_line_and_two_names_is_not_a_receipt() -> None:
    """Mutation check (2E-f, RD4): a returns-only id on one day - Ann named
    on a return, Bob on a coupon line. The return lines alone name one
    customer, but the id's lines name two: not one receipt."""
    parsed = _customers([("2026-08-05", "-1", "10", "Ann", "R7"),
                         ("2026-08-05", "1", "-5", "Bob", "R7"),
                         ("2026-08-05", "-1", "30", None, "R7")] + PADDING)

    assert pd.isna(parsed.customers.iloc[2])


def test_a_header_style_refund_receipt_is_filled() -> None:
    """A refund receipt of its own (Online Retail II's "C..." invoices),
    the customer on its first line: one day, one name - one receipt."""
    parsed = _customers([("2026-08-05", "-1", "10", "Ann", "C9"),
                         ("2026-08-05", "-2", "10", None, "C9")] + PADDING)

    assert parsed.customers.iloc[1] == "ann"


def test_no_fill_when_the_order_id_column_is_refused() -> None:
    """Mutation check (2E-f): every id spans two days, so the column is not
    an order id (2E-e's check) and the file counts lines - the blank lines
    are not filled from it."""
    parsed = _customers([("2026-08-03", "1", "10", "Ann", "1"),
                         ("2026-08-04", "1", "10", "Ann", "1"),
                         ("2026-08-03", "1", "10", None, "1")])

    assert parsed.orders_basis == "lines"
    assert pd.isna(parsed.customers.iloc[2])


def test_no_fill_when_order_id_is_not_mapped() -> None:
    mapping = {k: v for k, v in CUSTOMER_MAPPING.items() if v != "order_id"}
    parsed = _customers([("2026-08-03", "1", "10", "Ann", "1"),
                         ("2026-08-03", "1", "10", None, "1")], mapping)

    assert parsed.customers.tolist()[0] == "ann"
    assert pd.isna(parsed.customers.iloc[1])


def test_no_customer_column_means_no_customer_on_any_row() -> None:
    mapping = {k: v for k, v in CUSTOMER_MAPPING.items() if v != "customer"}
    parsed = _customers([("2026-08-03", "1", "10", "Ann", "1")], mapping)

    assert parsed.customers.isna().all()
