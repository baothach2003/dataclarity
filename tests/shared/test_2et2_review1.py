"""Session 2E-t2's first review (fresh context, 2026-09-28): how
`parse_transactions` reads the line-taxonomy columns.

#9  stage 1's order checks parse the RAW file: they need its classes, not
    its suggestions, and ran the candidate search for nothing (~4.7 s a
    parse on Online Retail II);
#10 cleaned.csv's `class_source` and `suggested_class` were never checked,
    two of the three columns were silently reclassified, and the refusal
    reached the user as a generic 500 - and a raw file's own column named
    `line_class` is the user's, never stage 1's.
"""

import pandas as pd
import pytest

from shared import line_taxonomy
from shared.order_checks import parse_for_checks
from shared.transactions import LineClassColumnsError, parse_transactions

MAPPING = {"Day": "transaction_date", "Order": "order_id", "Sku": "sku", "Name": "product_name",
           "Qty": "quantity", "Price": "unit_price"}


def _frame(**extra: list) -> pd.DataFrame:
    return pd.DataFrame({"Day": ["2026-08-01", "2026-08-02"], "Order": ["O1", "O2"], "Sku": ["P", "A1"],
                         "Name": ["POSTAGE", "Mug"], "Qty": ["1", "-1"], "Price": ["5", "10"], **extra})


def _classes(**changes: list) -> dict[str, list]:
    return {"line_class": ["sale", "customer_return"], "class_source": ["rule", "rule"],
            "suggested_class": ["charge", None]} | changes


def test_cleaned_csvs_classes_are_read() -> None:
    parsed = parse_transactions(_frame(**_classes()), MAPPING)
    assert (list(parsed.classes), list(parsed.class_source), list(parsed.suggested.fillna("-"))) == (
        ["sale", "customer_return"], ["rule", "rule"], ["charge", "-"])


@pytest.mark.parametrize(("column", "values", "shown"), [
    ("line_class", ["sale", "fee"], "fee"),
    ("line_class", ["sale", None], "(blank)"),
    ("class_source", ["rule", "USER"], "USER"),
    ("class_source", ["rule", None], "(blank)"),
    ("suggested_class", ["fee", None], "fee"),
])
def test_a_value_outside_its_closed_list_is_refused(column: str, values: list, shown: str) -> None:
    with pytest.raises(LineClassColumnsError, match=f"`{column}`.*{shown}.*re-upload"):
        parse_transactions(_frame(**_classes(**{column: values})), MAPPING)


def test_some_of_the_three_columns_without_the_others_are_refused() -> None:
    written = _classes()
    del written["class_source"]
    with pytest.raises(LineClassColumnsError, match="class_source"):
        parse_transactions(_frame(**written), MAPPING)


def test_a_raw_files_own_line_class_column_is_the_users(monkeypatch: pytest.MonkeyPatch) -> None:
    # The user's column is not stage 1's; the raw parse classifies by the
    # rules and never searches for the suggestions (#9).
    def no_search(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("searched for candidates on the raw file")

    monkeypatch.setattr(line_taxonomy, "non_product_candidates", no_search)
    raw = _frame(**_classes(line_class=["whatever", "the user wrote"], class_source=["x", "y"]))
    parsed = parse_for_checks(raw, MAPPING)
    assert parsed is not None
    assert list(parsed.classes) == ["sale", "customer_return"]
    assert parsed.suggested.isna().all()


def test_an_in_memory_frame_without_the_columns_is_classified_with_its_suggestions() -> None:
    parsed = parse_transactions(_frame(), MAPPING)
    assert (list(parsed.classes), list(parsed.suggested.fillna("-"))) == (["sale", "customer_return"],
                                                                          ["charge", "-"])
