"""The synthetic store of AI_PIPELINE 7.11: a fixed-seed generator of a sales
file, independent of the engine it validates (session 3E2).

It cannot be fitted to the engine by construction: this package imports only
the standard library, numpy and pandas (a test parses its imports), so no
engine figure can reach it, and every planted cause is a fixed rule written
from the scenario spec (scenarios.py) before the engine ran on it. The seed
was fixed in the method (C:\\Users\\Happy\\3E2-method.txt) before the first run.

One store: ~400 customers (320 from the start, 80 arriving over the months,
a monthly churn), 6 categories x 10 products at fixed prices, orders per day
by retail weekday weights, 1 + Poisson lines per order, a small share of
lines returned a few days later. Each month draws from its own random stream
(seed, month), so a scenario differs from the base only in the month it
plants - the history is identical, line for line.
"""

import calendar
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
import pandas as pd

SEED = 20261001
# Mon..Sun. Retail-shaped (Monday slowest, Saturday busiest) and chosen with
# the compared months so that both Aug -> Sep 2023 and the year-ago pair Aug
# -> Sep 2022 hold the same expected trading (sum of weights): no calendar
# and no year-ago calendar in any scenario but S1 (method, "calendar").
WEEKDAY_WEIGHTS = (0.60, 0.85, 0.90, 1.05, 1.30, 1.50, 0.95)
CATEGORIES = ("Stationery", "Kitchen", "Garden", "Toys", "Lighting", "Furniture")
CATEGORY_SHARES = (0.25, 0.22, 0.18, 0.15, 0.12, 0.08)
CATEGORY_PRICES = (6.0, 9.0, 12.0, 16.0, 20.0, 26.0)
PRODUCTS_PER_CATEGORY = 10
STARTING_CUSTOMERS = 320
ARRIVING_CUSTOMERS = 80
MONTHLY_CHURN = 0.008
ORDERS_PER_CUSTOMER_MONTH = 4.0
RATE_SHAPE = 3.0  # gamma shape of the customers' order rates
EXTRA_LINES_MEAN = 1.2  # lines per order: 1 + Poisson(this)
EXTRA_UNITS_MEAN = 0.3  # units per line: 1 + Poisson(this)
RETURN_SHARE = 0.015
RETURN_DAYS = 10
MAPPING = {"Invoice": "order_id", "Date": "transaction_date", "Product": "product_name",
           "Category": "category", "Qty": "quantity", "Price": "unit_price", "Customer": "customer"}


@dataclass(frozen=True)
class Catalog:
    names: tuple[str, ...]
    categories: tuple[int, ...]
    prices: tuple[float, ...]
    popularity: tuple[float, ...]  # within its category, sums to 1 per category


@dataclass(frozen=True)
class Customers:
    names: tuple[str, ...]
    rates: tuple[float, ...]  # orders per month
    first_day: tuple[date, ...]
    last_day: tuple[date, ...]  # the day after churn, or past the window
    preferences: tuple[tuple[float, ...], ...]  # per category


@dataclass
class MonthPlan:
    """What a scenario changes in one month; the defaults change nothing."""
    price_factor: dict[int, float] = field(default_factory=dict)  # product -> multiplier
    product_weight: dict[int, float] = field(default_factory=dict)  # product -> pick multiplier
    extra_lines_mean: float = EXTRA_LINES_MEAN
    dropped_customers: frozenset[int] = frozenset()  # their orders vanish (lost, not redistributed)
    dropped_products: dict[int, date] = field(default_factory=dict)  # product -> first day it sells nothing
    missing_days: frozenset[date] = frozenset()  # every row of these days is lost


def months_between(first: str, last: str) -> list[str]:
    year, month = int(first[:4]), int(first[5:])
    out = []
    while f"{year:04d}-{month:02d}" <= last:
        out.append(f"{year:04d}-{month:02d}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return out


def build_catalog(seed: int = SEED) -> Catalog:
    rng = np.random.default_rng([seed, 0])
    names, categories, prices, popularity = [], [], [], []
    ranks = np.arange(1, PRODUCTS_PER_CATEGORY + 1)
    weights = (1 / ranks) / (1 / ranks).sum()  # Zipf within the category
    for index, (category, level) in enumerate(zip(CATEGORIES, CATEGORY_PRICES)):
        for rank in range(PRODUCTS_PER_CATEGORY):
            names.append(f"{category}-{rank + 1:02d}")
            categories.append(index)
            prices.append(round(float(level * np.exp(rng.normal(0, 0.3))), 2))
            popularity.append(float(weights[rank]))
    return Catalog(tuple(names), tuple(categories), tuple(prices), tuple(popularity))


def build_customers(first_month: str, last_month: str, seed: int = SEED) -> Customers:
    rng = np.random.default_rng([seed, 1])
    months = months_between(first_month, last_month)
    start = date(int(first_month[:4]), int(first_month[5:]), 1)
    end = _last_day(months[-1])
    total = STARTING_CUSTOMERS + ARRIVING_CUSTOMERS
    first_days = [start] * STARTING_CUSTOMERS
    span = (end - start).days
    first_days += [start + timedelta(days=int(d)) for d in np.sort(rng.integers(28, span, ARRIVING_CUSTOMERS))]
    last_days = []
    for first in first_days:
        lifetime_months = rng.geometric(MONTHLY_CHURN)
        last_days.append(min(first + timedelta(days=int(lifetime_months * 30.44)), end + timedelta(days=1)))
    rates = rng.gamma(RATE_SHAPE, ORDERS_PER_CUSTOMER_MONTH / RATE_SHAPE, total)
    preferences = rng.dirichlet(np.array(CATEGORY_SHARES) * 4, total)
    return Customers(tuple(f"C{index + 1:04d}" for index in range(total)), tuple(float(r) for r in rates),
                     tuple(first_days), tuple(last_days), tuple(tuple(float(p) for p in row) for row in preferences))


def _last_day(month: str) -> date:
    year, number = int(month[:4]), int(month[5:])
    return date(year, number, calendar.monthrange(year, number)[1])


def generate(first_month: str, last_month: str, *, seed: int = SEED,
             plans: dict[str, MonthPlan] | None = None,
             season: Callable[[int], float] = lambda month: 1.0) -> pd.DataFrame:
    """The store's lines from the first day of `first_month` to the last of
    `last_month`, every month complete. `plans` plants a cause in a month;
    `season` multiplies a calendar month's order rate (S9)."""
    plans = plans or {}
    catalog, customers = build_catalog(seed), build_customers(first_month, last_month, seed)
    end = _last_day(last_month)
    rows: list[tuple[str, date, int, int, int, float]] = []  # order id, day, customer, product, qty, price
    for index, month in enumerate(months_between(first_month, last_month)):
        plan = plans.get(month, MonthPlan())
        rng = np.random.default_rng([seed, 100 + index])
        rows += _month_rows(month, rng, catalog, customers, plan, season, end)
    frame = pd.DataFrame(rows, columns=["order", "day", "customer", "product", "qty", "price"])
    # Lost days lose every row on them - a return landing there too (S5).
    missing = frozenset().union(*(plan.missing_days for plan in plans.values()))
    frame = frame[~frame["day"].isin(missing)]
    frame = frame.sort_values(["day", "order"], kind="stable")
    return pd.DataFrame({
        "Invoice": frame["order"].to_numpy(),
        "Date": [d.isoformat() for d in frame["day"]],
        "Product": [catalog.names[p] for p in frame["product"]],
        "Category": [CATEGORIES[catalog.categories[p]] for p in frame["product"]],
        "Qty": [str(q) for q in frame["qty"]],
        "Price": [f"{p:.2f}" for p in frame["price"]],
        "Customer": [customers.names[c] for c in frame["customer"]],
    })


def _month_rows(month: str, rng: np.random.Generator, catalog: Catalog, customers: Customers, plan: MonthPlan,
                season: Callable[[int], float], end: date) -> list[tuple[str, date, int, int, int, float]]:
    year, number = int(month[:4]), int(month[5:])
    weights = np.array(WEEKDAY_WEIGHTS) / np.mean(WEEKDAY_WEIGHTS)
    rates = np.array(customers.rates)
    pick = np.array(catalog.popularity) * np.array([plan.product_weight.get(p, 1.0) for p in range(len(catalog.names))])
    by_category = [np.flatnonzero(np.array(catalog.categories) == c) for c in range(len(CATEGORIES))]
    rows: list[tuple[str, date, int, int, int, float]] = []
    for day_number in range(1, calendar.monthrange(year, number)[1] + 1):
        day = date(year, number, day_number)
        active = np.array([first <= day < last for first, last in zip(customers.first_day, customers.last_day)])
        expected = rates[active].sum() / 30.44 * weights[day.weekday()] * season(number)
        orders = rng.poisson(expected)
        if not orders or not active.any():
            continue
        who = rng.choice(np.flatnonzero(active), size=orders, p=rates[active] / rates[active].sum())
        for order_number, customer in enumerate(who):
            order_id = f"{day:%y%m%d}{order_number:04d}"
            lines = 1 + rng.poisson(plan.extra_lines_mean)
            categories = rng.choice(len(CATEGORIES), size=lines, p=customers.preferences[customer])
            for category in categories:
                members = by_category[category]
                product = int(rng.choice(members, p=pick[members] / pick[members].sum()))
                qty = 1 + int(rng.poisson(EXTRA_UNITS_MEAN))
                price = round(catalog.prices[product] * plan.price_factor.get(product, 1.0), 2)
                # Every draw is made before a plant drops the line, so the
                # stream - and every later line - stays the base's.
                returned = rng.random() < RETURN_SHARE
                back = day + timedelta(days=int(rng.integers(1, RETURN_DAYS + 1)))
                back_qty = int(rng.integers(1, qty + 1))
                if customer in plan.dropped_customers or (
                        product in plan.dropped_products and day >= plan.dropped_products[product]):
                    continue
                rows.append((f"INV{order_id}", day, int(customer), product, qty, price))
                if returned and back <= end:
                    rows.append((f"RET{order_id}", back, int(customer), product, -back_qty, price))
    return rows
