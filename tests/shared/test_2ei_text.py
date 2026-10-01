"""Session 2E-i (Thach, after 2E-g: one text reading for every stage), written
before the change.

Two questions, two readings (shared/text.py):
- Is a cell EMPTY? Nothing visible - the same for every column: a cell of
  only whitespace or format characters that draw nothing renders as nothing.
- Are two cells the SAME value? These differences a reader cannot see merge
  (others still split - 2E-o Q5 #7):
  Unicode composition, the characters that render as nothing AND change
  nothing around them (zero-width space, word joiner, BOM, soft hyphen, the
  invisible operators), a no-break space for a space - and the direction
  marks (a known, rare cost). Never the direction overrides and isolates, the
  joiners or the variation selectors (they can change what is shown - 2E-g
  review cycle 3 F7), never full case folding ("Weiss" and
  "Weiss" with a sharp s are two people).

Every special character is built with chr(): a literal one would be invisible
in this file.
"""

import unicodedata
from datetime import date

import pandas as pd

from contracts.cleaning import OrderConfirmations
from shared.text import category_key, customer_identity, is_blank
from shared.transactions import is_stock_in, order_ids, parse_transactions
from stages.analyze.assemble import assemble_metrics
from stages.diagnose.bridge import compute_bridge
from stages.diagnose.members import category_totals
from stages.ingest import transforms
from tests.stages.diagnose.diagnose_fixtures import MAPPING, NOW, row, run_data

ZWSP, WJ, BOM, SHY, LRM, RLO, ZWNJ, VS16, NBSP = (
    chr(0x200B), chr(0x2060), chr(0xFEFF), chr(0x00AD), chr(0x200E), chr(0x202E), chr(0x200C),
    chr(0xFE0F), chr(0x00A0))
SHARP_S, HEART, MONGOLIAN_A, FVS1, BRAILLE_BLANK = chr(0xDF), chr(0x2764), chr(0x1820), chr(0x180B), chr(0x2800)
COMPOSED = "Nguy" + chr(0x1EC5) + "n"
DECOMPOSED = unicodedata.normalize("NFD", COMPOSED)


# --- the readings ----------------------------------------------------------------

def test_one_customer_however_invisibly_typed() -> None:
    values = pd.Series([" CUST_01", "cust_01" + ZWSP, BOM + "Cust_01", "CUST" + WJ + "_01",
                        "CUST_" + SHY + "01", COMPOSED, DECOMPOSED, "CUST" + NBSP + "02", "cust 02"])

    identity = customer_identity(values)

    assert identity.tolist()[:5] == ["cust_01"] * 5
    assert identity.iloc[5] == identity.iloc[6] == COMPOSED.lower()
    assert identity.iloc[7] == identity.iloc[8] == "cust 02"


def test_visibly_different_customers_stay_two() -> None:
    persian = chr(0x0645) + chr(0x0647)
    pairs = [("Weiss", "Wei" + SHARP_S),                        # full case folding would merge
             (persian + ZWNJ + chr(0x062F), persian + chr(0x062F)),  # a joiner changes the rendering
             (RLO + "1C", "1C"),                                 # a right-to-left override reverses it
             ("Ann" + HEART + VS16, "Ann" + HEART),              # emoji against text heart
             (MONGOLIAN_A + FVS1, MONGOLIAN_A),                  # a variation selector changes the glyph
             ("CUST  01", "CUST 01")]                            # a double space inside an id stays

    for a, b in pairs:
        assert customer_identity(pd.Series([a, b])).nunique() == 2, (ascii(a), ascii(b))


def test_a_cell_with_nothing_visible_is_blank_in_every_column() -> None:
    values = pd.Series([ZWSP, BOM + LRM, BRAILLE_BLANK, RLO, " " + NBSP + " ", None, " x ", "0"])

    assert is_blank(values).tolist() == [True, True, True, True, True, True, False, False]


def test_numbers_are_never_blank() -> None:
    assert not is_blank(pd.Series(pd.array([1, 2], dtype="Int64"))).any()
    assert is_blank(pd.Series([1.5, None])).tolist() == [False, True]


def test_an_order_id_reads_invisible_characters_away_and_keeps_its_case() -> None:
    df = pd.DataFrame({"Order": ["INV1", "INV1" + ZWSP, "inv1", " INV2 ", ZWSP, None]})

    assert order_ids(df, "Order").tolist()[:4] == ["INV1", "INV1", "inv1", "INV2"]
    assert order_ids(df, "Order").iloc[4:].isna().all()


def test_one_category_however_its_spaces_or_invisible_characters_are_typed() -> None:
    values = pd.Series(["Toys", "Toys" + ZWSP, "toys ", "Home" + NBSP + "Garden", "Home  Garden", "home garden"])

    assert category_key(values).tolist() == ["toys"] * 3 + ["home garden"] * 3


def test_a_stock_receipt_typed_with_an_invisible_character_is_still_in() -> None:
    values = pd.Series(["in", "IN" + ZWSP, BOM + "in", " In ", "inside", None])

    assert is_stock_in(values).tolist() == [True, True, True, True, False, False]


# --- the pipeline -------------------------------------------------------------------

def test_a_trailing_zero_width_space_does_not_make_a_new_and_a_lapsed_customer() -> None:
    # Alice buys 10 on the first and last day of July and August; in August
    # her id carries a trailing zero-width space. Read raw, she lapsed in July
    # and a "new" Alice arrived in August (2E-g review cycle 2).
    rows = [row(date(2026, 7, d), customer="Alice") for d in (1, 31)]
    rows += [row(date(2026, 8, d), customer="Alice" + ZWSP) for d in (1, 31)]
    data = run_data(rows)

    lens = compute_bridge(data)
    assert data.metrics.customers.new_vs_returning.new_customers == 0
    assert (lens.new, lens.lapsed) == (0.0, 0.0)


def test_one_category_in_both_stages_with_one_label() -> None:
    # The first spelling in the file carries a no-break space: both stages show
    # it as a reader sees it, "Home Garden" (review31 f6: stage 2 and stage 3
    # labelled one category differently).
    mapping = {**MAPPING, "Cat": "category"}
    rows = [{**row(date(2026, 7, d)), "Cat": "Home" + NBSP + " Garden"} for d in (1, 31)]
    rows += [{**row(date(2026, 8, d)), "Cat": "Home Garden" + ZWSP} for d in (1, 31)]
    df = pd.DataFrame(rows)

    metrics = assemble_metrics(df, mapping, now=NOW)
    stage2 = [(c.name, c.revenue_previous, c.revenue_current) for c in metrics.by_dimension.category]
    assert stage2 == [("Home Garden", 20.0, 20.0)]
    totals = category_totals(run_data(rows, mapping))
    assert list(totals.rev_prev.index) == list(totals.rev_cur.index) == ["home garden"]
    assert totals.labels["home garden"] == "Home Garden"


def test_the_mix_rate_split_reads_categories_as_the_dimensions_do() -> None:
    from stages.diagnose.mix_rate import _category_keys

    mapping = {**MAPPING, "Cat": "category"}
    rows = [{**row(date(2026, 7, 1)), "Cat": "Toys"}, {**row(date(2026, 8, 31)), "Cat": "Toys" + ZWSP},
            {**row(date(2026, 8, 30)), "Cat": ZWSP}]

    keys = _category_keys(run_data(rows, mapping))

    assert keys.iloc[0] == keys.iloc[1] == "toys"
    assert keys.iloc[2] != "toys"  # nothing visible: the uncategorised bucket


def test_an_invisible_character_does_not_split_one_receipt_into_two_orders() -> None:
    df = pd.DataFrame({"Date": ["2026-03-05"] * 2, "Order": ["INV1", "INV1" + ZWSP],
                       "Cust": ["C1", "C1" + ZWSP], "Name": ["MUG", "PLATE"], "Qty": ["1", "1"],
                       "Price": ["10", "10"]})
    mapping = {"Date": "transaction_date", "Order": "order_id", "Cust": "customer",
               "Name": "product_name", "Qty": "quantity", "Price": "unit_price"}

    # One customer on the receipt: the id is trusted once confirmed as a
    # receipt number in Review (2E-e2).
    parsed = parse_transactions(df, mapping, OrderConfirmations(order_id_is_receipt=True))

    assert parsed.orders_basis == "order_id"
    assert parsed.customers.nunique() == 1
    assert parsed.order_key.nunique() == 1


def test_stage_1_drops_a_name_with_nothing_visible() -> None:
    # 2E-g review cycle 3 F5: stage 1 kept these and stage 2 read them as the
    # "(no product name)" gap the user had asked to drop.
    df = pd.DataFrame({"Name": ["MUG", ZWSP, BOM + LRM, "   "], "Qty": ["1", "1", "1", "1"]})

    kept, entry = transforms.drop_rows_missing(df, "Name", {})

    assert kept["Name"].tolist() == ["MUG"]
    assert entry.detail == ("dropped 3 rows with no Name (1 of them only spaces, 2 only invisible "
                            "characters)")


def test_a_stock_receipt_typed_in_with_a_zero_width_space_is_no_sale() -> None:
    mapping = {**MAPPING, "Type": "transaction_type"}
    rows = [{**row(date(2026, 7, d)), "Type": "out"} for d in (1, 31)]
    rows += [{**row(date(2026, 8, d)), "Type": "out"} for d in (1, 31)]
    rows.append({**row(date(2026, 8, 10), qty=100.0, price=5.0), "Type": "IN" + ZWSP})

    metrics = assemble_metrics(pd.DataFrame(rows), mapping, now=NOW)

    assert metrics.core.revenue_current == 20.0


# --- the contracts ---------------------------------------------------------------------

def test_metrics_json_is_major_13_and_diagnosis_json_major_14_or_the_current_ones() -> None:
    # The same data can group customers, orders and categories differently
    # (CONTRACTS 10: a change of meaning is a major bump, as 2E-g's product
    # reading was). Readers refuse the earlier majors.
    import pytest
    from pydantic import ValidationError

    from contracts.diagnosis import DiagnosisContract
    from contracts.metrics import MetricsContract
    from stages.analyze.assemble import SCHEMA_VERSION
    from tests.contracts.test_diagnosis import diagnosis_payload
    from tests.contracts.test_metrics import metrics_payload

    assert (SCHEMA_VERSION, MetricsContract.supported_major, DiagnosisContract.supported_major) == ("16.1", 16, 18)  # 16.1 in 2E-u6 (additive); 16 / 18 since 3E1b (16 / 17 since 2E-t2, the line taxonomy); 13 / 14 in 2E-i; 14 / 15 in 2E-j; 15 / 16 since 2E-o
    metrics, diagnosis = metrics_payload(), diagnosis_payload()
    assert (metrics["schema_version"], diagnosis["schema_version"]) == ("16.0", "18.0")  # the payload: a 16.0 file reads
    metrics["schema_version"], diagnosis["schema_version"] = "14.0", "15.0"
    with pytest.raises(ValidationError, match="re-analyse"):
        MetricsContract.model_validate(metrics)
    with pytest.raises(ValidationError, match="re-analyse"):
        DiagnosisContract.model_validate(diagnosis)


# --- review cycle 1 ----------------------------------------------------------------------

RLM, ZWJ = chr(0x200F), chr(0x200D)


def test_a_direction_mark_does_not_split_a_value() -> None:
    # Review cycle 1 #1: a trailing RLM made Alice a lapsed and a new
    # customer. Cycle 2 #1: in right-to-left text a stray mark rarely changes
    # the rendering either, and those exports are where marks are typed - a
    # Persian or Hebrew name with a mark split the same way. Removed
    # everywhere, as the products' reading removes them (2E-g); the overrides
    # and isolates, which can reorder, stay (test above).
    assert customer_identity(pd.Series(["Alice", "Alice" + RLM, LRM + "Alice"])).nunique() == 1
    assert category_key(pd.Series(["Home", "Home" + LRM])).nunique() == 1
    hebrew, persian = chr(0x05E9) + chr(0x05DC), chr(0x0645) + chr(0x0647) + chr(0x062F) + chr(0x06CC)
    assert customer_identity(pd.Series([hebrew + "1", hebrew + RLM + "1", LRM + hebrew + "1"])).nunique() == 1
    assert customer_identity(pd.Series([persian, persian + RLM, RLM + persian, persian + LRM])).nunique() == 1
    assert customer_identity(pd.Series([chr(0x06F1) + chr(0x06F2), chr(0x06F1) + chr(0x06F2) + chr(0x061C)])).nunique() == 1


def test_a_cell_of_only_joiners_or_other_format_characters_is_blank() -> None:
    # #2: a lone joiner renders as nothing, like a zero-width space.
    assert is_blank(pd.Series([ZWJ, ZWNJ + ZWSP, chr(0x2066), chr(0x0301)])).tolist() == [True, True, True, False]


def test_only_a_no_break_space_reads_as_a_space() -> None:
    # #3: Python's \s also holds control characters and the wide ideographic
    # space; a Windows-1252 ellipsis read as latin-1 (U+0085) merged "A...B"
    # with "A B". A reader sees a box, a gap of another width, or nothing.
    for other in (chr(0x85), chr(0x1F), chr(0x3000), "\t", chr(0x1680)):
        assert customer_identity(pd.Series(["A" + other + "B", "A B"])).nunique() == 2, ascii(other)
    assert customer_identity(pd.Series(["A" + NBSP + "B", "A B"])).nunique() == 1


def test_an_invisible_character_before_a_combining_mark_still_composes() -> None:
    # #6: removed after composing, "Jose<ZWSP><acute>" stayed decomposed.
    assert customer_identity(pd.Series(["Jose" + ZWSP + chr(0x0301), "Jos" + chr(0xE9)])).nunique() == 1


def test_stage_1_refuses_a_fill_or_label_with_nothing_visible() -> None:
    # #4: the plan checks judged "reads back as missing" with strip alone.
    from stages.ingest.transform_params import params_problem

    for value in (ZWSP, LRM, ZWSP + " "):
        assert "read back as missing" in (params_problem("impute_constant", {"value": value}) or ""), ascii(value)
        assert "read back as missing" in (
            params_problem("standardize_categories", {"mapping": {"a": value}}) or ""), ascii(value)


def test_a_product_name_of_only_a_joiner_is_the_gap_as_stage_1_reads_it() -> None:
    # #2 for products: stage 1's drop reads is_blank; stage 2's key reads
    # product_text - one lone joiner must be nothing in both.
    from shared.text import product_text

    assert product_text(pd.Series([ZWJ, ZWNJ + " ", "A" + ZWJ + "B"])).isna().tolist() == [True, True, False]
    assert is_blank(pd.Series([ZWJ])).tolist() == [True]


# --- review cycle 2 ----------------------------------------------------------------------

def test_a_product_name_composes_after_its_invisible_characters_are_removed() -> None:
    # Cycle 2 #2: product_text removed invisible characters AFTER composing,
    # and "Cafe<ZWSP><acute>" stayed decomposed - another product than "Caf" + e-acute.
    from shared.text import product_text

    assert product_text(pd.Series(["Cafe" + ZWSP + chr(0x0301)])).tolist() == ["Caf" + chr(0xE9)]


def test_a_prepended_concatenation_mark_is_visible_and_a_supplementary_selector_is_not() -> None:
    # Cycle 2 #3: these format characters draw a sign (the Arabic number
    # sign, the end-of-ayah mark...); a variation selector 17-256 draws none.
    from shared.text import product_text

    visible = pd.Series([chr(code) for code in (0x0600, 0x0605, 0x06DD, 0x070F, 0x0890, 0x08E2, 0x110BD)])
    assert not is_blank(visible).any()
    assert product_text(visible).notna().all()
    assert is_blank(pd.Series([chr(0xE0100), chr(0xE01EF)])).all()
