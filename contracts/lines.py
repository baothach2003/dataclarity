"""The line taxonomy's blocks of metrics.json and diagnosis.json (session
2E-t2; docs/LINE_TAXONOMY.md sections 3 and 5; docs/CONTRACTS.md sections 6
and 7): the revenue identity, what stays outside revenue, the lines no rule
placed or could measure, and the notes the standing rule puts beside a
figure the data cannot fully tell apart (CLAUDE.md 3.3a). A note's sentence
and the figures it qualifies are fixed per code, here, so a stage that
writes a note cannot word it its own way."""

from math import isfinite
from typing import Annotated, Literal, Self

from pydantic import AfterValidator, Field, NonNegativeInt, model_validator

from contracts._base import ContractModel, NonNegativeFloat
from contracts.cleaning import CleanedLineClass

Scope = Literal["file", "current", "previous"]
NoteCode = Literal["same_day_cancellations", "returns_booked_as_in", "unconfirmed_suggestions",
                   "unconfirmed_deductions", "discounts_in_prices", "other_transaction_types"]
# What a note qualifies; `diagnosis` is stage 3's headline and causes, which
# read the whole history window.
NoteFigure = Literal["revenue", "gross_sales", "returns", "discounts", "other_deductions", "return_rate",
                     "orders", "aov", "units", "customers", "products", "diagnosis"]
UnmeasurableReason = Literal["no quantity", "no price", "amount too large to add"]
# A stock-in line's amount by its sign; `no_money` an amount of zero or none
# (`lines_without_amount` counts the latter - their money is unknown).
StockInSign = Literal["positive", "negative", "no_money"]

# Every figure a counted line's reading can move: a line whose meaning the
# data cannot tell is read by its signs into all of them (the standing rule).
_A_COUNTED_LINE: list[NoteFigure] = ["revenue", "gross_sales", "returns", "other_deductions", "return_rate",
                                     "orders", "aov", "units", "customers", "products", "diagnosis"]
NOTE_TEXTS: dict[str, str] = {
    "same_day_cancellations": (
        "Returns and the return rate include same-day cancellations, which the data cannot separate: the "
        "measures count the return lines rung the day their customer bought the same product, those sale "
        "lines, and the return lines no match can check: with no named customer, or on a pooled code."),
    "returns_booked_as_in": (
        'Lines typed "in" are outside revenue as stock received. A customer return booked as "in" cannot be '
        "told from stock received, so returns, the return rate and the customer figures leave it out, and "
        "revenue is not reduced by it."),
    "unconfirmed_suggestions": (
        "Some keys the file suggests are costs, charges, discounts, adjustments or gift cards were not confirmed "
        "in Review: their lines stay what their signs say, in every figure. The measures count them, their "
        "returns, and the orders holding only such lines."),
    "unconfirmed_deductions": (
        "Lines at a negative price are other deductions: refunds, coupons and write-offs the data cannot tell "
        "apart. A refund among them is not in returns or the return rate, and a write-off among them keeps "
        "revenue lower than it may be."),
    "discounts_in_prices": (
        "Discounts count only lines classed as discounts; a discount already taken off a line's price is not "
        "visible, and that line's gross sales are at the reduced price."),
    "other_transaction_types": (
        'Lines carry transaction types other than in or out; v1 reads only "in", so these are read by their '
        "signs as sales or returns. The measures count them by value, the rarest values together."),
}
# Every figure the note's lines move (the standing rule: the note is shown
# wherever the affected figure is - 2E-t2 reviews 1 #12 and 2 #4).
NOTE_FIGURES: dict[str, list[NoteFigure]] = {
    # A cancelled sale stays in its product's units sold.
    "same_day_cancellations": ["gross_sales", "returns", "return_rate", "orders", "aov", "customers", "products",
                               "diagnosis"],
    # A return booked "in" leaves revenue - and so the order value - and its
    # product's revenue and units unreduced.
    "returns_booked_as_in": ["revenue", "returns", "return_rate", "aov", "units", "customers", "products",
                             "diagnosis"],
    "unconfirmed_suggestions": _A_COUNTED_LINE,
    # A line at a negative price is in its product's and its customer's money.
    "unconfirmed_deductions": ["revenue", "other_deductions", "returns", "return_rate", "aov", "customers",
                               "products", "diagnosis"],
    "discounts_in_prices": ["gross_sales", "discounts"],
    # Read by its signs, a line of another type is a sale, an order, a buyer
    # and units like any other (2E-t2 review 1 #12).
    "other_transaction_types": _A_COUNTED_LINE,
}


class IdentityTerms(ContractModel):
    """One month's revenue identity: net revenue = gross sales - returns -
    discounts - other deductions (unconfirmed) + other revenue, to float
    residue. Returns, discounts and other deductions are what they took
    away (minus their signed sum). `returns_on_suggested_keys`: the part of
    returns on keys the file suggests are costs, charges, discounts,
    adjustments or gift cards and nobody confirmed (Thach's Q26).
    `money_moved`: the sum of the month's counted lines' amounts, each as a
    size - the scale residue is judged against (`shared/numbers.py`): a
    charge and its reversal cancel inside one term, and against the terms
    alone their residue read as a sum that does not add up (2E-t2 review 1
    #2)."""

    gross_sales: float
    returns: float
    discounts: float
    other_deductions: float
    other_revenue: float
    net_revenue: float
    returns_on_suggested_keys: float
    money_moved: NonNegativeFloat

    @model_validator(mode="after")
    def _adds_up(self) -> Self:
        terms = (self.gross_sales, self.returns, self.discounts, self.other_deductions, self.other_revenue,
                 self.net_revenue, self.returns_on_suggested_keys, self.money_moved)
        if not all(isfinite(t) for t in terms):
            raise ValueError("identity terms must be finite")
        derived = self.gross_sales - self.returns - self.discounts - self.other_deductions + self.other_revenue
        scale = max(self.money_moved, sum(abs(t) for t in terms[:6]), 1.0)
        if abs(derived - self.net_revenue) > 1e-9 * scale:
            raise ValueError(f"the revenue identity does not add up: {derived!r} against {self.net_revenue!r}")
        return self


class RevenueIdentity(ContractModel):
    current: IdentityTerms
    previous: IdentityTerms


class OutsideRevenueLines(ContractModel):
    """The lines of a class outside revenue in one scope (only where there
    are some): their count, the sum of their finite amounts, and how many
    carry no finite amount. Stock received is reported by the sign of its
    amount (docs/LINE_TAXONOMY.md section 3), so a receipt and its
    correction never net to a figure that hides both; the other classes
    carry no sign."""

    line_class: CleanedLineClass
    scope: Scope
    sign: StockInSign | None
    lines: int = Field(gt=0)
    amount: float
    lines_without_amount: NonNegativeInt

    @model_validator(mode="after")
    def _stock_in_by_sign(self) -> Self:
        if (self.line_class == "stock_in") != (self.sign is not None):
            raise ValueError("a sign is given exactly for stock_in lines")
        if self.lines_without_amount and self.sign not in (None, "no_money"):
            raise ValueError("stock-in lines with no amount are reported under no_money")
        return self


class UnclassifiedLines(ContractModel):
    """The lines no rule placed - none, while v1 refuses no shape (Thach): the
    tested, empty class. `share_of_money_moved`: their money over the money
    the counted lines moved in the file; null when nothing moved."""

    lines: NonNegativeInt
    amount: float
    share_of_money_moved: float | None


class UnmeasurableLines(ContractModel):
    """Lines counted nowhere because their quantity, price or amount is not a
    number that adds up, per scope and reason (only where there are some).
    Their money is unknown - never derived from another column."""

    scope: Scope
    reason: UnmeasurableReason
    lines: int = Field(gt=0)


class NoteMeasure(ContractModel):
    """One named count of a note's lines in one scope: `amount` the signed sum
    of their amounts (null where unknown), `orders` and `keys` where the
    note defines them."""

    name: str = Field(min_length=1)
    scope: Scope
    lines: NonNegativeInt
    amount: float | None
    orders: NonNegativeInt | None = None
    keys: NonNegativeInt | None = None


class FigureNote(ContractModel):
    """The standing rule's note (CLAUDE.md 3.3a): beside every figure it
    names, wherever the figure is shown - its code's fixed sentence and
    figures, its numbers in its measures."""

    code: NoteCode
    figures: list[NoteFigure]
    text: str
    measures: list[NoteMeasure]

    @model_validator(mode="after")
    def _fixed_per_code(self) -> Self:
        named = [(m.name, m.scope) for m in self.measures]
        if len(set(named)) != len(named):
            raise ValueError(f"note {self.code!r} names a measure twice in one scope")
        if self.text != NOTE_TEXTS[self.code]:
            raise ValueError(f"note {self.code!r} carries its code's fixed sentence (contracts/lines.py)")
        if self.figures != NOTE_FIGURES[self.code]:
            raise ValueError(f"note {self.code!r} names its code's figures: {NOTE_FIGURES[self.code]}")
        return self


def _one_per_code(notes: list[FigureNote]) -> list[FigureNote]:
    codes = [note.code for note in notes]
    if len(set(codes)) != len(codes):
        raise ValueError(f"one note per code: {codes}")
    return notes


Notes = Annotated[list[FigureNote], AfterValidator(_one_per_code)]
