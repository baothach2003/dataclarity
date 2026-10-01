"""DF-C (amounts and quantities) and DF-D (line types) samples - see dirty_base.py."""

from collections.abc import Callable
from datetime import date

from tests.data_failures.dirty_base import MAPPING, PRODUCTS, Sample, as_csv, base, edit, extra, invoiced

# --- C. amounts and quantities -----------------------------------------------------------------------

c1 = edit("2024-02-10", Qty="one")
c2 = edit("2024-02-10", Price="")
c3 = edit("2024-02-10", Price="inf")
c4 = edit("2024-02-10", Price="$10.00")
c5 = edit("2024-02-10", Price="10,5")


def c4b() -> Sample:
    # A dearer Mug written with a thousands separator, every line: Excel's
    # "save as CSV" writes the displayed format.
    rows = base()
    for row in rows:
        if row["Product"] == "Mug":
            row["Price"] = "1,000.00"
    return Sample(rows, raw=as_csv(rows))


def c4c() -> Sample:
    # Every price with its currency sign.
    rows = base()
    for row in rows:
        row["Price"] = "$" + row["Price"] + "0"
    return Sample(rows, raw=as_csv(rows))


def c6() -> Sample:
    rows = base(date(2024, 2, 1), date(2024, 2, 2))
    rows[0]["Price"] = "1000.0"  # a mistyped price among 10.0 and 4.0
    return Sample(raw=as_csv(rows))


def _x100(products: tuple[tuple[str, str], ...]) -> Callable[[], Sample]:
    def build() -> Sample:
        rows = base(products=products)
        for row in rows:
            if row["Date"].startswith("2024-02"):
                row["Price"] = str(float(row["Price"]) * 100)
        return Sample(rows)
    return build


c7 = _x100(PRODUCTS + (("Bowl", "6.0"),))  # three products: D2's small-catalogue rule applies
c7b = _x100(PRODUCTS)  # two: "no uniform to speak of" (AI_PIPELINE 7.3)
c8 = extra({"Date": "2024-02-10", "Qty": "1", "Price": "1e308"}, {"Date": "2024-02-11", "Qty": "1", "Price": "1e308"})
c9 = extra({"Date": "2024-02-10", "Qty": "1", "Price": "-10.0"})  # a refund at a negative price
c10 = extra({"Date": "2024-02-10", "Qty": "1", "Price": "0"})


# --- D. line types (the line taxonomy) ---------------------------------------------------------------

d1 = extra({"Date": "2024-02-10", "Qty": "-1"}, {"Date": "2024-02-11", "Qty": "-1"})


def d2() -> Sample:
    # Online Retail II's cancellations: an invoice "C" + number, quantity
    # negative, on a file whose every line has its receipt.
    rows = invoiced(base())
    rows.append({"Date": "2024-02-10", "Qty": "-1", "Price": "10.0", "Product": "Mug", "Cust": "Ann",
                 "Invoice": "C2024-02-10-Ann"})
    return Sample(rows, mapping=MAPPING | {"Invoice": "order_id"})


def _named(name: str, price: str, line_class: str | None, qty: str = "1", customer: str = "Ann") -> Callable[[], Sample]:
    answers = {"line_classes": [{"field": "product_name", "value": name, "line_class": line_class}]} if line_class else {}
    def build() -> Sample:
        sample = extra({"Date": "2024-02-10", "Product": name, "Price": price, "Qty": qty, "Cust": customer},
                       answers=answers)()
        sample.raw = as_csv(sample.rows)
        return sample
    return build


d3 = _named("POSTAGE", "5.0", None)
d3b = _named("POSTAGE", "5.0", "charge")
d4 = _named("Discount", "-3.0", "discount")
d5 = _named("AMAZON FEE", "-7.0", "cost")
d6 = _named("Adjust bad debt", "-50.0", "adjustment")
d6b = _named("Adjust bad debt", "-50.0", None)
d7 = _named("Manual", "12.0", "pooled")
d8 = _named("Gift card", "20.0", "gift_card")
d9 = extra({"Date": "2024-02-10", "Qty": "5", "Price": "3.0", "Product": "Box", "Cust": "", "Type": "in"},
           mapping={"Type": "transaction_type"})
# A type column naming a return on a line whose signs say sale.
d10 = extra({"Date": "2024-02-10", "Type": "Return"}, mapping={"Type": "transaction_type"})
# Online Retail II's own shape for a fee or a discount: quantity -1, price positive.
d11 = _named("AMAZON FEE", "7.0", None, qty="-1", customer="")
d12 = _named("Manual", "12.0", None)  # Online Retail II's "M", unanswered
d13 = _named("Service charge", "12.0", None)  # a word stage 1's suggestions miss
