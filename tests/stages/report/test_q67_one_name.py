"""Thach, Q67 (2026-10-09): stage 5's wording fixed at its one copy, for
report.html and the page alike - the waterfall reads "from the first bar to
the last" (a phone draws its bars across), and the technical part has one
name, "Technical details", never "the appendix". Written before the fix."""

import re
from html import unescape

from stages.report.html_report import render_html
from tests.stages.report.html_probe import Page
from tests.stages.report.real_runs import RUNS, build_real


def test_the_waterfall_reads_from_the_first_bar_to_the_last() -> None:
    for run in RUNS:
        caption = build_real(run).front.waterfall.caption  # type: ignore[union-attr]  # every real run compares

        assert caption.startswith("Read from the first bar to the last: ")
        assert "left to right" not in caption


def test_the_rows_left_out_name_technical_details() -> None:
    texts = [item.text for item in build_real("demo_classed").front.cannot_know]

    assert any("- they are listed in Technical details." in text for text in texts)
    assert not any("appendix" in text for text in texts)


def test_report_html_names_its_technical_part_technical_details() -> None:
    html = render_html(build_real("demo_classed"))

    assert '<summary>Technical details</summary>' in html
    assert "In Technical details, 'revenue' is the same figure as 'sales' above." in unescape(html)
    visible = re.sub(r"<script>.*?</script>|<style>.*?</style>|<[^>]+>", " ", html, flags=re.S)
    assert "appendix" not in visible.lower()
    assert "appendix" not in Page(html).front_text.lower()
