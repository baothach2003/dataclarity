"""Session 2E-v (the scoped review of 2E-t1-t3's cycle-3 fixes, Thach,
2026-09-29), metrics.json's side - written before the fixes.

#1  a month outside the two compared whose amounts overflow was written as
    null into a required float (revenue_by_month, a segment's avg_monetary):
    stage 2 answered 200 and wrote a metrics.json no reader could load. The
    contract now refuses any number JSON cannot carry, anywhere in the file.
#8  the check for a file written before the line taxonomy's blocks ran
    before the major-version check: a 15.0 file was told the wrong story, and
    a newer major was told to "re-analyse".
Review cycle 2 #2: a NaN is what an overflow leaves when +inf and -inf meet
(two customers of one segment): it is "too large to add" too, never a 500.
"""

import math

import pandas as pd
import pytest
from pydantic import ValidationError

from contracts.lines import TOO_LARGE_TO_ADD
from contracts.metrics import MetricsContract
from stages.analyze.assemble import assemble_metrics

MAPPING = {"Day": "transaction_date", "Order": "order_id", "Who": "customer", "Sku": "sku", "Name": "product_name",
           "Qty": "quantity", "Price": "unit_price"}
COLUMNS = list(MAPPING)
ROWS = [("2026-05-04", "O1", "Ann", "A1", "Mug", "1", "10"),
        ("2026-06-04", "O2", "Ann", "A1", "Mug", "1", "10"),
        ("2026-07-04", "O3", "Bo", "A1", "Mug", "2", "10"),
        ("2026-08-04", "O4", "Ann", "A1", "Mug", "1", "10"),
        ("2026-09-02", "O5", "Bo", "A1", "Mug", "1", "10")]


def _metrics(rows=ROWS):
    from datetime import UTC, datetime

    return assemble_metrics(pd.DataFrame(rows, columns=COLUMNS), MAPPING, datetime(2026, 9, 26, tzinfo=UTC))


def _messages(error: ValidationError) -> list[str]:
    return [str(problem["msg"]) for problem in error.errors()]


@pytest.mark.filterwarnings("ignore:overflow encountered:RuntimeWarning")  # the overflow is the case
def test_a_month_outside_the_two_compared_that_overflows_is_refused() -> None:
    # May (not compared: August against July) holds two sales of 1e308.
    rows = ROWS + [("2026-05-10", "O6", "Cy", "A1", "Mug", "1", "1e308"),
                   ("2026-05-11", "O7", "Cy", "A1", "Mug", "1", "1e308")]
    with pytest.raises(ValidationError) as caught:
        _metrics(rows)
    assert all(TOO_LARGE_TO_ADD in message for message in _messages(caught.value))


def test_every_number_the_file_carries_must_be_one_json_can_carry() -> None:
    written = _metrics().model_dump(mode="python")
    assert written["core"]["revenue_by_month"][0]["revenue"] == pytest.approx(10.0)
    written["core"]["revenue_by_month"][0]["revenue"] = math.inf
    with pytest.raises(ValidationError) as caught:
        MetricsContract.model_validate(written)
    [message] = _messages(caught.value)
    assert TOO_LARGE_TO_ADD in message and "core.revenue_by_month[0].revenue" in message


@pytest.mark.filterwarnings("ignore:overflow encountered:RuntimeWarning")  # the overflow is the case
def test_a_negative_overflow_alone_is_refused() -> None:
    # Two returns of -1e308 in May, outside the two compared: -inf alone
    # (review cycle 3 #6).
    rows = ROWS + [("2026-05-10", "O6", "Cy", "A1", "Mug", "-1", "1e308"),
                   ("2026-05-11", "O7", "Cy", "A1", "Mug", "-1", "1e308")]
    with pytest.raises(ValidationError) as caught:
        _metrics(rows)
    messages = _messages(caught.value)
    assert all(TOO_LARGE_TO_ADD in message for message in messages) and "(-inf)" in " ".join(messages)


def test_a_number_that_is_not_a_number_is_refused_as_too_large_to_add() -> None:
    written = _metrics().model_dump(mode="python")
    written["customers"]["segments"][0]["avg_monetary"] = math.nan
    with pytest.raises(ValidationError) as caught:
        MetricsContract.model_validate(written)
    [message] = _messages(caught.value)
    assert TOO_LARGE_TO_ADD in message and "customers.segments[0].avg_monetary" in message


@pytest.mark.filterwarnings("ignore:overflow encountered:RuntimeWarning")  # the overflow is the case
@pytest.mark.filterwarnings("ignore:invalid value encountered:RuntimeWarning")  # inf - inf
def test_an_overflow_that_leaves_only_a_nan_is_too_large_to_add() -> None:
    # May, outside the two compared: Xa's money sums to +inf, Yu's to -inf, the
    # month's own running total stays finite (20); one segment holds both, so
    # its average is inf + (-inf) = NaN and no infinity is left in the file.
    rows = ROWS + [("2026-05-10", "O6", "Xa", "A1", "Mug", "1", "1e308"),
                   ("2026-05-10", "O7", "Yu", "B1", "Plate", "-1", "1e308"),
                   ("2026-05-11", "O8", "Xa", "A1", "Mug", "1", "1e308"),
                   ("2026-05-11", "O9", "Yu", "B1", "Plate", "-1", "1e308"),
                   ("2026-05-12", "O10", "Yu", "B1", "Plate", "1", "10"),
                   ("2026-05-12", "O11", "Yu", "B1", "Plate", "1", "10")]
    with pytest.raises(ValidationError) as caught:
        _metrics(rows)
    assert all(TOO_LARGE_TO_ADD in message for message in _messages(caught.value))


def test_a_file_of_an_older_major_is_told_its_major_first() -> None:
    written = _metrics().model_dump(mode="json")
    written["schema_version"] = "15.0"
    del written["core"]["identity"]
    with pytest.raises(ValidationError) as caught:
        MetricsContract.model_validate(written)
    messages = " ".join(_messages(caught.value))
    assert "unsupported major version '15.0'" in messages
    assert "before the line taxonomy's blocks" not in messages


def test_a_file_of_a_newer_major_is_not_told_to_re_analyse() -> None:
    written = _metrics().model_dump(mode="json")
    written["schema_version"] = "17.0"
    del written["core"]["identity"]
    with pytest.raises(ValidationError) as caught:
        MetricsContract.model_validate(written)
    messages = " ".join(_messages(caught.value))
    assert "unsupported major version '17.0'" in messages
    assert "re-analyse" not in messages


def test_the_current_major_without_the_blocks_is_still_refused_as_stale() -> None:
    written = _metrics().model_dump(mode="json")
    del written["core"]["identity"]
    with pytest.raises(ValidationError) as caught:
        MetricsContract.model_validate(written)
    assert "before the line taxonomy's blocks" in " ".join(_messages(caught.value))
