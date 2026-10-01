"""DF-E (identities), DF-F (placeholders) and DF-G (coverage) samples - see dirty_base.py."""

from collections.abc import Callable
from datetime import date

from tests.data_failures.dirty_base import MAPPING, Sample, as_csv, base, invoiced, on

# --- E. identities -------------------------------------------------------------------------------------


def e1() -> Sample:
    rows = invoiced(base())
    for row in rows:
        if row["Date"] == "2024-02-11" and row["Cust"] == "Ann":
            row["Invoice"] = "2024-02-10-Ann"  # one id on two days
    return Sample(rows, mapping=MAPPING | {"Invoice": "order_id"})


def e2() -> Sample:
    rows = invoiced(base())
    on(rows, "2024-02-10")["Invoice"] = ""
    return Sample(rows, mapping=MAPPING | {"Invoice": "order_id"})


def e3() -> Sample:
    # A header-style export: each receipt names its customer on its first line only.
    rows = invoiced(base())
    for row in rows:
        if row["Product"] == "Tea":
            row["Cust"] = ""
    return Sample(rows, mapping=MAPPING | {"Invoice": "order_id"})


def e4() -> Sample:
    # One code per day for every customer: a daily batch, not a receipt.
    rows = base()
    for row in rows:
        row["Invoice"] = row["Date"]
    return Sample(rows, mapping=MAPPING | {"Invoice": "order_id"}, answers={"order_id_is_receipt": False})


def e5() -> Sample:
    rows = base()
    for row in rows:
        if row["Date"] == "2024-02-10" and row["Product"] == "Mug":
            row["Product"] = {"Ann": " mug", "Bo": "MUG ", "Cy": "Mu​g"}[row["Cust"]]
    return Sample(rows)


def e6() -> Sample:
    rows = base(date(2024, 2, 1), date(2024, 2, 2))
    rows[0]["Product"] = "Mug."  # the same label once punctuation is ignored
    return Sample(raw=as_csv(rows))


def e7() -> Sample:
    # Ann's Mug on the first day entered twice, the second with quantity 2.
    rows = base(last=date(2023, 1, 1))
    return Sample(rows + [rows[0] | {"Qty": "2"}])


def e8() -> Sample:
    rows = base()
    for row in rows:
        if row["Date"].startswith("2024-02"):
            row["Cust"] = ""
    return Sample(rows)


def e9() -> Sample:
    # Online Retail II leaves ~23% of lines without a customer: here every Tea line.
    rows = base()
    for row in rows:
        if row["Product"] == "Tea":
            row["Cust"] = ""
    return Sample(rows)


def e11() -> Sample:
    # February's sales name nobody; one return names Ann (a refunds desk
    # that records the customer while the till does not).
    rows = e8().rows + [{"Date": "2024-02-10", "Qty": "-1", "Price": "10.0", "Product": "Mug", "Cust": "Ann"}]
    return Sample(rows)


# --- F. placeholders -------------------------------------------------------------------------------------


def _relabelled(label: str, answer: bool) -> Callable[[], Sample]:
    def build() -> Sample:
        rows = base()
        for row in rows:
            if row["Cust"] == "Cy":
                row["Cust"] = label
        return Sample(rows, answers={"customer_placeholders": [label]} if answer else {})
    return build


f1, f1b, f5 = _relabelled("Guest", True), _relabelled("Guest", False), _relabelled("-", False)


def f2() -> Sample:
    # Numbered walk-in labels, one per till session.
    rows = base()
    for index, row in enumerate(rows):
        if row["Cust"] == "Cy":
            row["Cust"] = f"Walk-in {index % 40 + 1}"
    return Sample(rows)


def f3() -> Sample:
    # Read through stage 1's reader, as every cleaned file is.
    rows = base()
    for row in rows:
        if row["Cust"] == "Cy":
            row["Cust"] = {"Mug": "N/A", "Tea": "null"}[row["Product"]]
    return Sample(rows, raw=as_csv(rows))


def f4() -> Sample:
    rows = base()
    for row in rows:
        if row["Cust"] == "Cy":
            row["Cust"] = "​⁠"
    return Sample(rows)


# --- G. coverage ---------------------------------------------------------------------------------------


def g1() -> Sample:
    return Sample([row for row in base() if not "2024-02-12" <= row["Date"] <= "2024-02-18"])


def g1b() -> Sample:
    # Two days lost: under D1's caution (D1_CAUTION_DAYS 3).
    return Sample([row for row in base() if row["Date"] not in ("2024-02-12", "2024-02-13")])


def g2() -> Sample:
    return Sample([row for row in base() if not row["Date"].startswith("2023-06")])


def g3() -> Sample:
    return Sample(base(first=date(2024, 1, 1)))  # two complete months


def g4() -> Sample:
    return Sample(base(first=date(2023, 7, 1)))  # eight complete months: seven before the current one


def g5() -> Sample:
    return Sample(base())  # fourteen complete months: under the two years a season needs


def g6() -> Sample:
    rows = [row for row in base() if not row["Date"].startswith("2024-02")]
    # On the 29th, so February has elapsed and is the month compared.
    rows += [{"Date": "2024-02-29", "Qty": "-1", "Price": "10.0", "Product": "Mug", "Cust": "Ann"}]
    return Sample(rows)


def g7() -> Sample:
    return Sample(base(date(2024, 2, 10), date(2024, 2, 10)))


def g8() -> Sample:
    return Sample(base(date(2023, 11, 10), date(2023, 12, 9)))  # a "last 30 days" export


def g10() -> Sample:
    # A month of history holding one refund and no sale (not a compared month).
    rows = [row for row in base() if not row["Date"].startswith("2023-06")]
    rows.append({"Date": "2023-06-10", "Qty": "-1", "Price": "10.0", "Product": "Mug", "Cust": "Ann"})
    return Sample(rows)


def g11() -> Sample:
    # The "last 30 days" export with an unpriced line dated the 1st of its first month.
    rows = g8().rows + [{"Date": "2023-11-01", "Qty": "1", "Price": "", "Product": "Mug", "Cust": "Ann"}]
    return Sample(rows)
