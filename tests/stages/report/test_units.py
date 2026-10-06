"""Thach's root-cause fix (2026-10-05, after step 3's review found counts
printed "GBP 609.00"): every figure the report renders carries its unit -
money, count or ratio - from its field's contract, never guessed by the
formatter; the currency code goes on money alone. Over report.json's front
block AND the appendix of the three real runs, with GBP confirmed.

What is excluded, and why: sentences quoted as written from an earlier stage
(class "as-written") and a check's free-form evidence (class "evidence") -
CONTRACTS 11 reads them as text, never by their figures, so no unit is known
for a number inside them; the appendix says so in a line of its own."""

import copy
import re
from html.parser import HTMLParser

import pytest

from contracts.report import ReportContract
from stages.report.html_parts import count, money, ratio
from stages.report.html_parts import currency_code
from stages.report.html_report import render_html
from tests.stages.report.real_runs import RUNS, build_real, files

CODE = "GBP"
_MONEY_FACTORS, _COUNT_FACTORS = ("aov", "price_per_unit"), ("customers", "orders")


class _Text(HTMLParser):
    """The page's text, without what is quoted as written."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.skip: list[str] = []
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        classes = (dict(attrs).get("class") or "").split()
        if self.skip or "as-written" in classes or "evidence" in classes or tag in ("script", "style", "title"):
            self.skip.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if self.skip and self.skip[-1] == tag:
            self.skip.pop()

    def handle_data(self, data: str) -> None:
        if not self.skip:
            self.parts.append(data)


def _report(run: str) -> ReportContract:
    cleaning = copy.deepcopy(files(run)["cleaning_report.json"])
    cleaning["currency"] = {"code": CODE, "source": "user", "evidence": None}
    return build_real(run, cleaning=cleaning)


def _plain(value: float) -> str:
    with currency_code(None):
        return money(abs(value))


def _figures(report: ReportContract) -> tuple[set[str], set[str]]:
    """The report's money figures and its count and ratio figures, as
    printed, each by its field's unit."""
    numbers, causes = report.layer_1_numbers, report.layer_2_causes
    money_values: set[float] = set()
    other: set[str] = set()
    for kpi in numbers.kpis:
        values = [v for v in (kpi.current, kpi.previous) if v is not None]
        if kpi.unit == "money":
            money_values |= set(values) | ({kpi.change} if kpi.change is not None else set())
        else:
            other |= {count(v) if kpi.unit == "count" else ratio(v) for v in values}
    money_values |= {m.revenue for m in numbers.revenue_by_month if m.revenue is not None}
    for point in report.layer_3_actions.forecast.points:
        money_values |= {point.point, point.low, point.high}
    money_values |= {h.contribution for h in causes.hypotheses if h.contribution is not None}
    money_values |= {row.amount for row in numbers.non_product}
    for level in causes.lever_levels:
        for factor in level.factors:
            money_values.add(factor.contribution)
            if factor.name in _MONEY_FACTORS:
                money_values |= {factor.value_prev, factor.value_cur}
            elif factor.name in _COUNT_FACTORS:
                other |= {count(factor.value_prev), count(factor.value_cur)}
    waterfall = report.front.waterfall
    if waterfall is not None:
        money_values |= {waterfall.shown_previous, waterfall.shown_current, waterfall.shown_change}
        money_values |= {bar.shown for bar in waterfall.bars}
        other |= {bar.was for bar in waterfall.bars if bar.factor not in _MONEY_FACTORS}
        other |= {bar.now for bar in waterfall.bars if bar.factor not in _MONEY_FACTORS}
    printed = {_plain(v) for v in money_values if v is not None and _plain(v) != "0.00"}
    return printed, {o for o in other if o not in printed}


def _occurrences(text: str, figure: str) -> list[str]:
    """What stands before each time `figure` is printed as a whole number."""
    return [text[max(0, m.start() - 6):m.start()]
            for m in re.finditer(rf"(?<![\d.,]){re.escape(figure)}(?![\d])(?!\.\d)", text)]


def _texts(report: ReportContract) -> dict[str, str]:
    parser = _Text()
    parser.feed(render_html(report))
    front = " ".join(_strings(report.front.model_dump(exclude={"waterfall": {"bars": {"__all__": {"factor"}}}})))
    return {"front block": front, "page": " ".join(parser.parts)}


def _strings(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for item in value.values() for s in _strings(item)]
    if isinstance(value, list):
        return [s for item in value for s in _strings(item)]
    return []


@pytest.mark.parametrize("run", RUNS)
def test_every_money_figure_carries_the_code_and_nothing_else_does(run: str) -> None:
    report = _report(run)
    money_figures, other_figures = _figures(report)
    for where, text in _texts(report).items():
        uncoded = sorted({f for f in money_figures for before in _occurrences(text, f)
                          if not re.search(rf"{CODE} [+-]?$", before)})
        assert uncoded == [], (run, where, uncoded[:5])
        coded = sorted({f for f in other_figures for before in _occurrences(text, f)
                        if re.search(rf"{CODE} [+-]?$", before)})
        assert coded == [], (run, where, coded[:5])


def test_the_counts_the_review_found_are_never_money() -> None:
    page = _texts(_report("demo_classed"))["page"]

    for text in ("GBP 609", "GBP 756", "GBP 904", "GBP 1,234"):
        assert text not in page


def test_a_figure_of_no_known_unit_never_takes_the_code() -> None:
    # A check's evidence (free-form: CONTRACTS 11) - its numbers print bare under any currency.
    from stages.report.html_parts import evidence_value, number

    with currency_code(CODE):
        assert (number(609.0), number(12.32), evidence_value(1234.5)) == ("609.00", "12.32", "1,234.50")
        assert money(609.0) == "GBP 609.00"
