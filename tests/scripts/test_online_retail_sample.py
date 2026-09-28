"""The Online Retail II demo sample's rules (scripts/demo/online_retail_ii.py;
PROJECT_PLAN item DEMO) - written before the script. The workbook itself is
read only by the command; these pin the pure part on a frame built by hand."""

import importlib.util
from pathlib import Path

import pandas as pd
import pytest

_PATH = Path(__file__).resolve().parents[2] / "scripts" / "demo" / "online_retail_ii.py"
_SPEC = importlib.util.spec_from_file_location("online_retail_ii", _PATH)
assert _SPEC is not None and _SPEC.loader is not None
demo = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(demo)

COLUMNS = ["Invoice", "StockCode", "Description", "Quantity", "InvoiceDate", "Price", "Customer ID", "Country"]


def _row(invoice: str, customer: float | None, day: str, quantity: int = 1) -> dict:
    return dict(zip(COLUMNS, [invoice, "85048", "GLASS BALL", quantity, pd.Timestamp(day), 6.95, customer,
                              "United Kingdom"], strict=True))


def test_the_second_sheets_days_the_first_holds_are_dropped_by_date() -> None:
    first = pd.DataFrame([_row("1", 1.0, "2010-12-01 09:00"), _row("2", 2.0, "2010-12-09 20:00"),
                          _row("2", 2.0, "2010-12-09 20:00")])  # a genuine repeated line
    second = pd.DataFrame([_row("1", 1.0, "2010-12-01 09:00"), _row("2", 2.0, "2010-12-09 20:00"),
                           _row("3", 3.0, "2010-12-10 08:00")])

    whole = demo.one_file(first, second)

    assert whole["Invoice"].tolist() == ["1", "2", "2", "3"]


def _shop(customers: int = 400, nameless_invoices: int = 200) -> pd.DataFrame:
    rows = []
    for customer in range(1, customers + 1):
        rows += [_row(f"A{customer}", float(customer), "2011-01-05"), _row(f"B{customer}", float(customer),
                                                                         "2011-02-05")]
    for invoice in range(nameless_invoices):
        rows += [_row(f"N{invoice}", None, "2011-03-01"), _row(f"N{invoice}", None, "2011-03-01", 2)]
    rows += [_row("581483", 16446.0, "2011-12-09 09:15", 80995), _row("C581484", 16446.0, "2011-12-09 09:27", -80995),
             _row("541431", 12346.0, "2011-01-18 10:01", 74215), _row("C541433", 12346.0, "2011-01-18 10:17", -74215)]
    return pd.DataFrame(rows)


def test_the_sample_is_the_same_for_the_same_seed() -> None:
    shop = _shop()
    assert demo.sample(shop).equals(demo.sample(shop))
    assert not demo.sample(shop, seed=1).equals(demo.sample(shop, seed=2))


def test_every_customer_drawn_is_whole_and_about_the_fraction_is_drawn() -> None:
    shop = _shop()
    kept = demo.sample(shop, fraction=0.4)
    named = kept[kept["Customer ID"].notna()]
    for customer, lines in named.groupby("Customer ID"):
        assert len(lines) == int((shop["Customer ID"] == customer).sum())
    assert 0.3 < (named["Customer ID"].nunique() - 2) / 400 < 0.5


def test_the_nameless_rows_are_drawn_by_invoice_at_the_same_fraction() -> None:
    kept = demo.sample(_shop(), fraction=0.4)
    nameless = kept[kept["Customer ID"].isna()]
    assert (nameless.groupby("Invoice").size() == 2).all()  # an invoice whole or absent
    assert 0.3 < nameless["Invoice"].nunique() / 200 < 0.5


@pytest.mark.parametrize("seed", [0, 1, 502])
def test_both_typo_pairs_are_kept_whatever_the_draw(seed: int) -> None:
    kept = demo.sample(_shop(), fraction=0.0, seed=seed)
    assert sorted(kept["Invoice"]) == ["541431", "581483", "C541433", "C581484"]


# --- the command (DEMO review #6, #3, #12): the workbook read is faked --------------------------------


def _zip(tmp_path, workbook: bytes = b"workbook bytes") -> "Path":
    import zipfile

    path = tmp_path / "online+retail+ii.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(demo.WORKBOOK, workbook)
    return path


def _sheets(*_args, **_kwargs) -> dict:
    first = pd.DataFrame([_row("1", 1.0, "2010-12-01 09:00"), _row("2", None, "2010-12-09 20:00")])
    second = pd.DataFrame([_row("2", None, "2010-12-09 20:00"), _row("3", 3.0, "2010-12-10 08:00")])
    return {"Year 2009-2010": first, "Year 2010-2011": second}


@pytest.fixture
def recorded(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """A download the command accepts: its checksums recorded, the workbook's
    read faked (openpyxl is a build-only requirement)."""
    path = _zip(tmp_path)
    monkeypatch.setattr(demo, "SOURCE_SHA256", demo.sha256(path.read_bytes()))
    monkeypatch.setattr(demo, "WORKBOOK_SHA256", demo.sha256(b"workbook bytes"))
    monkeypatch.setattr(demo.pd, "read_excel", _sheets)
    monkeypatch.setattr(demo, "FRACTION", 1.0)
    sheets = list(_sheets().values())
    lf = chr(10)  # the script writes LF on every platform
    expected = demo.sample(demo.one_file(*sheets), 1.0, demo.SEED).to_csv(index=False, lineterminator=lf)
    monkeypatch.setattr(demo, "SAMPLE_SHA256", demo.sha256(expected.encode("utf-8")))
    return path


def test_the_command_writes_the_sample_with_lf_line_endings(recorded, tmp_path, capsys) -> None:
    out = tmp_path / "sample.csv"
    assert demo.main([str(recorded), "--out", str(out)]) == 0
    written = out.read_bytes()
    assert b"\r\n" not in written and written.count(b"\n") == 4  # the header and three lines
    assert demo.sha256(written) in capsys.readouterr().out


def test_a_download_whose_workbook_differs_is_refused(recorded, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(demo, "WORKBOOK_SHA256", "0" * 64)
    with pytest.raises(SystemExit, match="not the recorded workbook"):
        demo.main([str(recorded), "--out", str(tmp_path / "x.csv")])
    assert not (tmp_path / "x.csv").exists()


def test_a_repackaged_download_of_the_same_workbook_is_accepted(recorded, tmp_path, monkeypatch, capsys) -> None:
    # #12: UCI re-zips its files; the workbook inside is what is sampled.
    monkeypatch.setattr(demo, "SOURCE_SHA256", "0" * 64)
    assert demo.main([str(recorded), "--out", str(tmp_path / "x.csv")]) == 0
    assert "repackaged" in capsys.readouterr().out


def test_a_workbook_without_its_two_sheets_is_refused(recorded, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(demo.pd, "read_excel", lambda *_a, **_k: {"one": _sheets()["Year 2009-2010"]})
    with pytest.raises(SystemExit, match="two sheets"):
        demo.main([str(recorded), "--out", str(tmp_path / "x.csv")])


def test_a_sample_over_the_upload_cap_is_refused_and_not_written(recorded, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(demo, "MAX_BYTES", 10)
    with pytest.raises(SystemExit, match="lower FRACTION"):
        demo.main([str(recorded), "--out", str(tmp_path / "x.csv")])
    assert not (tmp_path / "x.csv").exists()


def test_a_sample_that_is_not_the_recorded_one_exits_non_zero(recorded, tmp_path, capsys, monkeypatch) -> None:
    # 4A review 1 #16: written (it may still be useful), but the command
    # fails; review 3 #13: beside the recorded sample, never over it.
    monkeypatch.setattr(demo, "SAMPLE_SHA256", "0" * 64)
    out = tmp_path / "sample.csv"
    out.write_bytes(b"the recorded sample")
    assert demo.main([str(recorded), "--out", str(out)]) == 1
    assert out.read_bytes() == b"the recorded sample"
    assert (tmp_path / "sample.not-recorded.csv").exists()
    assert "NOT the recorded sample" in capsys.readouterr().out
