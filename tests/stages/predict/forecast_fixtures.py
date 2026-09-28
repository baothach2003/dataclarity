"""What session 4A's tests share: a metrics.json holding only what the
forecast reads, a run of months, a season and Student's t.

T(k) is Student's t at its 90th percentile with k degrees of freedom - the
80% band - taken from a table (scipy's t.ppf(0.9, k), the same numbers)."""

from datetime import date

from contracts.metrics import MetricsContract
from tests.contracts.test_metrics import metrics_payload

T = {1: 3.0776835371752544, 2: 1.8856180831641272, 3: 1.637744353696209, 5: 1.4758840488244815,
     8: 1.3968153097438654, 20: 1.3253407069850465}
# A season with no steady climb through the year (a straight line explains
# 0.70 of its logs, under the 0.9 ramp refusal): mean exactly 1, strongest
# November 1.6, weakest February 0.7, a gap of (1.6 - 0.7) / 1.6 = 56%.
SEASON = [0.8, 0.7, 0.9, 0.8, 0.9, 0.9, 0.9, 0.9, 1.2, 1.3, 1.6, 1.1]
SEASONAL = ("weighted moving average of the last 3 complete months (weights 1, 2, 3) with a monthly "
            "seasonality index")
NONE = "weighted moving average of the last 3 complete months (weights 1, 2, 3), no seasonality claimed"


def months_from(start: str, values: list[float]) -> dict[str, float]:
    """{YYYY-MM: revenue} for consecutive months from `start`."""
    year, month = int(start[:4]), int(start[5:])
    found = {}
    for value in values:
        found[f"{year:04d}-{month:02d}"] = value
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return found


def metrics_for(months: dict[str, float], *, current: str, data_start: date | None = None,
                data_end: date | None = None, month_grain: bool = False) -> MetricsContract:
    """A metrics.json carrying only what 4A reads, the rest valid and empty;
    the file runs from the first month's 1st to the last month's last day
    unless told otherwise."""
    first, last = min(months), max(months)
    start = data_start or date(int(first[:4]), int(first[5:]), 1)
    if data_end is None:
        year, month = int(last[:4]), int(last[5:])
        data_end = date.fromordinal(date(year + month // 12, month % 12 + 1, 1).toordinal() - 1)
    payload = metrics_payload()
    payload["period"] |= {"current": current, "data_start": start.isoformat(), "data_end": data_end.isoformat(),
                          "month_grain": month_grain}
    payload["core"]["revenue_by_month"] = [{"period": m, "revenue": r} for m, r in sorted(months.items())]
    return MetricsContract.model_validate(payload)
