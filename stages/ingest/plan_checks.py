"""The checks a cleaning-plan answer must pass before it is trusted (stage 1,
AI step B; docs/AI_PIPELINE.md section 11).

Split out of `ai_plan.py`, which reads the inputs, calls the AI and writes the
contract. Everything here is pure: an answer and the columns in, a ValueError
naming every problem out.

The answer models take actions as plain strings on purpose. Typing them with the
catalog's `Literal` would make the schema layer reject an off-catalog name
before any other check ran, and the run has a single retry: a rejection that
named one mistake of three would spend it and fail on the other two. So every
problem is collected here and sent back together.
"""

from collections import Counter
from collections.abc import Sequence
from typing import Any, cast

from pydantic import BaseModel, Field, ValidationInfo, field_validator

from contracts.cleaning import TransformAction
from contracts.profile import CanonicalField, ColumnInference, SemanticType
from stages.ingest.ai_schema import resolve_name
from stages.ingest.issue_counts import business_key_columns
from stages.ingest.transform_catalog import illegality_reason
from stages.ingest.transform_params import params_problem

MAX_ALTERNATIVES = 2  # prompts/cleaning_plan.md

# The retry message. shared/ai_client keeps 4000 characters of a rejection, and
# the run has one retry, so everything wrong has to fit: what the AI chose (a
# name, an action) is shortened where it is echoed, every line is capped, and a
# message that still does not fit says how many problems it left out.
_MESSAGE_BUDGET = 3500  # below ai_client._MAX_ERROR_CHARS (a test pins the relation)
_TAIL_RESERVE = 40  # room for "... and N more problems"
_LINE_CHARS = 300
_NAME_CHARS = 60
_LISTED_CHARS = 200  # a list of column names in one line shows this much, then a count
_SHOWN_ACTION_CHARS = 40  # longer than any catalog name, so it is garbage anyway
# The retry prompt keeps the original one, where every column carries its
# "legal_actions"; saying so once is enough (repeating each column's list on
# every line is what used to push columns past the cut).
_HINT = (
    "Choose every action and alternative from that column's legal_actions, and dataset "
    "actions from dataset_legal_actions, as given in the schema-inference result."
)


class DatasetActionAnswer(BaseModel):
    """`params`, `rationale` and `alternatives` default when the AI omits them or
    sends null (a common slip on a flag_only column). A missing key would
    otherwise be a schema error, and the schema layer reports only itself: the
    run's single retry would go to that one omission while an illegal action
    elsewhere in the same answer was never mentioned. With a default,
    `check_plan` sees the whole plan: an empty rationale is rejected there, and
    missing params are caught by `params_problem` when the action needs them."""

    action: str
    params: dict[str, Any] = Field(default_factory=dict)
    rationale: str = ""
    alternatives: list[str] = Field(default_factory=list)

    @field_validator("params", "rationale", "alternatives", mode="before")
    @classmethod
    def _null_is_none_given(cls, value: Any, info: ValidationInfo) -> Any:
        empty = {"params": dict, "rationale": str, "alternatives": list}
        return empty[cast(str, info.field_name)]() if value is None else value


class ColumnActionAnswer(DatasetActionAnswer):
    source_name: str


class CleaningPlanAnswer(BaseModel):
    """What the AI returns: the plan without the header fields (ours to set)
    and without each column's type and mapping (the schema step's). An omitted
    list is an empty one: `check_plan` then names every column as missing."""

    dataset_actions: list[DatasetActionAnswer] = Field(default_factory=list)
    column_actions: list[ColumnActionAnswer] = Field(default_factory=list)

    @field_validator("dataset_actions", "column_actions", mode="before")
    @classmethod
    def _null_is_an_empty_list(cls, value: Any) -> Any:
        return [] if value is None else value


def check_plan(answer: CleaningPlanAnswer, columns: Sequence[ColumnInference]) -> None:
    """Stage checks the schema alone cannot express: every column planned once,
    every action and alternative in the catalog and legal for its column (the
    matrix in transform_catalog.py, not a second copy of it), params the action
    can run with, and dataset actions that stay dataset actions. Raising
    ValueError sends every reason back to the AI for the one retry."""
    names = [c.source_name for c in columns]
    by_name = {c.source_name: c for c in columns}
    resolved = [resolve_name(a.source_name, names) for a in answer.column_actions]
    seen = Counter(resolved)
    problems: list[str] = []
    missing = _listed([n for n in names if n not in seen])
    unknown = _listed(sorted(
        a.source_name for a, name in zip(answer.column_actions, resolved, strict=True)
        if name is None
    ))
    repeated = _listed(sorted(n for n, t in seen.items() if n is not None and t > 1))
    if missing:
        problems.append(f"columns missing: {missing}")
    if unknown:
        problems.append(f"columns unknown: {unknown}")
    if repeated:
        problems.append(f"columns listed more than once: {repeated}")
    # drop_column runs first in the fixed order, so a dataset action cannot
    # rely on a column this plan removes.
    dropped = {
        name for planned, name in zip(answer.column_actions, resolved, strict=True)
        if name is not None and planned.action == "drop_column"
    }
    # The dataset problems come before the column ones: there are few of them,
    # and the long column list is what gets cut when something has to be.
    problems += _dataset_problems(answer.dataset_actions, business_key_columns(columns), dropped)
    for planned, name in zip(answer.column_actions, resolved, strict=True):
        if name is not None:
            problems += _column_problems(planned, by_name[name])
    if problems:
        raise ValueError(_report(problems))


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _listed(names: list[str]) -> list[str]:
    """The first names that fit in `_LISTED_CHARS`, each shortened, and how many
    are left out: a line cut at the line limit would drop the rest (and any
    count after them) without saying so."""
    shown: list[str] = []
    used = 0
    for name in names:
        clipped = _clip(name, _NAME_CHARS)
        if shown and used + len(clipped) + 4 > _LISTED_CHARS:  # 4 = quotes, comma, space
            break
        shown.append(clipped)
        used += len(clipped) + 4
    if len(shown) < len(names):
        shown.append(f"... and {len(names) - len(shown)} more")
    return shown


def _report(problems: list[str]) -> str:
    """Every problem in one message that fits what the client keeps."""
    lines = [_HINT]
    used = len(_HINT)
    for index, problem in enumerate(problems):
        line = _clip(problem, _LINE_CHARS)
        room = _MESSAGE_BUDGET if index == len(problems) - 1 else _MESSAGE_BUDGET - _TAIL_RESERVE
        if used + len(line) + 1 > room:
            lines.append(f"... and {len(problems) - index} more problems")
            break
        lines.append(line)
        used += len(line) + 1
    # The last line of defence for the same reason as `_illegality`: whatever a
    # check echoed, the retry prompt must be encodable.
    return "\n".join(lines).encode("utf-8", "backslashreplace").decode("utf-8")


def _column_problems(planned: ColumnActionAnswer, column: ColumnInference) -> list[str]:
    label = f"column {_clip(column.source_name, _NAME_CHARS)!r}"
    semantic_type, field = column.semantic_type, column.canonical_field
    problems: list[str] = []
    reason = _illegality(planned.action, semantic_type, field)
    if reason is not None:
        problems.append(f"{label}: {reason}")
    elif problem := params_problem(cast(TransformAction, planned.action), planned.params):
        # Only for a legal action: an illegal one has one clear reason already.
        problems.append(f"{label}: {problem}")
    problems += _alternative_problems(
        label, planned.action, planned.alternatives, semantic_type, field)
    if not planned.rationale.strip():
        problems.append(f"{label}: rationale is empty")
    return problems


def _dataset_problems(
    actions: list[DatasetActionAnswer], key: list[str], dropped: set[str]
) -> list[str]:
    problems: list[str] = []
    listed: set[str] = set()
    for planned in actions:
        reason = _illegality(planned.action, None, None)
        if reason is not None:
            problems.append(f"dataset action: {reason}")
            continue
        label = f"dataset action {planned.action}"
        if planned.action in listed:
            # Two flag_duplicate_keys would write the same flag column twice.
            problems.append(f"{label} listed more than once")
        listed.add(planned.action)
        if problem := params_problem(cast(TransformAction, planned.action), planned.params):
            problems.append(f"{label}: {problem}")
        if planned.action == "flag_duplicate_keys":
            # Whatever else is wrong with the params: a missing key is a problem
            # of its own, and reporting it later would cost a second retry.
            problems += _key_problems(label, planned.params.get("keys"), key, dropped)
        # flag_duplicate_keys cannot run without a key, so it is no alternative either.
        unavailable = frozenset() if key else frozenset({"flag_duplicate_keys"})
        problems += _alternative_problems(
            label, planned.action, planned.alternatives, None, None, unavailable)
        if not planned.rationale.strip():
            problems.append(f"{label}: rationale is empty")
    return problems


def _key_problems(
    label: str, keys: Any, business_key: list[str], dropped: set[str]
) -> list[str]:
    """The count reported for `duplicate_business_key` and the rows this action
    flags must describe the same key, or the review screen would show two
    different numbers for one thing. The key columns must also survive the
    plan's own drop_column, which runs first."""
    if not business_key:
        # The AI cannot change the mapping (the schema step decided it), so the
        # only fix on offer is to leave the action out.
        return [f"{label}: the file has no business key (no sku or product_name column and "
                f"transaction_date column are both mapped); do not propose flag_duplicate_keys"]
    if not (isinstance(keys, list) and all(isinstance(key, str) for key in keys)):
        return []  # `params_problem` already says what is wrong with them
    problems: list[str] = []
    if set(keys) != set(business_key):
        shown = [_clip(key, _NAME_CHARS) for key in keys[:10]]
        problems.append(f"{label}: keys must be the business key "
                        f"{[_clip(k, _NAME_CHARS) for k in business_key]}, got {shown}")
    gone = [_clip(key, _NAME_CHARS) for key in keys if key in dropped]
    if gone:
        problems.append(f"{label}: key columns {gone} are dropped by this plan (drop_column)")
    return problems


def _alternative_problems(
    label: str,
    action: str,
    alternatives: list[str],
    semantic_type: SemanticType | None,
    field: CanonicalField | None,
    unavailable: frozenset[str] = frozenset(),
) -> list[str]:
    problems: list[str] = []
    # Counted after tidying: a repeat or the chosen action itself is dropped when
    # the contract is written (`tidy_alternatives`), so it must not cost the run's retry.
    distinct = tidy_alternatives(action, alternatives)
    if len(distinct) > MAX_ALTERNATIVES:
        problems.append(f"{label}: {len(distinct)} alternatives, at most {MAX_ALTERNATIVES}")
    for alternative in distinct:
        reason = _illegality(alternative, semantic_type, field)
        if reason is not None:
            problems.append(f"{label}: alternative {reason}")
        elif alternative in unavailable:
            problems.append(
                f"{label}: alternative {alternative} needs a business key, and the file has none")
    return problems


def _illegality(
    action: str, semantic_type: SemanticType | None, field: CanonicalField | None
) -> str | None:
    """`illegality_reason` for a name the AI chose. The catalog check is its
    first step, so an unknown name is reported ("not in the transform
    catalog"), never looked up; the cast only satisfies the type checker."""
    # Escaped, then shortened. A lone surrogate is valid JSON but cannot be
    # encoded as UTF-8, so echoing it raw made the retry request raise
    # UnicodeEncodeError (not an AIUnavailable: no degraded path), and a newline
    # would put text the AI chose on a line of its own in the retry prompt. A
    # catalog name is plain ASCII and passes through unchanged.
    escaped = action.encode("unicode_escape").decode("ascii")
    limit = _SHOWN_ACTION_CHARS
    shown = escaped if len(escaped) <= limit else escaped[: limit - 3] + "..."
    return illegality_reason(cast(TransformAction, shown), semantic_type, field)


def tidy_alternatives(action: str, alternatives: list[str]) -> list[str]:
    """An alternative is another choice: the chosen action and repeats are not
    (a dropdown offering "fix_negative" twice, or the action it already
    shows). Tidied, not rejected, so it costs no retry."""
    return [a for a in dict.fromkeys(alternatives) if a != action]
