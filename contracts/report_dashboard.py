"""report.json's dashboard block (2.10; the dashboard - Thach's D2, D3, D6, D7,
2026-10-14; docs/DASHBOARD_DESIGN.md sections 2-4 and 8): the KPI tiles and
the widgets in the order code decides, ONE copy, which report.html and the
Insights page both draw. Every figure is a field of an earlier file,
formatted by stage 5; the page computes and words none.

The order rule lives here, once: stage 5 orders the widgets with it and the
contract refuses any other order.

2.11 (Thach's layout, 2026-10-15; docs/DASHBOARD_DESIGN.md section 10): the
dashboard is pictures and figures - one short line under the tiles
(`headline`), and full-width bands for what needs words: next month's figure
and range (`next_month`), one row of chips for what was checked (`checked`),
one line per suggested action (`next_steps`). A note stands where its figure
is, as a marker (CLAUDE.md 3.3a as amended): each element's `notes` and the
sentences behind the same marker (`asides`, a tile's `reason`, a widget's
`caption`).
"""

from typing import Literal, Self

from pydantic import Field, model_validator

from contracts._base import ContractModel
from contracts.lines import NoteCode

TileId = Literal["sales", "orders", "aov", "customers", "return_rate"]
TILE_ORDER: tuple[TileId, ...] = ("sales", "orders", "aov", "customers", "return_rate")
WidgetId = Literal["summary", "trend", "waterfall", "customers", "products", "category", "breakdown_1", "breakdown_2",
                   "returns", "checklist", "next_steps", "next_month", "cannot_know"]
# D3's fixed fallback order: the widgets with no size, and equal sizes.
FALLBACK_ORDER: tuple[WidgetId, ...] = ("summary", "trend", "waterfall", "customers", "products", "category",
                                        "breakdown_1", "breakdown_2", "returns", "checklist", "next_steps",
                                        "next_month", "cannot_know")
TEXT_WIDGETS: frozenset[WidgetId] = frozenset({"summary", "checklist", "next_steps", "next_month", "cannot_know"})
# The widget that can draw what a hypothesis measures (design section 3's
# last column): the first of the headline's named causes that its widget
# draws leads. No product cause is tied (step 3's review: the products chart
# is this month's best sellers, stage 2's list - it draws no product cause).
TIED: dict[str, WidgetId] = {"B1": "waterfall", "B2": "waterfall", "P1": "waterfall", "P2": "waterfall",
                             "C1": "customers", "C2": "customers", "C3": "customers", "P3": "returns", "T2": "trend"}
# Under a blocked diagnosis no chart is drawn from the refused figures.
BLOCKED_WIDGETS: tuple[WidgetId, ...] = ("summary", "next_month", "cannot_know")
# Drawn only beside a comparison: they show the two months' difference.
COMPARED_ONLY: frozenset[WidgetId] = frozenset({"waterfall", "customers", "returns", "checklist", "next_steps"})
Unit = Literal["money", "count", "ratio"]
Chart = Literal["line", "waterfall", "bars", "diverging", "parts"]
CHART_OF: dict[WidgetId, tuple[Chart, ...]] = {
    "trend": ("line",), "waterfall": ("waterfall",), "customers": ("bars",), "products": ("bars",),
    "category": ("bars", "parts"), "breakdown_1": ("bars", "parts"), "breakdown_2": ("bars", "parts"),
    "returns": ("bars",)}


# Row 2's line: "at most about 20 words" (Thach).
MAX_HEADLINE_WORDS = 20
# The checked chips: one per subject, in this order (design section 10). A
# file that counts lines names B1 "Lines per customer" in the same place.
CHIP_ORDER: tuple[tuple[str, ...], ...] = (
    ("Data",), ("Customers",), ("Order frequency", "Lines per customer"), ("Basket size",), ("Prices",),
    ("Product mix",), ("Refunds",), ("Discounts",), ("Charges",), ("One product",), ("Products in or out",),
    ("Stock",), ("Calendar",), ("Last year",))
ChipStatus = Literal["checked", "matches", "moved", "other way", "can't tell", "caution"]


def printed_figure(text: str) -> float:
    """The number a printed figure shows ("GBP 1,234.50", "-2,646.13",
    "0.152"): its last token, the thousands marks dropped - so the contract
    holds every text to its value without formatting it a second time."""
    return float(text.split(" ")[-1].replace(",", "").replace("+", ""))


def _agrees(text: str, value: float, places: int = 2) -> bool:
    try:
        return round(printed_figure(text), places) == round(value, places)
    except ValueError:
        return False


def order_widgets(sizes: dict[WidgetId, float | None], tied: WidgetId | None) -> list[WidgetId]:
    """D3: the widget tied to the named cause first, then by size (largest
    first), then the fixed fallback order - which also places every widget with
    no size, after the sized ones (design D-1)."""
    def key(widget: WidgetId) -> tuple[int, int, float, int]:
        size = sizes[widget]
        return (0 if widget == tied else 1, 0 if size is not None else 1, -(size or 0.0),
                FALLBACK_ORDER.index(widget))
    return sorted(sizes, key=key)


class Tile(ContractModel):
    """One KPI tile (design section 2): this month as printed, and last
    month's value as printed beside it ("was") - or, for sales, its change as
    sentence A prints it. A withheld figure is no tile, but sales, which stands
    with its reason."""

    id: TileId
    label: str = Field(min_length=1)
    unit: Unit
    now: str | None
    now_value: float | None
    was: str | None
    # Last month's value the "was" prints (layer 1's, the contract checks it).
    was_value: float | None = None
    change: str | None
    # From the order of the two PRINTED figures; the neutral colour (no
    # verdict on the month, ADR-0007).
    direction: Literal["up", "down", "same"] | None
    reason: str | None
    notes: list[NoteCode]

    @model_validator(mode="after")
    def _a_figure_or_why_not(self) -> Self:
        if (self.now is None) != (self.now_value is None):
            raise ValueError(f"{self.id}: the printed figure and its value go together")
        if self.now is None and (self.id != "sales" or self.reason is None):
            raise ValueError(f"{self.id}: a tile shows a figure - only sales stands without one, with its reason")
        if self.change is not None and self.id != "sales":
            raise ValueError(f"{self.id}: only sales carries a change (CONTRACTS 11)")
        if self.change is not None and self.was is not None:
            raise ValueError(f"{self.id}: a change or last month's value, not both")
        if self.direction is not None and self.change is None and self.was is None:
            raise ValueError(f"{self.id}: a direction needs the comparison it reads")
        if (self.was is None) != (self.was_value is None):
            raise ValueError(f"{self.id}: last month's text and its value go together")
        places = 3 if self.unit == "ratio" else 2
        if self.now is not None and self.now_value is not None and not _agrees(self.now, self.now_value, places):
            raise ValueError(f"{self.id}: the printed figure is not its value")
        if self.was is not None and self.was_value is not None and not _agrees(self.was, self.was_value, places):
            raise ValueError(f"{self.id}: last month's printed figure is not its value")
        if self.unit == "ratio" and self.now is not None and self.now_value is not None \
                and self.now != f"{self.now_value:.3f}":
            raise ValueError(f"{self.id}: a ratio is printed as a ratio, never a percentage (CONTRACTS 6)")
        if self.was is not None and self.now is not None:
            now, was = printed_figure(self.now), printed_figure(self.was)
            if self.direction != ("up" if now > was else "down" if now < was else "same"):
                raise ValueError(f"{self.id}: the arrow follows the two printed figures")
        return self


class Bar(ContractModel):
    """One bar of a chart widget: its label as the file or stage 3 writes it,
    this month's value and last month's (None when the month is not compared),
    as printed beside the bar."""

    label: str = Field(min_length=1)
    now: float
    was: float | None
    now_text: str
    was_text: str | None
    is_blank: bool = False

    @model_validator(mode="after")
    def _texts_with_values(self) -> Self:
        if (self.was is None) != (self.was_text is None):
            raise ValueError(f"{self.label!r}: last month's value and its text go together")
        if not _agrees(self.now_text, self.now) or (self.was is not None and self.was_text is not None
                                                     and not _agrees(self.was_text, self.was)):
            raise ValueError(f"{self.label!r}: a bar's printed figure is its value")
        return self


class Widget(ContractModel):
    id: WidgetId
    kind: Literal["chart", "text"]
    chart: Chart | None
    placed_by: Literal["named", "size", "fallback"]
    # The money it shows moving (an existing contribution; design section 3),
    # null for a widget with none.
    size: float | None = Field(default=None, ge=0)
    title: str | None
    # A breakdown's column as written in the file.
    column: str | None = None
    bars: list[Bar] = Field(default_factory=list)
    caption: list[str] = Field(default_factory=list)
    notes: list[NoteCode] = Field(default_factory=list)

    @model_validator(mode="after")
    def _as_its_kind(self) -> Self:
        text = self.id in TEXT_WIDGETS
        if (self.kind == "text") != text:
            raise ValueError(f"{self.id}: the text widgets are {sorted(TEXT_WIDGETS)}")
        if text and (self.chart is not None or self.bars or self.size is not None or self.title is not None):
            raise ValueError(f"{self.id}: a text widget prints the front section's own sentences, nothing else")
        if not text and (self.chart not in CHART_OF[self.id] or not self.title):
            raise ValueError(f"{self.id}: drawn as {CHART_OF[self.id]}, with its title")
        if self.chart in ("bars", "diverging", "parts") and not self.bars:
            raise ValueError(f"{self.id}: a {self.chart} chart has bars")
        if self.chart in ("line", "waterfall") and self.bars:
            raise ValueError(f"{self.id}: the {self.chart} is drawn from report.json's own chart, not from bars")
        if (self.column is not None) != self.id.startswith("breakdown_"):
            raise ValueError(f"{self.id}: a breakdown, and only one, names its column")
        if self.placed_by == "size" and self.size is None:
            raise ValueError(f"{self.id}: placed by a size it does not have")
        if self.placed_by == "fallback" and self.size is not None:
            raise ValueError(f"{self.id}: a widget with a size is placed by it")
        return self


class Headline(ContractModel):
    """Row 2: the summary as one short line, code-written from existing
    fields; behind its marker the sales figure's notes and the caution lines
    (`asides`)."""

    text: str = Field(min_length=1)
    notes: list[NoteCode] = Field(default_factory=list)
    asides: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _short(self) -> Self:
        if len(self.text.split()) > MAX_HEADLINE_WORDS:
            raise ValueError(f"the line under the tiles is {MAX_HEADLINE_WORDS} words at most")
        return self


class Chip(ContractModel):
    """One subject of what was checked, and what the checklist found of it."""

    label: str
    status: ChipStatus


class NextMonthBand(ContractModel):
    """The forecast's first month as numbers: about `figure`, likely `low` to
    `high` - or why there is none (`reason`). Its other sentences stand
    behind its marker (`asides`) and in Technical details."""

    month: str | None
    figure: str | None
    value: float | None
    low: str | None
    low_value: float | None
    high: str | None
    high_value: float | None
    reason: str | None
    notes: list[NoteCode] = Field(default_factory=list)
    asides: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _figures_or_why_not(self) -> Self:
        texts, values = (self.figure, self.low, self.high), (self.value, self.low_value, self.high_value)
        if any((text is None) != (value is None) for text, value in zip(texts, values, strict=True)):
            raise ValueError("next month's printed figures and their values go together")
        if (self.figure is None) == (self.reason is None):
            raise ValueError("next month shows its figure, or why there is none - never both")
        if self.figure is not None and (self.month is None or self.low is None or self.high is None):
            raise ValueError("next month's figure comes with its month and its range")
        for text, value in zip(texts, values, strict=True):
            if text is not None and value is not None and not _agrees(text, value):
                raise ValueError("next month's printed figure is its value")
        if self.low_value is not None and self.high_value is not None and self.value is not None \
                and not self.low_value <= self.value <= self.high_value:
            raise ValueError("next month's figure lies inside its range")
        return self


class Dashboard(ContractModel):
    # As the front's: compared, not compared (this month alone), blocked.
    state: Literal["compared", "not_compared", "blocked"]
    tiles: list[Tile] = Field(min_length=1)
    # Why a tile the file's fields would call for is not shown (D2: never an
    # empty tile; its reason under the row instead).
    not_shown: list[str]
    # The data checks' caution lines, under the tiles (CLAUDE.md 3.3a: beside
    # the figures they caution).
    caution: list[str]
    widgets: list[Widget] = Field(min_length=1)
    # 2.11 (Thach's layout): row 2's line and row 4's bands.
    headline: Headline | None = None
    checked: list[Chip] = Field(default_factory=list)
    next_month: NextMonthBand | None = None
    next_steps: list[str] = Field(default_factory=list)
    # The notes beside the checked chips and the next steps - the front's
    # (CLAUDE.md 3.3a: where those findings are shown, behind a marker).
    checked_notes: list[NoteCode] = Field(default_factory=list)
    next_steps_notes: list[NoteCode] = Field(default_factory=list)

    @model_validator(mode="after")
    def _the_bands(self) -> Self:
        labels = [chip.label for chip in self.checked]
        places = [next((i for i, names in enumerate(CHIP_ORDER) if label in names), None) for label in labels]
        if None in places or places != sorted(set(places)):  # type: ignore[type-var]
            raise ValueError(f"the chips are {CHIP_ORDER}'s subjects, each once, in that order; got {labels}")
        if self.checked and (self.checked[0].label != "Data" or self.checked[0].status not in ("checked", "caution")):
            raise ValueError("the checked chips open with the data checks: checked or caution")
        if any(chip.status == "caution" for chip in self.checked[1:]):
            raise ValueError("only the data checks are a caution")
        if self.checked and self.checked[0].status == "caution" and not self.caution:
            raise ValueError("the data chip says caution exactly when a check cautions")
        if self.checked and self.checked[0].status != "caution" and self.caution:
            raise ValueError("the data chip says caution exactly when a check cautions")
        if self.state == "blocked" and (self.checked or self.next_steps):
            raise ValueError("a blocked report draws no chip and no next step: its line says why")
        if self.headline is not None and not set(self.caution) <= set(self.headline.asides):
            raise ValueError("the caution lines stand behind the line's marker (CLAUDE.md 3.3a)")
        if any(not step.strip() for step in self.next_steps):
            raise ValueError("a next step is a line of words")
        return self

    @model_validator(mode="after")
    def _by_the_rules(self) -> Self:
        ids = [tile.id for tile in self.tiles]
        if ids[0] != "sales" or ids != [t for t in TILE_ORDER if t in ids]:
            raise ValueError(f"the tiles are {TILE_ORDER} in that order, sales always first; got {ids}")
        if self.state != "compared" and any(t.was is not None or t.change is not None for t in self.tiles):
            raise ValueError("a month not compared shows no change and no last month's value (CONTRACTS 11)")
        widgets = [w.id for w in self.widgets]
        if len(widgets) != len(set(widgets)):
            raise ValueError("each widget is drawn once")
        if self.state == "blocked" and widgets != list(BLOCKED_WIDGETS):
            raise ValueError(f"a blocked report draws {BLOCKED_WIDGETS} only")
        if self.state != "compared" and set(widgets) & COMPARED_ONLY:
            raise ValueError("a month not compared draws nothing that shows the two months' difference")
        if self.state != "compared" and any(w.size is not None or any(b.was is not None for b in w.bars)
                                            for w in self.widgets):
            raise ValueError("a month not compared has no size and no last month's bar")
        named = [w.id for w in self.widgets if w.placed_by == "named"]
        if len(named) > 1:
            raise ValueError("one widget at most is tied to the named cause")
        if widgets != order_widgets({w.id: w.size for w in self.widgets}, named[0] if named else None):
            raise ValueError(f"the widgets are not in the order rule's order: {widgets}")
        if self.widgets and named and widgets[0] != named[0]:
            raise ValueError("the widget tied to the named cause comes first")
        return self
