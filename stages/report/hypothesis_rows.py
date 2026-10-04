"""The hypothesis table's rows as report.json carries them (Thach, 2026-10-04, decisions (vii) and (viii)
on the fifteenth report): whether a hypothesis was ruled out for moving AGAINST the change, its verdict as
shown and its evidence text - one copy, which report.html and the page print alike.

"Against" is stage 3's statement (diagnosis.json `against_the_change`, its own sign test on the total it
measured): stage 5 re-derives nothing. It decides only where the statement is shown - beside a compared
month the report shows (never an incomplete previous month, never a withheld one - CONTRACTS 11), and
never for a contribution that prints as zero. The verdict code is unchanged.
"""

from contracts.diagnosis import DiagnosisContract, Hypothesis
from contracts.report import HypothesisView, Numbers, compared_month_shown
from contracts.report_views import against_label, prints_as_zero
from stages.report.html_parts import evidence_value


def moved_against(hypothesis: Hypothesis, numbers: Numbers) -> bool:
    contribution = hypothesis.contribution
    if not hypothesis.against_the_change or contribution is None or prints_as_zero(contribution):
        return False
    return compared_month_shown(numbers)


def hypothesis_view(hypothesis: Hypothesis, diagnosis: DiagnosisContract, numbers: Numbers) -> HypothesisView:
    against = moved_against(hypothesis, numbers)
    label = (against_label(hypothesis.contribution) if against and hypothesis.contribution is not None
             else hypothesis.verdict.replace("_", " "))
    return HypothesisView(
        id=hypothesis.id, statement=hypothesis.statement, verdict=hypothesis.verdict,
        contribution=hypothesis.contribution, share=hypothesis.share, rule=hypothesis.rule,
        evidence=dict(hypothesis.evidence), moved_against=against, verdict_label=label,
        evidence_text=[f"{key}: {evidence_value(value, dict(diagnosis.suggested_classes))}"
                       for key, value in hypothesis.evidence.items()])
