"""Step 2: can the data be trusted? (docs/AI_PIPELINE.md section 7.3)

Three checks run before anything is explained, because explaining an artefact
is worse than explaining nothing. Each returns ok / caution / blocked /
inconclusive with the evidence behind it; the gate takes the worst.

Only D1 can block. D2 and D3 describe things that are *consistent with* a data
problem but equally consistent with a real business decision, and the engine
must not claim to tell those apart.
"""

import pandas as pd

from contracts.diagnosis import Trust, TrustCheck
from shared.transactions import product_identity, require_column
from stages.diagnose.inputs import RunData, days_in_month, month_dates
from stages.diagnose.thresholds import (
    D1_BLOCK_SHARE,
    D1_CAUTION_DAYS,
    D1_CAUTION_SHARE,
    D2_CLUSTER_SHARE,
    D2_CLUSTER_WIDTH,
    D2_MIN_PRODUCTS,
    D2_MIN_ROWS,
    D2_NEUTRAL_BAND,
    D2_SMALL_CLUSTER_SHARE,
    D2_SMALL_MIN_PRODUCTS,
    D2_SMALL_RATIO_HIGH,
    D2_SMALL_RATIO_LOW,
    D3_MIN_SHARE,
    D3_RATIO,
)

# Rows stage 1 removed are simply not in cleaned.csv, so nothing here can tell
# which period they belonged to. Stated in the output rather than quietly
# ignored; fixing it needs dropped-row counts per month in
# cleaning_report.json, which is a stage 1 contract change (Backlog).
DROPPED_ROWS_LIMITATION = (
    "rows dropped in stage 1 cannot be assigned to a period, so a gap caused by "
    "dropped rows is invisible here"
)


def evaluate_trust(data: RunData, history: list[str]) -> Trust:
    checks = [
        d1_coverage(data, history),
        d2_price_level(data),
        d3_flagged_rows(data),
    ]
    statuses = {check.status for check in checks}
    if "blocked" in statuses:
        verdict = "blocked"
    elif "caution" in statuses or "inconclusive" in statuses:
        # `inconclusive` downgrades too (Thach, 3B): a check that could not run
        # is not evidence that the data is fine, and reporting "trusted" on a
        # run where two of three checks never executed claims a verification
        # that did not happen. Caution never changes the headline (7.8), so the
        # cost is one honest badge on thin files.
        verdict = "caution"
    else:
        verdict = "trusted"
    return Trust(verdict=verdict, checks=checks, limitations=[DROPPED_ROWS_LIMITATION])


# --- D1: days of data missing -------------------------------------------------


def d1_coverage(data: RunData, history: list[str]) -> TrustCheck:
    """Zero-revenue days beyond what this store's own weekday pattern predicts.

    The expectation is per weekday, not one scalar rate (Thach, session 3B): a
    shop closed on Sundays has a zero-rate near 1.0 on Sundays and near 0 on
    Tuesdays, and months hold four or five of each. A single scalar leaves a
    residue that varies with month shape - bounded well under the caution
    threshold, but nonzero - while per-weekday rates cancel regular closing
    exactly. It also makes a *Tuesday* gap visible in a shop that never trades
    Sundays, which a scalar rate partly absorbs.
    """
    period = data.metrics.period
    # Only months that hold rows can teach what normal looks like. A history
    # month with nothing in it is itself a gap, and letting it set the
    # expectation lets missing data hide missing data: three empty months lift
    # the learned zero-rate enough to absorb a real six-day hole in the current
    # month, and the file with MORE missing data gets the cleaner verdict
    # (3B doubt-review finding 2).
    learned_from = [month for month in history if month in data.months_with_rows]
    empty_history = [month for month in history if month not in data.months_with_rows]
    if not learned_from:
        return TrustCheck(
            id="D1", status="inconclusive",
            evidence={"history_months": len(history), "history_months_with_rows": 0},
            message="No complete month before the current one holds any rows, so there is "
                    "no normal trading pattern to compare coverage against.")

    active = _active_dates(data)
    zero_rates = _zero_rate_by_weekday(active, learned_from)

    evidence: dict[str, object] = {
        "zero_rate_by_weekday": {str(day): round(rate, 4) for day, rate in zero_rates.items()},
        "history_months_with_rows": len(learned_from),
        "empty_history_months": empty_history,
    }
    excess = {}
    for label, month in (("cur", period.current), ("prev", period.previous)):
        observed = _zero_days(active, month)
        expected = _expected_zero_days(zero_rates, month)
        excess[label] = max(0.0, observed - expected)
        evidence[f"zero_days_{label}"] = observed
        evidence[f"expected_zero_days_{label}"] = round(expected, 3)
        evidence[f"excess_zero_days_{label}"] = round(excess[label], 3)

    gap = excess["cur"] * _mean_revenue_per_active_day(data, period.previous)
    evidence["estimated_revenue_gap"] = round(gap, 2)

    days = days_in_month(period.current)
    if excess["cur"] >= D1_BLOCK_SHARE * days:
        observed = evidence["zero_days_cur"]
        return TrustCheck(
            id="D1", status="blocked", evidence=evidence,
            message=f"{observed} of {days} days in the current month have no rows at all, "
                    f"about {excess['cur']:.0f} more than this store's normal closing "
                    "pattern explains. The period is too incomplete to diagnose.")
    if excess["cur"] >= D1_CAUTION_DAYS or excess["cur"] >= D1_CAUTION_SHARE * days:
        return TrustCheck(
            id="D1", status="caution", evidence=evidence,
            message=f"About {excess['cur']:.0f} days in the current month have no rows beyond "
                    f"this store's normal closing pattern, worth roughly {gap:,.0f} in revenue.")
    return TrustCheck(
        id="D1", status="ok", evidence=evidence,
        message="Coverage matches this store's normal trading pattern.")


def _active_dates(data: RunData) -> pd.Series:
    """Revenue per calendar date, over revenue-counted rows only."""
    counted = data.parsed.counted
    return data.parsed.revenue_amounts[counted].groupby(
        data.parsed.dates[counted].dt.normalize()).sum()


def _zero_rate_by_weekday(active: pd.Series, history: list[str]) -> dict[int, float]:
    """Share of history dates of each weekday (0 = Monday) with no revenue."""
    traded = set(active.index)
    rates: dict[int, float] = {}
    counts: dict[int, list[int]] = {day: [0, 0] for day in range(7)}
    for month in history:
        for day in month_dates(month):
            slot = counts[day.weekday()]
            slot[1] += 1
            if day not in traded:
                slot[0] += 1
    for day, (zeros, total) in counts.items():
        rates[day] = zeros / total if total else 0.0
    return rates


def _zero_days(active: pd.Series, month: str) -> int:
    traded = set(active.index)
    return sum(1 for day in month_dates(month) if day not in traded)


def _expected_zero_days(zero_rates: dict[int, float], month: str) -> float:
    return sum(zero_rates[day.weekday()] for day in month_dates(month))


def _mean_revenue_per_active_day(data: RunData, month: str) -> float:
    """Active days only: dividing by calendar days would understate the gap for
    a shop that closes regularly."""
    active = _active_dates(data)
    in_month = active[active.index.to_period("M").astype(str) == month]
    return float(in_month.mean()) if len(in_month) else 0.0


# --- D2: uniform price-level shift --------------------------------------------


def d2_price_level(data: RunData) -> TrustCheck:
    """A whole catalogue repricing by the same factor is the signature of a
    unit or currency change in the data - or of a deliberate repricing. This
    check never blocks, because nothing in point-of-sale rows can tell those
    two apart."""
    ratios = _price_ratios(data)
    count = len(ratios)
    evidence: dict[str, object] = {"comparable_products": count}

    if count >= D2_MIN_PRODUCTS:
        median = float(ratios.median())
        within = float((ratios.sub(median).abs() <= D2_CLUSTER_WIDTH * median).mean())
        evidence |= {"median_ratio": round(median, 4), "share_in_cluster": round(within, 4),
                     "rule": "cluster"}
        low, high = D2_NEUTRAL_BAND
        if within >= D2_CLUSTER_SHARE and not (low <= median <= high):
            return TrustCheck(
                id="D2", status="caution", evidence=evidence,
                message=f"Prices moved by about the same factor ({median:.2f}x) across "
                        f"{within:.0%} of comparable products. Verify whether this is a unit "
                        "or currency change in the data, or a deliberate repricing.")
        return TrustCheck(id="D2", status="ok", evidence=evidence,
                          message="No uniform price-level shift across products.")

    if count >= D2_SMALL_MIN_PRODUCTS:
        # Small catalogue: only an order-of-magnitude move is evidence, since a
        # tight cluster among a handful of products happens by chance.
        extreme = float(((ratios >= D2_SMALL_RATIO_HIGH) | (ratios <= D2_SMALL_RATIO_LOW)).mean())
        median = float(ratios.median())
        evidence |= {"median_ratio": round(median, 4), "share_extreme": round(extreme, 4),
                     "rule": "small_catalog_order_of_magnitude"}
        if extreme >= D2_SMALL_CLUSTER_SHARE:
            return TrustCheck(
                id="D2", status="caution", evidence=evidence,
                message=f"Prices changed by an order of magnitude (about {median:.2f}x) across "
                        f"{extreme:.0%} of the {count} comparable products. That is the "
                        "signature of a unit or currency error rather than repricing; verify "
                        "the price column.")
        return TrustCheck(
            id="D2", status="ok", evidence=evidence,
            message=f"No order-of-magnitude price shift across the {count} comparable products.")

    return TrustCheck(
        id="D2", status="inconclusive", evidence=evidence,
        message=f"Only {count} products sold in both periods with enough rows to compare "
                "prices; too few to tell a uniform shift from coincidence.")


def _price_ratios(data: RunData) -> pd.Series:
    """Median unit price this period over median unit price last period, per
    product sold in both with at least D2_MIN_ROWS counted rows in each."""
    reverse = data.parsed.reverse
    name_col = require_column(reverse, "product_name")
    identity = product_identity(data.df, name_col, reverse.get("sku"))
    period = data.metrics.period

    frame = pd.DataFrame({
        "identity": identity,
        "month": data.months,
        "price": data.parsed.prices,
    })[data.parsed.counted]

    medians = {}
    for label, month in (("cur", period.current), ("prev", period.previous)):
        rows = frame[frame["month"] == month]
        grouped = rows.groupby("identity")["price"]
        medians[label] = grouped.median()[grouped.size() >= D2_MIN_ROWS]

    shared = medians["cur"].index.intersection(medians["prev"].index)
    previous = medians["prev"].reindex(shared)
    current = medians["cur"].reindex(shared)
    # A zero or negative previous price cannot produce a meaningful ratio.
    usable = previous > 0
    return (current[usable] / previous[usable]).dropna()


# --- D3: flagged rows concentrated in the current period ----------------------


def d3_flagged_rows(data: RunData) -> TrustCheck:
    """Stage 1 marks cells it could not trust with `__flag_*` columns. A jump
    in their share between the periods means the current month's rows are of a
    different quality from the ones it is compared with."""
    flag_columns = [column for column in data.df.columns if str(column).startswith("__flag_")]
    if not flag_columns:
        return TrustCheck(id="D3", status="ok", evidence={"flag_columns": 0},
                          message="Stage 1 flagged no rows in this file.")

    flagged = _any_flag_set(data.df[flag_columns])
    period = data.metrics.period
    shares = {}
    for label, month in (("cur", period.current), ("prev", period.previous)):
        in_month = data.parsed.counted & (data.months == month)
        rows = int(in_month.sum())
        shares[label] = float(flagged[in_month].mean()) if rows else 0.0

    evidence = {"flag_columns": len(flag_columns),
                "flagged_share_cur": round(shares["cur"], 4),
                "flagged_share_prev": round(shares["prev"], 4)}
    if shares["cur"] >= D3_RATIO * shares["prev"] and shares["cur"] >= D3_MIN_SHARE:
        return TrustCheck(
            id="D3", status="caution", evidence=evidence,
            message=f"{shares['cur']:.1%} of this month's rows carry a data-quality flag, "
                    f"against {shares['prev']:.1%} last month.")
    return TrustCheck(id="D3", status="ok", evidence=evidence,
                      message="Flagged rows are not concentrated in the current period.")


def _any_flag_set(flags: pd.DataFrame) -> pd.Series:
    """cleaned.csv is read as text, so a flag arrives as "True"/"False"."""
    truthy = flags.apply(lambda column: column.astype(object).str.strip().str.lower().isin(
        ("true", "1")))
    return truthy.any(axis=1)
