"""Thach's layout decision (2026-10-15; docs/DASHBOARD_DESIGN.md section 10):
pictures and figures, almost no text - report.json 2.11. Row 1 the tiles
(label, figure, arrow, change - no sentence); row 2 one short line; row 3 the
chart cards (no caption under a chart); row 4 full-width bands (next month,
checked chips, next step); every long text in Technical details; a note shown
where its figure is as a marker (CLAUDE.md 3.3a as amended). Failing tests
first; expected texts from the real runs' own fields (fixtures/)."""

import html
import re
from functools import cache
from html.parser import HTMLParser

import pytest

from contracts.report import ReportContract
from contracts.report_front import FRONT_BANNED
from stages.report.builder import SCHEMA_VERSION
from stages.report.html_report import render_html
from tests.scenarios.scenarios import s0
from tests.stages.report.real_runs import RUNS, build_real, files, with_actions
from tests.stages.report.test_dashboard import _pipeline

ACTION = {"claim": "K1", "hypothesis_id": "B1", "fact": "Customers ordered more often: 343 orders, up from 308.",
          "action": "Thank the customers who came back this month.", "why": "They ordered more often.",
          "watch": "Orders per customer next month."}


@cache
def _real(run: str) -> ReportContract:
    return build_real(run)


_PAGES: dict[int, tuple[ReportContract, str]] = {}


def _html(report: ReportContract) -> str:
    """The page without its scripts (plotly's few megabytes): the tests read the structure, never the
    scripts. Rendered once per report."""
    if id(report) not in _PAGES:
        _PAGES[id(report)] = (report, re.sub(r"<script>.*?</script>", "<script></script>", render_html(report),
                                             flags=re.S))
    return _PAGES[id(report)][1]


def _blocked(breakdowns: tuple[str, ...] = ()) -> ReportContract:
    return _blocked_report(tuple(breakdowns))


@cache
def _blocked_report(breakdowns: tuple[str, ...]) -> ReportContract:
    # Half of September with no line at all: D1 blocks the comparison.
    frame = s0(1)
    frame = frame[~frame["Date"].between("2023-09-01", "2023-09-18")].reset_index(drop=True)
    frame["Till"] = ["T1", "T2"] * (len(frame) // 2) + ["T1"] * (len(frame) % 2)
    return _pipeline(frame, breakdowns=list(breakdowns) or None)


class Layout(HTMLParser):
    """report.html's structure: each <p>'s text with the classes of the
    elements around it; the markers (`details.mk`) and what they hold; the
    text outside Technical details and outside the markers."""

    def __init__(self, html: str) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, str, str]] = []  # (tag, class, id)
        self.paragraphs: list[tuple[str, list[str]]] = []
        self.markers: list[dict[str, str]] = []
        self.visible: list[str] = []
        self._p: list[str] | None = None
        self.feed(html)

    def _inside(self, cls: str = "", element_id: str = "") -> bool:
        return any((cls and cls in c.split()) or (element_id and i == element_id) for _, c, i in self.stack)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        found = dict(attrs)
        if tag in ("br", "img", "meta", "link", "input"):
            return
        self.stack.append((tag, found.get("class") or "", found.get("id") or ""))
        if tag == "p":
            self._p = []
        if tag == "details" and "mk" in (found.get("class") or "").split():
            self.markers.append({"notes": found.get("data-notes") or "", "text": "",
                                 "around": " ".join(c for _, c, _ in self.stack[:-1])})

    def handle_endtag(self, tag: str) -> None:
        if tag == "p" and self._p is not None:
            self.paragraphs.append((" ".join(self._p).strip(), [c for _, c, _ in self.stack]))
            self._p = None
        while self.stack:
            if self.stack.pop()[0] == tag:
                break

    def handle_data(self, data: str) -> None:
        if self._p is not None:
            self._p.append(data)
        if self._inside("mk") and self.markers:
            self.markers[-1]["text"] += " " + data
        elif not self._inside(element_id="appendix") and not self._inside(element_id="head"):
            self.visible.append(data)


def _page(report: ReportContract) -> Layout:
    return Layout(_html(report))


def _outside(classes: list[str], *allowed: str) -> bool:
    return not any(set(c.split()) & set(allowed) for c in classes)


def test_the_version_is_2_11() -> None:
    assert SCHEMA_VERSION == "2.11"  # 2.11: Thach's layout - the line, the chips, the bands (2026-10-15)


# --- row 1: the tiles, no sentence ----------------------------------------------------------------------------------

def test_a_tile_is_label_figure_arrow_and_change_only() -> None:
    tiles = {t.id: t for t in _real("kaggle").dashboard.tiles}
    assert tiles["sales"].change == "+4,925.00 (+11.9%)"  # the month moved to the line under the tiles
    assert (tiles["orders"].now, tiles["orders"].was) == ("343", "308")
    page = _html(_real("kaggle"))
    tiles_html = page[page.index('id="tiles"'):page.index("</section>", page.index('id="tiles"'))]
    # No paragraph (an icon's <path> is no paragraph: Thach's visual style puts one in each tile).
    assert "was 308" in tiles_html and "in November 2024" not in tiles_html and not re.search(r"<p[\s>]", tiles_html)


def test_a_sales_tile_with_no_comparison_keeps_its_reason_behind_its_marker() -> None:
    report = _blocked()
    sales = report.dashboard.tiles[0]
    assert sales.reason == "Not compared: the data checks did not pass - see Technical details."
    layout = _page(report)
    assert any(sales.reason in m["text"] and "tile" in m["around"] for m in layout.markers)


# --- row 2: one short line --------------------------------------------------------------------------------------------

@pytest.mark.parametrize(("run", "line"), [
    ("kaggle", "Sales +11.9% vs November 2024"),
    ("demo_classed", "Sales +27.2% vs October 2011 · same months last year +27.1%"),
    ("demo_unanswered", "Sales +27.08% vs October 2011 · same months last year +39.14%"),
])
def test_the_line_under_the_tiles(run: str, line: str) -> None:
    # The percentages at sentence B's decimals - one change printed one way (Q56): the unanswered demo's
    # season sentence prints 27.08% and 39.14%. The line states facts only (Thach, 2026-10-16): "in line with"
    # beside 27.08% and 39.14% read as false; the judgement and its yardstick stand behind the marker.
    report = _real(run)
    assert report.dashboard.headline.text == line
    assert line in " ".join(_page(report).visible)


@pytest.mark.parametrize("run", ["demo_classed", "demo_unanswered"])
def test_the_line_never_states_a_judgement_beside_two_different_printed_figures(run: str) -> None:
    # Thach, 2026-10-16: "in line with" only when the two printed changes are equal at the printed precision.
    report = _real(run)
    assert "in line with" not in report.dashboard.headline.text
    assert "differs from" not in report.dashboard.headline.text
    assert any("in line with" in aside for aside in report.dashboard.headline.asides)


def test_the_line_is_at_most_about_twenty_words_on_every_file() -> None:
    reports = [_real(run) for run in RUNS] + [_blocked(), _pipeline(s0(1))]
    for report in reports:
        assert len(report.dashboard.headline.text.split()) <= 20, report.dashboard.headline.text


def test_a_blocked_report_says_so_in_the_line() -> None:
    assert _blocked().dashboard.headline.text == "Not compared: the data checks did not pass"


def test_the_line_carries_the_sales_notes_and_any_caution_behind_its_marker() -> None:
    # The scoped review's R1: the line states the summary's verdict, so its marker carries the summary's notes
    # (the sales figure's among them) - same_day_cancellations names the diagnosis.
    report = _real("demo_unanswered")
    notes = report.dashboard.headline.notes
    assert notes == report.front.notes.summary and "same_day_cancellations" in notes
    assert {"unconfirmed_suggestions", "unconfirmed_deductions"} <= set(notes)
    layout = _page(report)
    assert any(m["notes"].split() == notes and "headline" in m["around"] for m in layout.markers)


# --- row 3: chart cards, no paragraph ---------------------------------------------------------------------------------

def test_no_paragraph_outside_technical_details_the_line_and_the_bands() -> None:
    for report in [_real(run) for run in RUNS] + [_blocked()]:
        page = _html(report)
        # Technical details is the <details id="appendix">: everything before it is the dashboard.
        dashboard = Layout(page[:page.index('<details id="appendix">')])
        # The page's header lines (the file, the months: class "meta") are no paragraph of the dashboard.
        stray = [text for text, classes in dashboard.paragraphs
                 if _outside(classes, "band", "headline", "mk", "meta")]
        assert stray == [], stray[:3]


def test_the_text_parts_are_not_drawn_as_cards() -> None:
    page = _html(_real("kaggle"))
    for title in ("In short", "What was checked", "What this report cannot know"):
        assert f"<h2>{title}</h2>" not in page[:page.index('<details id="appendix">')]


def test_no_caption_under_a_chart_it_stands_behind_the_cards_marker() -> None:
    report = _real("kaggle")
    trend = next(w for w in report.dashboard.widgets if w.id == "trend")
    assert trend.caption  # January 2025 is not in the chart
    layout = _page(report)
    assert trend.caption[0] not in " ".join(layout.visible)
    assert any(trend.caption[0] in m["text"] for m in layout.markers)


# --- markers: a note where its figure is (CLAUDE.md 3.3a as amended) ---------------------------------------------

@pytest.mark.parametrize("run", RUNS)
def test_every_note_marker_is_present_where_its_figure_is(run: str) -> None:
    report = _real(run)
    layout = _page(report)
    texts = {note.code: note.text for note in [*report.layer_1_numbers.notes, *report.layer_2_causes.notes]}
    expected = [t.notes for t in report.dashboard.tiles if t.notes]
    expected += [w.notes for w in report.dashboard.widgets if w.kind == "chart" and w.notes]
    expected += [report.dashboard.headline.notes] if report.dashboard.headline.notes else []
    band = report.dashboard.next_month
    expected += [band.notes] if band is not None and band.notes else []
    found = [m["notes"].split() for m in layout.markers]
    for codes in expected:
        assert codes in found, (run, codes)
    for marker in layout.markers:
        for code in marker["notes"].split():
            assert texts[code] in marker["text"]  # it opens the note's full sentence


def test_a_marker_is_a_keyboard_reachable_named_control() -> None:
    page = _html(_real("demo_classed"))
    markers = re.findall(r'<details class="mk"[^>]*><summary aria-label="([^"]+)">', page)
    assert markers and all(label.startswith("About ") for label in markers)


# --- row 4: the bands -----------------------------------------------------------------------------------------------

def test_next_month_is_its_figure_and_range_as_numbers() -> None:
    band = _real("kaggle").dashboard.next_month
    assert (band.month, band.figure, band.low, band.high) == ("January 2025", "43,835.33", "38,893.14", "49,405.54")
    # Behind its marker: the front's next-month sentences, the first one too (what "likely" means - the review).
    assert band.asides == _real("kaggle").front.next_month
    page = _html(_real("kaggle"))
    assert 'class="band next-month"' in page


CHIPS = {
    "kaggle": [("Data", "checked"), ("Customers", "checked"), ("Order frequency", "matches"),
               ("Basket size", "matches"), ("Prices", "checked"), ("Product mix", "other way"),
               ("Refunds", "checked"), ("Discounts", "checked"), ("Charges", "can't tell"),
               ("One product", "checked"), ("Products in or out", "matches"), ("Stock", "checked"),
               ("Calendar", "matches"), ("Last year", "matches")],
    "demo_classed": [("Data", "checked"), ("Customers", "moved"), ("Order frequency", "moved"),
                     ("Basket size", "can't tell"), ("Prices", "moved"), ("Product mix", "checked"),
                     ("Refunds", "moved"), ("Discounts", "checked"), ("Charges", "moved"), ("One product", "checked"),
                     ("Products in or out", "checked"), ("Stock", "checked"), ("Calendar", "moved"),
                     ("Last year", "moved")],
}


@pytest.mark.parametrize("run", sorted(CHIPS))
def test_checked_is_one_row_of_chips_from_the_checklists_own_groups(run: str) -> None:
    # Kaggle (rule 6, B1 named): matches B1, T2, B2, T1, R2; against P2; not the reason C1-C3, P1, P3, P4, R1, R3;
    # cannot show P5. Online Retail II (rule 7): moved T2, B1, P1, C3, P3, T1, P5; not the reason C1, C2, P2, P4,
    # R1, R2, R3; cannot show B2. Customers takes its strongest (C3 moved).
    report = _real(run)
    assert [(c.label, c.status) for c in report.dashboard.checked] == CHIPS[run]
    assert 'class="band checked"' in _html(report)


def test_a_caution_makes_the_data_chip_say_so() -> None:
    from tests.scenarios.scenarios import s10
    report = _pipeline(s10(1))
    assert report.dashboard.caution
    assert report.dashboard.checked[0].label == "Data" and report.dashboard.checked[0].status == "caution"
    assert all(line in report.dashboard.headline.asides for line in report.dashboard.caution)


def test_next_step_is_one_line_per_action() -> None:
    report = build_real("kaggle", forecast=with_actions("kaggle", "list", [ACTION]))
    assert report.dashboard.next_steps == ["Thank the customers who came back this month."]
    page = _html(report)
    assert 'class="band next-steps"' in page


def test_no_next_step_band_without_an_action() -> None:
    report = _real("kaggle")
    assert report.dashboard.next_steps == []
    assert 'class="band next-steps"' not in _html(report)


def test_a_blocked_report_has_the_line_and_next_month_only() -> None:
    dashboard = _blocked().dashboard
    assert dashboard.checked == [] and dashboard.next_steps == []
    assert dashboard.next_month is not None


# --- Technical details holds every long text, nothing deleted -------------------------------------------------------

@pytest.mark.parametrize("run", RUNS)
def test_every_long_text_is_in_technical_details(run: str) -> None:
    report = build_real(run, forecast=with_actions(run, "list", [ACTION]) if run == "kaggle" else
                        files(run)["forecast.json"])
    page = _html(report)
    text = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", page[page.index('<details id="appendix">'):])).split())
    front = report.front
    wanted = [*front.summary, front.sales_note, *front.data_checks, *front.next_month,
              *(line for group in front.checklist for line in group.lines),
              *(f"{item.title}." for item in front.cannot_know), *(item.text for item in front.cannot_know),
              *(line for w in report.dashboard.widgets for line in w.caption), *report.dashboard.not_shown]
    if front.waterfall is not None:
        wanted += [front.waterfall.caption, *([front.waterfall.note] if front.waterfall.note else [])]
    if front.next_steps is not None:
        wanted += [*(i.why for i in front.next_steps.items), *(i.watch for i in front.next_steps.items)]
        wanted += [front.next_steps.sentence] if front.next_steps.sentence else []
    missing = [line for line in wanted if line and " ".join(line.split()) not in text]
    assert missing == [], missing[:3]


# --- no mock label, no banned word ------------------------------------------------------------------------------------

@pytest.mark.parametrize("run", RUNS)
def test_no_mock_label_in_user_facing_output(run: str) -> None:
    page = _html(_real(run)).lower()
    for label in ("placed by", "mock", "fixed order", "placed_by"):
        assert label not in page, label


def test_no_banned_word_in_the_line_the_chips_or_the_bands() -> None:
    for report in [_real(run) for run in RUNS]:
        dashboard = report.dashboard
        words = [dashboard.headline.text, *(c.label for c in dashboard.checked), *dashboard.next_steps]
        band = dashboard.next_month
        words += [band.month or "", band.reason or ""] if band is not None else []
        text = " ".join(words).lower()
        assert not [word for word in FRONT_BANNED if re.search(rf"\b{re.escape(word)}", text)]


# --- the recorded fixes ------------------------------------------------------------------------------------------------

def test_a_blocked_report_with_a_chosen_split_never_says_this_version_does_not_split() -> None:
    # Was "This version does not split sales that way." beside a split the user kept in Review (step 3's
    # scoped review; Thach's 4.1, 2026-10-15).
    report = _blocked(("Till",))
    line = next(item.text for item in report.front.cannot_know if item.title.startswith("Sales by channel"))
    assert line == ('You kept "Till" in Review to split sales by; it is not drawn in this report: the data checks '
                    "did not pass.")


# --- products: re-enabled with the mark (Thach, 2026-10-15) -----------------------------------------------------------

def test_the_products_widget_marks_a_suggested_charge() -> None:
    # The unanswered demo's top product (Online Retail II's DOTCOM POSTAGE, anonymised in the fixture as
    # "Product 186") carries a suggested class nobody confirmed: it is never shown without its mark.
    report = _real("demo_unanswered")
    products = next(w for w in report.dashboard.widgets if w.id == "products")
    assert products.bars[0].label == "Product 186 (suggested: charge, not confirmed)"
    assert products.title == "Products with the most sales in November 2011"


@pytest.mark.parametrize("run", RUNS)
def test_no_suggested_product_is_drawn_without_its_mark(run: str) -> None:
    report = _real(run)
    suggested = files(run)["metrics.json"]["products"]["suggested_classes"]
    products = next((w for w in report.dashboard.widgets if w.id == "products"), None)
    assert products is not None, run
    for bar in products.bars:
        name = bar.label.split(" (suggested: ")[0]
        if name in suggested:
            assert bar.label == f"{name} (suggested: {suggested[name]}, not confirmed)"


def test_what_the_sales_figures_are_stands_behind_the_lines_marker() -> None:
    # The front's sales note ("not profit"; "Amounts are in your file's currency." when no code is known)
    # explains every amount shown: where the line states the change, behind its marker (3.3a as amended).
    report = _real("kaggle")
    assert report.front.sales_note in report.dashboard.headline.asides
    layout = _page(report)
    assert any(report.front.sales_note in " ".join(m["text"].split()) and "headline" in m["around"]
               for m in layout.markers)


# --- the review cycle's findings (each reproduced first) ---------------------------------------------------------

def test_r1_a_cards_head_wraps_so_an_open_marker_never_squeezes_its_title() -> None:
    from stages.report.html_dashboard import DASHBOARD_STYLE
    assert ".whead{display:flex;flex-wrap:wrap" in DASHBOARD_STYLE.replace("\n", "")


def test_r2_a_tiles_open_marker_spans_the_whole_row_never_a_narrow_column() -> None:
    from stages.report.html_dashboard import DASHBOARD_STYLE
    # The scoped review's R2: in the flow - the open tile takes the whole row - never over other figures.
    style = DASHBOARD_STYLE.replace("\n", "")
    assert ".tile:has(details.mk[open]){grid-column:1/-1}" in style and ".mk-panel{position:absolute" not in style


def test_r4_the_lines_marker_says_why_in_line_with() -> None:
    # demo_unanswered: "+27.08% ... same months last year +39.14%" - the judgement, sentence B ("in line with":
    # the gap within twice the typical gap), stands behind the line's marker.
    report = _real("demo_unanswered")
    assert all(line in report.dashboard.headline.asides for line in report.front.summary)


@pytest.mark.parametrize("run", RUNS)
def test_r5_the_checked_and_next_step_bands_carry_their_notes_behind_a_marker(run: str) -> None:
    report = build_real(run, forecast=with_actions(run, "list", [ACTION]) if run == "kaggle" else
                        files(run)["forecast.json"])
    dashboard = report.dashboard
    assert dashboard.checked_notes == report.front.notes.checked
    assert dashboard.next_steps_notes == report.front.notes.next_steps
    layout = _page(report)
    if dashboard.checked_notes:
        assert any(m["notes"].split() == dashboard.checked_notes and "checked" in m["around"] for m in layout.markers)


def test_the_next_month_marker_says_what_likely_means() -> None:
    band = _real("kaggle").dashboard.next_month
    assert any("about 8 months in 10" in line for line in band.asides)


def test_a_2_10_report_draws_its_front_section_as_before() -> None:
    report = _real("kaggle")
    old = report.model_copy(update={"dashboard": report.dashboard.model_copy(update={
        "headline": None, "next_month": None, "checked": [], "next_steps": []})})
    page = render_html(old)
    assert "In 30 seconds" in page and 'class="band' not in page
