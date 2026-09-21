"""The rows of a frame that show a kind of dirt (missing, duplicated, negative,
text in a column of numbers, padded, an unparseable date).

Shared by the sample the AI is shown (`ai_input.select_sample_rows`) and the sample
the preview shows (`preview.select_sample`), so both pick the rows that make a
plan's effect visible. Split out of `column_kinds.py`, whose detectors it uses, to
keep that file under the 300-line guideline.
"""

from collections.abc import Collection

import pandas as pd

from stages.ingest import column_kinds


def problem_masks(frame: pd.DataFrame, numeric_columns: Collection[str]) -> list[pd.Series]:
    """One mask per kind of dirt worth showing the AI. The kinds match the
    issue codes it is asked to report (`issue_counts.py`), so the sample holds
    an example of what the schema answer has to describe.

    A column is scanned for numbers or for dates only when its head looks that
    way: converting all 25 columns both ways would cost more than the whole
    profiling step.
    """
    nothing = pd.Series(False, index=frame.index)
    negative, non_numeric, whitespace, bad_date = (nothing.copy() for _ in range(4))
    for name in frame.columns:
        values = frame[name]
        whitespace |= column_kinds.whitespace_mask(values)
        if name in numeric_columns or column_kinds.probably_numeric(values):
            negative |= column_kinds.as_numbers(values) < 0
            # Text in a column of numbers: the "n/a" the AI must not average.
            non_numeric |= column_kinds.non_numeric_mask(values)
        elif column_kinds.probably_dates(values):
            bad_date |= column_kinds.invalid_date_mask(values)
    return [
        frame.isna().any(axis=1),
        frame.duplicated(keep=False),
        negative,
        non_numeric,
        whitespace,
        bad_date,
    ]


def first_positions(mask: pd.Series, limit: int) -> list[int]:
    return [int(p) for p in mask.to_numpy().nonzero()[0][:limit]]
