"""Build the Online Retail II demo sample (PROJECT_PLAN item DEMO; README
"Demo data"). A developer tool, not a stage: run once, on the UCI download.

    pip install -r scripts/demo/requirements.txt   # openpyxl, to read the workbook
    python scripts/demo/online_retail_ii.py <path/to/online+retail+ii.zip> [--out demo_data/online_retail_ii_sample.csv]

Keep the download outside the repository (the data is never committed). The
workbook inside it is checked against its recorded checksum (the zip's own is
reported: UCI has repackaged its files before); the sample is written with LF
line endings on every platform, where git ignores it, and its checksum is
printed, so the same seed gives a file anyone can verify. With library
versions other than the pinned ones (backend/requirements.txt,
scripts/demo/requirements.txt) the sample can differ: it is then written
as `<name>.not-recorded.csv` beside --out, never over it, and the command
exits with 1.

What it keeps (Thach's decisions, recorded in PROJECT_PLAN section 12):
- the two sheets (2009-12-01..2010-12-09 and 2010-12-01..2011-12-09) as one
  file, their overlap - 2010-12-01..09, in both - dropped by DATE from the
  second sheet, never with `duplicated()`: the file holds genuine repeated
  lines that must stay;
- every row of each customer drawn, at `FRACTION`, from one seeded
  generator; the rows with no customer, drawn by invoice at the same
  fraction, so the customer bridge's `unattributed` term has real data;
- both entered-then-cancelled typo pairs whole, whatever the draw: customers
  16446 (581483 / C581484, 80,995 units) and 12346 (541431 / C541433, 74,215
  units).
"""

import argparse
import hashlib
import io
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

SOURCE_URL = "https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip"
SOURCE_DOI = "10.24432/C5CG6D"  # UCI Machine Learning Repository, CC BY 4.0
SOURCE_SHA256 = "572e36277c2390fbfde10664750731e0a86f55e33470d91919085f0408e67bfb"
WORKBOOK = "online_retail_II.xlsx"
WORKBOOK_SHA256 = "bcbe73b35f5b7babf197fb0cb983a11f5d9ff929078d4aa53d171b1f2df2e980"
SEED = 502  # the dataset's UCI id
# The sample this seed and fraction built on 2026-09-29 (pandas 3.0.6, numpy
# 2.x - numpy's default generator keeps its stream across versions; another
# pandas may still write the same rows as other text).
SAMPLE_SHA256 = "a633097a586c6ab3efb17b8059288b7b3010d095a5510ad9c8b77cba017afe97"
FRACTION = 0.46  # about 40 MB (of 1,048,576 bytes, SPECS SEC-1's unit) of the two sheets' 90 MB
KEPT_CUSTOMERS = (16446.0, 12346.0)  # the two typo pairs, whole
SECOND_SHEET_STARTS = pd.Timestamp("2010-12-10")  # the first day the first sheet does not hold
MB = 1024 * 1024  # SPECS SEC-1's megabyte
MAX_BYTES = 48 * MB  # under the 50 MB upload cap, with room
CUSTOMER, INVOICE, DATE = "Customer ID", "Invoice", "InvoiceDate"
DEFAULT_OUT = Path(__file__).resolve().parents[2] / "demo_data" / "online_retail_ii_sample.csv"


def one_file(first: pd.DataFrame, second: pd.DataFrame) -> pd.DataFrame:
    """The two sheets as one: the second's rows the first also holds - its
    days before `SECOND_SHEET_STARTS` - dropped by date."""
    return pd.concat([first, second[second[DATE] >= SECOND_SHEET_STARTS]], ignore_index=True)


def sample(frame: pd.DataFrame, fraction: float = FRACTION, seed: int = SEED) -> pd.DataFrame:
    """Every row of each customer drawn; the no-customer rows by invoice at
    the same fraction; the typo customers whatever the draw. Rows keep their
    order."""
    rng = np.random.default_rng(seed)
    customers = np.sort(frame[CUSTOMER].dropna().unique())
    drawn = set(customers[rng.random(len(customers)) < fraction]) | set(KEPT_CUSTOMERS)
    nameless = frame[CUSTOMER].isna()
    invoices = np.sort(frame.loc[nameless, INVOICE].astype(str).unique())
    drawn_invoices = set(invoices[rng.random(len(invoices)) < fraction])
    keep = frame[CUSTOMER].isin(drawn) | (nameless & frame[INVOICE].astype(str).isin(drawn_invoices))
    return frame[keep]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("zip", type=Path, help=f"the UCI download ({SOURCE_URL})")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    download = args.zip.read_bytes()
    workbook = zipfile.ZipFile(io.BytesIO(download)).read(WORKBOOK)
    if sha256(workbook) != WORKBOOK_SHA256:
        raise SystemExit(f"{WORKBOOK} in {args.zip} is not the recorded workbook: sha256 {sha256(workbook)}, "
                         f"recorded {WORKBOOK_SHA256}")
    if sha256(download) != SOURCE_SHA256:
        print(f"the download was repackaged (sha256 {sha256(download)}, recorded {SOURCE_SHA256}); "
              "its workbook is the recorded one")
    sheets = list(pd.read_excel(io.BytesIO(workbook), sheet_name=None,
                                dtype={INVOICE: str, "StockCode": str}).values())
    if len(sheets) != 2:
        raise SystemExit(f"expected the workbook's two sheets, found {len(sheets)}")
    whole = one_file(*sheets)
    demo = sample(whole, FRACTION, SEED)
    # LF on every platform: the recorded checksum is the same everywhere.
    text = demo.to_csv(index=False, lineterminator="\n").encode("utf-8")
    if len(text) > MAX_BYTES:
        raise SystemExit(f"the sample is {len(text):,} bytes, over {MAX_BYTES:,}: lower FRACTION")
    recorded = sha256(text) == SAMPLE_SHA256
    # A sample that is not the recorded one never replaces it (4A review 3
    # #13: the recorded sample, git-ignored, is rebuilt only with the
    # recorded library versions); it is kept beside it, as it may still be
    # useful, and the command fails (4A review 1 #16).
    out = args.out if recorded else args.out.with_name(f"{args.out.stem}.not-recorded{args.out.suffix}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(text)
    named = demo[CUSTOMER].notna()
    print(f"source rows (overlap dropped): {len(whole):,}")
    print(f"sample rows: {len(demo):,} ({len(text) / MB:.1f} MB, {len(text):,} bytes) -> {out}")
    print(f"customers: {demo.loc[named, CUSTOMER].nunique():,} of {whole[CUSTOMER].nunique():,}; "
          f"no-customer invoices: {demo.loc[~named, INVOICE].nunique():,} of "
          f"{whole.loc[whole[CUSTOMER].isna(), INVOICE].nunique():,}")
    print(f"dates: {demo[DATE].min()} .. {demo[DATE].max()}")
    for invoice in ("581483", "C581484", "541431", "C541433"):
        lines = demo[demo[INVOICE].astype(str) == invoice]
        print(f"invoice {invoice}: {len(lines)} line(s), quantity {lines['Quantity'].sum():,}")
    print(f"sample sha256: {sha256(text)} ({'the recorded sample' if recorded else 'NOT the recorded sample'})")
    return 0 if recorded else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
