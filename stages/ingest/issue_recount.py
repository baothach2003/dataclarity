"""Replace the AI's issue counts with pandas' (PROJECT_PLAN 1D handover, 1E).

CLAUDE.md 3.2: every number comes from a tested pandas function. For the codes
in `issue_counts.COMPUTED_*` the AI's `count` is an estimate from at most 30
sample rows, so it is overwritten; the AI keeps the judgement (which issues are
worth reporting, how severe). The three codes `profile.json` measures were
already checked equal in `ai_schema.check_answer` and are left alone.

Three rules, decided by Thach in 1E:
* No retry on a difference. The AI has no figure to copy for these codes, so a
  mismatch is expected, not an error, and the run's single retry stays free for
  a broken answer.
* A count of 0 removes the issue: a badge saying "0 negative values" is noise.
* `pct` is never filled in here. Only a percentage the profile holds is legal
  (CONTRACTS.md section 3), and leaving the rest null means a replaced count
  can never contradict a stale percentage.

Both dataset issues get their `detail` rewritten from the figures: the AI's
sentence can quote another number than the one now beside it (its own estimate
for `duplicate_business_key`, a different count for `duplicate_rows`), and it
goes to the review screen and into the plan prompt. Only the AI's severity is
kept.

An impossible count (more than the file's rows or cells) is still rejected
before this runs, by `ai_schema.check_answer`; that is a confused answer, not a
difference between an estimate and the truth (accepted trade-off: it can spend
the run's one retry on a number pandas would have overwritten anyway).

An issue at a level its code cannot describe (`duplicate_rows` under a column,
`negative_values` on the dataset) or repeated for the same column is dropped
too: it has no source for its number, and keeping it would let an AI figure
into the contract.
"""

import logging
from dataclasses import dataclass

import pandas as pd

from contracts.profile import ColumnInference, ColumnIssue, DatasetIssue, IssueCode
from stages.ingest.issue_counts import (
    COMPUTED_COLUMN_CODES,
    COMPUTED_DATASET_CODES,
    business_key_columns,
    count_column_issue,
    count_duplicate_business_key,
)
from stages.ingest.transform_catalog import TEXTUAL_TYPES

logger = logging.getLogger(__name__)

# The levels each code can be reported at. A profile-measured code is here too:
# it is kept as `check_answer` left it.
_COLUMN_LEVEL_CODES: frozenset[IssueCode] = COMPUTED_COLUMN_CODES | {
    "missing_values", "all_null_column"}
_DATASET_LEVEL_CODES: frozenset[IssueCode] = COMPUTED_DATASET_CODES | {"duplicate_rows"}
# near_duplicate_labels ignores punctuation, which is right for "Coca-Cola" and
# "coca cola" and wrong for a number: "-2" and "2" are not one label (the 1E run
# on real data counted exactly that in a quantity column). So it is only reported
# for text and categorical columns (decided by Thach in 1F). An identifier, a date
# and a boolean are outside it too, by the same decision.
_NEAR_DUPLICATE_TYPES = TEXTUAL_TYPES


@dataclass(frozen=True)
class RecountStats:
    replaced: int  # issues whose count differed from the AI's and was overwritten
    dropped: int  # issues removed: nothing found, wrong level, or repeated


def recount_issues(
    columns: list[ColumnInference], dataset_issues: list[DatasetIssue], frame: pd.DataFrame
) -> tuple[list[ColumnInference], list[DatasetIssue], RecountStats]:
    """The same columns and dataset issues with every computable count taken
    from `frame`. `frame` is the raw file, so each figure describes the file as
    uploaded, before any cleaning. The inputs are not modified."""
    replaced = dropped = 0
    recounted: list[ColumnInference] = []
    for column in columns:
        issues: list[ColumnIssue] = []
        seen: set[IssueCode] = set()
        for issue in column.issues:
            if issue.code in seen or issue.code not in _COLUMN_LEVEL_CODES:
                dropped += 1
                continue
            near = issue.code == "near_duplicate_labels"
            if near and column.semantic_type not in _NEAR_DUPLICATE_TYPES:
                dropped += 1
                continue
            seen.add(issue.code)
            if issue.code in COMPUTED_COLUMN_CODES:
                count = count_column_issue(issue.code, frame[column.source_name])
                if count == 0:
                    dropped += 1
                    continue
                if count != issue.count:
                    replaced += 1
                    issue = issue.model_copy(update={"count": count})
            elif issue.count == 0:
                # A figure the profile holds, equal to it, and 0 ("0 missing
                # values"): true, and nothing to show on the review screen.
                dropped += 1
                continue
            issues.append(issue)
        recounted.append(column.model_copy(update={"issues": issues}) if issues != column.issues
                         else column)

    keys = business_key_columns(columns)
    dataset: list[DatasetIssue] = []
    seen_dataset: set[IssueCode] = set()
    for dataset_issue in dataset_issues:
        if dataset_issue.code in seen_dataset or dataset_issue.code not in _DATASET_LEVEL_CODES:
            dropped += 1
            continue
        seen_dataset.add(dataset_issue.code)
        if dataset_issue.code not in COMPUTED_DATASET_CODES and dataset_issue.count == 0:
            dropped += 1  # duplicate_rows equal to the profile, and 0
            continue
        if dataset_issue.code == "duplicate_rows":
            # Equal to the profile (checked), but the AI's sentence can quote
            # another figure ("12 exact duplicate rows" beside a 1).
            dataset_issue = dataset_issue.model_copy(update={
                "detail": f"{dataset_issue.count} rows are exact copies of an earlier row"})
        if dataset_issue.code in COMPUTED_DATASET_CODES:
            count = count_duplicate_business_key(frame, keys)
            if count == 0:
                dropped += 1
                continue
            if count != dataset_issue.count:
                replaced += 1
            # The description is rewritten even when the count was right: the
            # AI's sentence may quote another figure, and two numbers for one
            # thing would reach the review screen and the plan prompt.
            dataset_issue = dataset_issue.model_copy(update={
                "count": count,
                "detail": f"{count} rows share their {', '.join(keys)} key with another row",
            })
        dataset.append(dataset_issue)

    # Only counts: nothing here may hold a cell value (AI_PIPELINE section 3).
    logger.info("issue_recount replaced=%d dropped=%d", replaced, dropped)
    return recounted, dataset, RecountStats(replaced=replaced, dropped=dropped)
