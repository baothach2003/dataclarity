"""What a date column says about itself (session 2E-j): the order its
day-month-year cells are written in, and whether the file records months
rather than days. Split from dates.py (the reading), which it builds on.

"05/01/2026" is 5 January or 1 May, and nothing in the cell says which. A
first number 13-31 with a second 1-12 can only be a day, so it PROVES day
first; the reverse proves month first. A cell whose two numbers are equal
("05/05/2026") reads the same either way and proves nothing, and needs
nothing. Stage 1 decides on this evidence and the user's answer
(stages/ingest/date_order.py); stages 2 and 3 read what stage 1 recorded.
"""

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from contracts.profile import DateOrder
from shared.date_text import day_month_year


@dataclass(frozen=True)
class OrderEvidence:
    """What a column's cells say about their order."""

    shaped: int  # cells written day-month-year or month-day-year
    day_first: int  # cells only day first can read
    month_first: int  # cells only month first can read
    # Cells either order reads, each as a different date ("05/01/2026").
    ambiguous: int
    # The date text of the first cell proving each order (never the whole
    # cell: a notes column starting with a date must not carry the rest).
    day_first_example: str | None
    month_first_example: str | None
    ambiguous_example: str | None
    # A suggestion, never applied by itself (2E-d2): every such cell holds the
    # date alone, its first number 1 while the second varies - the 1st of
    # each month written day first, which can never prove itself - or the
    # reverse.
    hint: DateOrder | None

    @property
    def decision(self) -> DateOrder | Literal["ask"] | None:
        """The order the cells prove; "ask" when both prove it, or neither
        does and some cell reads differently each way; None when nothing
        depends on the order."""
        if self.day_first and not self.month_first:
            return "day_first"
        if self.month_first and not self.day_first:
            return "month_first"
        if (self.day_first and self.month_first) or self.ambiguous:
            return "ask"
        return None


def _holds_a_date(texts: np.ndarray) -> np.ndarray:
    return np.fromiter((isinstance(text, str) and day_month_year(text) is not None
                        for text in texts), dtype=bool, count=len(texts))


def shaped_cells(values: pd.Series) -> pd.Series:
    """Which cells hold a day-month-year or month-day-year date (read per
    distinct value)."""
    codes, uniques = pd.factorize(values.astype("str"))
    found = _holds_a_date(np.asarray(uniques, dtype=object))
    return pd.Series((codes >= 0) & found[codes], index=values.index)


def order_evidence(values: pd.Series) -> OrderEvidence:
    return order_evidence_of_counts(values.dropna().astype("str").value_counts())


def order_evidence_of_counts(counts: pd.Series) -> OrderEvidence:
    """`counts`: each distinct cell text and how many cells hold it (the
    profile has it already). Read per distinct value, and only the values
    that hold such a date are taken apart: a million rows of a few thousand
    dates cost a few thousand matches."""
    texts = np.asarray(counts.index.astype(str), dtype=object)
    found = _holds_a_date(texts)
    weights = counts.to_numpy()[found]
    # Every `found` text holds a match (the same test), so none is None.
    pairs = [(text, date) for text in texts[found] if (date := day_month_year(text)) is not None]
    first = np.array([date.first for _, date in pairs], dtype=int)
    second = np.array([date.second for _, date in pairs], dtype=int)
    dates = [date.text for _, date in pairs]
    date_only = all(text.strip() == date.text for text, date in pairs)
    proves_day = (first >= 13) & (first <= 31) & (second >= 1) & (second <= 12)
    proves_month = (second >= 13) & (second <= 31) & (first >= 1) & (first <= 12)
    ambiguous = (first >= 1) & (first <= 12) & (second >= 1) & (second <= 12) & (first != second)

    def example(proof: np.ndarray) -> str | None:
        return dates[int(np.argmax(proof))] if proof.any() else None

    # Only on date-only cells: 1-12 January with times of day read "the 1st
    # of each month" too (a short US export; 2E-j review cycle 2 #3). And
    # only where the order is asked: beside a proof it contradicted it
    # (review cycle 3 #9).
    hint: DateOrder | None = None
    if found.any() and date_only and not (proves_day.any() ^ proves_month.any()):
        if (first == 1).all() and len(set(second)) > 1:
            hint = "day_first"
        elif (second == 1).all() and len(set(first)) > 1:
            hint = "month_first"
    return OrderEvidence(
        shaped=int(weights.sum()), day_first=int(weights[proves_day].sum()),
        month_first=int(weights[proves_month].sum()), ambiguous=int(weights[ambiguous].sum()),
        day_first_example=example(proves_day), month_first_example=example(proves_month),
        ambiguous_example=example(ambiguous), hint=hint)


def answered_order(day_first: bool | None) -> DateOrder | None:
    """The order an answer to Review's date question names (None: none)."""
    return None if day_first is None else "day_first" if day_first else "month_first"


def applied_order(evidence: OrderEvidence, day_first: bool | None) -> DateOrder | None:
    """The order a column is read in: the user's answer, else what its cells
    prove; None when neither decides (nothing depends on it, or both or
    neither prove it and nobody answered - stage 1 refuses to run such a
    plan)."""
    if day_first is not None:
        return answered_order(day_first)
    decision = evidence.decision
    return None if decision == "ask" else decision


def month_grain(dates: pd.Series) -> bool:
    """Every dated line at midnight on the 1st - or every one at midnight on
    the last day of its month (Thach, 2E-o Q10: an accounting period end) -
    over at least two months: the file records months, not days (Thach, Q1
    of 2E-h). The caller passes the COUNTED lines' dates, as his words say.
    "Mar 2024" is read as the 1st, so such a file has no day to measure -
    and one month alone cannot be told from a shop that sold on one day. One
    end or the other throughout: a mix is no grain."""
    dated = dates.dropna()
    if dated.empty:
        return False
    midnight = dated.eq(dated.dt.normalize())
    one_end = (bool((midnight & dated.dt.day.eq(1)).all())
               or bool((midnight & dated.dt.is_month_end).all()))
    return one_end and dated.dt.to_period("M").nunique() >= 2
