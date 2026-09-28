"""Stage 1's side of the line taxonomy (session 2E-t1; docs/LINE_TAXONOMY.md
section 4): which plans are classed, and the source columns that make way for
cleaned.csv's three class columns. The classifier itself is
`shared/line_taxonomy.py` (2E-t2)."""

from contracts.cleaning import TAXONOMY_COLUMNS, CleaningPlanContract, CleaningWarning


def reserved_renames(columns: list[str], dropped: set[str] = frozenset()) -> dict[str, str]:
    """Source columns already named like one of the three stage 1 adds, and the
    name each takes: `<name>_source`, numbered from 2 while any source column
    has that name (Thach's Q24) - a column the plan drops included, as the
    plan runs on the renamed frame before its drops. A column the plan drops
    is not renamed: nothing of it is written (2E-t1 review cycle 3 #2). The
    data is kept; only its header moves."""
    taken = set(columns)
    renames: dict[str, str] = {}
    for name in TAXONOMY_COLUMNS:
        if name not in taken or name in dropped:
            continue
        new, number = f"{name}_source", 1
        while new in taken:
            number += 1
            new = f"{name}_source_{number}"
        taken.add(new)
        renames[name] = new
    return renames


# What each of stage 1's three columns holds, for the rename's warning.
_HOLDS = {
    "line_class": "each line's class",
    "class_source": "whether the user's answer or a rule decided each line's class",
    "suggested_class": "the class suggested for each line's key and not confirmed",
}


def is_classed(plan: CleaningPlanContract) -> bool:
    """Whether stage 1 writes the three columns for this plan: quantity and
    unit price mapped and kept. Otherwise - generic cleaning (SPECS section
    10), or a file without a price, which stages 2 and 3 cannot read - no line
    is classed and every source name is kept (2E-t1 review cycle 1 #3)."""
    kept = {a.canonical_field for a in plan.column_actions if a.action != "drop_column"}
    return {"quantity", "unit_price"} <= kept


def renamed_plan(plan: CleaningPlanContract, renames: dict[str, str]) -> CleaningPlanContract:
    """The plan as it runs on the renamed frame: the same actions, naming the
    columns as cleaned.csv will hold them - so the run's flags, its change log
    and the mapping carry the new name by themselves, and a flag can never
    take a name the frame already has (2E-t1 review cycle 2 #2-#4)."""
    if not renames:
        return plan
    columns = [a.model_copy(update={"source_name": renames.get(a.source_name, a.source_name)})
               for a in plan.column_actions]
    datasets = [a.model_copy(update={"params": {**a.params, "keys": [renames.get(k, k) for k in a.params["keys"]]}})
                if isinstance(a.params.get("keys"), list) else a for a in plan.dataset_actions]
    return plan.model_copy(update={"column_actions": columns, "dataset_actions": datasets})


def rename_warnings(renames: dict[str, str]) -> list[CleaningWarning]:
    return [CleaningWarning(code="reserved_column_renamed",
                            detail=f"the source column {old!r} is written as {new!r}: cleaned.csv's "
                                   f"{old!r} holds {_HOLDS[old]}")
            for old, new in renames.items()]
