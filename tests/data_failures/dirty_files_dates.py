"""DF-A (file structure) and DF-B (dates) samples - see dirty_base.py."""

import calendar
from datetime import date

from tests.data_failures.dirty_base import CUSTOMERS, MAPPING, PRODUCTS, Sample, as_csv, base, edit, on

# --- A. file structure (stage 1 reads the bytes) --------------------------------------------------


def a3() -> Sample:
    return Sample(raw=b"Date,Qty,Price,Product,Cust\n")


def a4() -> Sample:
    # A spreadsheet's bytes saved under .csv: a zip archive's header.
    return Sample(raw=b"PK\x03\x04\x14\x00\x06\x00\x08\x00\x00\x00!\x00" + bytes(range(256)) * 4)


def a5() -> Sample:
    rows = base(date(2024, 2, 1), date(2024, 2, 2))
    rows[0]["Product"] = "Café au lait"
    return Sample(raw=as_csv(rows).decode("utf-8").encode("latin-1"))


def _decimal_commas(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    for row in rows:
        row["Price"] = row["Price"].replace(".", ",")
    return rows


def a6() -> Sample:
    return Sample(raw=as_csv(_decimal_commas(base(date(2024, 2, 1), date(2024, 2, 2))), ";"))


def a6b() -> Sample:
    # The whole file so: a European export, through the real flow.
    return Sample(raw=as_csv(_decimal_commas(base()), ";"))


def a7() -> Sample:
    rows = base(date(2024, 2, 1), date(2024, 2, 2))
    return Sample(raw=as_csv(rows + rows[:3]))


def a8() -> Sample:
    return Sample(raw=as_csv([row | {"Note": ""} for row in base(date(2024, 2, 1), date(2024, 2, 2))]))


def a9() -> Sample:
    return Sample(raw=as_csv([row | {"Store": "Main"} for row in base(date(2024, 2, 1), date(2024, 2, 2))]))


def a10() -> Sample:
    rows = base(date(2024, 2, 1), date(2024, 2, 2))
    rows[0]["Qty"], rows[1]["Qty"] = "one", "two"
    return Sample(raw=as_csv(rows))


def a12() -> Sample:
    return Sample(base(), mapping={k: v for k, v in MAPPING.items() if v != "unit_price"})


def a13() -> Sample:
    # A NUL inside Ann's Mug price on 2024-02-10 ("1", NUL, "0.0") - far past
    # the first 8 KB, which the upload checks for binary data.
    rows = base()
    on(rows, "2024-02-10")["Price"] = "1\x000.0"
    return Sample(rows, raw=as_csv(rows))


def a14() -> Sample:
    return Sample(raw=b"Date,Qty,Price\n2024-02-01,1,10.0,extra,more\n2024-02-02,1,4.0\n")


def a15() -> Sample:
    return Sample(raw=as_csv(base(date(2024, 2, 1), date(2024, 2, 2))).decode("utf-8").encode("utf-16"))


# --- B. dates ---------------------------------------------------------------------------------------


def b1() -> Sample:
    rows = base()
    for row in rows:
        if row["Date"] == "2024-02-10" and not (row["Cust"] == "Cy" and row["Product"] == "Tea"):
            row["Date"] = "not a date"  # Ann's, Bo's and Cy's Mug: 10 + 4 + 10 + 4 + 10 = 38.00
    return Sample(rows)


def b2() -> Sample:
    rows = base()
    for row in rows:
        if row["Date"].startswith("2024-01"):
            row["Date"] = date.fromisoformat(row["Date"]).strftime("%d %b %Y")
    return Sample(rows)


def b3() -> Sample:
    # Day first, every day 1-12: either order reads every cell.
    return Sample([row for row in base(fmt="%d/%m/%Y") if int(row["Date"][:2]) <= 12])


def b4() -> Sample:
    rows = []
    for year, month in [(2023, m) for m in range(1, 13)] + [(2024, 1), (2024, 2)]:
        days = calendar.monthrange(year, month)[1]
        for customer in CUSTOMERS:
            for product, price in PRODUCTS:
                rows.append({"Date": f"{year:04d}-{month:02d}-01", "Qty": str(days), "Price": price,
                             "Product": product, "Cust": customer})
    return Sample(rows)


def b5() -> Sample:
    rows = b4().rows
    for row in rows:
        year, month = int(row["Date"][:4]), int(row["Date"][5:7])
        row["Date"] = f"{year:04d}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}"
    return Sample(rows)


b6 = edit("2024-02-10", Date="10.05.30 2026")  # a dotted time, then a year, in an ISO file


def b7() -> Sample:
    # Two-digit years, day first, every day 1-12 ("05/02/24"): no cell proves the order.
    return Sample([row for row in base(fmt="%d/%m/%y") if int(row["Date"][:2]) <= 12])


def b8() -> Sample:
    return Sample(base(last=date(2024, 3, 10)))


def b9() -> Sample:
    return Sample(base(first=date(2023, 1, 15)))


def b10() -> Sample:
    # The file starts five days into the previous month (an export cut short).
    return Sample(base(first=date(2024, 1, 6)))


def b10b() -> Sample:
    # Five days lost INSIDE the previous month of a longer file.
    return Sample([row for row in base() if not "2024-01-01" <= row["Date"] <= "2024-01-05"])


def b10c() -> Sample:
    # The file starts two days into the previous month: under the tolerance.
    return Sample(base(first=date(2024, 1, 3)))


b11 = edit("2024-02-10", Date="0000-00-00")
b12 = edit("2024-02-10", Date="Feb-24")  # Excel's month-year cell
b13 = edit("2024-02-10", Date="klo 10.30")  # a time with a word, no day


def b14() -> Sample:
    # Year, month, day with two-digit years ("24/02/10"), the whole file.
    return Sample(base(fmt="%y/%m/%d"))


def b15() -> Sample:
    # One line typed in the future (2042 for 2024).
    rows = base()
    rows.append({"Date": "2042-02-10", "Qty": "1", "Price": "10.0", "Product": "Mug", "Cust": "Ann"})
    return Sample(rows)


b16 = edit("2024-02-10", Date="45332")  # Excel's serial number for 2024-02-10
b17 = edit("2024-02-10", Date="10/02/2024 SA")  # Vietnamese AM marker
