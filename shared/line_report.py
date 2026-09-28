"""The line taxonomy's report (Thach, sessions 2E-t2 and 2E-t3;
docs/LINE_TAXONOMY.md sections 3 and 5): the revenue identity, the classes
outside revenue, the lines no rule placed and the lines that could not be
measured, and the notes the standing rule puts beside the figures the data
cannot fully tell apart (CLAUDE.md 3.3a) - for the scopes the caller names:
metrics.json's file and compared months (stage 2), Review's whole file
(stage 1). One definition, so Review and metrics.json cannot tell two
stories about one file. Every number is a count or a sum of the classes,
read through `shared/transactions.py` and `shared/line_effects.py`. No note
changes a figure.
"""

import numpy as np
import pandas as pd

from contracts.lines import (
    NOTE_FIGURES,
    NOTE_TEXTS,
    FigureNote,
    IdentityTerms,
    NoteMeasure,
    OutsideRevenueLines,
    Scope,
    UnclassifiedLines,
    UnmeasurableLines,
)
from shared.line_effects import EFFECTS, GROSS, OUTSIDE_REVENUE, RETURNS
from shared.products import netting_keys
from shared.text import identifier_text
from shared.transactions import ParsedTransactions

# The suggestions whose confirmation would move a line out of its place
# (Q26): a pooled key's lines stay sales and returns once confirmed (E2).
_LEAVING = ("cost", "charge", "discount", "adjustment", "gift_card")
_TERM_OF = {line_class: effect.term for line_class, effect in EFFECTS.items()}
# The order metrics.json lists the classes outside revenue in - every one.
_OUTSIDE_ORDER = ("gift_card_sale", "gift_card_redemption", "cost", "adjustment", "stock_in")
assert set(_OUTSIDE_ORDER) == OUTSIDE_REVENUE, "a class outside revenue that no report lists"
# How many transaction-type values `other_transaction_types` names, and how
# much of each name it keeps: the rest are measured together.
OTHER_TYPES_NAMED = 5
OTHER_TYPE_NAME_CHARS = 40
# Each scope's lines: {"file": every line} and, in metrics.json, the two
# compared months.
Scopes = dict[Scope, pd.Series]


def _money(values: pd.Series) -> float:
    """A sum of finite amounts, a zero written 0.0 (never -0.0)."""
    return float(values[np.isfinite(values)].sum()) + 0.0


def identity_terms(parsed: ParsedTransactions, lines: pd.Series) -> IdentityTerms:
    """The revenue identity over the counted lines among `lines`."""
    mask = parsed.counted & lines
    amounts, terms = parsed.revenue_amounts[mask], parsed.classes[mask].map(_TERM_OF)
    by_term = {term: float(amounts[terms == term].sum()) + 0.0
               for term in ("gross_sales", "returns", "discounts", "other_deductions", "other_revenue")}
    on = mask & parsed.returned & parsed.suggested.isin(_LEAVING)
    return IdentityTerms(
        gross_sales=by_term["gross_sales"], returns=-by_term["returns"] + 0.0,
        discounts=-by_term["discounts"] + 0.0, other_deductions=-by_term["other_deductions"] + 0.0,
        other_revenue=by_term["other_revenue"], net_revenue=float(amounts.sum()) + 0.0,
        returns_on_suggested_keys=-float(parsed.revenue_amounts[on].sum()) + 0.0,
        money_moved=float(amounts.abs().sum()) + 0.0)


def undated_lines(parsed: ParsedTransactions) -> int:
    """The lines with no date, in no month and so in no figure; an
    unmeasurable one is reported once, as unmeasurable (Thach's Q24)."""
    return int((parsed.dates.isna() & ~parsed.classes.eq("unmeasurable")).sum())


def outside_revenue(parsed: ParsedTransactions, scopes: Scopes) -> list[OutsideRevenueLines]:
    """Stock received by the sign of its amount: a receipt and its correction
    netted to one figure that hid both (2E-t2 review 1 #7)."""
    amounts = parsed.revenue_amounts
    finite = np.isfinite(amounts)
    signs = {None: pd.Series(True, index=amounts.index), "positive": finite & (amounts > 0),
             "negative": finite & (amounts < 0), "no_money": ~finite | (amounts == 0)}
    rows = []
    for line_class in _OUTSIDE_ORDER:
        for scope, in_scope in scopes.items():
            for sign, signed in signs.items():
                if (sign is None) == (line_class == "stock_in"):
                    continue
                mask = parsed.classes.eq(line_class) & in_scope & signed
                if mask.any():
                    rows.append(OutsideRevenueLines(
                        line_class=line_class, scope=scope, sign=sign, lines=int(mask.sum()),
                        amount=_money(amounts[mask]), lines_without_amount=int((mask & ~finite).sum())))
    return rows


def unclassified(parsed: ParsedTransactions) -> UnclassifiedLines:
    mask = parsed.classes.eq("unclassified")
    moved = float(parsed.revenue_amounts[parsed.counted].abs().sum())
    amount = _money(parsed.revenue_amounts[mask])
    share = abs(amount) / moved if moved else None
    return UnclassifiedLines(lines=int(mask.sum()), amount=amount, share_of_money_moved=share)


def unmeasurable(parsed: ParsedTransactions, scopes: Scopes) -> list[UnmeasurableLines]:
    """The rules' order says the reason: no quantity, else no price, else an
    amount too large to add."""
    reasons = pd.Series(np.select(
        [~np.isfinite(parsed.quantities), ~np.isfinite(parsed.prices)], ["no quantity", "no price"],
        default="amount too large to add"), index=parsed.classes.index)
    unmeasured = parsed.classes.eq("unmeasurable")
    rows = []
    for scope, in_scope in scopes.items():
        for reason in ("no quantity", "no price", "amount too large to add"):
            lines = int((unmeasured & in_scope & reasons.eq(reason)).sum())
            if lines:
                rows.append(UnmeasurableLines(scope=scope, reason=reason, lines=lines))
    return rows


def notes(df: pd.DataFrame, parsed: ParsedTransactions, scopes: Scopes) -> list[FigureNote]:
    found: list[FigureNote] = []

    def note(code: str, measures: list[NoteMeasure]) -> None:
        found.append(FigureNote(code=code, figures=NOTE_FIGURES[code], text=NOTE_TEXTS[code], measures=measures))

    def measure(name: str, mask: pd.Series, *, orders: bool = False, keys: pd.Series | None = None,
                money: bool = True) -> list[NoteMeasure]:
        return [NoteMeasure(name=name, scope=scope, lines=int((mask & in_scope).sum()),
                            amount=_money(parsed.revenue_amounts[mask & in_scope]) if money else None,
                            orders=int(parsed.order_key[mask & in_scope].nunique()) if orders else None,
                            keys=int(keys[mask & in_scope].nunique()) if keys is not None else None)
                for scope, in_scope in scopes.items()]

    dated = parsed.dates.notna()
    # A product's key as the first-day netting reads it: a line rung by name
    # alone is its one SKU's (2E-f L4) - on the raw line key a same-day return
    # rung by name was no match (review 3 #3), and one candidate key counted
    # as two (#7).
    keys = netting_keys(df, parsed)
    if parsed.returned.any():
        returns, sales = _same_day(parsed, keys, dated)
        # A return no match can check - no named customer, or a pooled code of
        # many items - is counted apart, never read as "not a cancellation"
        # (reviews 2 #2 and 3 #1: with no customer column every measure read 0).
        unchecked = parsed.returned & (parsed.customers.isna() | parsed.classes.eq("pooled_return"))
        note("same_day_cancellations", measure("returns", returns, orders=True) + measure("sales", sales, orders=True)
             + measure("returns_unchecked", unchecked, orders=True))
    stock_in = parsed.classes.eq("stock_in")
    if stock_in.any():
        finite = np.isfinite(parsed.revenue_amounts)
        amounts = parsed.revenue_amounts
        note("returns_booked_as_in",
             measure("positive", stock_in & finite & (amounts > 0))
             + measure("negative", stock_in & finite & (amounts < 0))
             + measure("zero", stock_in & finite & (amounts == 0))
             + measure("unknown", stock_in & ~finite, money=False))
    on = parsed.counted & parsed.suggested.isin(_LEAVING)
    if on.any():
        sale_lines, return_lines = parsed.classes.isin(GROSS) & dated, parsed.classes.isin(RETURNS) & dated
        note("unconfirmed_suggestions",
             [m.model_copy(update={"orders": _orders_only(parsed.order_key, on, sale_lines & scopes[m.scope])})
              for m in measure("lines", on, keys=keys)]
             + [m.model_copy(update={"orders": _orders_only(parsed.order_key, on, return_lines & scopes[m.scope])})
                for m in measure("returns", on & return_lines)])
    deductions = parsed.counted & parsed.classes.isin(("allowance", "pooled_allowance"))
    if deductions.any():
        note("unconfirmed_deductions", measure("lines", deductions))
    note("discounts_in_prices", [])
    other = _other_types(df, parsed)
    if other:
        note("other_transaction_types", [m for name, mask, values in other
                                         for m in measure(name, mask, keys=values)])
    return found


def _same_day(parsed: ParsedTransactions, keys: pd.Series, dated: pd.Series) -> tuple[pd.Series, pd.Series]:
    """The product return lines whose named customer has a sale line of the
    same product key the same day, and those sale lines (E11: products only -
    a pooled code is many items)."""
    frame = pd.DataFrame({"customer": parsed.customers, "key": keys, "day": parsed.dates.dt.normalize()})
    back = parsed.classes.eq("customer_return") & dated & frame["customer"].notna() & frame["key"].notna()
    sold = parsed.classes.eq("sale") & dated & frame["customer"].notna() & frame["key"].notna()
    pairs = ["customer", "key", "day"]
    returns = back & _in(frame, frame[sold][pairs].drop_duplicates(), pairs)
    sales = sold & _in(frame, frame[back][pairs].drop_duplicates(), pairs)
    return returns, sales


def _in(frame: pd.DataFrame, found: pd.DataFrame, columns: list[str]) -> pd.Series:
    hits = frame[columns].merge(found.assign(_hit=True), how="left", on=columns)["_hit"]
    return pd.Series(hits.fillna(False).to_numpy(dtype=bool), index=frame.index)


def _orders_only(order_key: pd.Series, lines: pd.Series, among: pd.Series) -> int:
    """The orders holding a line of `among` and every such line in `lines`."""
    return len(set(order_key[among & lines]) - set(order_key[among & ~lines]))


def _other_types(df: pd.DataFrame, parsed: ParsedTransactions
                 ) -> list[tuple[str, pd.Series, pd.Series | None]]:
    """Counted lines whose mapped transaction type is neither "in" nor "out",
    per value as "in" is read (`identifier_text`, case folded): the
    `OTHER_TYPES_NAMED` values with the most lines, each named by its
    commonest spelling cut to `OTHER_TYPE_NAME_CHARS`, in order of their
    names, then every other value in one measure whose `keys` counts its
    values; [] with no such line. Bounded, because the names are the file's
    own text and reach the AI through the notes, and a free-text column
    mapped as the type held thousands (review 2 #3: 3,000 values cost 25 s
    and 920 KB of notes)."""
    column = parsed.reverse.get("transaction_type")
    if column is None:
        return []
    folded = identifier_text(df[column]).str.lower()
    # A cell with nothing visible is blank, which reads as "out" (2E-i; 2E-t2
    # review 1 #3): it named a measure " ".
    other = parsed.counted & folded.notna() & ~folded.isin(("in", "out", ""))
    if not other.any():
        return []
    spellings = pd.DataFrame({"value": folded[other].to_numpy(), "spelled": df[column][other].astype(str).to_numpy()})
    counts = spellings.groupby(["value", "spelled"]).size().rename("lines").reset_index()
    by_value = counts.groupby("value")["lines"].sum().reset_index().sort_values(["lines", "value"],
                                                                                 ascending=[False, True])
    named = sorted(by_value["value"].head(OTHER_TYPES_NAMED))
    commonest = counts.sort_values(["lines", "spelled"], ascending=[False, True]).drop_duplicates("value")
    spelled = commonest.set_index("value")["spelled"]
    rest = other & ~folded.isin(named)
    # Every name told apart, the rest's own included (review 3 #8: two values
    # alike in their first 37 characters, or one spelled like the rest's).
    taken = {_REST} if rest.any() else set()
    found: list[tuple[str, pd.Series, pd.Series | None]] = []
    for value in named:
        found.append((_unique(str(spelled[value]), taken), other & folded.eq(value), None))
    if rest.any():
        found.append((_REST, rest, folded))
    return found


_REST = "(other values)"


def _unique(name: str, taken: set[str]) -> str:
    """The name cut to `OTHER_TYPE_NAME_CHARS`, numbered until no other
    measure of the note carries it."""
    number, suffix = 1, ""
    while True:
        room = OTHER_TYPE_NAME_CHARS - len(suffix)
        candidate = (name if len(name) <= room else name[:room - 3] + "...") + suffix
        if candidate.casefold() not in {t.casefold() for t in taken}:
            taken.add(candidate)
            return candidate
        number += 1
        suffix = f" ({number})"
