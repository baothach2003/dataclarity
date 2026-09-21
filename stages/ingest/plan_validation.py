"""Re-validating the plan the user submits (docs/SPECS.md sections 5 and 10,
docs/AI_PIPELINE.md section 11).

`plan_checks.check_plan` judges an AI *answer*: it forgives a tidied column name,
requires the business key, and writes a retry message. A plan the user has edited
is judged differently, because the user is the final authority (CLAUDE.md 3.3):

* the plan's own `semantic_type` and `canonical_field` decide what is legal for a
  column, since the user may have changed either;
* `flag_duplicate_keys` may use any columns of the file, not only the default
  business key;
* `alternatives` are never executed, so stale ones (the user changed the action
  they were listed for) do not reject a plan;
* names must match the file exactly.

What stays the same is the whitelist and the legality matrix, which are the shared
`illegality_reason` and `params_problem`, not a second copy. Nothing the client
sends is trusted, and a plan that was valid when the AI proposed it is not assumed
to still be.

Executing also needs what the UI enforces before Confirm (every required field
mapped, and kept); previewing does not, because the preview refreshes while the
user is still mapping columns.
"""

from collections import Counter
from collections.abc import Sequence
from typing import cast

from contracts.cleaning import CleaningPlanContract, TransformAction
from stages.ingest.transform_catalog import REQUIRED_CANONICAL_FIELDS, illegality_reason
from stages.ingest.transform_params import params_problem

_NAME_CHARS = 60
_LISTED_NAMES = 8


class InvalidPlanError(ValueError):
    """The plan cannot run: SPECS section 10, INVALID_PLAN (422), the whole plan
    rejected and never partially applied. `problems` lists every reason."""

    code = "INVALID_PLAN"

    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


def validate_final_plan(
    plan: CleaningPlanContract, source_columns: Sequence[str], *, for_execution: bool
) -> None:
    """Raise InvalidPlanError, naming every problem, unless `plan` can run on a
    file with these columns. `for_execution=False` (the preview) skips the
    required-field rules, which are the Confirm guard."""
    names = list(source_columns)
    planned = Counter(a.source_name for a in plan.column_actions)
    problems: list[str] = []

    missing = [n for n in names if n not in planned]
    unknown = [n for n in planned if n not in names]
    repeated = [n for n, times in planned.items() if times > 1]
    if missing:
        problems.append(f"columns missing from the plan: {_listed(missing)}")
    if unknown:
        problems.append(f"columns not in the file: {_listed(unknown)}")
    if repeated:
        problems.append(f"columns planned more than once: {_listed(repeated)}")

    dropped = {a.source_name for a in plan.column_actions if a.action == "drop_column"}
    problems += _mapping_problems(plan, dropped, for_execution)
    problems += _dataset_problems(plan, names, dropped)
    for column in plan.column_actions:
        label = f"column {_clip(column.source_name)!r}"
        reason = illegality_reason(column.action, column.semantic_type, column.canonical_field)
        if reason is not None:
            problems.append(f"{label}: {reason}")
        elif problem := params_problem(column.action, column.params):
            # Only for a legal action: an illegal one has one clear reason already.
            problems.append(f"{label}: {problem}")
    if problems:
        raise InvalidPlanError(problems)


def _mapping_problems(
    plan: CleaningPlanContract, dropped: set[str], for_execution: bool
) -> list[str]:
    problems: list[str] = []
    mapped: dict[str, list[str]] = {}
    for column in plan.column_actions:
        if column.canonical_field != "ignore":
            mapped.setdefault(column.canonical_field, []).append(column.source_name)
    for field, columns in mapped.items():
        if len(columns) > 1:
            problems.append(
                f"canonical field {field} is mapped by more than one column: {_listed(columns)}")
    if not for_execution:
        return problems
    for field in sorted(REQUIRED_CANONICAL_FIELDS):
        columns = mapped.get(field, [])
        if not columns:
            problems.append(f"required field {field} is not mapped to any column")
        for name in columns:
            if name in dropped:
                # Nothing after stage 1 could read the field, and Confirm is
                # locked until it is mapped (SPECS 4.2).
                problems.append(
                    f"column {_clip(name)!r} is mapped to the required field {field} "
                    f"but the plan drops it")
    return problems


def _dataset_problems(
    plan: CleaningPlanContract, names: list[str], dropped: set[str]
) -> list[str]:
    problems: list[str] = []
    listed: set[str] = set()
    for action in plan.dataset_actions:
        reason = illegality_reason(action.action)
        if reason is not None:
            problems.append(f"dataset action: {reason}")
            continue
        label = f"dataset action {action.action}"
        if action.action in listed:
            # Two flag_duplicate_keys would write the same flag column twice.
            problems.append(f"{label} listed more than once")
        listed.add(action.action)
        if problem := params_problem(cast(TransformAction, action.action), action.params):
            problems.append(f"{label}: {problem}")
        if action.action == "flag_duplicate_keys":
            problems += _key_problems(label, action.params.get("keys"), names, dropped)
    return problems


def _key_problems(label: str, keys: object, names: list[str], dropped: set[str]) -> list[str]:
    if not (isinstance(keys, list) and all(isinstance(key, str) for key in keys)):
        return []  # `params_problem` already says what is wrong with them
    problems: list[str] = []
    absent = [key for key in keys if key not in names]
    if absent:
        problems.append(f"{label}: keys not in the file: {_listed(absent)}")
    gone = [key for key in keys if key in dropped]
    if gone:
        # drop_column runs first (the fixed order), so the key would be gone.
        problems.append(f"{label}: key columns {_listed(gone)} are dropped by this plan")
    return problems


def _clip(text: str) -> str:
    return text if len(text) <= _NAME_CHARS else text[: _NAME_CHARS - 3] + "..."


def _listed(names: Sequence[str]) -> list[str]:
    """The first few names, each shortened, and how many are left out: this goes
    into an error message, and the names are whatever the client sent."""
    shown = [_clip(n) for n in names[:_LISTED_NAMES]]
    if len(names) > _LISTED_NAMES:
        shown.append(f"... and {len(names) - _LISTED_NAMES} more")
    return shown
