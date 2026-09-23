# ADR-0006: Level-mode signals are descriptive, never verdicts

## Status
Accepted. **Extended by ADR-0007** (2026-09-23): year-over-year rows are
descriptive too in v1, and exception 3 below - the masked-shift alert reading
step 4 - is superseded; the alert now rests on the tree and
`masked_shift_basis` is removed.

## Date
2026-09-23 (Phase 3, decided by Thach after session 3D5; supersedes the
level-chart gate that session shipped)

## Context

Step 4 puts process behaviour (XmR) limits around each monthly series so the
engine can say "this month was within normal variation" and mean it
(`docs/AI_PIPELINE.md` section 7.5). The limits are centred on the mean of the
baseline and widened by the moving range.

**An XmR chart assumes a stable process.** A seasonal retail series is not
stable in level terms: December is not a noisy draw from the same distribution
as March. Year-over-year mode is the standard way to make it stable, and the
engine uses it whenever the file supports it.

The problem is what happens when it does not - a file under 21 complete
months, or a current month whose year-ago comparator is missing or netted zero
or below. The series falls back to a level chart, and that chart's centre is
the average of every month, so it is in the wrong place for any month with a
season. The failure is symmetric and both halves are damaging:

- a December that **halves** still lands above that centre and reads `within`,
  or on a wider file `above` - the engine calls a collapse ordinary, or good;
- an **ordinary** December fires `above` for being ordinary.

### Four sessions tried to fix this inside the chart

| Session | Attempt | Outcome |
|---|---|---|
| 3D2 | Median centre + step-change detection and re-baselining | Reverted. Zero-width limits on flat series, 40 of 72 seasonal shapes re-baselined, a real step reported 12 months late |
| 3D3 | Minimum spread in each series' own units; margin cut to residue | Shipped, but the first floor silenced a real 2% drop on a shop with 0.2% variation |
| 3D4 | Year-over-year refused a base that is not a positive denominator | Shipped, and **collided with 3D3's R3**: the fallback it forces put a seasonal shop's 50% collapse onto a level chart that reported `within` |
| 3D5 | A gate: refuse the fallback when the level chart cannot see a halving, then also when its centre sits off the month's own season | Both deleted by this ADR |

Each session closed with deeper open items on the same block. The cause is
structural rather than a sequence of bugs: **the information a level chart
would need to judge a seasonal month - what this month normally does - is
exactly the information that is missing when year-over-year is unavailable.**
No gate can synthesise it.

3D5 produced the decisive evidence for that, by accident. Its second condition
compared the current calendar month's own history against the centre. But
`HISTORY_MAX_MONTHS` is 24, so a 24-month file has a 23-month window holding
**one** prior occurrence of the current calendar month - and that occurrence is
the comparator whose failure put the series in level mode. The condition can
therefore never fire on a 24-month file. Twenty-four complete months is the
project's recommended demo dataset. **The fix could not run on the reference
shape it was written for.**

The same session's width constant told the same story from the other side.
`LEVEL_BLIND_SHARE = 0.50` was presented as tuned, and was not: a drop of
fraction X moves a month X*centre from the centre, so `half_width >= X *
|centre|` *is* "blind to a drop of X". The constant and the drop size are one
number, the first sweep offered as evidence scored the rule against its own
definition, and on the consequence table 0.30 through 0.50 scored identically.
The data never picked the constant.

### What actually reads a signal

Measured against the code and the hypothesis catalog, not assumed:

- In code, exactly one consumer: `lever.py::_masked_shift`. `tree.py` only
  passes the list through.
- In the catalog, exactly one hypothesis of nineteen: **T3**, "the change is
  routine variation". D1-D3, T1-T2, C1-C4, B1-B2, P1-P3 and R1-R3 take their
  evidence from the tree, `metrics.json`, localization or their own check.
- Those two reach the report as headline rules 3 and 4.

So the blast radius of a level-mode signal is two claims, and both are claims
rather than descriptions.

## Decision

**Only year-over-year rows are verdicts. Level-mode rows describe.**

1. A level-mode signal is still computed, still carries its limits and its
   rule, and is still written to `diagnosis.json`. It is evidence a reader can
   look at. Step 7 does not read it as a judgement about the month.
   `contracts.diagnosis.is_verdict` is the definition of which rows step 7 may
   read; `is_actionable` is the narrower one, adding the rule-1-only contract,
   for which rows may become a headline cause. The two are different and a
   single predicate cannot serve both: a rule-2 row IS a judgement - it blocks
   T3, by 3D4's deliberate asymmetry - and may never become a cause. The
   masked-shift alert fits neither, filtering rule 1 across both modes, and
   says so at its call site.
2. **T3 is `inconclusive`, never `supported`, when `revenue` has no
   year-over-year verdict**, at any file length. Its evidence must list every
   series that had no verdict, so a month called routine shows which parts
   were not judged.
3. **Exception: the masked-shift alert may read level rows.** It records which
   kind it rested on in `Lever.masked_shift_basis` (`yoy` or `level`).
4. A level-mode row **must never be rendered as a judgement, in either
   direction** - not `within` as "within normal variation", and not
   `above`/`below` as "unusually high" or "unusually low". Stage 5 renders
   level rows with different wording; the 3F narration validator rejects both
   shapes; and headline rule 4's wording is conditional on
   `masked_shift_basis` in AI_PIPELINE 7.8, because the headline is written by
   code and still runs in degraded mode where no validator does.
5. `_level_is_blind`, `_month_not_comparable_to_centre`, `LEVEL_BLIND_SHARE`
   and the reasons `neither_chart_informative` and
   `month_not_comparable_to_centre` are deleted. `no_current_value` and
   `no_measurable_spread` stay: they fix a field that reported a wrong reason
   and are unrelated to this policy.

## Alternatives considered

### Keep improving the level-mode gate
Rejected. Four sessions of evidence, and the 24-month result above is the
specific reason: the gate's own best condition is inert on the project's
reference file length, because the data it needs is the data that is missing.
A fifth attempt would be a fifth threshold tuned against shapes chosen by the
person tuning it - which is how 3D2's re-baselining, 3D3's first floor and
3D5's first sweep each passed review and each turned out to be wrong.

### Rest the masked-shift alert on `gross_to_net` alone
Rejected, and this is why the alert is an exception rather than a casualty.
`gross_to_net` is the sum of the absolute component contributions over the
absolute change in revenue. As the change approaches zero the ratio explodes
for **every** month, including months where nothing happened - so the ratio
alone fires on exactly the flat months the alert exists to catch. The
conjunction is load-bearing. It also survives a level basis better than the
rest of the engine would: the ratio's failure mode needs revenue to be flat,
the level chart's failure mode needs the month to sit off its own season, and
a seasonal month compared with the month before it is rarely flat.

One precision, because the code has two branches and the sentence above
describes only one. When revenue did not move **at all**, `gross_to_net` is
`null` - the ratio divides by zero - and the alert is decided on the step-4
row alone. That is not the conjunction going missing: it is the ratio at its
limit, infinitely above any threshold, and the step-4 row can only have fired
if something moved. But it does mean the alert on an exactly-flat month rests
on one predicate, and a reader of the code should not have to derive that from
a docstring that says both halves are required.

### Replace the signal half with an absolute materiality test
Rejected for now. It would keep two halves without reading a level row, but it
introduces a new tuned threshold on the one path this ADR clears of them.
Recorded as a backlog option if the level basis proves noisy in the scenario
suite.

### Suppress only level-mode `within`
Rejected. It treats half the failure. An ordinary December firing `above`
against an off-season centre is the same defect with the sign reversed, and
suppressing only the quiet half would leave the engine confidently wrong in
the direction that produces a headline.

## Consequences

**The cost, stated plainly: a month with no year-over-year comparator can
never be called routine, at any file length.** Not only files under 21 months
- a five-year file whose current month's comparator netted zero is in the same
position. The engine will say "we could not tell" where it used to say
"nothing happened". That is honest, and it is consistent with stage 4's rule
that seasonality needs two cycles: fewer than two cannot separate season from
noise, and one broken cycle is fewer than two.

**What is gained.** No tuned threshold remains on this path. The two open
items that motivated the change disappear rather than being gated: a halved
peak month cannot produce a `within` verdict because it cannot produce a
verdict, and a 20-month seasonal file charted without examination is no longer
a hazard because nothing downstream treats its rows as judgements.

**What moves rather than disappears.** The gate was the only thing stopping a
level-mode `within` reaching a reader as "within normal variation". That
responsibility is now stage 5's, written as a rule in `docs/CONTRACTS.md`
section 7 and in the 3F narration rules, not left as a note.

**What a reader still gets on such a file.** The change itself is never
hidden: the metric tree, localization and the hypothesis catalog are computed
from the same months regardless of signals, so headline rules 5-7 still speak.
What is withheld is the specific claim that the month was normal.

**Risk accepted.** A level-based masked-shift alert can be factually right
that composition moved and wrong that the movement was unusual - a seasonal
shoulder month has flat revenue and a shifting mix. `masked_shift_basis`
exists so 3F can phrase that case as possibly seasonal, and so the scenario
suite can count how often it happens. It is `yoy` only when EVERY component
row feeding the alert is `yoy`: headline rule 4 names the two largest opposing
contributions, so if the evidence that a named contributor moved unusually is
a level row, the hedge applies regardless of what other rows in the run say.
Because headline rule 4 is written by code and still runs in degraded mode,
that conditional wording lives in AI_PIPELINE 7.8 as well as in the 7.9
narration rules.
