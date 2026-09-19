from datetime import UTC, datetime

import pytest

from contracts import ProfileContract
from stages.ingest.profiling import profile_csv

NOW = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)

# 4 data rows x 3 columns; row 2 repeats row 1; one qty and one price missing.
SMALL = b"sku,qty,price\nA1,3,9.99\nA1,3,9.99\nB2,,12.50\nC3,5,\n"


def test_dataset_stats_are_hand_checked() -> None:
    profile = profile_csv(SMALL, now=NOW)

    assert profile.dataset.rows == 4
    assert profile.dataset.columns == 3
    assert profile.dataset.duplicate_rows == 1
    assert profile.dataset.missing_cells_pct == pytest.approx(2 / 12 * 100)  # 16.67
    assert profile.dataset.encoding_used == "utf-8"
    assert profile.dataset.delimiter == ","


def test_columns_keep_file_order_and_carry_their_stats() -> None:
    profile = profile_csv(SMALL, now=NOW)

    assert [c.name for c in profile.columns] == ["sku", "qty", "price"]
    qty = profile.columns[1]
    assert qty.dtype == "float64"
    assert qty.mean == pytest.approx(11 / 3)  # (3 + 3 + 5) / 3
    assert qty.median == 3.0
    assert profile.columns[0].dtype == "str"
    assert profile.columns[0].mean is None


def test_header_fields_of_the_contract() -> None:
    profile = profile_csv(SMALL, now=NOW)

    assert profile.schema_version == "1.0"
    assert profile.generated_at == NOW


def test_a_row_with_the_same_missing_cells_is_still_a_duplicate() -> None:
    profile = profile_csv(b"sku,qty\nA1,\nA1,\nB2,4\n", now=NOW)

    assert profile.dataset.duplicate_rows == 1


def test_latin1_fallback_is_recorded_for_the_cleaning_report() -> None:
    # SPECS section 10 wants a warning; profile.json has no warnings field, so it
    # records the encoding and 1F turns it into cleaning_report.warnings.
    profile = profile_csv(b"sku,name\nA1,Caf\xe9\n", now=NOW)

    assert profile.dataset.encoding_used == "latin-1"
    assert profile.columns[1].top_values[0].value == "Café"


def test_one_data_row_file() -> None:
    profile = profile_csv(b"sku,qty\nA1,7\n", now=NOW)

    assert profile.dataset.rows == 1
    assert profile.dataset.duplicate_rows == 0
    assert profile.columns[1].q1 == profile.columns[1].q3 == 7.0


def test_all_null_column_counts_toward_missing_cells() -> None:
    profile = profile_csv(b"sku,note\nA1,\nB2,\n", now=NOW)

    assert profile.dataset.missing_cells_pct == 50.0  # 2 of 4 cells
    assert profile.columns[1].null_pct == 100.0


def test_output_is_a_valid_contract_that_survives_json() -> None:
    profile = profile_csv(SMALL, now=NOW)

    assert ProfileContract.model_validate_json(profile.model_dump_json()) == profile
