# ADR-0005: A pre-registered hypothesis catalog the AI cannot choose from

## Status
Accepted

## Date
2026-09-22 (Stage 3 SPECS UPDATE session, from `docs/DIAGNOSE_DESIGN.md`
sections 1.5, 2.7 and 7)

## Context
Stage 3 has to say *why* a metric moved. The original Phase 3A design handed
that judgement to the model: `prompts/root_cause.md` instructed the AI to
identify a root cause and to "rule out at least two plausible alternative
explanations, each with the figure that rules it out".

Two separate problems with that, both structural rather than fixable by
better prompt wording.

**The AI was choosing what gets measured.** It picked which hypotheses to
test and which to rule out. Nothing stopped it from ruling out two easy
hypotheses, never considering the real cause, and producing a confident,
well-cited, plausible paragraph. The citations would all check out - they
would just be answers to questions the model chose because they were
answerable. That is the letter of ADR-0002 satisfied and its spirit broken:
"pandas computes, the AI interprets" is meaningless if the AI decides what
pandas computes.

**Choosing hypotheses after seeing the data inflates false findings.** This
is the garden of forking paths (Gelman and Loken): when the analysis is
selected in response to the data, the reported confidence no longer means
what it appears to mean, even when every individual step is honest and no
result is ever suppressed. An engine that scans a run, notices that the
category breakdown looks interesting, and then reports on categories will
find something interesting nearly every time - including on data where
nothing happened. Spotify standardizes its analysis pipeline partly for this
reason.

The failure mode this produces is specific and bad for this product: a
diagnosis that is never "nothing unusual happened". A shop owner who is told
every month that something is wrong learns to ignore the report.

## Decision
**The hypothesis catalog is fixed in advance, identical for every run, and
the AI has no say in it.**

- The catalog (`docs/AI_PIPELINE.md` section 7.8) lists every cause the engine
  will ever test: three data-quality hypotheses, three time hypotheses, four
  customer hypotheses, two lever hypotheses, three product and returns
  hypotheses, three localization and product-lifecycle hypotheses. It is
  written down before any run, not derived from a run.
- **Every hypothesis is evaluated and reported on every run**, in catalog
  order, including the ones that come out `ruled_out`, `inconclusive` or
  `not_testable`. A cause is never absent from the output because it failed.
  Showing what was tested and rejected is what makes the supported ones
  credible.
- Verdicts are assigned by code from the decomposition, against fixed
  thresholds (`docs/AI_PIPELINE.md` section 7.10), before the AI is called.
- The headline sentence is selected by code, by a fixed rule order
  (`docs/AI_PIPELINE.md` section 7.8), and written into
  `diagnosis.headline.message`.
- The AI's only job is narration (step 8). It **may not choose, add, remove or
  re-rank hypotheses, and may not upgrade a verdict** - an `inconclusive`
  hypothesis may never be described as a cause. A code validator checks the
  answer against the evidence before it is accepted, and a failure falls back
  to degraded mode where the deterministic headline and hypothesis table are
  still shown.
- Causes the schema genuinely cannot reach - marketing, competitors, weather,
  footfall, margin, country, channel - are listed explicitly as not testable
  rather than silently omitted, so the reader can see the shape of the blind
  spot.

## Alternatives Considered

**Let the AI propose hypotheses, then verify each in code.** Keeps the
model's breadth while making it prove its claims. Rejected: verification
catches a *wrong* hypothesis, not a *missing* one. The dangerous failure here
is the cause that was never proposed, and no amount of downstream checking
detects an absence. It also makes the output non-reproducible - the same file
could yield different hypotheses on two runs, which is indefensible in a
report meant to support a decision.

**Data-dependent slicing** (automatically search dimensions and surface
whichever slices look most anomalous, as wise-pizza or Adtributor-style tools
do). Genuinely useful with many high-cardinality dimensions. Rejected for two
reasons: DataClarity's canonical schema has very few dimensions to search
(category, product, customer type), so the technique's main advantage barely
applies; and an automatic search is exactly the forking-paths problem above,
now industrialized. Recorded as deferred rather than dismissed in
`docs/DIAGNOSE_DESIGN.md` section 14.

**A catalog that adapts to available columns.** Rejected as unnecessary: the
catalog already handles missing columns through the `not_testable` and
`inconclusive` verdicts, which keeps the list stable across runs and across
customers while still being honest about what this particular file supports.

## Consequences

**Benefits**
- The engine can say "nothing unusual happened" - scenario S0 in the
  validation suite asserts exactly that, and a diagnosis that is capable of
  finding nothing is what makes its positive findings worth reading.
- Runs are reproducible and comparable: the same file always produces the same
  hypothesis table, and two different months of the same shop can be compared
  hypothesis by hypothesis.
- The planted-cause suite (`docs/AI_PIPELINE.md` section 7.11) is only
  meaningful because the catalog is fixed - it can measure how often the
  engine names the planted cause and how many decoys it raises, which is the
  README's evidence that the thing works.
- ADR-0002's boundary is restored and sharpened: the AI now sits strictly
  downstream of every decision, not upstream of the measurement.

**Trade-offs accepted**
- **The engine cannot find a cause that is not in the catalog.** A real cause
  outside the eighteen tested hypotheses is reported as "no single tested
  cause explains most of the change" (headline rule 7), not discovered.
  Extending the catalog is a deliberate act with a code change and tests, not
  something the model can do at runtime - the same trade-off ADR-0002 already
  accepted for KPIs, applied to explanations.
- Every run pays for every hypothesis, including ones that are obviously
  irrelevant for a given shop. Acceptable: the computations are small and
  bounded, and the alternative is the data-dependent selection this ADR
  rejects.
- The output is longer and less immediately dramatic than a single confident
  narrative. The headline rules exist to give the reader one sentence to act
  on, with the full table behind it.
- Threshold choices (`SUPPORTED_MIN_SHARE` and friends) now carry real weight,
  since they decide verdicts that the AI can no longer soften. They are
  documented heuristics, flagged as uncalibrated until run against real data.

## Clarification (session 3E1): statements rendered from the data's direction

For a cause that can move either way (C1-C4, B1, B2, P2), the catalog tests a
direction-neutral statement ("Purchase frequency changed") and the statement a
reader sees is chosen by code from the sign of the contribution ("Customers
bought less often" / "more often"). The verdict rule already requires the
contribution to have the same sign as the change, so the rendered wording is
always the one the data supports. This does not reopen the decision above:
the catalog, the tests and both wordings are fixed in advance in
`stages/diagnose/catalog.py`; nothing chooses what to test after seeing the
data, only which of two pre-written sentences describes it, deterministically.
The alternative - two ids per cause, one per direction - doubles the table
and makes one of each pair `ruled_out` on every run by construction. The
first version tested one-way statements with a sign-blind rule and headlined
"baskets got smaller" on a month whose baskets grew 2.7x.
