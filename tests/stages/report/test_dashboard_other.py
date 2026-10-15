"""A breakdown's "Other (N values)" member in the dashboard (Thach's Q3,
2026-10-15; metrics.json 16.4): drawn after the values shown one by one, the
blank bar last; its change never sizes the widget - it is many values, not a
mover (decision made alone). Figures worked by hand in the comments."""

import copy

from contracts.report import ReportContract
from tests.stages.report.real_runs import build_real, files


def _member(name: str, now: float, was: float, **extra: object) -> dict:
    return {"name": name, "is_blank": False, "revenue_current": now, "revenue_previous": was, "change": now - was,
            **extra}


def _report() -> ReportContract:
    # Kaggle's months: 46,292.50 now, 41,367.50 before. D1..D8 4,000.00 now, 3,500.00 before (+500.00 each);
    # Other (5 values) 13,000.00 / 11,000.00 (+2,000.00 - the largest change); the blank 1,292.50 / 2,367.50
    # (-1,075.00). 32,000 + 13,000 + 1,292.50 = 46,292.50; 28,000 + 11,000 + 2,367.50 = 41,367.50.
    members = [_member(f"D{i}", 4000.0, 3500.0) for i in range(1, 9)]
    members.append(_member("Other (5 values)", 13000.0, 11000.0, is_other=True, values=5))
    members.append(_member("(blank)", 1292.5, 2367.5) | {"is_blank": True})
    metrics = copy.deepcopy(files("kaggle")["metrics.json"])
    metrics["schema_version"] = "16.4"
    metrics["by_dimension"]["breakdowns"] = [{"column": "Country", "change_reason": None, "withheld_reason": None,
                                              "members": members}]
    cleaning = files("kaggle")["cleaning_report.json"] | {"breakdowns": ["Country"]}
    return build_real("kaggle", metrics=metrics, cleaning=cleaning)


def _widget():
    report = _report()
    assert report.dashboard is not None
    return next(w for w in report.dashboard.widgets if w.id == "breakdown_1")


def test_other_is_drawn_after_the_values_and_the_blank_last() -> None:
    # Other's 13,000.00 is more than any value's, yet it is not a value: it follows them.
    assert [b.label for b in _widget().bars] == [*(f"D{i}" for i in range(1, 9)), "Other (5 values)", "(blank)"]


def test_others_change_never_sizes_the_widget() -> None:
    # The largest change of a value or the blank: the blank's 1,075.00 - not Other's 2,000.00.
    assert _widget().size == 1075.0
