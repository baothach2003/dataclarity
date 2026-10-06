"""Sections 4 to 6 of the front, and what report.json carries for them
(docs/REPORT_REDESIGN.md 1.4-1.6, 6.4, 7): what to do next by forecast.json's
actions status, next month in plain words (Q12, Q13), what this report cannot
know, the rows the cleaning left out (one line per dropping step), the
part-months by their dates (D7), and the currency (D6, Q8)."""

import calendar
from datetime import date

from contracts.cleaning import CleaningReportContract
from contracts.diagnosis import NotTestable
from contracts.forecast import ForecastContract
from contracts.metrics import MetricsContract
from contracts.report import ForecastView, Numbers
from contracts.report_front import CannotKnow, FrontAction, NextSteps, PartialMonth, ReportCurrency, RowsLeftOut
from shared.periods import complete_months
from stages.report.wording import amount, count, days, month_name

SWITCHED_OFF = "Suggested actions are switched off for this report."
NOT_AVAILABLE = "Suggested actions are not available for this report."
SUPPRESSED = ("Suggested actions are not shown for this report: the AI's answer did not pass our checks, so nothing "
              "was shown rather than something unchecked. Every figure above is unaffected.")
# Why no claim was selected, by the headline's rule (the review: under rule 2
# "no single reason stands out" contradicted sentence C).
_NONE_WHY = {2: "the change matches days with no sales, a matter of the data rather than of the shop",
             5: "the change matches the calendar or the time of year, which no action in the shop changes",
             6: "no figure above is one an action in the shop works on"}
_NO_REASON = "no single reason stands out in these figures"
NEXT_MONTH = " Next month, compare sales with the estimate in section 5."


def none_selected(rule: int) -> str:
    return f"No action is suggested: {_NONE_WHY.get(rule, _NO_REASON)}.{NEXT_MONTH}"
NOT_STATED = "Amounts are in your file's currency."


def next_steps(forecast: ForecastContract, rule: int, ai_on: bool) -> NextSteps:
    """By `actions_status` (Thach: off, suppressed, list). A forecast from
    before 2.1 carries none: "switched off" when the AI step is off, else not
    available (Q36). Actions listed where no cause is named (rules 1-4, 7)
    are no answer this report can show (design 4.2; the review)."""
    status, actions = forecast.actions_status, forecast.actions
    if status is None:
        return NextSteps(status="unavailable" if ai_on else "off",
                         sentence=NOT_AVAILABLE if ai_on else SWITCHED_OFF, items=[])
    if status == "suppressed":
        return NextSteps(status="suppressed", sentence=SUPPRESSED, items=[])
    if status == "list" and actions is not None:
        if actions and rule not in (5, 6):
            return NextSteps(status="unavailable", sentence=NOT_AVAILABLE, items=[])
        items = [FrontAction(rests_on=a.fact, action=a.action, why=a.why, watch=a.watch) for a in actions]
        return NextSteps(status="list", sentence=None if items else none_selected(rule), items=items)
    return NextSteps(status="off", sentence=SWITCHED_OFF, items=[])


def next_month(view: ForecastView, partial: list[PartialMonth], code: str | None) -> list[str]:
    """The estimate in plain words (Q12); the part-month by its dates only
    (Q13); how the range is built is the appendix's."""
    if view.insufficient_history or not view.points:
        months = f"{view.months_used} full month{'' if view.months_used == 1 else 's'}"
        return [f"There is too little history to estimate next month: {months}, and 3 are needed."]
    first = view.points[0]
    tenths = round(first.confidence * 10)
    found = [f"Next month ({month_name(first.period)}): about {amount(first.point, code)}, likely between "
             f"{amount(first.low, code)} and {amount(first.high, code)} (the real figure should land in this range "
             f"about {tenths} months in 10)."]
    if view.season_years is None:
        found.append("It is based on the last three full months, the latest counting most, and assumes no "
                     "seasonal pattern.")
        if view.season_note:
            # The forecast's ramp note, by its condition: no season claimed,
            # a note said (shared/seasonality RAMP_NOTE), worded once here.
            found.append("No seasonal pattern is assumed: the months rise or fall steadily through the year, which a "
                         "one-time change in the shop's level could also explain.")
    elif view.season_years == 2:
        found.append("It follows the seasonal pattern of the last two years - the fewest years that can show one - "
                     "so the shape is less certain than more years would make it.")
    else:
        found.append(f"It follows the seasonal pattern of the last {view.season_years} years.")
    if view.history_note:
        # Its history cut by a month with none (shared/seasonality.season_window).
        found.append(f"It uses the last {view.months_used} full months only: an earlier month with no sales (a "
                     "closed month or missing data, which the file cannot tell apart) cuts off the months before it.")
    if view.first_month_in_file:
        part = next((p for p in partial if p.period == first.period), None)
        if part is not None:
            found.append(f"Your file already has sales for {days(part.covers_from, part.covers_to)}; that part-month "
                         "is not compared with this estimate.")
        else:
            found.append(f"Your file already has sales for {month_name(first.period)}; they are not compared with "
                         "this estimate.")
    return found


def partial_months(metrics: MetricsContract) -> list[PartialMonth]:
    """The first and last months the file covers only part of, by the one
    definition of a complete month (shared/periods; CONTRACTS 11 "Months")."""
    period = metrics.period
    if period.month_grain:
        return []
    covered = set(complete_months(period.data_start, period.data_end, month_grain=False))
    first, last = f"{period.data_start:%Y-%m}", f"{period.data_end:%Y-%m}"
    found = []
    if first not in covered:
        end = period.data_end if first == last else _last_day(period.data_start)
        found.append(PartialMonth(period=first, covers_from=period.data_start, covers_to=end, position="first"))
    if last != first and last not in covered:
        found.append(PartialMonth(period=last, covers_from=period.data_end.replace(day=1), covers_to=period.data_end,
                                  position="last"))
    return found


def _last_day(day: date) -> date:
    return day.replace(day=calendar.monthrange(day.year, day.month)[1])


def chart_note(partial: list[PartialMonth]) -> list[str]:
    return [f"{month_name(p.period)} is not in the chart: the file covers only {days(p.covers_from, p.covers_to)}. "
            "Comparing part of a month with full months would mislead, so it is left out." for p in partial]


def rows_left_out(cleaning: CleaningReportContract) -> list[RowsLeftOut]:
    """One line per cleaning step that dropped rows, by its action (design
    1.6's table); flagging and marking steps drop nothing."""
    found = []
    for change in cleaning.changes:
        rows, column = change.rows_affected, change.column
        if rows <= 0:
            continue
        if change.action == "drop_rows_missing":
            sentence = f'{count(rows)} rows with no value in "{column}" were left out'
        elif change.action == "remove_exact_duplicates":
            sentence = f"{count(rows)} rows that repeated another row exactly were left out"
        elif change.action == "fix_negative" and change.params.get("strategy") == "drop":
            sentence = f'{count(rows)} rows with a negative value in "{column}" were left out'
        else:
            continue
        found.append(RowsLeftOut(action=change.action, column=column, rows=rows, sentence=sentence))
    return found


def cannot_know(not_testable: list[NotTestable], cleaning: CleaningReportContract, numbers: Numbers,
                left_out: list[RowsLeftOut]) -> list[CannotKnow]:
    """Section 6 in plain words: the not-testable list by id (its code reasons
    stay in the appendix), stock, and the rows left out."""
    ids = {item.id for item in not_testable}
    found = [CannotKnow(title="Profit", text="The file has no costs, so these figures are sales, not profit.")]
    if "X1" in ids:
        found.append(CannotKnow(title="Marketing and promotions", text="The file has no campaign data."))
    if ids & {"X2", "X3"}:
        found.append(CannotKnow(title="Competitors, weather and events", text="Nothing outside the file is used."))
    if "X4" in ids:
        found.append(CannotKnow(title="How many people visited or browsed", text="The file records only purchases."))
    found.append(CannotKnow(title="Stock", text="This version analyses sales, not stock levels."))
    if ids & {"X6", "X7"}:
        found.append(CannotKnow(title="Sales by channel, payment method or country",
                                text="This version does not split sales that way."))
    read, used = cleaning.rows_in, cleaning.rows_out
    if left_out:
        text = (f"{count(read)} rows were read and {count(used)} used: {'; '.join(r.sentence for r in left_out)} "
                "during cleaning, as the plan you approved in Review said. Rows left out are in no figure, and a gap "
                "they leave cannot be seen.")
    elif read == used:
        text = f"{count(read)} rows were read and used; no row was left out."
    else:
        text = f"{count(read)} rows were read and {count(used)} used."
    if numbers.outside_revenue:
        text += " Some lines are left out of sales by the class you gave them in Review - the appendix lists them."
    found.append(CannotKnow(title="Rows left out", text=text))
    return found


def currency(cleaning: CleaningReportContract) -> ReportCurrency:
    """The code on every amount, or "not stated" (no report before 4.3 or a
    file whose currency nobody named carries one)."""
    applied = cleaning.currency
    code = applied.code if applied is not None else None
    return ReportCurrency(code=code, sentence=None if code else NOT_STATED)
