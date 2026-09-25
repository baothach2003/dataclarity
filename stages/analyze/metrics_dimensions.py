"""Stage 2 Analyze - the `by_dimension` block of metrics.json
(docs/CONTRACTS.md section 6): revenue by country and category, current vs
previous period. Pure pandas; no AI call in this stage
(docs/adr/0002-pandas-computes-ai-interprets.md). Reuses
`stages.analyze.metrics_core`'s row parsing and revenue-scope convention
(2A) instead of redefining them - same stage package.

Design decisions (Thach, Phase 2D):
- `country`: no canonical field carries country information anywhere in the
  schema (contracts/profile.py's CanonicalField has no country, and
  docs/SPECS.md section 9 never defined one) - always reports `[]` rather
  than fabricate an attribution from an unrelated field. Revisit only if a
  country canonical field is added to the schema (a stage-1 change, out of
  scope here).
- `category` is a real canonical field and is computed normally: every
  category value seen on a revenue-counted row in either the current or
  previous period, current/previous revenue summed, no positivity filter
  (unlike products' top_products - a category dropping to $0, or newly
  appearing, is exactly what this block exists to show, not something to
  exclude). A blank category value (missing, or whitespace-only - the same
  "missing" definition metrics_core.is_blank already uses for `customer`)
  is excluded; its revenue is still counted in core.revenue_current, just
  not attributed to a category here.
- A category value is stripped and case-folded before grouping (the same
  pattern metrics_products.py already uses for product identity, after that
  session's own doubt-review found formatting noise silently fragmenting
  one real value into several), so "Home Decor", " Home Decor" and "home
  decor" are one category. The displayed `name` is that category's
  first-seen spelling anywhere in the file.
- `contribution_pct` = this member's own (revenue_current - revenue_previous),
  divided by core's own total change (core.revenue_current -
  core.revenue_previous) - the "total change" docs/CONTRACTS.md section 6
  names, not a locally-recomputed one, and not a share of revenue.
  Reproduces the worked example exactly: Home Decor (210000 - 268000) /
  (1150000 - 1290000) * 100 = 41.43%, rounds to the documented 41.4. Null for
  every member, with `contribution_reason`, when the total change is zero or
  negligible (shared/numbers.is_negligible): a share of nothing is not 0%,
  and a share of float residue read 1e15 in stage 3. This SUPERSEDES 2A's
  "0.0 when the total change is 0" (Thach, 2E).
- `contribution_pct` exists only to compare the two periods, so it is null
  for every member, with the period's reason in `contribution_reason`, when
  the previous month is incomplete (Thach, 2E): a share of a change measured
  against half a month is not a share of anything. The raw per-member
  `revenue_previous` totals stay; stage 5 labels them a partial month.
"""

import pandas as pd

from contracts.cleaning import OrderConfirmations
from contracts.metrics import CoreMetrics, DimensionBreakdown, DimensionChange, Period
from shared.numbers import is_negligible
from shared.transactions import ParsedTransactions, is_blank, parse_transactions


def compute_dimension_metrics(
    df: pd.DataFrame, column_mapping: dict[str, str], period: Period, core: CoreMetrics,
    confirmations: OrderConfirmations | None = None,
) -> DimensionBreakdown:
    """Pure computation. `period` and `core` are metrics_core's own outputs
    for this same run (docs/CONTRACTS.md section 6 has one `period` shared
    by every block; `contribution_pct` is defined against core's own total
    revenue change, so this block cannot be computed independently of it)."""
    parsed = parse_transactions(df, column_mapping, confirmations)
    total_change = core.revenue_current - core.revenue_previous

    months = parsed.dates.dt.to_period("M").astype(str)
    current_mask = parsed.counted & (months == period.current)
    previous_mask = parsed.counted & (months == period.previous)

    category_col = parsed.reverse.get("category")
    if not period.previous_complete:
        reason = period.previous_incomplete_reason
    # Against the money that moved in both months, not the two nets: when
    # both nets are residue the nets make residue look like a scale, and the
    # shares read 1.8e20 (2E doubt-review F5).
    elif is_negligible(total_change, core.revenue_current, core.revenue_previous,
                       float(parsed.revenue_amounts[current_mask | previous_mask].abs().sum())):
        reason = ("the total change is nothing (zero, or floating-point residue), so no "
                  "member has a share of it")
    else:
        reason = None
    category = _dimension_changes(df, category_col, parsed, current_mask, previous_mask,
                                  total_change, reason is None)

    return DimensionBreakdown(country=[], category=category, contribution_reason=reason)


def _dimension_changes(
    df: pd.DataFrame,
    column: str | None,
    parsed: ParsedTransactions,
    current_mask: pd.Series,
    previous_mask: pd.Series,
    total_change: float,
    comparable: bool,
) -> list[DimensionChange]:
    if column is None:
        return []

    raw = df[column]
    identified = ~is_blank(raw)
    normalized = raw.astype(object).str.strip().str.lower()

    table = pd.DataFrame({"key": normalized, "display": raw, "revenue": parsed.revenue_amounts})
    display_names = table.loc[identified].groupby("key")["display"].first()

    current = table[current_mask & identified].groupby("key")["revenue"].sum()
    previous = table[previous_mask & identified].groupby("key")["revenue"].sum()

    changes = []
    for key in set(current.index) | set(previous.index):
        revenue_current = float(current.get(key, 0.0))
        revenue_previous = float(previous.get(key, 0.0))
        contribution_pct = ((revenue_current - revenue_previous) / total_change * 100
                            if comparable else None)
        changes.append(
            DimensionChange(
                name=display_names[key],
                revenue_current=revenue_current,
                revenue_previous=revenue_previous,
                contribution_pct=contribution_pct,
            )
        )
    return sorted(changes, key=lambda change: change.name)
