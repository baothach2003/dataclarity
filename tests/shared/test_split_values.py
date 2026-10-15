"""A line's value when sales are split by a column (Thach's Q4, 2026-10-15,
and his Q6 and Q7, 2026-10-16; methods C:/Users/Happy/dashboard-q345-method.txt
and C:/Users/Happy/dashboard-q678-method.txt): one definition for stage 1's
eligibility and stage 2's figures (CLAUDE.md 3.1). Each line is read alone;
only a column written on each order's first line, which the user said applies
to the whole order (Q7), fills its order's blank lines. Two values in one
order mark a line attribute (Q6): each line keeps its own."""

import pandas as pd

from shared.split_values import split_values

VALUES = pd.Series(["Card", None, " card", None, None, "Cash", "Card", "", "Cash", None])
ORDERS = pd.Series(["A", "A", "A", "B", "B", "C", "C", "D", "E", "E"])
EVERY = pd.Series(True, index=VALUES.index)
# Shopify's shape: each order's value on its first line only.
FIRST = pd.Series(["Card", None, None, None, "Cash", None, "", "Cash", None])
FIRST_ORDERS = pd.Series(["A", "A", "A", "B", "C", "C", "D", "E", "E"])
FIRST_SCOPE = pd.Series(True, index=FIRST.index)


def test_a_first_line_column_is_found_and_filled_only_when_the_user_said_so() -> None:
    # Q7 (Thach, 2026-10-16): never filled alone. Asked: A has Card on its first line, so its two blank lines
    # are Card's; B: no value - stays blank; C: Cash; D: "" is blank, no value; E: Cash.
    found = split_values(FIRST, FIRST_ORDERS, by_order=True, scope=FIRST_SCOPE, fill=True)
    assert found.keys.tolist() == ["card", "card", "card", None, "cash", "cash", None, "cash", "cash"]
    assert found.first_line_only and found.filled
    assert found.names == {"card": "Card", "cash": "Cash"}  # the first spelling in the file


def test_a_first_line_column_not_answered_is_read_line_by_line() -> None:
    found = split_values(FIRST, FIRST_ORDERS, by_order=True, scope=FIRST_SCOPE)
    assert found.keys.tolist() == ["card", None, None, None, "cash", None, None, "cash", None]
    assert found.first_line_only and not found.filled


def test_two_values_in_one_order_are_a_line_attribute_each_line_its_own() -> None:
    # Q6: C holds Cash and Card - a line attribute: each line keeps its value, nothing is filled or asked.
    found = split_values(VALUES, ORDERS, by_order=True, scope=EVERY, fill=True)
    assert not found.first_line_only and not found.filled
    assert found.keys.tolist() == ["card", None, "card", None, None, "cash", "card", None, "cash", None]


def test_without_an_order_id_every_line_is_read_alone_and_nothing_is_asked() -> None:
    found = split_values(FIRST, FIRST_ORDERS, by_order=False, scope=FIRST_SCOPE, fill=True)
    assert found.keys.tolist() == ["card", None, None, None, "cash", None, None, "cash", None]
    assert not found.first_line_only and not found.filled


def test_only_the_scope_lines_say_what_an_order_holds() -> None:
    # E's Cash (line 7) is outside the scope (not counted in revenue): E holds no value on a counted line, so its
    # line 8 stays blank; the rest is Shopify's shape.
    scope = FIRST_SCOPE.copy()
    scope[7] = False
    found = split_values(FIRST, FIRST_ORDERS, by_order=True, scope=scope, fill=True)
    assert found.keys[8] is None and found.filled


def test_a_later_line_counts_as_first_when_the_first_is_outside_the_scope() -> None:
    # Order A's first line is a gift card (not counted): its first COUNTED line holds the value.
    values = pd.Series([None, "Card", None])
    found = split_values(values, pd.Series(["A", "A", "A"]), by_order=True,
                         scope=pd.Series([False, True, True]), fill=True)
    assert found.first_line_only and found.keys.tolist() == [None, "card", "card"]


def test_an_order_whose_values_differ_only_in_spelling_is_one_value() -> None:
    found = split_values(pd.Series(["Web", None, "WEB "]), pd.Series(["A", "A", "B"]), by_order=True,
                         scope=pd.Series([True, True, True]), fill=True)
    assert found.keys.tolist() == ["web", "web", "web"]


def test_an_empty_column() -> None:
    empty = pd.Series([], dtype="object")
    found = split_values(empty, empty, by_order=True, scope=pd.Series([], dtype=bool), fill=True)
    assert found.keys.tolist() == [] and found.names == {} and not found.first_line_only and not found.filled


def test_a_column_written_on_later_lines_too_is_read_per_line() -> None:
    # The scoped review's F1 (probe V2): a value on an order's SECOND line shows the column is not written on
    # each order's first line - it is read per line, even when a fill is asked; filling would give a bag's
    # sales to a vendor.
    values = pd.Series(["Acme", None, None, "Bolt"])
    orders = pd.Series(["A", "A", "B", "B"])
    found = split_values(values, orders, by_order=True, scope=pd.Series([True] * 4), fill=True)
    assert found.keys.tolist() == ["acme", None, None, "bolt"]
    assert not found.first_line_only and not found.filled


def test_a_value_on_every_line_of_its_order_asks_nothing() -> None:
    # WooCommerce's shape: the order's fields repeated on each line - nothing to fill, nothing to ask.
    found = split_values(pd.Series(["Card", "Card", "Cash"]), pd.Series(["A", "A", "B"]), by_order=True,
                         scope=pd.Series([True] * 3), fill=True)
    assert not found.first_line_only and found.keys.tolist() == ["card", "card", "cash"]


def test_one_line_orders_ask_nothing() -> None:
    # Kaggle's shape: every order one line - every value is on a first line, but no blank line would take it.
    found = split_values(pd.Series(["Card", None, "Cash"]), pd.Series(["A", "B", "C"]), by_order=True,
                         scope=pd.Series([True] * 3), fill=True)
    assert not found.first_line_only and found.keys.tolist() == ["card", None, "cash"]


def test_an_order_with_no_value_does_not_make_a_first_line_column() -> None:
    # B's lines are all blank: nothing of B to fill; A alone has a blank line under its value.
    values = pd.Series(["Card", None, None, None])
    found = split_values(values, pd.Series(["A", "A", "B", "B"]), by_order=True, scope=pd.Series([True] * 4),
                         fill=True)
    assert found.first_line_only and found.keys.tolist() == ["card", "card", None, None]
    only_b_blank = split_values(pd.Series(["Card", "Cash", None, None]), pd.Series(["A", "C", "B", "B"]),
                                by_order=True, scope=pd.Series([True] * 4), fill=True)
    assert not only_b_blank.first_line_only
