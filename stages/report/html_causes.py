"""report.html's "Why it happened" (session 5B), split out of html_report.py
for file size: the diagnosis as report.json has it - the code's headline,
the AI's reading or "unavailable", every hypothesis tested, what the data
cannot test, where the month sits (a description, never a verdict), the
diagnosis's notes and the suggested classes."""

from contracts.report import Causes, Numbers, SignalView
from stages.report.html_parts import (
    esc,
    evidence_value,
    items,
    links,
    money,
    note,
    para,
    share,
    signal_value,
    table,
)

# By the rule that fired (contracts/diagnosis.py): 1 = beyond a limit, 2 = a
# run of months on one side of the centre - its value can sit inside the
# limits (5B review 1 #2).
_WHERE = {("above", 1): "above the upper limit", ("below", 1): "below the lower limit",
          ("above", 2): "above the centre for a run of months", ("below", 2): "below the centre for a run of months"}
_NO_CHART = {"too_few_points": "too few months", "no_current_value": "no value this month",
             "no_measurable_spread": "no measurable spread"}


def _where(signal: SignalView) -> str:
    """Only what the row says: no rule or reason is filled in (5B review 2
    #10)."""
    if signal.signal == "within":
        return "within the limits"
    if signal.signal == "insufficient_history":
        why = _NO_CHART.get(signal.insufficient_reason or "")
        return f"no chart: {why}" if why else "no chart"
    return _WHERE.get((signal.signal, signal.rule or 0), signal.signal)


def _signals(causes: Causes) -> str:
    if causes.signals is None:
        return para("The signals were not measured for this run.")
    rows = []
    for s in causes.signals:
        chart = s.mode + (f" ({s.mode_fallback.replace('_', ' ')})" if s.mode_fallback else "") + (
            " - floor limits: no variation measured" if s.limits_method == "minimum_spread" else "")
        figures = ["" if v is None else signal_value(s.series, s.mode, v) for v in (s.value_cur, s.center, s.lower,
                                                                                   s.upper)]
        rows.append([esc(s.label), esc(chart), *figures, esc(_where(s))])
    return ("<h3>Where this month sits</h3>"
            + para("Against limits drawn from the history's own variation - or, where the history did not vary, "
                   "from a floor, which the row says - a description, never a verdict: no month is called normal "
                   "or unusual. A level chart reads the series' own unit; a year-over-year one, the change on the "
                   "year before in percent.")
            + table(["Series", "Chart", "This month", "Centre", "Lower limit", "Upper limit", "Where"], rows))


def causes_html(causes: Causes, numbers: Numbers) -> str:
    whole = numbers.period.previous_complete
    parts = ["<h2>Why it happened</h2>", para(causes.headline.message, "headline")]
    story = causes.narration
    if story is None:
        parts.append(para("The AI narration is unavailable for this report."))
    else:
        parts.append("<h3>The AI's reading</h3>" + para(story.summary) + para(story.headline_explanation)
                     + items(f"{esc(n.id)}: {esc(n.text)}" for n in story.hypothesis_notes)
                     + para(story.not_tested_note))
    rows = [[esc(h.id), esc(h.statement), esc(h.verdict.replace("_", " ")),
             "" if h.contribution is None else money(h.contribution), "" if h.share is None else share(h.share),
             esc(h.rule), items(f"{esc(k)}: {esc(evidence_value(v, causes.suggested_classes))}"
                                for k, v in h.evidence.items())]
            for h in causes.hypotheses]
    parts.append(table(["ID", "Hypothesis", "Verdict", "Contribution", "Share", "Rule", "Evidence"], rows,
                       "Every hypothesis tested, the ruled-out ones included"))
    if causes.not_testable:
        parts.append("<h3>What this data cannot test</h3>"
                     + items(f"{esc(n.statement)}: {esc(n.reason)}" for n in causes.not_testable))
    parts.append(_signals(causes))
    if numbers.unconfirmed_placeholders_reason:
        # The customer causes read the same customers (2E-u3).
        parts.append(para(numbers.unconfirmed_placeholders_reason, "reason"))
    beside = {n.code for n in numbers.notes}
    if causes.notes:
        # A note the numbers already show is linked, never a second anchor.
        shared = [n.code for n in causes.notes if n.code in beside]
        parts.append("<h3>Notes on the diagnosis</h3>"
                     + "".join(note(n, previous_complete=whole) for n in causes.notes if n.code not in beside)
                     + (f"<p>Read with: {links(shared)}</p>" if shared else ""))
    if causes.suggested_classes:
        parts.append(table(["Product", "Suggested class"],
                           [[esc(p), esc(c)] for p, c in causes.suggested_classes.items()],
                           "Classes suggested for these products that nobody confirmed in Review"))
    return "".join(parts)
