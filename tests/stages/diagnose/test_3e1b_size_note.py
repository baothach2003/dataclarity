"""Thach, 2026-10-03 (decisions 4 and 5), written before the code: when the
size test keeps every cause out of the headline - the change within the
usual movement, or a history too short to tell - the hypothesis table carries
one note; too short names no cause. Every figure worked by hand."""

from shared.periods import shift_month


def _months(first: str, count: int) -> list[str]:
    return [shift_month(first, i) for i in range(count)]


# --- decision 4: one table-level note when the gate fires ------------------------------------------


def test_the_table_carries_one_note_when_the_change_is_within_the_usual_movement() -> None:
    from contracts.diagnosis import HeadlineMovement
    from stages.diagnose.headline import choose_headline, hypotheses_note
    from tests.stages.diagnose.test_3e1b_headline_gate import INSIDE, SHORT, _all, _h, _moved, _trust

    within = choose_headline(_trust(), _all(_h("B1", "supported", 12.0, 1.0)), None, _moved(INSIDE))
    assert hypotheses_note(within) == (
        "This month's change is within the shop's usual month-to-month movement, so the verdicts below "
        "describe a change too small to single out: each shows what its hypothesis measured, and none is "
        "named as the cause.")
    short = choose_headline(_trust(), _all(_h("B1", "supported", 12.0, 1.0)), None, _moved(SHORT))
    assert hypotheses_note(short) == (
        "The history is too short to tell whether this change is larger than ordinary movement, so the "
        "verdicts below describe a change that cannot be singled out: each shows what its hypothesis "
        "measured, and none is named as the cause.")
    beyond = HeadlineMovement(change_pct=12.0, typical_pct=4.5, movements=23, factor=2.0, singled_out=True,
                              reason=None)
    named = choose_headline(_trust(), _all(_h("B1", "supported", 12.0, 1.0)), None, _moved(beyond))
    assert named.rule == 6 and hypotheses_note(named) is None


def test_nothing_supported_inside_the_usual_movement_carries_the_note_too() -> None:
    from stages.diagnose.headline import choose_headline, hypotheses_note
    from tests.stages.diagnose.test_3e1b_headline_gate import INSIDE, _all, _moved, _trust

    assert hypotheses_note(choose_headline(_trust(), _all(), None, _moved(INSIDE))) is not None


def test_a_blocked_run_carries_no_table_note() -> None:
    from contracts.diagnosis import Headline
    from stages.diagnose.headline import hypotheses_note
    from tests.stages.diagnose.test_3e1b_headline_gate import INSIDE

    assert hypotheses_note(Headline(rule=1, hypothesis_id=None, lens=None, message="blocked",
                                    movement=INSIDE)) is None


# --- the pipeline (mutation check) --------------------------------------------------------------


def _daily_shop(first: str, months: int, last_scale: float = 1.0):
    """One product, sold every day: 100 a day, the last month x `last_scale`. Dates as stage 2 reads them."""
    import calendar

    import pandas as pd

    rows = []
    for index, month in enumerate(_months(first, months)):
        year, number = int(month[:4]), int(month[5:])
        factor = last_scale if index == months - 1 else 1.0
        for day in range(1, calendar.monthrange(year, number)[1] + 1):
            rows.append({"Date": f"{month}-{day:02d}", "Qty": "1", "Price": f"{100 * factor:.4f}",
                         "Product": "Mug", "Cust": f"C{day % 7}"})
    return pd.DataFrame(rows)


def _diagnose(frame):
    from datetime import UTC, datetime

    from stages.analyze.assemble import assemble_metrics
    from stages.diagnose.assemble import diagnose
    from stages.diagnose.inputs import build_run_data

    mapping = {"Date": "transaction_date", "Qty": "quantity", "Price": "unit_price", "Product": "product_name",
               "Cust": "customer"}
    now = datetime(2026, 10, 3, tzinfo=UTC)
    metrics = assemble_metrics(frame, mapping, now=now)
    return diagnose(build_run_data(frame, mapping, metrics), now)


def test_a_flat_shops_small_change_carries_the_table_note() -> None:
    found = _diagnose(_daily_shop("2010-01", 13, last_scale=1.01))  # Dec -> Jan, both 31 days
    assert found.headline.rule == 7 and found.hypotheses_note is not None


def test_no_percentage_carries_no_table_note() -> None:
    from contracts.diagnosis import Headline, HeadlineMovement
    from stages.diagnose.headline import hypotheses_note

    nopct = HeadlineMovement(change_pct=None, typical_pct=None, movements=23, factor=2.0, singled_out=None,
                             reason="this month's change has no percentage: no revenue before")
    assert hypotheses_note(Headline(rule=7, hypothesis_id=None, lens=None, message="m", movement=nopct)) is None
