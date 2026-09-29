"""Session 5A, review 3's cases (the bound): a file that starts part-way
through the current month, an inconclusive trust check, a file with no
readable date."""

from contracts.diagnosis import DiagnosisContract
from contracts.metrics import MetricsContract
from stages.report.layers import numbers
from tests.contracts.test_diagnosis import diagnosis_payload
from tests.contracts.test_metrics_reasons import _partial
from tests.stages.report.report_fixtures import build, metrics_data

PART_WAY = ("The file starts on 2011-11-10, part-way through 2011-11: the current month's figures cover it from that "
            "day - a shop that opened then, or an export cut short, which the file cannot tell apart.")


def test_a_file_starting_part_way_through_the_current_month_says_so_beside_its_figures() -> None:
    # Review 3 #1 (the standing rule): a "last 30 days" export pulled on
    # 9 December. Stage 2 takes November as the month; its figures stand
    # (the fixture's revenue_current), the note beside them.
    metrics = _partial(metrics_data(months=(("2011-11", 490614.86), ("2011-12", 170647.13))))
    metrics["period"]["data_start"] = "2011-11-10"
    report = build(metrics=metrics)
    numbers_ = report.layer_1_numbers
    assert (numbers_.current_note, numbers_.kpis[0].current, numbers_.kpis[0].current_reason) == (
        PART_WAY, 1150000.0, None)
    assert [(m.period, m.complete) for m in numbers_.revenue_by_month] == [("2011-11", False), ("2011-12", False)]


def test_no_note_when_the_current_month_is_whole() -> None:
    # From its first day, or a month-grain file (its lines stand for months).
    metrics = metrics_data()
    metrics["period"]["data_start"] = "2011-11-01"
    assert build(metrics=metrics).layer_1_numbers.current_note is None
    metrics["period"] |= {"data_start": "2011-11-30", "month_grain": True}
    assert build(metrics=metrics).layer_1_numbers.current_note is None
    assert build().layer_1_numbers.current_note is None
    # A file starting mid-month long before: the current month is whole.
    metrics = metrics_data()
    metrics["period"]["data_start"] = "2010-12-05"
    assert build(metrics=metrics).layer_1_numbers.current_note is None


def test_an_inconclusive_trust_check_is_a_caution_on_the_charts() -> None:
    # Review 3 #5: whether the month was cut short cannot be judged.
    diagnosis = diagnosis_payload()
    diagnosis["trust"]["checks"][0]["status"] = "inconclusive"
    message = diagnosis["trust"]["checks"][0]["message"]
    assert [c.cautions for c in build(diagnosis=diagnosis).charts] == [[message], [message]]
    diagnosis["trust"]["checks"][0]["status"] = "blocked"
    diagnosis["trust"]["verdict"] = "blocked"
    diagnosis.update({"calendar": None, "signals": None, "tree": None, "localization": None})
    diagnosis["headline"] = {"rule": 1, "hypothesis_id": None, "lens": None, "message": "Not trusted."}
    assert [c.cautions for c in build(diagnosis=diagnosis).charts] == [[message], [message]]
    diagnosis = diagnosis_payload()
    diagnosis["trust"]["checks"][0]["status"] = "not_applicable"
    assert [c.cautions for c in build(diagnosis=diagnosis).charts] == [[], []]


def test_a_file_with_no_readable_date_says_so_not_a_start_day() -> None:
    # Review 3 #7: stage 2 then dates the period by the analysis day; every
    # line is undated (a real run: 3,000 of 3,000).
    metrics = _partial(metrics_data(months=(), undated_lines=3000, undated_lines_reason="3,000 lines carry no date"))
    metrics["period"] |= {"current": "2026-08", "previous": "2026-07", "data_start": "2026-09-26",
                          "data_end": "2026-09-26"}
    kpis = numbers(MetricsContract.model_validate(metrics), DiagnosisContract.model_validate(diagnosis_payload()),
                   has_customers=True).kpis
    assert {k.current_reason for k in kpis} == {"no line counted in revenue carries a date the file can read"}


def test_a_file_with_no_readable_date_analysed_on_a_month_end_gets_no_part_way_note() -> None:
    # Review 4 #1: stage 2's fallback day then falls inside the current month.
    metrics = _partial(metrics_data(months=(), undated_lines=3000, undated_lines_reason="3,000 lines carry no date"))
    metrics["period"] |= {"current": "2026-09", "previous": "2026-08", "data_start": "2026-09-30",
                          "data_end": "2026-09-30"}
    numbers_ = numbers(MetricsContract.model_validate(metrics), DiagnosisContract.model_validate(diagnosis_payload()),
                       has_customers=True)
    assert numbers_.current_note is None
    assert numbers_.kpis[0].current_reason == "no line counted in revenue carries a date the file can read"


def test_a_current_month_whose_lines_cannot_be_measured_says_so() -> None:
    # Review 4 #3 and #4: dates readable, every November line unpriced - no
    # "closed month", no unreadable dates, and no part-way note beside
    # figures that are all withheld.
    unmeasurable = [{"scope": "file", "reason": "no price", "lines": 211827},
                    {"scope": "current", "reason": "no price", "lines": 37691}]
    metrics = _partial(metrics_data(months=(("2011-12", 170647.13),), unmeasurable=unmeasurable))
    metrics["period"]["data_start"] = "2011-11-10"
    numbers_ = numbers(MetricsContract.model_validate(metrics), DiagnosisContract.model_validate(diagnosis_payload()),
                       has_customers=True)
    assert {k.current_reason for k in numbers_.kpis} == {
        "no line dated in 2011-11 can be measured - see the lines in no figure"}
    assert numbers_.current_note is None


def test_no_part_way_note_for_a_file_starting_after_the_current_month() -> None:
    # Review 4 #6: a file from 5 December holds none of November.
    metrics = _partial(metrics_data(months=(("2011-12", 170647.13),)))
    metrics["period"]["data_start"] = "2011-12-05"
    assert build(metrics=metrics).layer_1_numbers.current_note is None


def test_an_inconclusive_price_check_is_the_badges_not_every_charts() -> None:
    # Review 4 #7: D2's "inconclusive" is too few products to compare prices.
    diagnosis = diagnosis_payload()
    diagnosis["trust"]["checks"][0]["status"] = "ok"
    diagnosis["trust"]["checks"].append({"id": "D2", "status": "inconclusive", "evidence": {},
                                         "message": "Only 0 products sold in both periods ..."})
    report = build(diagnosis=diagnosis)
    assert [c.cautions for c in report.charts] == [[], []]
    assert [c.id for c in report.layer_1_numbers.trust.checks] == ["D1", "D2"]


def test_each_empty_month_reason_needs_its_own_evidence() -> None:
    # Review 4 #3: unreadable dates only when lines are undated and none is
    # dated; unmeasurable only for the current month's own lines.
    def reason(**core: object) -> str | None:
        metrics = _partial(metrics_data(**core))  # type: ignore[arg-type]  # the core fields vary per case
        return numbers(MetricsContract.model_validate(metrics), DiagnosisContract.model_validate(diagnosis_payload()),
                       has_customers=True).kpis[0].current_reason

    unpriced = [{"scope": "file", "reason": "no price", "lines": 9}, {"scope": "current", "reason": "no price", "lines": 4}]
    assert reason(months=(), unmeasurable=unpriced) == (
        "no line dated in 2011-11 can be measured - see the lines in no figure")
    gap = (("2011-09", 1000000.0), ("2011-10", 1290000.0), ("2011-12", 300000.0))
    closed = ("no line counted in revenue is dated in 2011-11 - a closed month or missing data, which the file "
              "cannot tell apart")
    assert reason(months=gap, undated_lines=5, undated_lines_reason="5 lines carry no date") == closed
    assert reason(months=gap, unmeasurable=[{"scope": "previous", "reason": "no price", "lines": 4}]) == closed
