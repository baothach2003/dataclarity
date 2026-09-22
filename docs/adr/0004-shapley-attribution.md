# ADR-0004: Shapley attribution over sequential substitution

## Status
Accepted

## Date
2026-09-22 (Stage 3 SPECS UPDATE session, from `docs/DIAGNOSE_DESIGN.md`
section 1.1; the design it replaces was the original Phase 3A checklist line)

## Context
Stage 3 answers "why did revenue move?" by decomposing a change into the
contributions of the factors that produce it - `revenue = customers x
frequency x AOV` at the top level, and several other multiplicative
decompositions beneath it (`docs/AI_PIPELINE.md` section 7.6).

The original Phase 3A plan said "sequential substitution": switch one factor
at a time from its previous value to its current value, and record the change
in the total at each switch. It is simple, exact (the pieces sum to the total
change), and wrong in a way that is easy to miss - **the answer depends on the
order the factors are switched in**, and nothing in the business chooses that
order. A developer does, once, in code.

The size of that arbitrariness was measured before deciding. Take a business
whose revenue barely moved (100,000 -> 100,800) while its composition changed
sharply: customers 1,000 -> 600, frequency 2.0 -> 2.4, AOV 50 -> 70. Across
the six possible orderings, sequential substitution reports:

| Factor | Smallest attribution | Largest attribution | Shapley |
|---|---|---|---|
| Customers | -40,000 | -67,200 | -53,066.67 |
| Frequency | +12,000 | +28,000 | +18,933.33 |
| AOV | +24,000 | +48,000 | +34,933.33 |

The customer effect swings by 68% and the AOV effect by exactly 2x, driven by
nothing but the order. A report built on one ordering would state "the loss of
customers cost 40,000" where another, equally defensible, implementation of
the same documented method would state 67,200. On the smaller Figma sample
data (`docs/FIGMA_DESIGN_NOTES.md` section 6, revenue 104,160 -> 96,152) the
orderings disagree by a few hundred - small enough that the problem would
likely have gone unnoticed in development and shown up on a real customer's
data.

This matters more here than in most products, because the whole promise of
stage 3 is that a number in the report can be defended. "That figure would
have been different if we had written the loop the other way round" is not a
defence.

## Decision
**Contributions are computed with the Shapley value, never by sequential
substitution.**

For `F = x_1 * x_2 * ... * x_n`, factor `i`'s contribution is its marginal
effect averaged over all `n!` orderings of the factors. With `n <= 3` (every
decomposition in stage 3) the orderings are enumerated directly, so there is
no approximation and no sampling.

Two properties carry the decision:

- **Order independence.** There is no ordering left to choose, so there is no
  arbitrary choice to defend or to accidentally change during a refactor.
- **Exactness.** The contributions still sum to `F(cur) - F(prev)` - verified
  above, and enforced by tests at a relative tolerance of 1e-9
  (`docs/AI_PIPELINE.md` section 7.6). Exactness is not traded away for
  fairness; both hold.

The same method is used for every multiplicative decomposition in the stage:
the lever tree at both levels, the price-volume-mix split of gross sales, and
the mix-versus-rate split of a moved average.

## Alternatives Considered

**Sequential substitution** (the original plan). Rejected for the order
dependence measured above. Its only advantage is that it is marginally easier
to explain in one sentence, and that advantage disappears the moment someone
asks why the numbers changed after a code change that reordered a loop.

**LMDI (logarithmic mean Divisia index).** A standard exact decomposition in
energy economics, and genuinely order-independent. Rejected because it is
built on logarithms and is undefined at zero or negative values. DataClarity
allows both: returns are negative-quantity rows (the 2A convention), so a
product, a category or a whole period can legitimately net to zero or below.
A method that breaks on the data the product is designed to accept is not a
candidate, and special-casing it back to life would reintroduce the arbitrary
choices this ADR exists to remove.

**Reporting a range instead of a point** (show the min and max across
orderings). Honest, but unusable: the report exists so a shop owner can act,
and "customers cost you somewhere between 40,000 and 67,200" hands the
judgement back to the reader while sounding less trustworthy than either
number alone.

## Consequences

**Benefits**
- The attribution is a property of the data, not of the implementation. Two
  correct implementations of this spec produce the same numbers.
- The exactness tests are meaningful rather than tautological: they check a
  real invariant that a wrong Shapley implementation would break.
- Every decomposition in the stage uses one method, so the report never has to
  explain why two breakdowns were computed differently.

**Trade-offs accepted**
- `n!` enumeration is exponential. Fine at `n <= 3` (six orderings), but it
  caps how far the metric tree can be extended: a four- or five-factor
  decomposition would need a sampled or analytic Shapley variant, and that
  decision is deferred until something actually needs it.
- Shapley values are harder to explain to a reader than "we changed customers
  first". The report never shows the method to the shop owner - only the
  contributions - and `tree.method` records `"shapley"` for anyone who asks.
- The contributions of a factor no longer match the intuitive "what if only
  this changed?" figure, which is the smallest-attribution column above. That
  intuition is precisely the one that hides how much of the effect depends on
  what else moved.
