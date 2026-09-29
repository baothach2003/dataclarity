"""Session 4B (ninth run), after review 2: the AI writes no number (CLAUDE.md
3.2 by construction). It cites a figure by its path in the input and code
renders it; its own numbers are bounded tokens; code computes an expected
impact. Written before the code; every rendering is worked out beside it.
"""

import pytest

from stages.predict.strategy_impact import impact
from stages.predict.strategy_render import digits_left, render, resolve

PAYLOAD = {
    "metrics": {
        "period": {"current": "2011-11"},
        "core": {"revenue_current": 663315.58, "revenue_change_pct": 27.18, "orders_current": 1240,
                 "return_rate_current": 0.1524, "revenue_by_month": [{"period": "2011-10", "revenue": 521560.17},
                                                                    {"period": "2011-11", "revenue": 663315.58}]},
        "customers": {"segments": [{"segment": "At-risk", "customers": 339, "avg_monetary": 1976.38,
                                    "revenue_share_pct": 8.39},
                                   {"segment": "No purchases in file", "customers": 31, "avg_monetary": -1197.4,
                                    "revenue_share_pct": -0.4646},
                                   {"segment": "New", "customers": 120, "avg_monetary": 40.0,
                                    "revenue_share_pct": 0.4847}]},
        "products": {"top_products": [{"product": "DOTCOM POSTAGE", "revenue": 18434.67, "units": 512},
                                      {"product": "PACK OF 72 RETROSPOT CAKE CASES", "revenue": 9876.5, "units": 88}]},
    },
    "diagnosis": {
        "signals": [{"series": "revenue", "mode": "yoy", "value_cur": -8.3, "center": 2.5},
                    {"series": "orders", "mode": "level", "value_cur": 1240.0, "center": 1100.0}],
        "localization": {"dimensions": [{"name": "category", "members": [{"name": "Home Decor", "delta": -58000.0,
                                                                           "share_of_change": 0.414}]}]},
        "hypotheses": [{"id": "T2", "share": 1.4455, "contribution": 205000.0}],
    },
    "forecast": {"revenue": [{"period": "2011-12", "point": 401224.73}]},
}
SUGGESTED = {"DOTCOM POSTAGE": "charge"}


def _render(text: str, allowed: tuple[str, ...] = ()) -> tuple[str, list[str]]:
    return render(text, PAYLOAD, SUGGESTED, allowed=set(allowed))


# --- resolving a path -------------------------------------------------------------------------


@pytest.mark.parametrize(("path", "value"), [
    ("metrics.core.revenue_current", 663315.58),
    ("metrics.customers.segments[At-risk].customers", 339),
    ("metrics.customers.segments[0].avg_monetary", 1976.38),
    ("metrics.core.revenue_by_month[2011-10].revenue", 521560.17),
    ("metrics.products.top_products[DOTCOM POSTAGE].revenue", 18434.67),
    ("diagnosis.signals[revenue].value_cur", -8.3),
    ("diagnosis.hypotheses[T2].share", 1.4455),
    ("diagnosis.localization.dimensions[category].members[Home Decor].delta", -58000.0),
    ("forecast.revenue[2011-12].point", 401224.73),
    ("metrics.period.current", "2011-11"),
])
def test_a_path_names_one_figure_by_key_index_or_natural_key(path: str, value: object) -> None:
    assert resolve(PAYLOAD, path).value == value


@pytest.mark.parametrize(("path", "reason"), [
    ("metrics.core.revenue_previous", "no key 'revenue_previous'"),
    ("metrics.customers.segments[Champions].customers", "no item 'Champions'"),
    ("metrics.customers.segments[7].customers", "no item 7"),
    ("metrics.customers.segments", "not a figure"),
    ("report.total", "starts with metrics, diagnosis or forecast"),
])
def test_a_path_that_names_no_figure_is_refused_with_its_reason(path: str, reason: str) -> None:
    with pytest.raises(ValueError, match=reason):
        resolve(PAYLOAD, path)


# --- rendering a figure -----------------------------------------------------------------------


@pytest.mark.parametrize(("text", "rendered"), [
    ("Revenue was £{metrics.core.revenue_current}.", "Revenue was £663,315.58."),
    ("{metrics.customers.segments[At-risk].customers} customers", "339 customers"),
    ("a return rate of {metrics.core.return_rate_current}", "a return rate of 15.2%"),
    ("New holds {metrics.customers.segments[New].revenue_share_pct}", "New holds 0.48%"),
    ("T2 explains {diagnosis.hypotheses[T2].share}", "T2 explains 144.6%"),
    ("revenue {diagnosis.signals[revenue].value_cur} on last year", "revenue -8.3% on last year"),
    ("orders at {diagnosis.signals[orders].value_cur}", "orders at 1,240"),
    ("in {metrics.period.current}", "in 2011-11"),
])
def test_a_figure_is_rendered_by_code_percentages_as_percentages(text: str, rendered: str) -> None:
    # A *_pct field as it is (0.4847 -> 0.48%: two decimals under 1%); a
    # share or rate x 100 (0.1524 -> 15.2%; 1.4455 -> 144.6%); a yoy
    # signal's points (-8.3%); a level signal in its own units; money with
    # its pence; a count whole.
    assert _render(text) == (rendered, [])


def _numeric_fields(tp: object, seen: set[type]) -> set[str]:
    """The names of every number field of the models reachable from `tp`."""
    import typing

    from pydantic import BaseModel

    found: set[str] = set()
    if isinstance(tp, type) and issubclass(tp, BaseModel) and tp not in seen:
        seen.add(tp)
        for name, info in tp.model_fields.items():
            leaves = {a for a in typing.get_args(info.annotation) if a is not type(None)} or {info.annotation}
            if leaves & {float, int} or any(typing.get_origin(a) is typing.Annotated
                                               and typing.get_args(a)[0] in (float, int) for a in leaves):
                found.add(name)
            found |= _numeric_fields(info.annotation, seen)
    for arg in typing.get_args(tp):
        found |= _numeric_fields(arg, seen)
    return found


def test_every_share_or_rate_field_of_the_contracts_is_classed() -> None:
    # 4B review 2 #15: FRACTIONS is a hand-written list of field names; a new
    # share or rate field would be rendered as a plain number. Every number
    # field named so is a fraction - but mix_rate's `rate`, money.
    from contracts.diagnosis import DiagnosisContract
    from contracts.metrics import MetricsContract
    from stages.predict.strategy_render import FRACTIONS

    seen: set[type] = set()
    fields = _numeric_fields(MetricsContract, seen) | _numeric_fields(DiagnosisContract, seen)
    named = {name for name in fields if ("share" in name or "rate" in name) and not name.endswith("_pct")}
    assert named - {"rate"} == FRACTIONS - {"confidence"}


def test_a_direction_word_takes_the_size_and_must_agree_with_the_sign() -> None:
    # 4B review 2 #2: revenue ROSE 27.18%; the fall of Home Decor is -58,000.
    assert _render("Revenue rose {metrics.core.revenue_change_pct} to £{metrics.core.revenue_current}.") == (
        "Revenue rose 27.2% to £663,315.58.", [])
    assert _render("Home Decor fell by £{diagnosis.localization.dimensions[category].members[Home Decor].delta}.") == (
        "Home Decor fell by £58,000.", [])
    _, problems = _render("Revenue fell {metrics.core.revenue_change_pct}.")
    assert problems == ["{metrics.core.revenue_change_pct} is 27.2%: a rise, not a fall"]


def test_a_marked_product_is_rendered_with_its_mark() -> None:
    assert _render("{metrics.products.top_products[0].product} took £{metrics.products.top_products[0].revenue}")[0] \
        == "DOTCOM POSTAGE (suggested: charge, not confirmed) took £18,434.67"


# --- the AI's own numbers: bounded tokens -----------------------------------------------------


def test_offers_assumptions_and_windows_are_bounded_tokens() -> None:
    assert _render("Offer {offer:10%} for {window:30 days}.", ("offer",)) == ("Offer 10% for 30 days.", [])
    assert _render("{assume:20%} of them", ("assume",)) == ("20% (assumed) of them", [])
    assert _render("{offer:150%}", ("offer",))[1] == ["{offer:150%}: a percentage above 0% and at most 100%"]
    assert _render("{window:13 months}")[1] == ["{window:13 months}: a window of at most a year"]
    assert _render("{offer:10%}")[1] == ["{offer:10%}: an offer only in an action or a tempting action"]


def test_a_placeholder_that_is_no_figure_is_named() -> None:
    assert _render("{metrics.core.revenue_previous}")[1] == [
        "{metrics.core.revenue_previous} is not a figure of the input: no key 'revenue_previous'"]


# --- no digit the AI wrote --------------------------------------------------------------------


def test_a_digit_the_ai_wrote_is_refused_but_an_input_text_holding_one_is_not() -> None:
    # 4B review 2 #5, #6, #13: a computed ratio, an invented statistic, a
    # figure copied instead of cited - any digit left is the AI's.
    assert digits_left("Furniture rose 19.7% on {metrics.core.revenue_current}", PAYLOAD) == ["19.7"]
    assert digits_left("lifts spend by 37% across UK retailers", PAYLOAD) == ["37"]
    assert digits_left("Feature PACK OF 72 RETROSPOT CAKE CASES in {metrics.period.current}", PAYLOAD) == []
    assert digits_left("In 2011-11 revenue grew", PAYLOAD) == []  # a period of the input


# --- the expected impact: code computes it ----------------------------------------------------


@pytest.mark.parametrize(("formula", "rendered"), [
    ("{metrics.customers.segments[At-risk].customers} customers x £{metrics.customers.segments[At-risk].avg_monetary}"
     " x {assume:20%} win-back",
     "339 customers x £1,976.38 x 20% (assumed) win-back = 133,999"),
    ("{assume:5%} of £{metrics.core.revenue_current}", "5% (assumed) of £663,315.58 = 33,166"),
    ("£{metrics.core.revenue_current} / {metrics.core.orders_current}", "£663,315.58 / 1,240 = 535"),
    ("£{metrics.core.revenue_current} x {window:3 months}", "£663,315.58 x 3 months = 1,989,947"),
    ("£{metrics.core.revenue_current} - £{metrics.core.revenue_by_month[2011-10].revenue}",
     "£663,315.58 - £521,560.17 = 141,755"),
    ("{metrics.customers.segments[New].customers} x {metrics.customers.segments[New].revenue_share_pct}",
     "120 x 0.48% = 0.58"),
])
def test_the_impact_is_computed_by_code(formula: str, rendered: str) -> None:
    # 339 x 1,976.38 x 0.20 = 133,998.56; 0.05 x 663,315.58 = 33,165.78;
    # 663,315.58 / 1,240 = 534.93 (535); x 3 months = 1,989,946.74; 663,315.58 -
    # 521,560.17 = 141,755.41; 120 x 0.004847 = 0.58. A result from 100 up is
    # rounded to the unit.
    assert impact(formula, PAYLOAD, SUGGESTED) == (rendered, [])


@pytest.mark.parametrize(("formula", "problem"), [
    ("£{metrics.core.revenue_current} / {assume:1%}", "an assumption or a window only multiplies"),
    ("£{metrics.core.revenue_current} + {assume:100%}", "an assumption or a window only multiplies"),
    ("£{metrics.core.revenue_current} x {window:52 weeks}", "a window multiplies in months"),
    ("£{metrics.core.revenue_current} x {window:2 months} x {window:3 months}", "at most one window"),
    ("{assume:10%} x {assume:10%} x {assume:10%} x £{metrics.core.revenue_current}", "at most two assumptions"),
    ("£{metrics.core.revenue_current}", "at least two terms"),
    ("£{metrics.core.revenue_current} x {assume:20%} = £132,663", "write no result"),
    ("£{metrics.core.revenue_current} x x {assume:20%}", "one operator between two terms"),
    ("£{metrics.core.revenue_current} / {diagnosis.signals[orders].value_cur} x 0", "0 is the AI's"),
    ("{metrics.customers.segments[No purchases in file].customers} x {assume:20%}", "never sized"),
    ("{offer:10%} x £{metrics.core.revenue_current}", "an offer only in an action"),
])
def test_an_impact_that_does_not_hold_is_named(formula: str, problem: str) -> None:
    # 4B review 2 #1: dividing by 1%, chained +100%, 52 weeks as x52, two
    # windows stacked all inflated an impact without limit.
    rendered, problems = impact(formula, PAYLOAD, SUGGESTED)
    assert any(problem in p for p in problems), problems
