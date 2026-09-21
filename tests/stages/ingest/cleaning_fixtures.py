"""Shared builders for the cleaning tests (validation, execute, preview)."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from contracts import CleaningPlanContract
from contracts.cleaning import ColumnAction, DatasetAction
from shared.run_registry import create_run
from stages.ingest.profiling import profile_run

NOW = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)

# (semantic_type, canonical_field) of each source column, as the user left them.
COLUMN_TYPES: dict[str, tuple[str, str]] = {
    "sku": ("identifier", "sku"),
    "name": ("text", "product_name"),
    "qty": ("numeric_discrete", "quantity"),
    "price": ("numeric_continuous", "unit_price"),
    "day": ("datetime", "transaction_date"),
}
SOURCE_COLUMNS = list(COLUMN_TYPES)

# Five data rows; every expected result in the tests is worked out by hand:
#   row 1 and row 3 are the same row, padded name included (an exact duplicate);
#   row 2 has a negative quantity, a missing price and a day-first slash date;
#   row 4 has no name and no problem with anything else;
#   row 5 has a date that is not a date.
RAW_CSV = (
    "sku,name,qty,price,day\n"
    "A1, Mug ,3,9.99,2024-01-05\n"
    "B2,Cup,-1,,15/01/2024\n"
    "A1, Mug ,3,9.99,2024-01-05\n"
    "C3,,5,12.50,2024-01-07\n"
    "D4,Plate,4,7.00,not a date\n"
).encode()


def column_action(
    name: str,
    action: str = "flag_only",
    params: dict[str, Any] | None = None,
    **overrides: Any,
) -> ColumnAction:
    semantic_type, canonical_field = COLUMN_TYPES[name]
    entry: dict[str, Any] = {
        "source_name": name, "semantic_type": semantic_type, "canonical_field": canonical_field,
        "action": action, "params": params or {}, "rationale": "chosen by the user",
        "alternatives": [], "edited_by_user": True,
    }
    entry.update(overrides)
    return ColumnAction.model_validate(entry)


def dataset_action(action: str, params: dict[str, Any] | None = None) -> DatasetAction:
    return DatasetAction.model_validate({
        "action": action, "params": params or {}, "rationale": "chosen by the user",
        "alternatives": [], "edited_by_user": True,
    })


def default_column_actions() -> list[ColumnAction]:
    return [
        column_action("sku", "trim_whitespace"),
        column_action("name", "trim_whitespace"),
        column_action("qty", "fix_negative", {"strategy": "flag"}),
        column_action("price", "impute_median"),
        column_action("day", "parse_datetime"),
    ]


def make_plan(
    column_actions: list[ColumnAction] | None = None,
    dataset_actions: list[DatasetAction] | None = None,
    source: str = "user_edited",
) -> CleaningPlanContract:
    return CleaningPlanContract(
        schema_version="1.0", generated_at=NOW, source=source,  # type: ignore[arg-type]  # a plain str for the Literal, checked by pydantic
        dataset_actions=dataset_actions or [],
        column_actions=column_actions if column_actions is not None else default_column_actions(),
    )


def raw_run(runs_root: Path, csv: bytes = RAW_CSV) -> str:
    """A run with raw.csv and profile.json on disk."""
    run = create_run(runs_root)
    (run.path / "raw.csv").write_bytes(csv)
    profile_run(runs_root, run.run_id, now=NOW)
    return run.run_id
