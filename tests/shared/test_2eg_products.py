"""Session 2E-g (Thach), shared product identity, written before the change:
one module (shared/products.py) keys and names products for stage 2's
tables and stage 3's product lens alike.

- Key: the SKU when the line has one, else the name; NaN when it has
  neither - the data gap, "(no product name)", never a product.
- L4: a name-only line takes the SKU when its name, as carried by SALE lines
  that have a SKU, maps to exactly one SKU.
- Label: the name the product's sale lines carry most often, over the whole
  file, a tie going to the most recent sale - so a product has one label in
  both periods. With no named sale line, the most common name on any line,
  else the SKU. A name shared by several products shows each one's SKU.
- A product name is read as a reader sees it (`product_text`): composed,
  invisible characters removed, spaces as one. PRODUCTS ONLY (Thach, option
  A): customers, categories, order ids and stage 1 read text exactly as
  before 2E-g - widening the shared rules reached every other reader, and one
  widening merged two visibly different customer ids.
"""

import pandas as pd

from shared.products import GAP_LABEL, product_keys, product_labels, product_text
from shared.text import customer_identity, is_blank, normalize_text
from shared.transactions import parse_transactions

MAPPING = {"Date": "transaction_date", "Qty": "quantity", "Price": "unit_price",
           "Product": "product_name", "Sku": "sku"}


def _frame(rows, mapping=MAPPING):
    df = pd.DataFrame(rows, columns=["Date", "Qty", "Price", "Product", "Sku"])
    return df, parse_transactions(df, mapping)


def _keys(rows, mapping=MAPPING):
    df, parsed = _frame(rows, mapping)
    return product_keys(df, parsed)


def _labels(rows, mapping=MAPPING):
    df, parsed = _frame(rows, mapping)
    keys = product_keys(df, parsed)
    return keys, product_labels(df, parsed, keys)


def test_a_line_with_a_sku_and_no_name_is_its_sku() -> None:
    keys = _keys([("2026-08-01", "1", "10", None, "M1"), ("2026-08-01", "1", "10", "Mug", "M1")])

    assert keys.tolist() == ["sku:m1", "sku:m1"]


def test_a_line_with_neither_is_the_gap() -> None:
    keys = _keys([("2026-08-01", "1", "10", "  ", None), ("2026-08-01", "1", "10", None, " ")])

    assert keys.isna().all()


def test_a_name_only_line_takes_the_one_sku_its_name_is_sold_under() -> None:
    """L4: "Mug" is sold under M1 only, so a name-only "mug " line is M1."""
    keys = _keys([("2026-08-01", "1", "10", "Mug", "M1"), ("2026-08-02", "-1", "10", "mug ", None)])

    assert keys.tolist() == ["sku:m1", "sku:m1"]


def test_a_name_sold_under_two_skus_stays_a_name() -> None:
    keys = _keys([("2026-08-01", "1", "10", "Mug", "M1"), ("2026-08-01", "1", "10", "Mug", "M2"),
                  ("2026-08-02", "1", "10", "Mug", None)])

    assert keys.tolist() == ["sku:m1", "sku:m2", "name:mug"]


def test_l4_reads_sale_lines_only() -> None:
    """A stock note "damaged" written on one SKU's write-off (-1 at 0) must
    not pull every "damaged" line to that SKU."""
    keys = _keys([("2026-08-01", "-1", "0", "damaged", "M1"), ("2026-08-02", "-1", "0", "damaged", None)])

    assert keys.tolist() == ["sku:m1", "name:damaged"]


def test_the_label_is_the_name_sale_lines_carry_most() -> None:
    """Online Retail II's renamings: 20665 was first written "RED SPOTTY
    PURSE" (on a write-off) and sold as "RED RETROSPOT PURSE"."""
    keys, labels = _labels([("2026-06-01", "-1", "0", "RED SPOTTY PURSE", "20665"),
                            ("2026-06-02", "1", "5", "RED RETROSPOT PURSE", "20665"),
                            ("2026-07-02", "1", "5", "RED RETROSPOT PURSE", "20665"),
                            ("2026-08-02", "1", "5", "RED SPOTTY PURSE", "20665")])

    assert labels["sku:20665"] == "RED RETROSPOT PURSE"


def test_a_tie_goes_to_the_most_recent_sale() -> None:
    keys, labels = _labels([("2026-06-01", "1", "5", "Old name", "S1"),
                            ("2026-08-01", "1", "5", "New name", "S1")])

    assert labels["sku:s1"] == "New name"


def test_a_stock_note_on_non_sale_lines_is_not_the_label() -> None:
    keys, labels = _labels([("2026-06-01", "-3", "0", "Damaged", "S1"),
                            ("2026-06-01", "-1", "0", "Damaged", "S1"),
                            ("2026-06-02", "1", "5", "Lamp", "S1")])

    assert labels["sku:s1"] == "Lamp"


def test_with_no_named_sale_line_the_label_is_the_commonest_name_else_the_sku() -> None:
    keys, labels = _labels([("2026-06-01", "-1", "0", "given away", "S1"),
                            ("2026-06-01", "1", "5", None, "S2")])

    assert (labels["sku:s1"], labels["sku:s2"]) == ("given away", "S2")


def test_a_name_shared_by_two_skus_shows_each_sku() -> None:
    """Online Retail II: 21171 and 82580 are both BATHROOM METAL SIGN."""
    keys, labels = _labels([("2026-06-01", "1", "5", "BATHROOM METAL SIGN", "21171"),
                            ("2026-06-01", "1", "5", "BATHROOM METAL SIGN", "82580"),
                            ("2026-06-01", "1", "5", "Lamp", "L1")])

    assert (labels["sku:21171"], labels["sku:82580"], labels["sku:l1"]) == (
        "BATHROOM METAL SIGN (21171)", "BATHROOM METAL SIGN (82580)", "Lamp")


def test_labels_that_differ_only_in_case_show_their_skus() -> None:
    """"Mug" under S1 and "MUG" under S2 read as one name to a reader."""
    keys, labels = _labels([("2026-06-01", "1", "5", "Mug", "S1"), ("2026-06-01", "1", "5", "MUG", "S2")])

    assert (labels["sku:s1"], labels["sku:s2"]) == ("Mug (S1)", "MUG (S2)")


def test_a_real_product_named_like_the_gap_is_told_apart() -> None:
    keys, labels = _labels([("2026-06-01", "1", "5", GAP_LABEL, "Z9")])

    assert labels["sku:z9"] == f"{GAP_LABEL} (Z9)"


def test_an_empty_file_has_no_products_and_no_labels() -> None:
    """Edge case: the empty frame crashed `product_keys` ("name:" + a float
    series) until its columns were read as objects."""
    keys, labels = _labels([])

    assert (len(keys), len(labels)) == (0, 0)


def test_a_file_without_a_sku_column_labels_by_name() -> None:
    keys, labels = _labels([("2026-08-01", "1", "10", "Mug", None)],
                           {k: v for k, v in MAPPING.items() if v != "sku"})

    assert labels.to_dict() == {"name:mug": "Mug"}


def test_a_real_product_named_like_the_gap_with_no_sku_is_told_apart() -> None:
    """2E-g doubt-review F2: with no SKU to append, it kept the bare gap
    label, and the report seemed to rank the gap."""
    keys, labels = _labels([("2026-06-01", "1", "5", GAP_LABEL, None)],
                           {k: v for k, v in MAPPING.items() if v != "sku"})

    assert labels.iloc[0] != GAP_LABEL
    assert labels.iloc[0].startswith(GAP_LABEL)


def test_every_format_character_is_invisible() -> None:
    """2E-g doubt-review F3: a left-to-right mark, a soft hyphen, a Hangul
    filler and their kind still made a gap line a product with an empty
    label - the top product and the biggest decliner."""
    marks = ["\u200e", "\u200f", "\u00ad", "\u3164", "\u2063", "\u180e", "\u202c", "\u2061"]

    assert product_text(pd.Series(marks)).isna().all()


def test_case_folding_is_full() -> None:
    """2E-g doubt-review F6: "Maßband" and "MASSBAND" are one product."""
    keys = _keys([("2026-08-01", "1", "10", "Maßband", None), ("2026-08-01", "1", "10", "MASSBAND", None)])

    assert keys.nunique() == 1


def test_whitespace_inside_a_name_does_not_split_a_product() -> None:
    """2E-g doubt-review F7: "RED MUG", "RED  MUG" and "RED\\u00a0MUG" are one
    product - and read alike, so they are one label too."""
    keys = _keys([("2026-08-01", "1", "10", "RED MUG", None),
                  ("2026-08-01", "1", "10", "RED  MUG", None),
                  ("2026-08-01", "1", "10", "RED MUG", None)])

    assert keys.nunique() == 1


def test_two_skus_whose_names_differ_only_in_spacing_show_their_skus() -> None:
    """The labels are read as products are (spaces as one), so both show
    "RED MUG" and each gets its SKU."""
    keys, labels = _labels([("2026-06-01", "1", "5", "RED MUG", "A1"),
                            ("2026-06-01", "1", "5", "RED\u00a0MUG", "B2")])

    assert (labels["sku:a1"], labels["sku:b2"]) == ("RED MUG (A1)", "RED MUG (B2)")


def test_composed_and_decomposed_text_is_one_product() -> None:
    """2E-g doubt-review cycle 2, F3: "Cà phê sữa" typed composed in July and
    decomposed (macOS exports) in August was both a top seller and the
    biggest decliner."""
    import unicodedata

    decomposed = unicodedata.normalize("NFD", "Cà phê sữa")
    keys = _keys([("2026-07-01", "1", "10", "Cà phê sữa", None), ("2026-08-01", "1", "10", decomposed, None)])

    assert keys.nunique() == 1


def test_a_suffixed_label_never_collides_with_another() -> None:
    """2E-g doubt-review cycle 2, F6: a name-only "MUG (S1)" and SKU S1's
    "MUG" suffixed to "MUG (S1)" read as one product with both sums."""
    keys, labels = _labels([("2026-06-01", "1", "5", "MUG (S1)", None),
                            ("2026-06-01", "1", "5", "MUG", "S1"),
                            ("2026-06-01", "1", "5", "MUG", "S2")])

    assert labels.is_unique
    assert labels.str.casefold().is_unique


def test_braille_and_tag_blanks_are_blank() -> None:
    """2E-g doubt-review cycle 2, F8: a braille blank made a top product
    with a label that looks empty."""
    blanks = pd.Series(["\u2800", "\U000e0020", "\ufff9", "\U0001d173"])

    assert product_text(blanks).isna().all()


def test_customers_categories_and_blanks_read_exactly_as_before_2eg() -> None:
    """Option A (Thach): the shared helpers are HEAD's - strip and lower-case,
    nothing else - so no product rule reaches a customer, a category, an order
    id or stage 1. "Weiss" and "Wei\u00df" stay two customers, a zero-width
    space stays part of a customer id, composition is left alone. One text
    reading for every stage is its own session."""
    import unicodedata

    decomposed = unicodedata.normalize("NFD", "Nguy\u1ec5n")
    values = pd.Series([" Weiss ", "Wei\u00df", "An\u200b", decomposed, "\u200b"])

    assert customer_identity(values).tolist() == [
        "weiss", "wei\u00df", "an\u200b", decomposed.lower(), "\u200b"]
    assert normalize_text(values).tolist() == customer_identity(values).tolist()
    assert is_blank(values).tolist() == [False, False, False, False, False]


def test_an_invisible_character_inside_a_name_does_not_split_a_product() -> None:
    """2E-g doubt-review cycle 3 F5: "RED\u200bMUG" and "REDMUG" read alike and
    were two products (or two labels that look the same)."""
    keys = _keys([("2026-08-01", "1", "10", "REDMUG", None),
                  ("2026-08-01", "1", "10", "RED\u200bMUG", None),
                  ("2026-08-01", "1", "10", "MUG\u00adHOLDER", None),
                  ("2026-08-01", "1", "10", "MUGHOLDER", None)])

    assert keys.nunique() == 2


def test_a_joiner_inside_a_name_is_kept() -> None:
    """The zero-width non-joiner changes how a Persian word renders: two names."""
    keys = _keys([("2026-08-01", "1", "10", "\u0645\u0647\u200c\u062f\u06cc", None),
                  ("2026-08-01", "1", "10", "\u0645\u0647\u062f\u06cc", None)])

    assert keys.nunique() == 2


def test_invisible_characters_are_no_product_name() -> None:
    """A zero-width space or a BOM is not a name: such a line is the gap."""
    values = pd.Series(["\u200b", "\ufeff ", " \u200b \ufeff", "Mug\u200b"])

    assert product_text(values).isna().tolist() == [True, True, True, False]
    assert _keys([("2026-08-01", "1", "10", "\u200b", None)]).isna().all()


def test_invisible_characters_do_not_split_a_product() -> None:
    keys = _keys([("2026-08-01", "1", "10", "Mug​", None), ("2026-08-01", "1", "10", "Mug", None)])

    assert keys.nunique() == 1
