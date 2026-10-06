"""The checklist's lines and sentence C's phrases, one wording per hypothesis
id (docs/REPORT_REDESIGN.md 1.3 and section 3's glossary; Thach Q16, Q20,
Q33, Q34). One copy for stage 5's checklist and stage 4's claims (design
4.1: a claim's fact is the checklist's own sentence; CLAUDE.md 3.1). Every
figure is a field of metrics.json or diagnosis.json read through CONTRACTS
11's rows - never a hypothesis's evidence keys - formatted; nothing is
computed. The words match the field's unit (Q34): a money field
is worded as money ("Refunds for returned goods fell: X, down from Y"), a
count as a count. A direction word reads which of two fields is larger, or a
field's sign, never a new figure."""

from dataclasses import dataclass

from contracts.diagnosis import Hypothesis, Tree, YearAgo
from contracts.lever_bridge import LeverBridge
from contracts.metrics import MetricsContract
from shared.wording import amount, month_only, prints_as_zero, signed, two

# What each check is about, in plain words - where a line names no figure.
SUBJECTS = {
    "D1": "days without sales", "D2": "a sudden price jump or fall across most products",
    "D3": "rows flagged during cleaning",
    "T1": "The calendar: the month's length and mix of weekdays",
    "T2": "The change a year earlier between the same months",
    "C1": "new customers", "C2": "customers who stopped buying", "C3": "customers who came back after a break",
    "B1": "How often customers ordered", "B2": "Basket size (items per order)",
    "P1": "Prices of products sold in both months", "P2": "A shift to cheaper or pricier products",
    "P3": "Refunds for returned goods", "P4": "Discounts booked as separate lines",
    "P5": "Postage and other charges paid by customers", "R1": "One product or category",
    "R2": "Products sold in only one of the two months", "R3": "A best-seller that may have run out"}
# A file with no order id counts lines (metrics `orders_basis`, the existing
# rule): its subjects never say "order" (the review).
LINES_SUBJECTS = {"B1": "How many lines each customer bought", "B2": "Basket size (items per line)"}
DATA_IDS, CUSTOMER_IDS = ("D1", "D2", "D3"), ("C1", "C2", "C3")


@dataclass(frozen=True)
class Context:
    metrics: MetricsContract
    tree: Tree | None
    bridge: LeverBridge | None
    year_ago: YearAgo | None
    code: str | None

    @property
    def lines_basis(self) -> bool:
        return self.metrics.core.orders_basis == "lines"

    def subject(self, hypothesis_id: str) -> str:
        if self.lines_basis and hypothesis_id in LINES_SUBJECTS:
            return LINES_SUBJECTS[hypothesis_id]
        return SUBJECTS[hypothesis_id]

    def bar(self, factor: str) -> float | None:
        if self.bridge is None:
            return None
        return next((bar.shown for bar in self.bridge.bars if bar.factor == factor), None)

    def price_bar(self) -> tuple[str, float] | None:
        """The chart's bar that holds the price per item: its own bar where the
        split is drawn, the order value's where it is withheld (Q20)."""
        if self.bridge is None:
            return None
        if self.bridge.aov_split:
            shown = self.bar("price_per_unit")
            return None if shown is None else ("average price per item", shown)
        shown = self.bar("aov")
        label = "average line value" if self.lines_basis else "average order value"
        return None if shown is None else (label, shown)

    def more_often(self, hypothesis: Hypothesis) -> bool:
        """B1's direction: orders per customer, the bar's own values (the
        review: the order count can rise while each customer orders less)."""
        bar = None if self.bridge is None else next((b for b in self.bridge.bars if b.factor == "frequency"), None)
        if bar is not None:
            return bar.value_cur > bar.value_prev
        return (hypothesis.contribution or 0.0) > 0


def _worth(hypothesis: Hypothesis, ctx: Context) -> str:
    return "" if hypothesis.contribution is None else f" - worth about {signed(hypothesis.contribution, ctx.code)}"


def _small(hypothesis: Hypothesis, text: str) -> str:
    """A partial verdict is "a small part" (design 1.3), said once at the end."""
    return f"{text[:-1]} (a small part)." if hypothesis.verdict == "partial" else text


def _up(now: float, was: float) -> str:
    return "up" if now > was else "down" if now < was else "the same as"


def _money_moved(subject: str, now: float, was: float, ctx: Context, rose: str = "rose", fell: str = "fell") -> str:
    """A money field this month against last: "Refunds for returned goods
    fell: 13,951.29, down from 41,074.29" (Thach, Q34)."""
    if amount(now, None) == amount(was, None):  # the two as printed: no difference computed
        return f"{subject} stayed at {amount(now, ctx.code)}"
    word = rose if now > was else fell
    return f"{subject} {word}: {amount(now, ctx.code)}, {_up(now, was)} from {amount(was, ctx.code)}"


def money_terms(hypothesis_id: str, ctx: Context) -> tuple[str, float, float] | None:
    """The money fields a customer or returns line compares: the subject, this
    month's amount, last month's."""
    tree = ctx.tree
    if tree is None:
        return None
    customers, returns = tree.customers, tree.returns
    previous = customers.previous_transition if customers is not None else None
    match hypothesis_id:
        case "C1" if customers is not None and previous is not None:
            return "Sales from new customers", customers.new, previous.new
        case "C2" if customers is not None and previous is not None and customers.lapsed <= 0 \
                and previous.lapsed <= 0:
            # Worded as a loss only where both fields are one (the review: a
            # positive lapsed term is no loss; the front then says less).
            return "Sales lost to customers who stopped buying", abs(customers.lapsed), abs(previous.lapsed)
        case "C3" if customers is not None and previous is not None:
            return "Sales from customers who came back after a break", customers.resurrected, previous.resurrected
        case "P3":
            return "Refunds for returned goods", abs(returns.returns_cur), abs(returns.returns_prev)
        case "P4":
            return ("Discounts booked as separate lines", abs(returns.deductions_cur), abs(returns.deductions_prev))
        case "P5":
            return "Postage and other charges paid by customers", returns.charges_cur, returns.charges_prev
    return None


def _inside_price_bar(hypothesis: Hypothesis, ctx: Context, finding: str, measured: str) -> str:
    """P1 and P2 as part of the chart's price bar, never an amount beside it
    (Q20)."""
    contribution = hypothesis.contribution or 0.0
    bar = ctx.price_bar()
    if bar is None:
        return f"{finding[:1].upper()}{finding[1:]}{_worth(hypothesis, ctx)}."
    label, shown = bar
    return (f"Inside the chart's {label} ({signed(shown, ctx.code)}): {finding}. Measured product by product, "
            f"{measured}about {signed(contribution, ctx.code)} - a different measure, not an amount to add to the "
            "chart.")


def moved_line(hypothesis: Hypothesis, ctx: Context) -> str:
    """A line of the first group or "pulled the other way": what moved, with
    its figures."""
    core, code = ctx.metrics.core, ctx.code
    up = (hypothesis.contribution or 0.0) > 0
    month, previous = month_only(ctx.metrics.period.current), month_only(ctx.metrics.period.previous)
    worth = _worth(hypothesis, ctx)
    unit = "lines" if ctx.lines_basis else "orders"
    terms = money_terms(hypothesis.id, ctx)
    match hypothesis.id:
        case "D1":
            text = ("Days with no sales at all - missing data, or days the shop was closed (the file cannot tell "
                    f"which){worth}.")
        case "D2":
            text = ("A sudden price jump or fall across most products: a change in the data's units or currency, or "
                    "a deliberate repricing (the file cannot tell which).")
        case "D3":
            text = "Rows flagged during cleaning are concentrated in this month."
        case "T1":
            text = f"The calendar: {month}'s length and mix of weekdays{worth}."
        case "T2":
            text = _last_year(hypothesis, ctx)
        case "C1" | "C2" | "C3" | "P3" | "P4" | "P5" if terms is not None:
            text = f"{_money_moved(*terms, ctx)}."
        case "B1":
            more = ctx.more_often(hypothesis)
            how = (f"Customers bought {'more' if more else 'fewer'} lines each" if ctx.lines_basis
                   else f"Customers ordered {'more' if more else 'less'} often")
            text = (f"{how}: {core.orders_current:,} {unit}, {_up(core.orders_current, core.orders_previous)} from "
                    f"{core.orders_previous:,}{worth}.")
        case "B2":
            text = _baskets(hypothesis, ctx, up)
        case "P1":
            text = _inside_price_bar(hypothesis, ctx, "prices of products sold in both months went "
                                     f"{'up' if up else 'down'}", "")
        case "P2":
            text = _inside_price_bar(hypothesis, ctx, f"customers chose {'pricier' if up else 'cheaper'} products "
                                     "among those sold in both months", "that shift is ")
        case "R1":
            text = f"The change was concentrated in one product or category{worth}."
        case "R2" if ctx.tree is not None:
            products = ctx.tree.products
            together = ("" if hypothesis.contribution is None else
                        f" - together worth about {signed(hypothesis.contribution, code)}")
            text = (f"Products sold in only one of the two months: sales of products sold in {month} but not in "
                    f"{previous} ({signed(products.new_products, code)}) and the other way round "
                    f"({signed(products.discontinued_products, code)}){together}.")
        case "R3":
            # Stage 3's own words (stockout.py; Thach, Q54).
            text = (f"At least one best-selling product stopped selling - consistent with a stockout, verify on the "
                    f"shelf{worth}.")
        case _:
            subject = ctx.subject(hypothesis.id)
            text = f"{subject[:1].upper()}{subject[1:]}{worth}."
    return _small(hypothesis, text)


def match_phrase(hypothesis: Hypothesis, ctx: Context, *, with_worth: bool = False) -> str:
    """Sentence C's name for a cause, "the figures match {phrase}" (Q33): a
    phrase of its own per id, never a checklist line lowercased."""
    core, code = ctx.metrics.core, ctx.code
    up = (hypothesis.contribution or 0.0) > 0
    month, previous = month_only(ctx.metrics.period.current), month_only(ctx.metrics.period.previous)
    worth = _worth(hypothesis, ctx) if with_worth else ""
    terms = money_terms(hypothesis.id, ctx)
    unit = "lines" if ctx.lines_basis else "orders"
    match hypothesis.id:
        case "B1":
            more = ctx.more_often(hypothesis)
            phrase = (f"customers buying {'more' if more else 'fewer'} lines each" if ctx.lines_basis
                      else f"customers ordering {'more' if more else 'less'} often")
            if with_worth:
                return phrase + worth
            return _customers_ordering(phrase, ctx, unit)
        case "T1":
            return f"the calendar: {month}'s length and mix of weekdays{_worth(hypothesis, ctx)}"
        case "T2" if ctx.year_ago is not None:
            year_ago = ctx.year_ago
            rose = year_ago.revenue_current > year_ago.revenue_previous
            fell = year_ago.revenue_current < year_ago.revenue_previous
            change = core.revenue_change
            also = change is not None and ((rose and change > 0) or (fell and change < 0))
            moved = "rose" if rose else "fell" if fell else "stayed the same"
            return (f"the same months a year earlier: last year sales {'also ' if also else ''}{moved} between "
                    f"{month_only(year_ago.previous)} and {month_only(year_ago.current)} "
                    f"({amount(year_ago.revenue_previous, code)} to {amount(year_ago.revenue_current, code)})"
                    f"{worth}")
        case "C1" | "C2" | "C3" | "P3" | "P4" | "P5" if terms is not None:
            subject, now, was = terms
            return (f"{subject[:1].lower()}{subject[1:]}: {amount(now, code)}, {_up(now, was)} from "
                    f"{amount(was, code)}{worth}")
        case "B2":
            bar = None if ctx.bridge is None else next((b for b in ctx.bridge.bars if b.factor == "units_per_order"),
                                                      None)
            word = "bigger" if up else "smaller"
            if bar is None or with_worth:
                return f"{word} baskets{worth}"
            return (f"{word} baskets: {two(bar.value_cur)} items per {'line' if ctx.lines_basis else 'order'}, "
                    f"{_up(round(bar.value_cur, 2), round(bar.value_prev, 2))} from {two(bar.value_prev)}")
        case "P1" | "P2":
            found = (f"prices of products sold in both months going {'up' if up else 'down'}" if hypothesis.id == "P1"
                     else f"customers choosing {'pricier' if up else 'cheaper'} products among those sold in both "
                          "months")
            # Q20's caveat wherever the amount is printed: not the chart's bar.
            return (f"{found}: measured product by product, about {signed(hypothesis.contribution or 0.0, code)} - "
                    "a different measure from the chart, not an amount to add to it")
        case "R1":
            return f"one product or category: the change was concentrated in it{worth}"
        case "R2" if ctx.tree is not None:
            products = ctx.tree.products
            return (f"products sold in only one of the two months: sales of products sold in {month} but not in "
                    f"{previous} ({signed(products.new_products, code)}) and the other way round "
                    f"({signed(products.discontinued_products, code)}){worth}")
        case "R3":
            return ("at least one best-selling product that stopped selling - consistent with a stockout, verify on "
                    f"the shelf{worth}")
        case "D1":
            return f"days with no sales at all - missing data, or days the shop was closed{worth}"
    subject = ctx.subject(hypothesis.id)
    return f"{subject[:1].lower()}{subject[1:]}{worth}"


def _customers_ordering(phrase: str, ctx: Context, unit: str) -> str:
    core = ctx.metrics.core
    orders = (f"{core.orders_current:,} {unit}, {_up(core.orders_current, core.orders_previous)} from "
              f"{core.orders_previous:,}")
    customers = None if ctx.bridge is None else next((b for b in ctx.bridge.bars if b.factor == "customers"), None)
    placed, bought = ("bought", "bought") if ctx.lines_basis else ("placed", "placed an order")
    if customers is None:
        return f"{phrase}: they {placed} {orders}"
    if customers.value_prev == customers.value_cur:
        who = f"{customers.value_cur:,.0f} customers {bought} in each month"
    else:
        who = (f"{customers.value_prev:,.0f} customers {bought} in {month_only(ctx.metrics.period.previous)} "
               f"and {customers.value_cur:,.0f} in {month_only(ctx.metrics.period.current)}")
    return f"{phrase}: {who}, and together they {placed} {orders}"


def _last_year(hypothesis: Hypothesis, ctx: Context) -> str:
    year_ago = ctx.year_ago
    if year_ago is None:
        return f"{SUBJECTS['T2']}{_worth(hypothesis, ctx)}."  # no year_ago pair (before 18.4): Q46's subject
    rose = year_ago.revenue_current > year_ago.revenue_previous
    fell = year_ago.revenue_current < year_ago.revenue_previous
    moved = "rose" if rose else "fell" if fell else "stayed the same"
    # The fact only (Thach, Q41): "no regular pattern" was a judgement, and
    # contradicted a season read from several years. The year's change is
    # its two amounts - year_ago holds no percentage, and none is computed.
    return (f"Last year alone, sales {moved} between {month_only(year_ago.previous)} and "
            f"{month_only(year_ago.current)}: {amount(year_ago.revenue_previous, ctx.code)} to "
            f"{amount(year_ago.revenue_current, ctx.code)}.")


def _baskets(hypothesis: Hypothesis, ctx: Context, up: bool) -> str:
    worth = _worth(hypothesis, ctx)
    word = "Bigger" if up else "Smaller"
    bar = None if ctx.bridge is None else next((b for b in ctx.bridge.bars if b.factor == "units_per_order"), None)
    if bar is None:
        return f"{word} baskets{worth}."
    per = "line" if ctx.lines_basis else "order"
    moved = _up(round(bar.value_cur, 2), round(bar.value_prev, 2))
    return (f"{word} baskets: {two(bar.value_cur)} items per {per}, {moved}"
            f" from {two(bar.value_prev)}{worth}.")


def not_reason_lines(ruled_out: list[Hypothesis], ctx: Context) -> list[str]:
    """"Checked - not the reason": the subject of each check, in the
    catalog's order, the data checks and the customer checks each one line."""
    ids = {h.id: h for h in ruled_out}
    lines: list[str] = []
    # D1-D3 are the front's one data-checks line (Thach, 2026-10-06).
    for hypothesis in ruled_out:
        if hypothesis.id in DATA_IDS or (hypothesis.id in CUSTOMER_IDS and hypothesis.id != _first_customer(ids)):
            continue
        lines.append(_customers(ids, ctx) if hypothesis.id in CUSTOMER_IDS else _checked(hypothesis, ctx))
    return lines


def _first_customer(ids: dict[str, Hypothesis]) -> str | None:
    return next((i for i in CUSTOMER_IDS if i in ids), None)


def _customers(ids: dict[str, Hypothesis], ctx: Context) -> str:
    customers = ctx.tree.customers if ctx.tree is not None else None
    if (all(i in ids for i in CUSTOMER_IDS) and customers is not None
            and all(prints_as_zero(v) for v in (customers.new, customers.resurrected, customers.lapsed))):
        return ("Customers: no new customers, none stopped buying, none came back after a break - the same "
                f"customers {'bought' if ctx.lines_basis else 'placed orders'} in both months.")
    return f"Customers: {', '.join(SUBJECTS[i] for i in CUSTOMER_IDS if i in ids)}."


def _checked(hypothesis: Hypothesis, ctx: Context) -> str:
    tree, code = ctx.tree, ctx.code
    match hypothesis.id:
        case "P1" if hypothesis.contribution is not None and prints_as_zero(hypothesis.contribution):
            bar = ctx.price_bar()
            if bar is not None and ctx.bridge is not None and ctx.bridge.aov_split:
                return (f"Prices: products sold in both months kept their prices, so the chart's {bar[0]} "
                        f"({signed(bar[1], code)}) moved with what customers bought, not with price changes.")
            return "Prices: products sold in both months kept their prices."
        case "P3" if tree is not None and prints_as_zero(tree.returns.returns_prev) \
                and prints_as_zero(tree.returns.returns_cur):
            return "Refunds for returned goods: none in either month."
        case "P4" if tree is not None and prints_as_zero(tree.returns.deductions_prev) \
                and prints_as_zero(tree.returns.deductions_cur):
            return "Discounts: none booked as separate lines (a discount already taken off a price cannot be seen)."
        case "R1":
            return "One product or category: the change was not concentrated in one."
        case "R3":
            return "Stockouts: no best-selling product stopped selling in a way that suggests it ran out."
    return f"{ctx.subject(hypothesis.id)}."


def cannot_show_line(hypothesis: Hypothesis, ctx: Context) -> str:
    """"This file cannot show it": why, in plain words."""
    if hypothesis.id == "P5" and hypothesis.verdict == "not_testable":
        return "Postage and other charges paid by customers: no line was classed as a charge in Review."
    if hypothesis.id == "B2" and ctx.bridge is not None and ctx.bridge.aov_split_withheld == "refund_lines":
        return f"{ctx.subject('B2')}: returns make it unreliable this month."
    subject = ctx.subject(hypothesis.id)
    subject = subject[:1].upper() + subject[1:]
    if hypothesis.verdict == "not_testable":
        return f"{subject}: this file holds nothing to check it with."
    return f"{subject}: the figures cannot tell."
