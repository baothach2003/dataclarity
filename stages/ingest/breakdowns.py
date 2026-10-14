"""The dashboard's sales breakdowns, stage 1's part (Thach's D4, 2026-10-14;
docs/DASHBOARD_DESIGN.md section 5; method C:/Users/Happy/dashboard-step4-method.txt).

Code decides which columns COULD split sales (`eligible_columns`, from
profile.json - computed on the whole raw file, the AI's bounded input - and
the plan as the user edited it); the AI only chooses up to two of them
(`suggest_breakdowns`), once per run, with no retry: its answer is column
names from that list, validated, and anything else is no suggestion
(suppress, never fabricate). The user decides in Review (CLAUDE.md 3.3);
execute checks the answer again (`breakdowns_problem`)."""

import json
import re
import unicodedata
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from pydantic import ValidationError

from contracts.breakdowns import BreakdownAnswer, BreakdownQuestion, BreakdownSuggestion, EligibleColumn
from contracts.cleaning import CleaningPlanContract
from contracts.metrics import MAX_BREAKDOWN_VALUES, MAX_BREAKDOWNS
from contracts.profile import ColumnProfile, ProfileContract
from shared.ai_client import AIClient, AIUnavailable, RetryBudget
from shared.contract_files import write_atomically
from shared.dates import as_dates
from shared.run_registry import run_file
from stages.ingest.ai_input import _cut

SCHEMA_VERSION = "1.0"
PROMPT = "breakdowns"
MAX_TOKENS = 300  # two column names in JSON
# "Few blanks" (D4): at most this share of the file's rows blank (design D-3).
MAX_BLANK_PCT = 10.0
MIN_VALUES = 2
# The AI sees at most this many columns, in the file's order: with each column's
# at most 10 values, each cut to AI_PIPELINE section 1's 100 characters, the
# input stays bounded on a wide export (the step 4 review #1).
MAX_AI_COLUMNS = 12
SPLIT_TYPES = frozenset({"categorical_nominal", "categorical_ordinal", "boolean", "text"})
_UNNAMED = re.compile(r"^Unnamed: \d+$")
_NUMERIC_DTYPE = re.compile(r"^(u?int|float|Int|Float|UInt)")
# A value that is a number however it is dressed (the step 4 review #3): a
# sign, a currency sign or code, brackets for a negative, separators, a percent
# or a short unit ("$4.50", "4,50 EUR", "(1.00)", "10%", "1kg", "1 pc"). Any
# such value makes the column an amount or a measure, never a category - a
# doubtful column is not offered (Thach's detector principle).
_NUMBER_LIKE = re.compile(
    r"^[(+\-]?\s*(?:[A-Z]{3}\s+|Rs\.?\s*)?[+\-]?\s*[$€£¥₫₹]?\s*[+\-]?\d[\d.,' ]*"
    r"\s*(?:%|[^\W\d_]{1,3}\.?)?\s*\)?$")
# A period written as text: a quarter, a half, a week ("Q1", "2024-Q1",
# "2024-W01") or a month's name. Two compared months split by a period are
# not a split (the step 4 review #7).
_PERIOD_LIKE = re.compile(
    r"^(?:\d{4}\s*[-/ ]?\s*)?(?:Q[1-4]|H[12]|W\d{1,2})(?:\s*[-/ ]?\s*\d{2,4})?$"
    r"|^(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?"
    r"|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?(?:\s*[-/ ]?\s*\d{2,4})?$",
    re.IGNORECASE)

NOT_ANALYSED = "This file is not analysed as sales data, so sales are not split."
MESSAGES = {
    "chosen": "Suggested from your file's columns. Change or remove them; at most two.",
    "none_chosen": "No column was suggested. You can pick up to two from the list.",
    "none_eligible": ("No column of your file can split sales: each needs 2 to 12 values and few blanks, and "
                      "must not be a date, an amount, an id or a field already used."),
    "ai_unavailable": "No suggestion could be made. You can pick up to two from the list.",
}


def _is_number_like(value: str) -> bool:
    """A number however dressed: the pattern above, after a Unicode minus is
    read as "-", or any digit beside a currency sign ("R$ 4,90", "US$4.90" -
    Unicode's Sc class, the scoped review's R2)."""
    text = value.strip().replace("\u2212", "-")
    if _NUMBER_LIKE.match(text):
        return True
    return any(ch.isdigit() for ch in text) and any(unicodedata.category(ch) == "Sc" for ch in text)


def _any_number(values: Iterable[str]) -> bool:
    return any(_is_number_like(value) for value in values)


def _any_date(values: Iterable[str]) -> bool:
    """Any value a date by the shared reading of dates (CLAUDE.md 3.1), or a
    period written as text."""
    listed = [value.strip() for value in values]
    if any(_PERIOD_LIKE.match(value) for value in listed):
        return True
    return bool(listed) and bool(as_dates(pd.Series(listed, dtype="object")).notna().any())


def why_not_eligible(profile: ColumnProfile | None, plan: CleaningPlanContract, name: str) -> str | None:
    """None when the column can split sales; else why not (Review's hint and
    execute's refusal say it)."""
    action = next((a for a in plan.column_actions if a.source_name == name), None)
    if action is None or profile is None:
        return "it is not one of the file's profiled columns"
    if action.action == "drop_column":
        return "the plan drops it"
    if action.canonical_field != "ignore":
        return "the plan already uses it as a field"
    if not name.strip() or _UNNAMED.match(name):
        return "it has no header"
    if action.semantic_type not in SPLIT_TYPES:
        return "it is not a column of categories"
    if not MIN_VALUES <= profile.unique_count <= MAX_BREAKDOWN_VALUES:
        return f"it needs {MIN_VALUES} to {MAX_BREAKDOWN_VALUES} values"
    if profile.null_pct > MAX_BLANK_PCT:
        return "too many of its cells are blank"
    top = [value.value for value in profile.top_values]
    if _NUMERIC_DTYPE.match(profile.dtype) or profile.number_format is not None or _any_number(top):
        return "its values are numbers"
    if profile.date_order is not None or _any_date(top):
        return "its values are dates"
    return None


def eligible_columns(profile: ProfileContract, plan: CleaningPlanContract) -> list[EligibleColumn]:
    """The columns that can split sales, in the file's order (design 5.1)."""
    found = []
    for column in profile.columns:
        if why_not_eligible(column, plan, column.name) is None:
            # Each value cut as the AI's input cuts it: Review shows what the AI sees.
            found.append(EligibleColumn(column=column.name, values=[_cut(value.value) for value in column.top_values]))
    return found


def check_answer(answer: BreakdownAnswer, names: list[str]) -> None:
    """The AI's names are the list's, each once (ValueError: an invalid answer)."""
    unknown = [name for name in answer.breakdowns if name not in names]
    if unknown:
        raise ValueError(f"{len(unknown)} name(s) are not in the list")
    if len(set(answer.breakdowns)) != len(answer.breakdowns):
        raise ValueError("a name is chosen twice")


def suggest_breakdowns(make_client: Callable[[], AIClient], model: str, eligible: list[EligibleColumn],
                       now: datetime | None = None) -> BreakdownSuggestion:
    """The AI's choice, asked once - no retry (the run's shared retry stays for
    the schema and the plan). Any failure is no suggestion, never a guess. With
    no eligible column the AI is not asked (no client is even built). It sees
    the first MAX_AI_COLUMNS eligible columns and chooses among them."""
    eligible = eligible[:MAX_AI_COLUMNS]
    names = [column.column for column in eligible]
    stamp = {"schema_version": SCHEMA_VERSION, "generated_at": now or datetime.now(UTC), "eligible": names}
    if not names:
        return BreakdownSuggestion(**stamp, chosen=[], status="none_eligible", model_used=None)
    variables = {"columns": json.dumps({"columns": [c.model_dump() for c in eligible]}, ensure_ascii=False)}
    try:
        answer = make_client().call_structured(PROMPT, variables, BreakdownAnswer, model, MAX_TOKENS,
                                        RetryBudget(remaining=0), validate=lambda a: check_answer(a, names))
    except AIUnavailable:
        return BreakdownSuggestion(**stamp, chosen=[], status="ai_unavailable", model_used=None)
    return BreakdownSuggestion(**stamp, chosen=list(answer.value.breakdowns), status="chosen",
                               model_used=answer.model)


def question(suggestion: BreakdownSuggestion, eligible: list[EligibleColumn]) -> BreakdownQuestion:
    """What Review shows for the plan as it stands: the suggestion's columns
    still eligible, and where they came from."""
    names = [column.column for column in eligible]
    suggested = [name for name in suggestion.chosen if name in names]
    if not eligible:
        status, message = "none_eligible", MESSAGES["none_eligible"]
    elif suggestion.status == "ai_unavailable":
        status, message = "ai_unavailable", MESSAGES["ai_unavailable"]
    else:
        status, message = "chosen", MESSAGES["chosen" if suggested else "none_chosen"]
    return BreakdownQuestion(eligible=eligible, suggested=suggested, status=status, message=message)


def read_profile(runs_root: Path, run_id: str) -> ProfileContract:
    return ProfileContract.model_validate_json(
        run_file(runs_root, run_id, ProfileContract.filename or "profile.json").read_text(encoding="utf-8"))


def run_suggestion(runs_root: Path, run_id: str, eligible: list[EligibleColumn],
                   ask: Callable[[list[EligibleColumn]], BreakdownSuggestion]) -> BreakdownSuggestion:
    """The run's suggestion: the stored one, or - the first time a column is
    eligible - the AI's (`ask`), stored whatever it answered: the AI is asked
    once per run. Nothing is stored while nothing is eligible, so a later edit
    that makes a column eligible still asks (the step 4 review #4). A stored
    file this version cannot read is no suggestion, never a second call. The
    caller runs this one ask at a time per run (the step 4 review #5)."""
    path = run_file(runs_root, run_id, BreakdownSuggestion.filename or "")
    if path.exists():
        try:
            return BreakdownSuggestion.model_validate_json(path.read_text(encoding="utf-8"))
        except (ValidationError, ValueError, OSError):
            names = [column.column for column in eligible]
            return BreakdownSuggestion(schema_version=SCHEMA_VERSION, generated_at=datetime.now(UTC), eligible=names,
                                       chosen=[], status="ai_unavailable" if names else "none_eligible",
                                       model_used=None)
    suggestion = ask(eligible)
    if eligible:
        write_atomically(path, suggestion.model_dump_json(indent=2).encode("utf-8"))
    return suggestion


def breakdown_question_run(runs_root: Path, run_id: str, plan: CleaningPlanContract,
                           suggestion_for: Callable[[list[EligibleColumn]], BreakdownSuggestion]) -> BreakdownQuestion:
    """Review's breakdown control for the plan as edited: the eligible columns
    and the run's suggestion (`suggestion_for`, normally `run_suggestion`)."""
    eligible = eligible_columns(read_profile(runs_root, run_id), plan)
    return question(suggestion_for(eligible), eligible)


def breakdowns_problem(profile: ProfileContract, plan: CleaningPlanContract) -> str | None:
    """Execute's check of the user's answer (the plan is the user's: refused,
    never silently changed): at most two, each once, each still eligible."""
    names = plan.breakdowns
    if not names:
        return None
    if len(names) > MAX_BREAKDOWNS:
        return f"sales can be split by {MAX_BREAKDOWNS} columns at most"
    if len(set(names)) != len(names):
        return "a column is chosen twice to split sales"
    by_name = {column.name: column for column in profile.columns}
    for name in names:
        why = why_not_eligible(by_name.get(name), plan, name)
        if why is not None:
            return f'column "{name}" cannot split sales: {why}'
    return None
