"""Session 4B (ninth run), after review 2: the checks on the strategy step's
answer and its rendering. The AI cites figures by path and proposes bounded
tokens; any digit it wrote itself is refused; the words are checked in
context (a verdict only about a period; the tempting action names what not
to do). Every answer here is hand-written; written before the code.
"""

import pytest

from contracts.forecast import DoNotDo, Recommendation
from stages.predict.strategy_checks import check_answer, review
from tests.stages.predict.test_4b_render import PAYLOAD

SUGGESTED = {"DOTCOM POSTAGE": "charge", "Discount": "discount"}
AT_RISK = "metrics.customers.segments[At-risk]"
REC = {"insight": "Revenue rose {metrics.core.revenue_change_pct} to £{metrics.core.revenue_current} in "
                  "{metrics.period.current}.",
       "cause": "The At-risk segment holds {" + AT_RISK + ".customers} customers.",
       "action": "Email the At-risk customers a {offer:10%} offer within {window:30 days}.",
       "expected_impact": "{" + AT_RISK + ".customers} customers x £{" + AT_RISK + ".avg_monetary} x {assume:20%} "
                          "win-back",
       "how_to_measure": "Revenue from the At-risk customers over {window:30 days}.",
       "confidence": 0.6}
AVOID = DoNotDo(tempting_action="A {offer:20%} discount to every customer",
                why_wrong_here="Only {" + AT_RISK + ".customers} customers are at risk.")


def _recs(count: int = 3, **changes: str) -> list[Recommendation]:
    """`count` recommendations, priorities 1..count, the first changed."""
    return [Recommendation(priority=i, **(REC | (changes if i == 1 else {}))) for i in range(1, count + 1)]


def _check(recommendations: list[Recommendation], do_not_do: list[DoNotDo] | None = None,
           basis: str = "order_id") -> None:
    check_answer(recommendations, [AVOID] if do_not_do is None else do_not_do, PAYLOAD, SUGGESTED, basis)


def _problems(recommendations: list[Recommendation], do_not_do: list[DoNotDo] | None = None,
              basis: str = "order_id") -> str:
    with pytest.raises(ValueError) as caught:
        _check(recommendations, do_not_do, basis)
    return str(caught.value)


# --- a sound answer, rendered by code ---------------------------------------------------------


def test_a_sound_answer_passes_and_every_number_in_it_is_the_codes() -> None:
    _check(_recs())
    reviewed = review(_recs(), [AVOID], PAYLOAD, SUGGESTED, "order_id")
    first = reviewed.recommendations[0]
    assert first["insight"] == "Revenue rose 27.2% to £663,315.58 in 2011-11."
    assert first["action"] == "Email the At-risk customers a 10% offer within 30 days."
    # 339 x 1,976.38 x 20% = 133,998.56: computed, never written by the AI.
    assert first["expected_impact"] == "339 customers x £1,976.38 x 20% (assumed) win-back = 133,999"
    assert reviewed.do_not_do[0] == {"tempting_action": "A 20% discount to every customer",
                                     "why_wrong_here": "Only 339 customers are at risk."}


# --- the answer's shape -----------------------------------------------------------------------


@pytest.mark.parametrize("count", [2, 6])
def test_three_to_five_recommendations(count: int) -> None:
    assert f"give 3 to 5 recommendations, not {count}" in _problems(_recs(count))


def test_the_recommendations_are_ranked_in_order() -> None:
    recs = _recs()
    recs[1], recs[2] = recs[2], recs[1]
    assert "rank the recommendations by priority 1, 2, 3... in order" in _problems(recs)


def test_at_least_one_thing_not_to_do_and_no_empty_field() -> None:
    assert "give at least one do_not_do" in _problems(_recs(), [])
    assert "recommendation 1 action is empty" in _problems(_recs(action="  "))


# --- no number the AI wrote -------------------------------------------------------------------


@pytest.mark.parametrize(("field", "text", "digits"), [
    ("insight", "Revenue was £50,000 in {metrics.period.current}.", "50,000"),
    ("cause", "Furniture rose 19.7% on {metrics.core.revenue_current}.", "19.7"),
    ("action", "Early access lifts spend by 37% across UK retailers: offer it within {window:30 days}.", "37"),
    ("how_to_measure", "The usual response of 14.5% over {window:30 days}.", "14.5"),
])
def test_a_number_the_ai_wrote_is_refused(field: str, text: str, digits: str) -> None:
    # 4B review 2 #5, #6, #13: computed ratios, invented statistics, a
    # figure copied instead of cited - any digit the AI wrote.
    assert f"recommendation 1 {field}: {digits} is a number you wrote" in _problems(_recs(**{field: text}))


def test_a_do_not_do_states_no_number_of_its_own() -> None:
    avoid = DoNotDo(tempting_action="Spend £250,000 on ads", why_wrong_here="Only 999 would see them.")
    problems = _problems(_recs(), [avoid])
    assert "do_not_do 1 tempting_action: 250,000 is a number you wrote" in problems
    assert "do_not_do 1 why_wrong_here: 999 is a number you wrote" in problems


def test_a_recommendation_cites_a_figure_by_its_path() -> None:
    assert "recommendation 1 cites no figure in its insight or cause" in _problems(
        _recs(insight="Revenue rose.", cause="Customers came back."))
    # A product's name or a period is text, not a figure.
    assert "recommendation 1 cites no figure in its insight or cause" in _problems(
        _recs(insight="{metrics.products.top_products[1].product} sold well in {metrics.period.current}.",
              cause="Customers came back."))
    assert "{metrics.core.revenue_previous} is not a figure of the input" in _problems(
        _recs(insight="Revenue was {metrics.core.revenue_previous}."))


def test_a_direction_word_must_agree_with_the_figures_sign() -> None:
    # 4B review 2 #2: on the sample revenue ROSE 27.2%.
    assert "is 27.2%: a rise, not a fall" in _problems(_recs(insight="Revenue fell {metrics.core.revenue_change_pct}."))


def test_tokens_stay_in_their_place_and_bounds() -> None:
    assert "an offer only in an action or a tempting action" in _problems(
        _recs(insight="A {offer:10%} offer on {metrics.core.revenue_current}."))
    assert "a percentage above 0% and at most 100%" in _problems(
        _recs(action="Offer {offer:150%} within {window:30 days}."))


def test_how_to_measure_names_a_window_token() -> None:
    # SPECS 7.6; the window is a token, so "the next month" in words is sent
    # back with the token to use.
    assert "how_to_measure names no review window - use {window:30 days}" in _problems(
        _recs(how_to_measure="Revenue from the At-risk customers over the next month."))


def test_the_impact_is_the_codes() -> None:
    assert "write no result - the code computes it" in _problems(
        _recs(expected_impact=REC["expected_impact"] + " = £133,999"))
    assert "an assumption or a window only multiplies" in _problems(
        _recs(expected_impact="£{metrics.core.revenue_current} / {assume:1%}"))


# --- the words --------------------------------------------------------------------------------


@pytest.mark.parametrize("action", [
    "Reorder the top products within {window:30 days}.", "Restock Home Decor within {window:30 days}.",
    "Stock up on the top sellers within {window:30 days}.", "Increase inventory within {window:30 days}.",
    "Avoid a stockout within {window:30 days}."])
def test_no_stock_in_v1(action: str) -> None:
    assert "never stock, inventory, a reorder or a stockout" in _problems(_recs(action=action))


def test_stage_3s_stockout_wording_passes_and_a_tempting_action_may_name_what_not_to_do() -> None:
    _check(_recs(cause="Revenue rose {metrics.core.revenue_change_pct}: consistent with a stockout, verify on the "
                       "shelf."))
    _check(_recs(), [DoNotDo(tempting_action="Reorder stock for December, treating {metrics.period.current} as an "
                                             "exceptional month",
                             why_wrong_here="Revenue rose {metrics.core.revenue_change_pct}, as it does each year.")])


@pytest.mark.parametrize("insight", [
    "Revenue in {metrics.period.current} was within its usual range: £{metrics.core.revenue_current}.",
    "The rise of {metrics.core.revenue_change_pct} in 2011-11 is routine variation.",
    "Revenue of £{metrics.core.revenue_current} was as expected for November.",
    "An unusual month: £{metrics.core.revenue_current}.",
    "£{metrics.core.revenue_current} in {metrics.period.current} is an outlier."])
def test_no_period_is_called_normal_or_unusual(insight: str) -> None:
    # 4B review 2 #7: the first three passed.
    assert "never call a month normal" in _problems(_recs(insight=insight))


def test_a_verdict_word_about_no_period_is_sound() -> None:
    # 4B review 2 #7: "a typical Champion" and stage 3's own D1 wording.
    _check(_recs(insight="A typical At-risk customer spent £{" + AT_RISK + ".avg_monetary}; coverage matches this "
                         "store's normal trading pattern."))


def test_lines_are_never_called_orders() -> None:
    # 4B review 1 #12, review 2 #8: the singular too; "in order to" is no order.
    _check(_recs(), basis="lines")
    for insight in ("Orders fell to {metrics.core.orders_current}.",
                    "The average order was £{metrics.core.revenue_current}.",
                    "The order count was {metrics.core.orders_current}."):
        assert "never orders" in _problems(_recs(insight=insight), basis="lines")
    _check(_recs(insight="In order to grow, revenue rose {metrics.core.revenue_change_pct}."), basis="lines")


def test_a_marked_product_carries_its_mark_and_is_never_acted_on() -> None:
    _check(_recs(cause="{metrics.products.top_products[0].product} took £{metrics.products.top_products[0].revenue}."))
    spend = "£{" + AT_RISK + ".avg_monetary}."
    assert "cite 'DOTCOM POSTAGE' by its path" in _problems(_recs(cause="DOTCOM POSTAGE took " + spend))
    # 4B review 2 #10: another case of a name of several words is the name.
    assert "cite 'DOTCOM POSTAGE' by its path" in _problems(_recs(cause="Dotcom Postage took " + spend))
    assert "never the subject of an action" in _problems(_recs(
        action="Raise {metrics.products.top_products[0].product} within {window:30 days}."))


def test_a_one_word_mark_is_matched_in_its_own_case() -> None:
    _check(_recs(action="Early access, never a discount, within {window:30 days}."))
    assert "cite 'Discount' by its path" in _problems(_recs(cause="Discount took £{" + AT_RISK + ".avg_monetary}."))


def test_the_customers_with_no_purchase_are_only_looked_into() -> None:
    # 4B review 2 #4: the prompt's own "look into" is sound.
    _check(_recs(action="Look into why the No purchases in file customers' lines exist within {window:30 days}."))
    assert "never a target" in _problems(_recs(action="Win back the No purchases in file customers within "
                                                      "{window:30 days}."))


def test_every_problem_is_named_at_once_for_the_one_retry() -> None:
    problems = _problems(_recs(2, insight="Revenue was £50,000.", how_to_measure="Revenue."), [])
    for expected in ("give 3 to 5", "50,000 is a number you wrote", "no review window", "at least one do_not_do"):
        assert expected in problems


def test_an_unreadable_answer_is_a_problem_never_a_crash(monkeypatch: pytest.MonkeyPatch) -> None:
    def overflow(*args: object, **kwargs: object) -> None:
        raise OverflowError("a number past a float")

    monkeypatch.setattr("stages.predict.strategy_checks.render", overflow)
    assert "could not be read (OverflowError)" in _problems(_recs())
