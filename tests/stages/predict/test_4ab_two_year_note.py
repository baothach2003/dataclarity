"""Session 4A-b (tenth run): Thach's decision on 4A's season claim (option b) -
keep the claim, and note it whenever it rests on exactly two years: the
step/season split is not certain at the theoretical minimum of two cycles
(Hyndman & Kostenko 2007). Written before the code (PROJECT_PLAN 4A-b).
"""

import json
from pathlib import Path

import pytest

from contracts.forecast import ForecastBlock
from stages.predict.forecast import forecast
from shared.seasonality import RAMP_NOTE, TWO_YEAR_NOTE, season_reading
from tests.stages.predict.forecast_fixtures import NONE, SEASON, SEASONAL, metrics_for, months_from


def _block(values: list[float], start: str = "2024-01") -> ForecastBlock:
    months = months_from(start, values)
    return forecast(metrics_for(months, current=max(months)))


@pytest.mark.parametrize("months", [24, 30, 35])
def test_a_season_claimed_from_two_years_carries_the_note(months: int) -> None:
    # C1: 24-35 months count back two full years from the compared month.
    values = [100 * p for p in (SEASON * 3)[-months:]]
    block = _block(values, start={24: "2024-01", 30: "2023-07", 35: "2023-02"}[months])
    assert (block.method, block.months_used, block.season_years, block.season_note) == (
        SEASONAL, months, 2, TWO_YEAR_NOTE)


@pytest.mark.parametrize("years", [3, 4])
def test_three_years_or_more_carry_no_note(years: int) -> None:
    # C3: the decision names exactly two years.
    block = _block([100 * p for p in SEASON * years], start="2022-01")
    assert (block.method, block.season_years, block.season_note) == (SEASONAL, years, None)


def test_no_season_claimed_no_two_year_note() -> None:
    # C2: growth alone, one big month, a ramp, under two years.
    growth = [100 * 1.05 ** i for i in range(24)]
    spike = [100.0] * 24
    spike[12] = 400.0
    assert (_block(growth).method, _block(growth).season_note) == (NONE, None)
    assert _block(spike).season_note is None
    # A step between the two years (test_4a_season's case): refused as a
    # ramp, with the ramp's own note - never the two-year one (review 1 #5).
    ramp = _block([1000.0] * 12 + [2000.0] * 12)
    assert (ramp.method, ramp.season_years, ramp.season_note) == (NONE, None, RAMP_NOTE)
    short = _block([100 * p for p in (SEASON * 2)[1:]], start="2024-02")  # 23 months
    assert (short.method, short.season_note) == (NONE, None)


def test_the_reading_returns_the_two_years_and_the_note() -> None:
    values = [100 * p for p in SEASON * 2]
    cycles, note = season_reading(sorted(months_from("2024-01", values)), values)
    assert cycles is not None and len(cycles) == 2 and note == TWO_YEAR_NOTE


def test_the_note_never_says_a_step_happened() -> None:
    # C6: true wherever it is written - two years cannot tell the two apart;
    # it never asserts that a change of level occurred.
    for claim in ("there was a step", "a step happened", "the level changed"):
        assert claim not in TWO_YEAR_NOTE.lower()
    assert "two years" in TWO_YEAR_NOTE


def test_the_report_shows_it_wherever_the_forecast_is_shown() -> None:
    # C5: forecast.json's season_note reaches the forecast view, the
    # forecast chart's note and the page.
    from stages.report.html_report import render_html
    from tests.contracts.test_forecast import forecast_payload
    from tests.stages.report.html_probe import Page
    from tests.stages.report.report_fixtures import build

    payload = forecast_payload()
    payload["forecast"] |= {"months_used": 24, "season_years": 2, "season_note": TWO_YEAR_NOTE}
    report = build(forecast=payload)
    assert report.layer_3_actions.forecast.season_note == TWO_YEAR_NOTE
    assert TWO_YEAR_NOTE in (report.charts[1].note or "")
    assert " ".join(TWO_YEAR_NOTE.split()) in Page(render_html(report)).section("actions")


# --- forecast.json 2.0 (review 1 #1, #2) -----------------------------------------------------------


def _contract(**forecast: object) -> dict:  # type: ignore[type-arg]  # a JSON payload
    from tests.contracts.test_forecast import forecast_payload

    payload = forecast_payload()
    payload["forecast"] |= forecast
    return payload


@pytest.mark.parametrize("change,refused", [
    ({"months_used": 24, "season_years": 2, "season_note": None}, "carries its note"),
    ({"season_years": 3, "season_note": TWO_YEAR_NOTE}, "carries no season note"),
    ({"season_years": 1}, "season_years"),
    ({"revenue": [], "horizon_periods": 0, "insufficient_history": True, "months_used": 2, "season_years": 2},
     "no season and no season note"),
])
def test_the_contract_holds_the_two_year_rule(change: dict, refused: str) -> None:  # type: ignore[type-arg]  # a JSON payload
    from pydantic import ValidationError

    from contracts.forecast import ForecastContract

    with pytest.raises(ValidationError, match=refused):
        ForecastContract.model_validate(_contract(**change))
    ForecastContract.model_validate(_contract(months_used=24, season_years=2, season_note=TWO_YEAR_NOTE))


def test_a_forecast_written_before_the_note_is_refused_never_shown_without_it() -> None:
    # Review 1 #1: a change of meaning is a major (CONTRACTS 10) - a 1.x file
    # is "run the prediction again", never a two-year season shown bare.
    from pydantic import ValidationError

    from contracts.forecast import ForecastContract

    old = _contract(months_used=24, season_note=None)
    old["schema_version"] = "1.0"
    del old["forecast"]["season_years"]
    with pytest.raises(ValidationError, match="run the prediction again"):
        ForecastContract.model_validate(old)


# --- review 2: the years tied to the history, the report's own copy, the 1.x shape ----------------


@pytest.mark.parametrize("change", [
    {"months_used": 36, "season_years": 2, "season_note": TWO_YEAR_NOTE},  # 3 full years held
    {"months_used": 47, "season_years": 4},  # more years than the history holds
    {"months_used": 24, "season_years": 3},
    {"months_used": 12, "season_years": 1},  # the history's own years, but fewer than a season needs
])
def test_season_years_are_the_full_years_of_the_history(change: dict) -> None:  # type: ignore[type-arg]  # a JSON payload
    # Review 2 #2: never a count the history does not hold.
    from pydantic import ValidationError

    from contracts.forecast import ForecastContract

    with pytest.raises(ValidationError, match="full years of the history"):
        ForecastContract.model_validate(_contract(**change))


@pytest.mark.parametrize("months,years,note", [(24, 2, TWO_YEAR_NOTE), (35, 2, TWO_YEAR_NOTE), (36, 3, None),
                                               (47, 3, None), (48, 4, None)])
def test_every_history_length_has_its_years(months: int, years: int, note: str | None) -> None:
    from contracts.forecast import ForecastContract

    ForecastContract.model_validate(_contract(months_used=months, season_years=years, season_note=note))


def test_the_minimum_is_the_contracts_one_copy() -> None:
    # Review 2 #4: stage 4 and the model read one minimum (SPECS 7.5).
    from contracts.forecast import MIN_SEASON_YEARS
    from shared.seasonality import SEASONAL_MIN_MONTHS

    assert (MIN_SEASON_YEARS, SEASONAL_MIN_MONTHS) == (2, 24)


def test_the_report_carries_the_years_a_consumer_decides_on() -> None:
    # Review 2 #7: report.json 2.0's forecast view has `season_years`, so a
    # reader of the report never parses the note either.
    from tests.contracts.test_forecast import forecast_payload
    from tests.stages.report.report_fixtures import build

    two = forecast_payload()
    two["forecast"] |= {"months_used": 24, "season_years": 2, "season_note": TWO_YEAR_NOTE}
    view = build(forecast=two).layer_3_actions.forecast
    assert (view.season_years, view.season_note) == (2, TWO_YEAR_NOTE)
    assert build().layer_3_actions.forecast.season_years == 3
    none = forecast_payload()
    none["forecast"] |= {"method": "weighted moving average of the last 3 complete months (weights 1, 2, 3)",
                         "season_years": None, "season_note": RAMP_NOTE}
    assert build(forecast=none).layer_3_actions.forecast.season_years is None


def test_a_report_written_before_is_refused_build_the_report_again() -> None:
    # Review 2 #1: report.json 1.x showed a two-year season bare.
    from pydantic import ValidationError

    from contracts.report import ReportContract
    from tests.stages.report.report_fixtures import build

    old = build().model_dump(mode="json")
    old["schema_version"] = "1.0"
    del old["layer_3_actions"]["forecast"]["season_years"]
    with pytest.raises(ValidationError, match="build the report again"):
        ReportContract.model_validate(old)
    assert build().schema_version == "2.9"  # 2.9 the front section (step 3); 2.8 not_in_v1 and the revenue KPI's change (Q21, Q22); 2.7 the headline's hedge; 2.6 each hypothesis's lens (Thach, 2026-10-05, Q2); 2.5 the labels, evidence text and outside reasons (Thach, 2026-10-04, (vii)-(ix)); 2.4 the headline's season comparison (decision 1); 2.3 since 3E1b-F1 (b), the hypotheses note; 2.2 since 2E-u6 (the lines after the upload); 2.1 since 3E1b (the headline's optional movement)


def test_the_cli_answers_a_forecast_of_the_version_before_with_run_the_prediction_again(
        tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    # Review 2 #5: the real 1.x shape (no `season_years`), not only "9.0".
    from stages.report import cli
    from tests.stages.report.report_fixtures import RUN, run_dir

    monkeypatch.setattr(cli, "DOTENV", tmp_path / "no.env")
    monkeypatch.setenv("STRATEGY_AI_ENABLED", "false")
    run = run_dir(tmp_path)
    forecast = json.loads((run / "forecast.json").read_text(encoding="utf-8"))
    forecast["schema_version"] = "1.0"
    del forecast["forecast"]["season_years"]
    (run / "forecast.json").write_text(json.dumps(forecast), encoding="utf-8")

    assert cli.main(["--run", RUN, "--runs-dir", str(tmp_path), "--source-file", "sales.csv"]) == 1

    err = capsys.readouterr().err
    assert "forecast.json cannot be read" in err and "run the prediction again" in err and "Traceback" not in err
    assert not (run / "report.json").exists() and not (run / "report.html").exists()


# --- review 3: report.json's view holds the same rules; the note is the two years' ----------------


@pytest.mark.parametrize("change,refused", [
    ({"months_used": 24, "season_years": 2, "season_note": None}, "carries its note"),
    ({"season_years": 7, "season_note": None}, "full years of the history"),
    ({"season_years": -4}, "full years of the history"),
    ({"season_years": 3, "season_note": TWO_YEAR_NOTE}, "carries no season note"),
    ({"insufficient_history": True, "points": [], "months_used": 2, "season_years": 2, "first_month_in_file": False,
      "partial_first_month_until": None}, "no season and no season note"),
])
def test_the_reports_forecast_view_holds_the_season_rules(change: dict, refused: str) -> None:  # type: ignore[type-arg]  # a JSON payload
    # Review 3 #4: CONTRACTS 9 tells a reader of the report to decide on
    # its `season_years`, so the report's model holds what forecast.json's does.
    from pydantic import ValidationError

    from contracts.report import ForecastView
    from tests.stages.report.report_fixtures import build

    view = build().layer_3_actions.forecast.model_dump(mode="json") | change
    with pytest.raises(ValidationError, match=refused):
        ForecastView.model_validate(view)


def test_the_note_is_keyed_on_thachs_two_years_not_on_the_minimum() -> None:
    # Review 3 #6: the note names two years; a later minimum (8D's option
    # (d)) must not put "two years" beside a three-year season.
    from contracts.forecast import MIN_SEASON_YEARS, NOTED_SEASON_YEARS

    assert (NOTED_SEASON_YEARS, MIN_SEASON_YEARS) == (2, 2)
    assert "two years" in TWO_YEAR_NOTE


# --- review 4 (scoped): an empty note is no note; the keying observed --------------------------------


def test_an_empty_note_is_no_note() -> None:
    # Review 4 #2: the page and the chart skip a falsy note, so "" beside a
    # two-year season showed it bare.
    from pydantic import ValidationError

    from contracts.forecast import ForecastContract
    from contracts.report import ForecastView
    from tests.stages.report.report_fixtures import build

    with pytest.raises(ValidationError, match="carries its note"):
        ForecastContract.model_validate(_contract(months_used=24, season_years=2, season_note=""))
    view = build().layer_3_actions.forecast.model_dump(mode="json") | {"months_used": 24, "season_years": 2,
                                                                       "season_note": " "}
    with pytest.raises(ValidationError, match="carries its note"):
        ForecastView.model_validate(view)


def test_the_model_keys_the_note_on_the_two_years_not_the_minimum(monkeypatch: pytest.MonkeyPatch) -> None:
    # Review 4 #5: observable once the minimum differs from two.
    import contracts.forecast as contract

    monkeypatch.setattr(contract, "MIN_SEASON_YEARS", 3)
    contract.check_season(36, False, 3, None)
    with pytest.raises(ValueError, match="carries no season note"):
        contract.check_season(36, False, 3, "a note")


def test_stage_4_keys_the_note_on_the_two_years_not_the_minimum(monkeypatch: pytest.MonkeyPatch) -> None:
    import shared.seasonality as seasonality

    monkeypatch.setattr(seasonality, "MIN_SEASON_YEARS", 3)
    values = [100 * p for p in SEASON * 2]
    assert season_reading(sorted(months_from("2024-01", values)), values)[1] == TWO_YEAR_NOTE
