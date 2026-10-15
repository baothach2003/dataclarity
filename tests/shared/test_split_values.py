"""A line's value when sales are split by a column (Thach's Q4, 2026-10-15;
method C:/Users/Happy/dashboard-q345-method.txt): one definition for stage 1's
eligibility and stage 2's figures (CLAUDE.md 3.1). With a trusted order id a
blank line takes its order's one value; two values in one order are counted."""

import pandas as pd

from shared.split_values import split_values

VALUES = pd.Series(["Card", None, " card", None, None, "Cash", "Card", "", "Cash", None])
ORDERS = pd.Series(["A", "A", "A", "B", "B", "C", "C", "D", "E", "E"])
EVERY = pd.Series(True, index=VALUES.index)
# Shopify's shape: each order's value on its first line only.
FIRST = pd.Series(["Card", None, None, None, "Cash", None, "", "Cash", None])
FIRST_ORDERS = pd.Series(["A", "A", "A", "B", "C", "C", "D", "E", "E"])


def test_a_blank_line_takes_its_orders_one_value() -> None:
    found = split_values(FIRST, FIRST_ORDERS, by_order=True, scope=pd.Series(True, index=FIRST.index))
    # A: Card on its first line, so its two blank lines are Card's. B: no value - stays blank. C: Cash. D: ""
    # is blank, no value. E: Cash.
    assert found.keys.tolist() == ["card", "card", "card", None, "cash", "cash", None, "cash", "cash"]
    assert found.filled and found.conflicting_orders == 0
    assert found.names == {"card": "Card", "cash": "Cash"}  # the first spelling in the file


def test_two_values_in_one_order_are_counted_and_nothing_is_filled() -> None:
    # VALUES: C holds Cash and Card; A holds Card on two lines - values on later lines, so no fill (F1).
    found = split_values(VALUES, ORDERS, by_order=True, scope=EVERY)
    assert found.conflicting_orders == 1 and not found.filled
    assert found.keys.tolist() == ["card", None, "card", None, None, "cash", "card", None, "cash", None]


def test_without_an_order_id_every_line_is_read_alone() -> None:
    found = split_values(VALUES, ORDERS, by_order=False, scope=EVERY)
    assert found.keys.tolist() == ["card", None, "card", None, None, "cash", "card", None, "cash", None]
    assert found.conflicting_orders == 0


def test_only_the_scope_lines_say_what_an_order_holds() -> None:
    # Line 8 (E's Cash) is outside the scope (not counted in revenue): E has no value, so line 9 stays blank;
    # line 6 (C's Card) outside too: C holds Cash only, so it is no conflict.
    scope = EVERY.copy()
    scope[[6, 8]] = False
    found = split_values(VALUES, ORDERS, by_order=True, scope=scope)
    assert found.keys[9] is None
    assert found.conflicting_orders == 0


def test_an_order_whose_values_differ_only_in_spelling_is_one_value() -> None:
    found = split_values(pd.Series(["Web", "WEB "]), pd.Series(["A", "A"]), by_order=True,
                         scope=pd.Series([True, True]))
    assert found.keys.tolist() == ["web", "web"] and found.conflicting_orders == 0


def test_an_empty_column() -> None:
    empty = pd.Series([], dtype="object")
    found = split_values(empty, empty, by_order=True, scope=pd.Series([], dtype=bool))
    assert found.keys.tolist() == [] and found.conflicting_orders == 0 and found.names == {}


def test_an_order_holding_two_values_fills_nothing() -> None:
    # Mutation's survivor: order C holds Cash and Card, and a blank line - which of the two is its? Neither.
    found = split_values(pd.Series(["Cash", "Card", None]), pd.Series(["C", "C", "C"]), by_order=True,
                         scope=pd.Series([True, True, True]))
    assert found.keys.tolist() == ["cash", "card", None] and found.conflicting_orders == 1


def test_a_column_written_on_later_lines_too_is_read_per_line() -> None:
    # The scoped review's F1 (probe V2): a value on an order's SECOND line shows the column is not an order's
    # first-line field (Shopify's shape) - a per-line attribute; filling would give a bag's sales to a vendor.
    values = pd.Series(["Acme", None, None, "Bolt"])
    orders = pd.Series(["A", "A", "B", "B"])
    found = split_values(values, orders, by_order=True, scope=pd.Series([True] * 4))
    assert found.keys.tolist() == ["acme", None, None, "bolt"]
    assert not found.filled


def test_a_first_line_field_is_filled() -> None:
    values = pd.Series(["Card", None, "Cash", None, None])
    orders = pd.Series(["A", "A", "B", "B", "B"])
    found = split_values(values, orders, by_order=True, scope=pd.Series([True] * 5))
    assert found.keys.tolist() == ["card", "card", "cash", "cash", "cash"] and found.filled
