"""The front section's rules on the cases the three real runs do not show
(the report redesign, step 3; found unpinned by hand mutation): a fall, last
year moving the other way, returns and customers that did move, a cleaning
step that only flagged, and the contract's own refusals."""

import copy

import pytest
from pydantic import ValidationError

from contracts.cleaning import CleaningReportContract
from contracts.diagnosis import DiagnosisContract, YearAgo
from contracts.metrics import MetricsContract
from contracts.report_front import FrontBar, Waterfall
from shared.claim_lines import Context, moved_line, not_reason_lines
from stages.report.front_rest import rows_left_out
from stages.report.front_summary import sentence_a
from tests.stages.report.real_runs import build_real, files


def _loaded(run: str = "kaggle") -> tuple[MetricsContract, DiagnosisContract]:
    data = files(run)
    return (MetricsContract.model_validate(data["metrics.json"]),
            DiagnosisContract.model_validate(data["diagnosis.json"]))


def _ctx(run: str = "kaggle", **changes) -> tuple[Context, DiagnosisContract]:
    metrics, diagnosis = _loaded(run)
    tree = diagnosis.tree
    fields = {"metrics": metrics, "tree": tree, "bridge": tree.lever.bridge, "year_ago": diagnosis.year_ago,
              "code": None} | changes
    return Context(**fields), diagnosis


def _hypothesis(diagnosis: DiagnosisContract, hypothesis_id: str, **changes):
    found = next(h for h in diagnosis.hypotheses if h.id == hypothesis_id)
    return found.model_copy(update=changes)


def test_sentence_a_prints_the_bridges_shown_cents_not_the_exact_change_q22() -> None:
    metrics, diagnosis = _loaded()
    bridge = diagnosis.tree.lever.bridge.model_copy(
        update={"shown_previous": 41_367.49, "shown_current": 46_292.51, "shown_change": 4_925.02})

    assert sentence_a(metrics, bridge, None) == ("Sales in December 2024 were 46,292.51, up 4,925.02 (+11.9%) on "
                                                 "November 2024 (41,367.49).")


def test_a_fall_is_said_down() -> None:
    metrics, diagnosis = _loaded()
    bridge = diagnosis.tree.lever.bridge.model_copy(
        update={"shown_previous": 46_292.5, "shown_current": 41_367.5, "shown_change": -4_925.0})

    assert "were 41,367.50, down 4,925.00" in sentence_a(metrics, bridge, None)


def test_last_year_moving_the_other_way_is_no_also() -> None:
    ctx, diagnosis = _ctx(year_ago=YearAgo(previous="2023-11", current="2023-12", revenue_previous=41_046.0,
                                           revenue_current=34_900.0))

    assert moved_line(_hypothesis(diagnosis, "T2"), ctx).startswith(
        "Last year alone, sales fell between November and December: 41,046.00 to 34,900.00.")  # Q41


def test_how_often_customers_ordered_is_read_from_orders_per_customer_not_the_sign() -> None:
    # The bar says 12.32 -> 13.72: more often, whatever the contribution's sign (the review).
    ctx, diagnosis = _ctx()
    line = moved_line(_hypothesis(diagnosis, "B1", contribution=-4_712.29), ctx)

    assert line.startswith("Customers ordered more often: 343 orders, up from 308 - worth about -4,712.29")


def test_the_same_customers_are_claimed_only_when_nobody_came_or_went() -> None:
    ctx, diagnosis = _ctx()
    moved = ctx.tree.model_copy(update={"customers": ctx.tree.customers.model_copy(update={"new": 120.0})})
    ctx = Context(metrics=ctx.metrics, tree=moved, bridge=ctx.bridge, year_ago=ctx.year_ago, code=None)
    ruled_out = [_hypothesis(diagnosis, i) for i in ("C1", "C2", "C3")]

    assert not_reason_lines(ruled_out, ctx) == [
        "Customers: new customers, customers who stopped buying, customers who came back after a break."]


def test_prices_that_moved_are_not_said_kept() -> None:
    ctx, diagnosis = _ctx()

    assert not_reason_lines([_hypothesis(diagnosis, "P1", contribution=12.5)], ctx) == [
        "Prices of products sold in both months."]


def test_returns_that_happened_are_not_said_none() -> None:
    ctx, diagnosis = _ctx("demo_classed")

    assert not_reason_lines([_hypothesis(diagnosis, "P3", verdict="ruled_out")], ctx) == ["Refunds for returned goods."]


def test_against_moves_below_the_partial_bar_stay_checked_not_the_reason() -> None:
    # C2, P2 and P4 moved against the change on the demo, each under 5% of it.
    kinds = [group.kind for group in build_real("demo_classed").front.checklist]

    assert kinds == ["moved", "not_reason", "cannot_show"]


def test_a_cleaning_step_that_only_flagged_left_no_row_out() -> None:
    cleaning = copy.deepcopy(files("kaggle")["cleaning_report.json"])
    flagged = copy.deepcopy(cleaning["changes"][0]) | {"action": "fix_negative", "column": "Quantity",
                                                        "params": {"strategy": "flag"}, "rows_affected": 7}
    dropped = flagged | {"params": {"strategy": "drop"}, "rows_affected": 3}
    cleaning["changes"] += [flagged, dropped]

    found = rows_left_out(CleaningReportContract.model_validate(cleaning))

    assert [(r.action, r.rows, r.sentence) for r in found] == [
        ("drop_rows_missing", 1213, '1,213 rows with no value in "Item" were left out'),
        ("fix_negative", 3, '3 rows with a negative value in "Quantity" were left out')]


def _waterfall(**changes) -> dict:
    bar = {"factor": "frequency", "label": "Orders per customer", "was": "1", "now": "2", "shown": 10.0,
           "worth": "+10.00"}
    return {"previous_label": "a", "current_label": "b", "shown_previous": 100.0, "shown_current": 110.0,
            "shown_change": 10.0, "previous_text": "100.00", "current_text": "110.00", "change_text": "+10.00",
            "bars": [bar], "caption": "c", "note": None} | changes


def test_the_contract_refuses_bars_that_do_not_add_up() -> None:
    Waterfall.model_validate(_waterfall())
    with pytest.raises(ValidationError, match="add up"):
        Waterfall.model_validate(_waterfall(shown_change=10.01, shown_current=110.01))
    with pytest.raises(ValidationError, match="this month"):
        Waterfall.model_validate(_waterfall(shown_current=111.0))
    assert FrontBar.model_validate(_waterfall()["bars"][0]).shown == 10.0


def test_the_contract_refuses_a_split_beside_no_comparison() -> None:
    front = build_real("kaggle").front.model_dump()

    with pytest.raises(ValidationError, match="compared"):
        type(build_real("kaggle").front).model_validate(front | {"state": "not_compared", "next_steps": None})


def test_returns_last_month_only_are_not_said_none() -> None:
    ctx, diagnosis = _ctx("demo_classed")
    returns = ctx.tree.returns.model_copy(update={"returns_cur": 0.0})
    ctx = Context(metrics=ctx.metrics, tree=ctx.tree.model_copy(update={"returns": returns}), bridge=ctx.bridge,
                  year_ago=ctx.year_ago, code=None)

    assert not_reason_lines([_hypothesis(diagnosis, "P3", verdict="ruled_out")], ctx) == ["Refunds for returned goods."]
