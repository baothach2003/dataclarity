# ADR-0007: No step-4 row is a verdict in v1

## Status
Accepted. Extends ADR-0006 (level rows are descriptive) to year-over-year
rows, and supersedes its exception 3 (the masked-shift alert reading step 4).

## Date
2026-09-23 (Phase 3, decided by Thach after session 3D6; implemented in
session 3D6b)

## Context

ADR-0006 made level-mode rows descriptive because a level chart cannot judge
a seasonal month, and kept year-over-year rows as verdicts. Session 3D6 then
guarded the year-over-year denominator against a year-ago month too small to
divide by, and its two doubt-review cycles showed the problem had moved rather
than closed. Every known limit was run through the real pipeline to the
headline and classified (Thach's triage rule):

| case | shape | class |
|---|---|---|
| L1 | trickle off-season (300/month), 12.50 in-season comparator | FABRICATE |
| L2 | off-season 2,000, in-season comparator 100 | FABRICATE |
| L3 | a baseline base at 3.5-25% of normal, ordinary current month | FABRICATE |
| L4 | growing off-season, 3D6's share refusing genuine bases | FABRICATE (made by 3D6) |
| L5 | real recovery after a deep slump | SUPPRESS |
| L6 | real halving in a deep seasonal trough | SUPPRESS |
| L7 | one tiny month as a year-over-year NUMERATOR | FABRICATE |

Two root causes, not one:

1. **The comparator.** A year-over-year point compares with ONE year-ago
   month. When that month was anomalous (a shut month, a trickle off-season,
   a data gap) an ordinary month reads as unusual, and telling whether the
   comparator was itself normal needs further years - which a 24-month file
   does not have. L1, L2, L5, L6.
2. **The centre.** The chart's centre is a MEAN, so one anomalous point in the
   baseline drags it, whichever comparator produced the point. L3, L4, L7.
   L7 survives any comparator scheme: the tiny month there is a numerator.

3D6's share is a policy, not a measurement: a base at fraction f is refused iff
f is below it, and the exclusion side has no edge at all (a comparator at half
normal already fires an actionable +100%). Seven sessions have now gone to
step 4, and each closed with a deeper open item on the same block.

## Decision

1. **In v1 every step-4 row is descriptive, in either mode.**
   `contracts.diagnosis.is_verdict` returns False. Rows are still computed,
   carry limits and a rule, and are written to `diagnosis.json`; nothing reads
   them as a judgement about the month.
2. **T3 is never `supported`; headline rule 3 is dormant.**
3. **The masked-shift alert rests on the tree alone.** Against one floor,
   `MASKED_MIN_CONTRIBUTION_SHARE` times the largest of the TYPICAL month
   (median |revenue| over the history window's trading months, the 3D6
   yardstick), the previous month and the current month: on the ORDERS x
   AOV split of level 1 (`masked_shift_pair`), one contribution of each sign
   clears the floor; the revenue change stays under the same share of the
   larger compared month; and `gross_to_net >= MASKED_GROSS_TO_NET` is kept
   and live - it can only remove an alert, and was not found binding under
   this rule in a targeted search. With no trading month in the history the alert is null with a
   reason. The max and the change bound were Thach's choice after the doubt-
   review; the floor as first decided used the typical month alone (below).
   `masked_shift_basis` is removed. **Headline rule 4 is always worded as a
   movement that may be seasonal**, because nothing now establishes that the
   movement was unusual - only that it was large and cancelled out.
4. **3D4's and 3D6's base guards stay, for display.** A descriptive row is
   still shown to a reader, and +399,900% must not be printed as a growth
   rate.
5. **The credibility claim is reframed, not dropped.** The engine no longer
   claims "nothing unusual happened". Its claim is that it never invents a
   cause when no hypothesis is supported. Scenarios S0 and S11 both expect
   headline rule 7 with zero `supported` hypotheses.

## Alternatives considered

### Continue 3D9 (a robust centre, then the off-season yardstick)
Rejected for v1. Each of the last seven sessions exposed the next hole, and
3D9's own candidate addresses only the centre half (L3, L4, L7); L1 and L2 need
a separate idea. It moves to the Backlog as part of "unusualness verdicts".

### Verdicts only against a median of the same calendar month in at least TWO prior years
Proposed by Thach and **rejected on arithmetic, recorded so nobody re-proposes
it**: the median of two values is their mean. It halves an anomalous year
instead of ignoring it - L1 becomes (50,000 + 12.50) / 2 = 25,006, so an
ordinary June still reads +99.95% and fires. Robustness to one bad year needs
the median of at least THREE prior years, and with eight baseline points each
needing three lags a file needs `36 + 8 + 1 = 45` complete months. Even then
L7 fabricates, because it lives in the centre. So the Backlog item needs
BOTH a three-year comparator AND a robust centre, with its own sweep.

### Make a year-over-year verdict actionable only when the level chart agrees
Rejected (Thach). ADR-0006 exists because the level chart is uninformative on
seasonal series; this would silence year-over-year exactly where it is the
only informative chart - the C1 case in reverse.

### A floor on the typical month alone
Thach's decision 3 as first taken, and rejected on measurement by the 3D6b
doubt-review. The typical month is small against a peak - a trickle
off-season shop's typical month was 300 against in-season months of 500,000,
so a 1% composition wiggle cleared a floor of 60 - and on the sweep's noise
model the alert fired on 15-25% of months at 3x and 10x typical with nothing
planted, against 3.2-12.9% at 1x across the four noise rows (3.2-3.3% on the
two lower-noise ones). And with flatness decided by the ratio
alone, a month that went from 1,000 to 2,000 had `gross_to_net` 3.5 and was
"flat". The max and the change bound fix both; detection of a planted 30%
shift at typical scale drops from 32% to 25%.

### Measure the change against the materiality floor
The first floor C did, and the doubt-review of the pair found it
fabricating: in a trough the floor is 20% of a typical month far larger than
the months compared, so a month that fell 200 -> 50 (-75%) passed as "flat"
and headline rule 4 would have called it stable. The change is measured
against 20% of the larger compared month; at or above typical scale the two
coincide.

### Decide materiality on level 1's customers x frequency x AOV
The first implementation did, and the second doubt-review cycle found it
fabricating. customers x frequency = orders BY DEFINITION, so whenever
orders hold steady and the customer count moves, those two factors cancel
exactly and the rule reads an identity as a masked shift: 19-39% of such
months with nothing planted, on a noise structure (stable orders, a swinging
customer count) a small or B2B shop plausibly has. Thach: under the
asymmetry a headline fabricated that often blocks, and it needs no real data
to see - it is structural. Deciding on orders x AOV, which have no
definitional link, gives 0-2.4% on that structure; S6's shape is caught
identically without noise and 0.2-1.8 points less often with it. The customers/frequency story stays in level 1 and B1/C1.

### Keep the step-4 half of the masked-shift alert
Not possible: with no row a verdict, it would rest on descriptive rows. Resting
on `gross_to_net` alone was rejected in ADR-0006 because the ratio explodes as
the change nears zero; the materiality floor is what makes that explosion
harmless, since a month where nothing moved has contributions small in
absolute terms.

## Consequences

**What is lost, plainly.** The engine can never say a month was routine, at
any file length. The 24-month demo dataset (Online Retail II) and the ~36-month
Kaggle set both fall short of the 45 months a robust verdict would need, so
the loss is not avoidable by choosing a longer demo file today.

**What is gained.** Zero FABRICATE cases among L1-L7: no step-4 row can reach
a headline as a finding. The masked-shift alert now works on any file whose
history holds one complete trading month, including files too short for any
chart, where before it could never fire. It is null on a file with no
complete month before the current one, such as a two-month export that starts
mid-month, and when a compared month netted zero or below (the Shapley terms
of a product change sign there). In a deep trough it effectively cannot
fire: the floor never drops below 20% of the typical month.

**Risk accepted, and measured.** Without a statistical half the alert fires on
ordinary noise more often than before. On hand-built shapes with nothing
planted, at the chosen share of 0.20, it fires 2.4% (typical scale) to 2.9%
(3x peak) of the time at orders 20% / AOV 10% noise. On data with a
customer column: 2.0-2.4% with frequency stable, 2.1-2.3% with independent
noise, about 0 at 0.3x typical, 5.0-6.2% at 30/15/15, and 0-2.4% with stable orders and a swinging
customer count - the structure that fired 19-39% while materiality was read
on the three-factor split. These are chosen noise models, not a bound; 3E
re-sweeps on the real suite. Such an alert is
a TRUE statement - both sides did move that much - in hedged wording, so it
misleads by emphasis rather than fabricating a finding; its cost is that it
takes the headline from rules 5-7. And a seasonal shoulder month (flat revenue,
shifting mix) fires it by design, which is why the hedge is permanent.

**`MASKED_MIN_CONTRIBUTION_SHARE` is PROVISIONAL.** It was tuned on hand-built
shapes because the scenario generator does not exist until 3E. 3E re-runs the
sweep against the real S0-S11 suite and may change the value; planted causes
are ground truth only once the generator exists and was not built to fit it.
