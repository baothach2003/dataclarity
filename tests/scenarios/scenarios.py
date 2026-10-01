"""S0-S11 (AI_PIPELINE 7.11): each plants exactly one cause, by a fixed rule
written from the spec before the engine ran on it (session 3E2's method).

`expected` is what the engine must say: a headline rule, with the cause it
names where the rule names one, or - for S10, whose finding is a trust
caution and never a headline - a verdict. `implied` lists the hypotheses
the planted cause makes true by their documented definitions (AI_PIPELINE
7.8): a supported hypothesis outside it is a decoy. Both were fixed from
the definitions, never from engine output.

Compared months: Aug -> Sep 2023 (calendar-neutral, with its year-ago pair:
store.WEEKDAY_WEIGHTS), planted in September, over 26 complete months
(2021-08 .. 2023-09) - except S1, whose own window ends in Sep 2024 (the
calendar's -7.09%, its year-ago pair neutral), and S11, S0 cut to its last
six complete months.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
import pandas as pd

from tests.scenarios.store import (CATEGORIES, SEED, MonthPlan, build_catalog, build_customers, generate)

FIRST, LAST, CURRENT = "2021-08", "2023-09", "2023-09"
# Mean lines per order 1 + 1.2 = 2.2; x1.4 is 3.08 (S6's AOV +40%, 3D6b).
S6_EXTRA_LINES = 2.08
# S9: a season that repeats every year - September 25% below August.
SEASON = {1: 0.90, 2: 0.90, 3: 0.95, 4: 1.00, 5: 1.00, 6: 1.05, 7: 1.10, 8: 1.20, 9: 0.90, 10: 0.95,
          11: 1.05, 12: 1.25}


@dataclass(frozen=True)
class Expected:
    rule: int | None = None  # the headline rule
    names: str | None = None  # the cause it names: a hypothesis id (rule 6) or T1/T2 (rule 5)
    supported: str | None = None  # instead of a headline: this hypothesis supported (S10)


@dataclass(frozen=True)
class Scenario:
    id: str
    cause: str
    expected: Expected
    implied: frozenset[str]
    build: Callable[[int], pd.DataFrame] = field(repr=False)


def _sep(day: int) -> date:
    return date(2023, 9, day)


def _active_on(first_day: date, seed: int) -> list[int]:
    customers = build_customers(FIRST, LAST, seed)
    return [index for index, (first, last) in enumerate(zip(customers.first_day, customers.last_day))
            if first <= first_day < last]


def _some(population: list[int], share: float, seed: int, stream: int) -> frozenset[int]:
    rng = np.random.default_rng([seed, stream])
    return frozenset(int(i) for i in rng.choice(population, size=round(share * len(population)), replace=False))


def s0(seed: int) -> pd.DataFrame:
    return generate(FIRST, LAST, seed=seed)


def s1(seed: int) -> pd.DataFrame:
    # Nothing planted: Aug -> Sep 2024 holds one Thursday, Friday and
    # Saturday fewer and one Sunday and Monday more - the calendar alone.
    return generate("2022-08", "2024-09", seed=seed)


def s2(seed: int) -> pd.DataFrame:
    # Like-for-like: every product cut by its own 10-30% (mean 20%) - not
    # one uniform factor, which D2 reads as a possible unit error by design.
    rng = np.random.default_rng([seed, 2])
    cuts = {p: float(1 - rng.uniform(0.10, 0.30)) for p in range(len(build_catalog(seed).names))}
    return generate(FIRST, LAST, seed=seed, plans={CURRENT: MonthPlan(price_factor=cuts)})


def s3(seed: int) -> pd.DataFrame:
    # Mix: in every category the five cheapest products picked 3x as often,
    # the five dearest a third as often - the same units, cheaper lines.
    catalog = build_catalog(seed)
    weight: dict[int, float] = {}
    for category in range(len(CATEGORIES)):
        members = sorted((p for p, c in enumerate(catalog.categories) if c == category), key=lambda p: catalog.prices[p])
        weight |= {p: 3.0 for p in members[:5]} | {p: 1 / 3 for p in members[5:]}
    return generate(FIRST, LAST, seed=seed, plans={CURRENT: MonthPlan(product_weight=weight)})


def s4(seed: int) -> pd.DataFrame:
    # 30% of the customers active on 1 September buy nothing in it.
    gone = _some(_active_on(_sep(1), seed), 0.30, seed, 4)
    return generate(FIRST, LAST, seed=seed, plans={CURRENT: MonthPlan(dropped_customers=gone)})


def s5(seed: int) -> pd.DataFrame:
    # A whole week lost (11-17 September): every weekday once, so the gap
    # carries no calendar of its own.
    days = frozenset(_sep(11) + timedelta(days=d) for d in range(7))
    return generate(FIRST, LAST, seed=seed, plans={CURRENT: MonthPlan(missing_days=days)})


def s6(seed: int) -> pd.DataFrame:
    # 3D6b's masked shape: customers -40%, AOV +40% (lines per order x1.4).
    gone = _some(_active_on(_sep(1), seed), 0.40, seed, 6)
    return generate(FIRST, LAST, seed=seed,
                    plans={CURRENT: MonthPlan(dropped_customers=gone, extra_lines_mean=S6_EXTRA_LINES)})


def _august_revenue(seed: int) -> pd.Series:
    base = s0(seed)
    august = base[base["Date"].str.startswith("2023-08")]
    return (august["Qty"].astype(float) * august["Price"].astype(float)).groupby(august["Product"]).sum()


def s7(seed: int) -> pd.DataFrame:
    # August's best-selling product sells on 1-2 September, then nothing
    # for the rest of the month: a stockout, its sales lost (no substitute).
    names = build_catalog(seed).names
    top = names.index(str(_august_revenue(seed).idxmax()))
    return generate(FIRST, LAST, seed=seed, plans={CURRENT: MonthPlan(dropped_products={top: _sep(3)})})


def s8(seed: int) -> pd.DataFrame:
    # Each category's second most popular product discontinued from 1 September.
    catalog = build_catalog(seed)
    second = {p for p, name in enumerate(catalog.names) if name.endswith("-02")}
    return generate(FIRST, LAST, seed=seed, plans={CURRENT: MonthPlan(dropped_products=dict.fromkeys(second, _sep(1)))})


def s9(seed: int) -> pd.DataFrame:
    return generate(FIRST, LAST, seed=seed, season=lambda month: SEASON[month])


def s10(seed: int) -> pd.DataFrame:
    # Every September price entered x100 (cents read as units).
    factor = dict.fromkeys(range(len(build_catalog(seed).names)), 100.0)
    return generate(FIRST, LAST, seed=seed, plans={CURRENT: MonthPlan(price_factor=factor)})


def s11(seed: int) -> pd.DataFrame:
    base = s0(seed)
    return base[base["Date"] >= "2023-04-01"].reset_index(drop=True)


# Fewer orders from every customer (the calendar, a lost week, the season)
# reads, by definition, as customers buying less often (B1) and more of
# them skipping the month (C2) or not coming back (C3).
_FEWER_ORDERS = frozenset({"B1", "C2", "C3"})

SCENARIOS: tuple[Scenario, ...] = (
    Scenario("S0", "nothing", Expected(rule=7), frozenset(), s0),
    Scenario("S1", "calendar", Expected(rule=5, names="T1"), _FEWER_ORDERS | {"T1"}, s1),
    Scenario("S2", "like-for-like price cut", Expected(rule=6, names="P1"), frozenset({"P1"}), s2),
    Scenario("S3", "mix shift", Expected(rule=6, names="P2"), frozenset({"P2"}), s3),
    Scenario("S4", "lapsed customers", Expected(rule=6, names="C2"), frozenset({"C2"}), s4),
    Scenario("S5", "missing days", Expected(rule=2), _FEWER_ORDERS | {"D1"}, s5),
    Scenario("S6", "masked shift", Expected(rule=4), frozenset({"C2", "B2"}), s6),
    Scenario("S7", "stockout", Expected(rule=6, names="R3"), frozenset({"R3", "R1", "P2", "B2"}), s7),
    Scenario("S8", "discontinued products", Expected(rule=6, names="R2"), frozenset({"R2", "B2"}), s8),
    Scenario("S9", "seasonality", Expected(rule=5, names="T2"), _FEWER_ORDERS | {"T2"}, s9),
    Scenario("S10", "x100 price error", Expected(supported="D2"), frozenset({"D2", "P1"}), s10),
    Scenario("S11", "nothing, 6 months", Expected(rule=7), frozenset(), s11),
)
