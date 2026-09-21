"""Re-validating the plan the user submits (stages/ingest/plan_validation.py,
docs/SPECS.md sections 5 and 10: INVALID_PLAN).

The plan the AI proposed was checked once, but the user may have edited it since,
and nothing the client sends is trusted: the plan is checked again against the
catalog, the legality matrix and the mapping rules before anything runs.
"""

from typing import Any

import pytest

from contracts.cleaning import CleaningPlanContract
from stages.ingest.plan_validation import InvalidPlanError, validate_final_plan
from tests.stages.ingest.cleaning_fixtures import SOURCE_COLUMNS, dataset_action, make_plan


def problems(plan: CleaningPlanContract, *, for_execution: bool = True) -> list[str]:
    with pytest.raises(InvalidPlanError) as caught:
        validate_final_plan(plan, SOURCE_COLUMNS, for_execution=for_execution)
    return caught.value.problems


def edited(plan: CleaningPlanContract, name: str, **changes: Any) -> CleaningPlanContract:
    """The plan with one column's entry changed, as a user's edit would."""
    columns = [{**a.model_dump(), **changes} if a.source_name == name else a.model_dump()
               for a in plan.column_actions]
    return CleaningPlanContract.model_validate({
        **plan.model_dump(), "source": "user_edited", "column_actions": columns})


# --- a good plan -------------------------------------------------------------


def test_a_good_plan_passes_for_execution_and_for_preview() -> None:
    validate_final_plan(make_plan(), SOURCE_COLUMNS, for_execution=True)
    validate_final_plan(make_plan(), SOURCE_COLUMNS, for_execution=False)


def test_invalid_plan_carries_its_code_and_every_reason() -> None:
    plan = edited(edited(make_plan(), "qty", action="impute_median"), "name", action="impute_mode")

    with pytest.raises(InvalidPlanError) as caught:
        validate_final_plan(plan, SOURCE_COLUMNS, for_execution=True)

    assert caught.value.code == "INVALID_PLAN"
    assert len(caught.value.problems) == 2
    assert isinstance(caught.value, ValueError)


# --- an edit after the proposal is checked like the proposal was -----------------------


def test_an_edit_to_an_illegal_action_is_rejected_although_the_proposal_was_legal() -> None:
    proposal = make_plan()
    validate_final_plan(proposal, SOURCE_COLUMNS, for_execution=True)  # what the AI proposed

    found = problems(edited(proposal, "qty", action="impute_median", params={}))

    assert any("column 'qty': impute_median is not legal for quantity, a required field" in p
               for p in found)


def test_the_plans_own_semantic_type_governs_not_the_ais() -> None:
    # The user retyped price as text; impute_median (numeric only) no longer fits.
    found = problems(edited(make_plan(), "price", semantic_type="text"))

    assert any("column 'price': impute_median is not legal for a text column" in p for p in found)


def test_a_user_who_remaps_a_column_to_a_required_field_gets_the_required_field_rule() -> None:
    found = problems(edited(make_plan(), "price", canonical_field="product_name", semantic_type="text",
                            action="impute_mode", params={}))
    found = [p for p in found if "column 'price'" in p]

    assert found and "impute_mode is not legal for product_name, a required field" in found[0]


def test_an_action_outside_the_catalog_never_reaches_the_validator() -> None:
    # The contract's own type is the whitelist: it cannot even be constructed.
    with pytest.raises(ValueError):
        CleaningPlanContract.model_validate({
            **make_plan().model_dump(),
            "column_actions": [{**make_plan().column_actions[0].model_dump(), "action": "rm_rf"}]})


def test_params_are_validated_again() -> None:
    found = problems(edited(make_plan(), "name", action="normalize_case", params={}))

    assert any("column 'name': normalize_case needs the param ['mode']" in p for p in found)


def test_alternatives_are_never_executed_so_stale_ones_do_not_reject_the_plan() -> None:
    # The user changed the action; the alternatives the AI listed for the old one
    # may be illegal for the new type. They only fill a dropdown.
    validate_final_plan(edited(make_plan(), "qty", alternatives=["impute_median", "impute_mode"]),
                        SOURCE_COLUMNS, for_execution=True)


# --- every source column exactly once ------------------------------------------------------


def test_a_column_left_out_is_named() -> None:
    plan = make_plan()
    short = CleaningPlanContract.model_validate({
        **plan.model_dump(),
        "column_actions": [a.model_dump() for a in plan.column_actions if a.source_name != "price"]})

    assert "columns missing from the plan: ['price']" in problems(short)


def test_an_unknown_column_and_a_repeated_column_are_named() -> None:
    plan = make_plan()
    entries = [a.model_dump() for a in plan.column_actions]
    entries += [{**entries[0], "source_name": "ghost"}, {**entries[1]}]
    bad = CleaningPlanContract.model_validate({**plan.model_dump(), "column_actions": entries})

    found = problems(bad)

    assert "columns not in the file: ['ghost']" in found
    assert f"columns planned more than once: ['{entries[1]['source_name']}']" in found


def test_names_are_matched_exactly_the_user_submits_the_files_names() -> None:
    # No tidying here (the AI's near-misses are forgiven at proposal time only).
    found = problems(edited(make_plan(), "qty", source_name=" qty "))

    assert "columns missing from the plan: ['qty']" in found


# --- the dataset actions ---------------------------------------------------------------------


def test_a_column_action_at_dataset_level_is_rejected() -> None:
    found = problems(make_plan(dataset_actions=[dataset_action("trim_whitespace")]))

    assert "dataset action: trim_whitespace applies to a column, not to the dataset" in found


def test_a_dataset_action_listed_twice_is_rejected() -> None:
    found = problems(make_plan(dataset_actions=[
        dataset_action("remove_exact_duplicates"), dataset_action("remove_exact_duplicates")]))

    assert "dataset action remove_exact_duplicates listed more than once" in found


def test_flag_duplicate_keys_may_use_any_columns_of_the_file_not_only_the_default_key() -> None:
    # The AI's proposal had to use the business key; the user is the final authority.
    validate_final_plan(
        make_plan(dataset_actions=[dataset_action("flag_duplicate_keys", params={"keys": ["name"]})]),
        SOURCE_COLUMNS, for_execution=True)


def test_flag_duplicate_keys_on_a_column_that_is_not_in_the_file_is_rejected() -> None:
    found = problems(make_plan(dataset_actions=[
        dataset_action("flag_duplicate_keys", params={"keys": ["sku", "ghost"]})]))

    assert "dataset action flag_duplicate_keys: keys not in the file: ['ghost']" in found


def test_flag_duplicate_keys_on_a_column_the_plan_drops_is_rejected() -> None:
    plan = edited(make_plan(dataset_actions=[
        dataset_action("flag_duplicate_keys", params={"keys": ["sku", "day"]})]),
        "sku", action="drop_column", params={})

    found = problems(plan)

    assert "dataset action flag_duplicate_keys: key columns ['sku'] are dropped by this plan" in found


def test_flag_duplicate_keys_needs_its_keys() -> None:
    found = problems(make_plan(dataset_actions=[dataset_action("flag_duplicate_keys", params={})]))

    assert any("needs the param ['keys']" in p for p in found)


# --- the mapping rules (SPECS section 5) ---------------------------------------------------------


def test_two_columns_on_one_canonical_field_are_rejected_but_ignore_may_repeat() -> None:
    doubled = edited(make_plan(), "price", canonical_field="quantity")

    assert any("canonical field quantity is mapped by more than one column" in p
               for p in problems(doubled))
    validate_final_plan(edited(edited(make_plan(), "price", canonical_field="ignore"),
                               "sku", canonical_field="ignore"), SOURCE_COLUMNS, for_execution=True)


@pytest.mark.parametrize("field", ["product_name", "transaction_date", "quantity"])
def test_execution_needs_every_required_field_mapped(field: str) -> None:
    unmapped = make_plan()
    entries = [{**a.model_dump(), **({"canonical_field": "ignore"} if a.canonical_field == field else {})}
               for a in unmapped.column_actions]
    plan = CleaningPlanContract.model_validate({**unmapped.model_dump(), "column_actions": entries})

    assert any(f"required field {field} is not mapped to any column" in p for p in problems(plan))
    # Previewing while the user is still mapping is fine.
    validate_final_plan(plan, SOURCE_COLUMNS, for_execution=False)


def test_execution_rejects_dropping_a_column_mapped_to_a_required_field() -> None:
    plan = edited(make_plan(), "qty", action="drop_column", params={})

    found = problems(plan)

    assert any("column 'qty' is mapped to the required field quantity but the plan drops it" in p
               for p in found)
    validate_final_plan(plan, SOURCE_COLUMNS, for_execution=False)  # preview may still show it


def test_dropping_an_ordinary_column_is_fine() -> None:
    validate_final_plan(edited(make_plan(), "price", action="drop_column", params={}),
                        SOURCE_COLUMNS, for_execution=True)


# --- hostile input -------------------------------------------------------------------------------


def test_a_huge_column_name_is_shortened_in_the_message() -> None:
    plan = make_plan()
    entries = [a.model_dump() for a in plan.column_actions] + [
        {**plan.column_actions[0].model_dump(), "source_name": "x" * 5000}]
    bad = CleaningPlanContract.model_validate({**plan.model_dump(), "column_actions": entries})

    assert all(len(p) < 300 for p in problems(bad))


def test_the_plan_source_does_not_matter_only_its_content() -> None:
    for source in ("ai", "user_edited", "manual"):
        validate_final_plan(
            CleaningPlanContract.model_validate({**make_plan().model_dump(), "source": source}),
            SOURCE_COLUMNS, for_execution=True)
