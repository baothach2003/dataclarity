"""The conformance suite, part 2: DF-C amounts and quantities, DF-D line
types (docs/DATA_FAILURE_MODES.md; the rule and the base: test_conformance.py)."""

from pathlib import Path

import pandas as pd
import pytest
from pydantic import ValidationError

from shared.line_words import non_product_candidates
from stages.ingest.issue_counts import count_column_issues
from stages.ingest.profiling import read_csv_text
from tests.data_failures.flow import (CAST_PRICE, FEB, check, diagnosis, metrics, notes, real_flow, sample,
                                      unmeasurable, verdicts)

# --- C. amounts and quantities --------------------------------------------------------------------


@pytest.mark.parametrize("mode,reason", [("DF-C1", "no quantity"), ("DF-C2", "no price"), ("DF-C3", "no price"),
                                         ("DF-C4", "no price"), ("DF-C5", "no price")])
def test_a_number_that_does_not_read_is_counted_nowhere_and_reported(mode: str, reason: str) -> None:
    # Ann's Mug on 2024-02-10 (10.00) leaves revenue and is listed among the
    # lines that cannot be measured.
    found = metrics(sample(mode))
    assert found.core.revenue_current == FEB - 10.0
    assert ("current", reason, 1) in unmeasurable(found)


def test_df_c4b_a_thousands_separator_is_read(tmp_path: Path) -> None:
    """Was a LIMIT, a silent wrong figure (2E-u F1): every Mug line was
    unmeasurable and revenue was Tea's alone, 348.00. Since 2E-u1 "1,000.00"
    proves a decimal point (both marks: the last is the decimal one): February
    is 3 x 1,000.00 x 29 + 3 x 4.00 x 29 = 87,348.00, nothing unmeasurable."""
    found, _ = real_flow(sample("DF-C4B"), tmp_path, CAST_PRICE)
    assert found.core.revenue_current == 87348.0
    assert unmeasurable(found) == set()
    assert notes(found) == {"discounts_in_prices"}


def test_df_c4c_currency_signs_are_stripped(tmp_path: Path) -> None:
    """Was a LIMIT (2E-u F1): "$10.00" everywhere - nothing read, and the run
    blocked saying the export was cut short. Since 2E-u1 stage 1 strips the
    sign (Thach): February 29 x 42.00 = 1,218.00, as the clean file."""
    found, diagnosed = real_flow(sample("DF-C4C"), tmp_path, CAST_PRICE)
    assert (found.core.revenue_current, found.core.revenue_previous) == (1218.0, 1302.0)
    assert diagnosed.headline.rule != 1


def test_df_c4d_a_price_that_reads_two_ways_refuses_the_plan(tmp_path: Path) -> None:
    """2E-u1: every price written "1,000" or "4,000" - nothing in the file
    proves whether those are thousands or decimal commas: the plan is refused
    with the reason, nothing written - never a default either way (Thach)."""
    from stages.ingest.number_apply import NumberQuestionUnanswered

    with pytest.raises(NumberQuestionUnanswered, match="'1,000' is one thousand with a thousands comma"):
        real_flow(sample("DF-C4D"), tmp_path, CAST_PRICE)


def test_df_c4d_answered_the_file_is_read_as_the_user_said(tmp_path: Path) -> None:
    case = sample("DF-C4D")
    # Answered a decimal comma: Mug 1.000, Tea 4.000 - February 3 x 5.00 x 29 = 435.00.
    answered = case.__class__(case.rows, raw=case.raw, answers={"number_formats": {"Price": "decimal_comma"}})
    found, _ = real_flow(answered, tmp_path, CAST_PRICE)
    assert found.core.revenue_current == 435.0


def test_df_c6_an_outlying_price_is_counted_by_stage_1() -> None:
    # Prices 1000, 4, 10, 4, ... : quartiles 4 and 10, fence -5 to 19.
    frame = read_csv_text(sample("DF-C6").raw or b"").frame
    assert count_column_issues(frame["Price"]).get("outliers_iqr") == 1


def test_df_c7_every_price_x100_is_a_trust_caution() -> None:
    found = diagnosis(sample("DF-C7"))
    assert check(found, "D2") == "caution" and verdicts(found)["D2"] == "supported"


def test_known_limit_df_c7b_with_two_products_a_x100_entry_is_headlined_as_a_price_rise() -> None:
    """LIMIT (AI_PIPELINE 7.3, by design): with one or two products there is
    no "uniform" to speak of - D2 is inconclusive, as on any two-product
    file, and the headline names like-for-like prices (1,302.00 to
    121,800.00) as the cause."""
    found = diagnosis(sample("DF-C7B"))
    assert (verdicts(found)["D2"], found.headline.rule, found.headline.hypothesis_id) == ("inconclusive", 6, "P1")


@pytest.mark.filterwarnings("ignore:overflow encountered:RuntimeWarning")
def test_df_c8_amounts_too_large_to_add_are_refused() -> None:
    with pytest.raises(ValidationError, match="too large to add"):
        metrics(sample("DF-C8"))


def test_df_c9_a_refund_at_a_negative_price_is_a_deduction_with_its_note() -> None:
    found = metrics(sample("DF-C9"))
    assert found.core.revenue_current == FEB - 10.0 and "unconfirmed_deductions" in notes(found)


def test_df_c10_a_zero_price_line_moves_no_money() -> None:
    assert metrics(sample("DF-C10")).core.revenue_current == FEB


# --- D. line types -----------------------------------------------------------------------------------


def test_df_d1_return_lines_take_their_money_back() -> None:
    # Two return lines against February's 174 sale lines (no order id: lines).
    found = metrics(sample("DF-D1"))
    assert found.core.revenue_current == FEB - 20.0
    assert found.core.return_rate_current == pytest.approx(2 / 174)


def test_df_d2_a_c_invoice_is_a_return() -> None:
    # One return receipt against February's 87 (one a customer a day).
    found = metrics(sample("DF-D2"))
    assert (found.core.revenue_current, found.core.orders_basis) == (FEB - 10.0, "order_id")
    assert found.core.return_rate_current == pytest.approx(1 / 87)


def test_df_d3_an_unanswered_postage_line_is_suggested_noted_and_stays_a_product(tmp_path: Path) -> None:
    case = sample("DF-D3")
    candidates = non_product_candidates(pd.DataFrame(case.rows), case.mapping) or []
    assert [(c.value, c.suggested) for c in candidates] == [("POSTAGE", "charge")]
    found, _ = real_flow(case, tmp_path)
    assert found.core.revenue_current == FEB + 5.0 and "unconfirmed_suggestions" in notes(found)


@pytest.mark.parametrize("mode,revenue,line_class,where", [
    ("DF-D3B", FEB + 5.0, "charge", "non_product"), ("DF-D4", FEB - 3.0, "discount", "non_product"),
    ("DF-D5", FEB, "cost", "outside"), ("DF-D6", FEB, "adjustment", "outside"),
    ("DF-D8", FEB, "gift_card_sale", "outside")])
def test_an_answered_line_takes_its_class(mode: str, revenue: float, line_class: str, where: str) -> None:
    found = metrics(sample(mode))
    assert found.core.revenue_current == revenue
    listed = found.core.non_product if where == "non_product" else found.core.outside_revenue
    assert line_class in {entry.line_class for entry in listed}


def test_df_d6b_an_unanswered_bad_debt_is_an_unconfirmed_deduction_with_its_note() -> None:
    found = metrics(sample("DF-D6B"))
    assert found.core.revenue_current == FEB - 50.0 and "unconfirmed_deductions" in notes(found)


def test_df_d7_an_answered_pooled_item_is_sold_and_never_ranked() -> None:
    found = metrics(sample("DF-D7"))
    assert found.core.revenue_current == FEB + 12.0
    assert "Manual" not in {p.product for p in found.products.top_products}


def test_df_d9_stock_received_is_outside_revenue_with_its_note() -> None:
    found = metrics(sample("DF-D9"))
    assert found.core.revenue_current == FEB
    assert ("stock_in", "current", 15.0) in {(o.line_class, o.scope, o.amount) for o in found.core.outside_revenue}
    assert "returns_booked_as_in" in notes(found)


def test_known_limit_df_d10_a_type_naming_a_return_on_a_sale_line_is_a_sale() -> None:
    """LIMIT (LINE_TAXONOMY section 0: only "in" is read; review #3): a line
    typed "Return" whose signs say sale counts +10.00, with the
    `other_transaction_types` note beside the figures."""
    found = metrics(sample("DF-D10"))
    assert found.core.revenue_current == FEB + 10.0 and "other_transaction_types" in notes(found)


def test_df_d11_online_retail_iis_fee_shape_unanswered_is_a_return_with_its_note(tmp_path: Path) -> None:
    # Quantity -1 at a positive price: a customer return by its signs, -7.00,
    # flagged as an unconfirmed suggestion.
    found, _ = real_flow(sample("DF-D11"), tmp_path)
    assert found.core.revenue_current == FEB - 7.0 and "unconfirmed_suggestions" in notes(found)


@pytest.mark.parametrize("mode,name", [("DF-D12", "Manual"), ("DF-D13", "Service charge")])
def test_known_limit_an_unsuggested_non_product_is_ranked_without_a_note(mode: str, name: str,
                                                                        tmp_path: Path) -> None:
    """LIMIT (8D "From 2E-d2": missed words; review #3): Online Retail II's
    "Manual" unanswered, "Service charge" - ranked as products, no note."""
    found, _ = real_flow(sample(mode), tmp_path)
    assert name in {p.product for p in found.products.top_products}
    assert "unconfirmed_suggestions" not in notes(found)
