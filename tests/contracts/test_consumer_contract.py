"""Session 3G0 (Thach, 2026-09-29): the consumer contract - the fields of
metrics.json and diagnosis.json that stages 4 and 5 and the frontend may
read (docs/CONTRACTS.md section 11; CLAUDE.md 3.7). Written before section
11 existed; widened by 3G0's review (a type's constraints and the JSON key
are part of it; the closed vocabularies consumers decide on are pinned).

One source: section 11's tables. Every row must name a field the models
have, with the type written there (its constraints included: a percentage
turned into a share, or another date format, changes the type); every
vocabulary must equal the code's. The rows and vocabularies as first written
are frozen (`consumer_fields_v1.json`) and must all still be there - an
enum may gain values, never lose one. So what a consumer reads cannot be
renamed, removed or retyped: it changes only additively.
"""

import json
import re
import types
import typing
from pathlib import Path

import annotated_types
import pytest
from pydantic import BaseModel

from contracts.diagnosis import DiagnosisContract
from contracts.lines import NOTE_MEASURES
from contracts.metrics import MetricsContract

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_MD = ROOT / "docs" / "CONTRACTS.md"
FROZEN = Path(__file__).with_name("consumer_fields_v1.json")
MODELS: dict[str, type[BaseModel]] = {"metrics.json": MetricsContract, "diagnosis.json": DiagnosisContract}
READERS = {"4A", "4B", "5", "FE"}
_ROW = re.compile(r"^\| `(?P<path>[^`]+)` \| `(?P<type>(?:[^`\\]|\\.)+)` \| (?P<readers>[^|]+) \|$")
_VOCABULARY = re.compile(r"^\| `(?P<name>[^`]+)` \| (?P<values>.+) \|$")
YEAR_MONTH = r"^\d{4}-(0[1-9]|1[0-2])$"


def _constraint(item: object) -> str:
    """One constraint as section 11 writes it."""
    name = type(item).__name__
    if hasattr(item, "metadata") and name == "FieldInfo":
        return ", ".join(_constraint(inner) for inner in item.metadata)  # type: ignore[attr-defined]  # FieldInfo
    if name == "_PydanticGeneralMetadata":
        pattern = item.__dict__.get("pattern")
        return "YYYY-MM" if pattern == YEAR_MONTH else ", ".join(f"{k}={v}" for k, v in sorted(item.__dict__.items()))
    if name == "AfterValidator":
        return item.func.__name__.lstrip("_")  # type: ignore[attr-defined]  # AfterValidator has func
    fields = getattr(item, "__dataclass_fields__", None)
    if fields:
        return ", ".join(f"{key}={getattr(item, key)}" for key in fields)
    return repr(item)


def _with(base: str, constraints: list[object]) -> str:
    written = [text for text in (_constraint(c) for c in constraints) if text]
    return f"{base} ({', '.join(written)})" if written else base


def render(tp: object) -> str:
    """A field's type as section 11 writes it, its constraints in brackets."""
    origin, args = typing.get_origin(tp), typing.get_args(tp)
    if origin is typing.Annotated:
        return _with(render(args[0]), list(args[1:]))
    if origin in (typing.Union, types.UnionType):
        return " | ".join(render(a) for a in args)
    if origin is typing.Literal:
        return "Literal[" + ", ".join(repr(a) for a in args) + "]"
    if origin is list:
        return f"list[{render(args[0])}]"
    if origin is dict:
        return f"dict[{render(args[0])}, {render(args[1])}]"
    if isinstance(tp, type) and issubclass(tp, BaseModel):
        return "object"
    if tp is type(None):
        return "None"
    return str(getattr(tp, "__name__", tp))


def _nested(tp: object, suffix: str = "") -> typing.Iterator[tuple[type[BaseModel], str]]:
    origin, args = typing.get_origin(tp), typing.get_args(tp)
    if origin is typing.Annotated:
        yield from _nested(args[0], suffix)
    elif origin in (typing.Union, types.UnionType):
        for arg in args:
            yield from _nested(arg, suffix)
    elif origin is list:
        yield from _nested(args[0], suffix + "[]")
    elif origin is dict:
        yield from _nested(args[1], suffix + "{}")
    elif isinstance(tp, type) and issubclass(tp, BaseModel):
        yield tp, suffix


def fields(model: type[BaseModel], prefix: str = "") -> dict[str, str]:
    """Every field path of `model` as the files carry it, with its rendered
    type: `a.b`, `a[].b` for a list's items, `a{}.b` for a dict's values;
    a computed field too (it is written)."""
    found: dict[str, str] = {}
    for name, field in model.model_fields.items():
        path = prefix + name
        found[path] = _with(render(field.annotation), list(field.metadata))
        for inner, suffix in _nested(field.annotation):
            found |= fields(inner, path + suffix + ".")
    for name, computed in model.model_computed_fields.items():
        found[prefix + name] = render(computed.return_type)
    return found


def section_11() -> tuple[dict[str, dict[str, tuple[str, set[str]]]], dict[str, set[str]]]:
    text = CONTRACTS_MD.read_text(encoding="utf-8")
    assert "\n## 11. " in text, "docs/CONTRACTS.md has no section 11 (the consumer contract)"
    body = text.split("\n## 11. ", 1)[1].split("\n## ", 1)[0]
    tables: dict[str, dict[str, tuple[str, set[str]]]] = {}
    vocabularies: dict[str, set[str]] = {}
    current = None
    for line in body.splitlines():
        if line.startswith("#### "):
            current = line[5:].strip()
            if current != "Vocabularies":
                tables[current] = {}
        elif current == "Vocabularies" and (vocabulary := _VOCABULARY.match(line.strip())):
            if vocabulary["name"] != "Vocabulary":
                values = vocabulary["values"].strip()
                vocabularies[vocabulary["name"]] = set() if values == "-" else {
                    v.strip().strip("`") for v in values.split(",")}
        elif current and (row := _ROW.match(line.strip())):
            assert row["path"] not in tables[current], f"{current}: {row['path']} listed twice"
            # A pipe inside a table cell is written `\|` (Markdown).
            rendered = row["type"].replace("\\|", "|")
            tables[current][row["path"]] = (rendered, {r.strip() for r in row["readers"].split(",")})
    return tables, vocabularies


_LITERAL = re.compile(r"Literal\[([^\]]*)\]")


def problems(model: type[BaseModel], rows: dict[str, str]) -> list[str]:
    """What a model breaks of a consumer's rows (path -> type)."""
    have = fields(model)
    found = []
    for path, rendered in rows.items():
        if path not in have:
            found.append(f"{path}: no such field (renamed or removed)")
        elif have[path] != rendered:
            found.append(f"{path}: {have[path]} where the consumer reads {rendered}")
    return found


def _grew_only(before: str, after: str) -> bool:
    """`after` is `before` with values added to its closed enums, wherever
    they sit (bare, in a list, beside None, a dict's values)."""
    if _LITERAL.sub("Literal[]", before) != _LITERAL.sub("Literal[]", after):
        return False
    return all({v.strip() for v in old.split(",")} <= {v.strip() for v in new.split(",")}
               for old, new in zip(_LITERAL.findall(before), _LITERAL.findall(after), strict=True))


def narrowed(frozen: dict[str, str], documented: dict[str, str]) -> list[str]:
    """Frozen rows the documented ones dropped or changed; an enum may only
    have gained values."""
    found = []
    for path, rendered in frozen.items():
        now = documented.get(path)
        if now is None:
            found.append(f"{path}: no longer in the consumer contract")
        elif now != rendered and not _grew_only(rendered, now):
            found.append(f"{path}: {rendered} became {now}")
    return found


def code_vocabularies() -> dict[str, set[str]]:
    """The closed vocabularies consumers decide on, as the code writes them."""
    from stages.analyze.rfm import NEEDS_ATTENTION, NO_PURCHASES, assign_segment
    from stages.diagnose.catalog import CATALOG, NOT_TESTABLE

    found = {"segment": {assign_segment(r, f) for r in range(1, 6) for f in range(1, 6)}
             | {NEEDS_ATTENTION, NO_PURCHASES},
             "hypothesis id": {spec.id for spec in CATALOG},
             "not-testable id": {spec.id for spec in NOT_TESTABLE}}
    for code, names in NOTE_MEASURES.items():
        found[f"measure of {code}"] = set(names) if names is not None else {"(the file's own values)"}
    return found


@pytest.mark.parametrize("name", sorted(MODELS))
def test_every_consumer_field_exists_with_its_type(name: str) -> None:
    rows = section_11()[0][name]
    assert rows, f"section 11 lists no field of {name}"
    assert problems(MODELS[name], {path: rendered for path, (rendered, _) in rows.items()}) == []
    assert all(readers and readers <= READERS for _, readers in rows.values())


@pytest.mark.parametrize("name", sorted(MODELS))
def test_the_consumer_fields_change_only_additively(name: str) -> None:
    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))[name]
    documented = {path: rendered for path, (rendered, _) in section_11()[0][name].items()}
    assert narrowed(frozen, documented) == []


def test_every_vocabulary_is_the_codes_and_only_grows() -> None:
    documented = section_11()[1]
    assert documented == code_vocabularies()
    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))["vocabularies"]
    assert {name: sorted(set(values) - documented.get(name, set())) for name, values in frozen.items()
            if not set(values) <= documented.get(name, set())} == {}


def _models(model: type[BaseModel]) -> typing.Iterator[type[BaseModel]]:
    yield model
    for field in model.model_fields.values():
        for inner, _ in _nested(field.annotation):
            yield from _models(inner)


@pytest.mark.parametrize("name", sorted(MODELS))
def test_no_field_has_an_alias(name: str) -> None:
    # 3G-lite review 1 #3: the stages write the attribute name, the API the
    # alias - a field with one would carry two keys, and a rename behind it
    # would pass the check above.
    assert [(model.__name__, field) for model in _models(MODELS[name])
            for field, info in model.model_fields.items()
            if info.alias or info.serialization_alias or info.validation_alias] == []
    # A computed field (a note's always_on) too (3G-lite review 2 #3).
    assert [(model.__name__, field) for model in _models(MODELS[name])
            for field, info in model.model_computed_fields.items() if info.alias] == []


def test_a_note_is_read_by_its_code_never_its_sentence() -> None:
    # Adjustment 2 (Thach): code, figures and measures; `always_on` says where
    # it is shown (adjustment 1). The sentence is no consumer's field.
    tables = section_11()[0]
    for name, prefix in (("metrics.json", "core.notes[]."), ("diagnosis.json", "notes[].")):
        assert {prefix + f for f in ("code", "figures", "always_on", "measures[].name", "measures[].scope",
                                     "measures[].lines", "measures[].amount")} <= set(tables[name])
        assert prefix + "text" not in tables[name]


# --- the checker catches what it must (models nobody ships) --------------------------------------


class _Inner(BaseModel):
    lines: int
    kind: typing.Literal["a", "b"]


class _Shipped(BaseModel):
    total: float | None
    share: typing.Annotated[float, annotated_types.Le(100)]
    items: list[_Inner]


class _Renamed(BaseModel):
    total_amount: float | None
    share: typing.Annotated[float, annotated_types.Le(100)]
    items: list[_Inner]


class _Retyped(BaseModel):
    total: float
    share: typing.Annotated[float, annotated_types.Le(1)]
    items: list[_Inner]


class _InnerNarrowed(BaseModel):
    lines: int
    kind: typing.Literal["a"]


class _Narrowed(BaseModel):
    total: float | None
    share: typing.Annotated[float, annotated_types.Le(100)]
    items: list[_InnerNarrowed]


def test_the_checker_catches_a_rename_a_removal_a_retype_and_a_new_scale() -> None:
    rows = fields(_Shipped)
    assert rows == {"total": "float | None", "share": "float (le=100)", "items": "list[object]",
                    "items[].lines": "int", "items[].kind": "Literal['a', 'b']"}
    assert problems(_Shipped, rows) == []
    assert problems(_Renamed, rows) == ["total: no such field (renamed or removed)"]
    assert problems(_Retyped, rows) == ["total: float where the consumer reads float | None",
                                        "share: float (le=1) where the consumer reads float (le=100)"]
    assert problems(_Narrowed, rows) == ["items[].kind: Literal['a'] where the consumer reads Literal['a', 'b']"]


def test_the_frozen_list_lets_an_enum_grow_anywhere_and_nothing_shrink() -> None:
    frozen = {"kind": "Literal['a', 'b']", "rule": "Literal[1, 2] | None", "figures": "list[Literal['x']]",
              "marks": "dict[str, Literal['p', 'q']]", "total": "float | None"}
    grown = {"kind": "Literal['a', 'b', 'c']", "rule": "Literal[1, 2, 3] | None",
             "figures": "list[Literal['x', 'y']]", "marks": "dict[str, Literal['p', 'q', 'r']]",
             "total": "float | None"}
    assert narrowed(frozen, grown) == []
    assert narrowed(frozen, grown | {"kind": "Literal['a']"}) == ["kind: Literal['a', 'b'] became Literal['a']"]
    assert narrowed(frozen, grown | {"rule": "Literal[1, 2, 3]"}) == [
        "rule: Literal[1, 2] | None became Literal[1, 2, 3]"]
    assert narrowed(frozen, {k: v for k, v in grown.items() if k != "total"}) == [
        "total: no longer in the consumer contract"]
