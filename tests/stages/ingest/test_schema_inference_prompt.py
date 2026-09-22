"""prompts/schema_inference.md must keep the transaction_type clarification.

Regression test for a real bug found manually testing the Review UI with real
Kaggle data (2026-09-22): the AI mapped a "Payment Method" column (values
Cash / Credit Card / Digital Wallet) to canonical_field `transaction_type`,
which docs/SPECS.md section 9 defines as stock movement direction (in|out) -
an unrelated concept the field's own name (containing "type" and
"transaction") invites confusing it with. Nothing downstream catches this: the
mapped value is a syntactically ordinary string either way, so a wrong mapping
would silently reach `column_mapping` and, once stage 2 exists, corrupt
`current_stock`. The fix is prompt wording, not a contract or a validation
rule (docs/AI_PIPELINE.md section 5), so the regression test is that the
wording stays in the prompt - a real-API check that the model now defaults such
a column to "ignore" is not part of the suite (CLAUDE.md: never spend real
tokens in tests), but was covered by the same real-API note in AI_PIPELINE
section 5 as a place to reverify if this file's wording ever changes.
"""

import re
from pathlib import Path

PROMPT = (Path(__file__).resolve().parents[3] / "prompts" / "schema_inference.md").read_text(
    encoding="utf-8")


def section(name: str) -> str:
    """The text from a heading line to the next all-caps heading."""
    match = re.search(rf"^{name}[^\n]*\n(.*?)(?=^[A-Z][A-Z ]+(?: \(|$)|\Z)", PROMPT,
                      re.DOTALL | re.MULTILINE)
    assert match, f"no {name} section in the prompt"
    return match.group(1)


def test_the_prompt_has_a_canonical_field_notes_section() -> None:
    notes = section("CANONICAL FIELD NOTES")

    assert "transaction_type" in notes


def test_transaction_type_is_defined_as_stock_movement_direction_only() -> None:
    notes = section("CANONICAL FIELD NOTES")

    assert "stock movement" in notes
    assert '"in"' in notes
    assert '"out"' in notes


def test_the_prompt_rules_out_payment_method_and_sales_channel_by_name() -> None:
    notes = section("CANONICAL FIELD NOTES")

    assert "payment method" in notes.lower()
    assert "sales channel" in notes.lower()


def test_the_prompt_gives_a_concrete_negative_example_mapped_to_ignore() -> None:
    notes = section("CANONICAL FIELD NOTES")

    assert "Payment Method" in notes
    assert re.search(r"Payment Method.{0,200}ignore", notes, re.DOTALL), (
        "the Payment Method example must say it maps to ignore")
