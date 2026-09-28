"""The line classifier (Thach, session 2E-t1; docs/LINE_TAXONOMY.md
sections 2 and 4): every line of the cleaned file gets exactly one class of
the closed list (`contracts.cleaning.CLEANED_LINE_CLASSES`), decided ONCE,
in stage 1, and written into cleaned.csv - stages 2 and 3 read it instead of
re-deriving a line's meaning from its signs in several places. In shared/
since 2E-t2: `parse_transactions` classifies a frame that has no stage 1
columns (one built in memory) by this same function.

Two questions decide a class: what the ITEM is (per key - the user's answer
in Review, else a product; a line with neither SKU nor name is pooled by
rule) and what the LINE does to money (the sign of its amount). v1 is the
money ledger only (Thach, 2026-09-28): no stock ledger, and no type value or
invoice prefix is mapped - a line typed "in" stays outside revenue whatever
its sign, as 2A has always read it (Q25), because the sign cannot tell a
supplier's receipt correction from a customer's return.

The rules, in order, first match wins (section 4.2):
 1. typed "in" -> stock_in
 2-4. no finite quantity, no finite price, or an amount too large to add ->
    unmeasurable
 5. the user's item: charge, discount, cost, adjustment -> that class at any
    sign; gift_card -> gift_card_sale (amount >= 0) or gift_card_redemption
 6-9. a product or pooled item by its signs: an amount of 0 -> no_money, a
    sale, a return, else (a negative price) an allowance - each with a pooled
    twin, so the item survives in the class stages read alone.
The date never decides a class (an undated line is in no month, which is the
stages' business) - except through the name-only vote, which reads the dated
sale lines as `shared/transactions.py` always has (E7).

A suggestion never applies itself (2E-d2; Thach's Q3): a key the class words
suggest is a charge keeps its rule-based class, and the suggestion is written
beside it (`suggested_class`) for the stages to show.
"""

from typing import get_args

import numpy as np
import pandas as pd

from contracts.cleaning import (
    CLASS_SOURCE_COLUMN,
    CLEANED_LINE_CLASSES,
    LINE_CLASS_COLUMN,
    SUGGESTED_CLASS_COLUMN,
    TAXONOMY_COLUMNS,
    OrderConfirmations,
)
from contracts.profile import LineClass
from shared.date_evidence import answered_order
from shared.dates import as_dates
from shared.line_classes import answer_keys, answered_items, keyed, name_only_sku, text_identity
from shared.line_numbers import LineClassColumnsError, line_numbers, require_column
from shared.line_words import non_product_candidates

# The items the user's answer places at any sign (rule 5).
_ITEM_CLASSES = ("charge", "discount", "cost", "adjustment")


def read_classes(df: pd.DataFrame, column_mapping: dict[str, str], answers: OrderConfirmations, *, raw: bool,
                 dated: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Each line's class, its source and its pending suggestion, as
    `parse_transactions` hands them to every reader: stage 1's, as
    cleaned.csv holds them, each checked against its closed list; for a
    frame without them, this module's classifier on the frame given. A raw
    file is always classified - a column of its own named `line_class` is
    the user's, not stage 1's - and without suggestions, which stage 1 finds
    on the cleaned file (E6). `dated`: the lines whose date the caller read."""
    present = [name for name in TAXONOMY_COLUMNS if name in df.columns]
    if raw or not present:
        found = classify_lines(df, column_mapping, answers, suggest=not raw, dated=dated)
        return found["line_class"], found["class_source"], found["suggested_class"]
    if len(present) < len(TAXONOMY_COLUMNS):
        raise LineClassColumnsError(f"it has {present} without {sorted(set(TAXONOMY_COLUMNS) - set(present))}")
    classes = df[LINE_CLASS_COLUMN].astype(object)
    sources = df[CLASS_SOURCE_COLUMN].astype(object)
    suggested = df[SUGGESTED_CLASS_COLUMN].astype(object).where(df[SUGGESTED_CLASS_COLUMN].notna())
    for column, values, allowed, blank_allowed in (
            (LINE_CLASS_COLUMN, classes, CLEANED_LINE_CLASSES, False),
            (CLASS_SOURCE_COLUMN, sources, ("user", "rule"), False),
            (SUGGESTED_CLASS_COLUMN, suggested, get_args(LineClass), True)):
        strange = sorted(set(values.dropna()) - set(allowed))
        if values.isna().any() and not blank_allowed:
            strange.append("(blank)")
        if strange:
            raise LineClassColumnsError(f"`{column}` holds values outside its closed list: {strange[:5]}")
    return classes, sources, suggested


def classify_lines(df: pd.DataFrame, column_mapping: dict[str, str], confirmations: OrderConfirmations, *,
                   suggest: bool = True, dated: pd.Series | None = None) -> pd.DataFrame:
    """`line_class`, `class_source` and `suggested_class` for every line of
    `df` - the cleaned file as stages 2 and 3 read it (text cells). The date
    order is the one stage 1 applied (`confirmations.dates_day_first`, as
    `CleaningReportContract.applied_confirmations` gives it). `suggest`
    False leaves every suggestion missing without searching for candidates:
    stage 1's order checks need the classes of the raw file, never its
    suggestions (2E-t2 review 1 #9: the search cost ~4.7 s a parse on Online
    Retail II). `dated`: the lines with a date, when the caller has read
    them - read again, a day-first date column cost ~20 s on 650,000 lines
    (review 3 #2). Raises RequiredColumnMissingError if quantity or
    unit_price is not mapped."""
    reverse = {field: source for source, field in column_mapping.items()}
    quantities, prices, counts_as_sale = line_numbers(df, reverse, require_column(reverse, "quantity"),
                                                      require_column(reverse, "unit_price"))
    typed_in = ~counts_as_sale
    with np.errstate(over="ignore", invalid="ignore"):
        amounts = quantities * prices
    has_quantity, has_price = np.isfinite(quantities), np.isfinite(prices)
    has_amount = np.isfinite(amounts)
    names = text_identity(df, reverse.get("product_name"))
    skus = text_identity(df, reverse.get("sku"))
    keys = keyed(names, skus)
    # The name-only vote reads the lines that would be sales if nothing were
    # classed, dated, as parse_transactions has always read them (E7). With
    # no name-only line there is no vote, and the dates are not read.
    if dated is None and (skus.isna() & names.notna()).any():
        dated = _dates(df, reverse, confirmations)
    elif dated is None:
        dated = pd.Series(False, index=df.index)
    would_sell = dated & has_quantity & has_price & counts_as_sale & (quantities > 0) & (amounts > 0)
    items = answered_items(df, reverse, confirmations.line_classes, would_sell, names=names, skus=skus)
    pooled = items.eq("pooled") | (items.isna() & keys.isna())
    product_like = items.isna() | items.isin(("product", "pooled"))

    def twin(base: str) -> np.ndarray:
        return np.where(pooled, f"pooled_{base}", base)

    rules = [
        (typed_in, "stock_in"),
        (~has_quantity | ~has_price | ~has_amount, "unmeasurable"),
        *[(items.eq(item), item) for item in _ITEM_CLASSES],
        (items.eq("gift_card") & (amounts >= 0), "gift_card_sale"),
        (items.eq("gift_card"), "gift_card_redemption"),
        (product_like & (amounts == 0), twin("no_money")),
        (product_like & (quantities > 0) & (amounts > 0), twin("sale")),
        (product_like & (quantities < 0) & (amounts < 0), np.where(pooled, "pooled_return", "customer_return")),
        (product_like, twin("allowance")),
    ]
    line_class = np.select([np.asarray(condition, dtype=bool) for condition, _ in rules],
                           [np.broadcast_to(np.asarray(choice, dtype=object), len(df)) for _, choice in rules],
                           default="unclassified")
    # "user" when the item answer decided the class: an answer (a class,
    # "pooled" or "a product", own or inherited) and a class from rules 5-9.
    by_item = ~typed_in & has_quantity & has_price & has_amount
    class_source = np.where(items.notna() & by_item, "user", "rule")
    return pd.DataFrame({
        "line_class": pd.Series(line_class, index=df.index, dtype=object),
        "class_source": pd.Series(class_source, index=df.index, dtype=object),
        "suggested_class": (_suggested(df, column_mapping, keys, names, skus, would_sell).where(items.isna())
                            if suggest else pd.Series(np.nan, index=df.index, dtype=object)),
    }, index=df.index)


def _dates(df: pd.DataFrame, reverse: dict[str, str], confirmations: OrderConfirmations) -> pd.Series:
    column = reverse.get("transaction_date")
    if column is None:
        return pd.Series(False, index=df.index)
    dates = as_dates(df[column], offsets="wall_clock", order=answered_order(confirmations.dates_day_first))
    return dates.notna()


def _suggested(df: pd.DataFrame, column_mapping: dict[str, str], keys: pd.Series, names: pd.Series,
               skus: pd.Series, would_sell: pd.Series) -> pd.Series:
    """Each line's pending suggestion: its key's line-class candidate (the list
    Review asks about, found on this file - E6), else, for a name-only line,
    the candidate of the one SKU its name is sold under; NaN otherwise. The
    caller keeps it only where nobody answered the line's item."""
    candidates = [c for c in non_product_candidates(df, column_mapping) or [] if c.suggested is not None]
    # Every candidate's key read in one pass: one reading per candidate took
    # 25 s over 53,907 of them (2E-t1 review cycle 2 #1).
    keyed_candidates = answer_keys([c.value for c in candidates], [c.field for c in candidates])
    by_key = {key: c.suggested for key, c in zip(keyed_candidates, candidates, strict=True) if key is not None}
    if not by_key:
        return pd.Series(np.nan, index=df.index, dtype=object)
    own = keys.map(by_key).astype(object)
    inherited = ("sku:" + name_only_sku(names, skus, would_sell)).map(by_key).astype(object)
    return own.where(own.notna(), inherited).astype(object)
