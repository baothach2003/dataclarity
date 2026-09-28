"""The line taxonomy's effects matrix (Thach, session 2E-t2;
docs/LINE_TAXONOMY.md section 3): what each class of the closed list does to
revenue and to every figure built on it - the single source of truth stages
2 and 3 read, through `shared/transactions.py`'s sets.

Infrastructure in the sense of `shared/transactions.py`: which lines a figure
counts is one definition for every stage, or two stages describe two
different files. What a figure MEANS stays with the stage that computes it.

The identity: net revenue = gross sales - returns - discounts - other
deductions (unconfirmed) + other revenue. Every money term sums its lines'
amounts as signed; returns, discounts and other deductions are reported as
what they took away (minus their signed sum).
"""

from dataclasses import dataclass
from typing import Literal

from contracts.cleaning import CLEANED_LINE_CLASSES

Term = Literal["gross_sales", "returns", "discounts", "other_deductions", "other_revenue"]


@dataclass(frozen=True)
class Effect:
    """One row of the matrix. `counted`: in revenue and every counted figure
    (a counted line also needs a date to be in a month). `term`: its place in
    the identity. `reported`: where metrics.json reports a line counted
    nowhere - every such class has one, so none is dropped silently (2E-t2
    review 3 #9: a new class written `Effect(False, None)` would have been
    in no report). Stage 3's product dimension reads the item
    (`ParsedTransactions.line_class`), not this matrix."""

    counted: bool
    term: Term | None
    reported: Literal["outside_revenue", "unclassified", "unmeasurable"] | None = None

    def __post_init__(self) -> None:
        if self.counted == (self.reported is not None):
            raise ValueError("a counted class is in the figures; any other is reported somewhere")


EFFECTS: dict[str, Effect] = {
    "sale": Effect(True, "gross_sales"),
    "pooled_sale": Effect(True, "gross_sales"),
    "customer_return": Effect(True, "returns"),
    "pooled_return": Effect(True, "returns"),
    # Unconfirmed: a refund, a coupon or a bad-debt write-off at a negative
    # price, which the data cannot tell apart (Thach's Q16).
    "allowance": Effect(True, "other_deductions"),
    "pooled_allowance": Effect(True, "other_deductions"),
    "discount": Effect(True, "discounts"),
    "charge": Effect(True, "other_revenue"),
    "no_money": Effect(True, None),
    "pooled_no_money": Effect(True, None),
    # Outside revenue, reported: a liability, an expense, a reconciling
    # amount, stock received.
    "gift_card_sale": Effect(False, None, "outside_revenue"),
    "gift_card_redemption": Effect(False, None, "outside_revenue"),
    "cost": Effect(False, None, "outside_revenue"),
    "adjustment": Effect(False, None, "outside_revenue"),
    "stock_in": Effect(False, None, "outside_revenue"),
    # The tested, empty class (Thach: no refusals in v1), and the lines with
    # no finite quantity, price or amount: counted nowhere, reported.
    "unclassified": Effect(False, None, "unclassified"),
    "unmeasurable": Effect(False, None, "unmeasurable"),
}
assert set(EFFECTS) == set(CLEANED_LINE_CLASSES), "a class without its effects"

COUNTED = frozenset(c for c, e in EFFECTS.items() if e.counted)
GROSS = frozenset(c for c, e in EFFECTS.items() if e.term == "gross_sales")
RETURNS = frozenset(c for c, e in EFFECTS.items() if e.term == "returns")
# Counted, neither a sale nor a return nor a charge: 2E-c's deduction bucket.
DEDUCTIONS = frozenset(c for c, e in EFFECTS.items()
                       if e.counted and e.term in ("discounts", "other_deductions", None))
# Outside revenue by the user's answer about the item - left out, reported
# per class in metrics.json's `non_product` (2E-d2).
OUTSIDE_REVENUE = frozenset(c for c, e in EFFECTS.items() if e.reported == "outside_revenue")
# A line typed "in" is out by its type, the others by the user's item.
LEFT_OUT = OUTSIDE_REVENUE - {"stock_in"}
